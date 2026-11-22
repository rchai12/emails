"""Independent store-reader probe: seeded chains read through shuffled projections.

Synthetic data only.
"""

import argparse
import itertools
import os
import random
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

TRIALS = 40
SHUFFLES = 3
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=25)
DUES = ("none", "date", "timed")
ANSWERS = ("none", "approve", "change", "nodeadline", "drop")
PROJECTIONS = (
    ("posts", "POST_COLUMNS"),
    ("tasks", "TASK_COLUMNS"),
    ("tasks", "LINK_COLUMNS"),
    ("approvals", "APPROVAL_COLUMNS"),
    ("messages", "MESSAGE_COLUMNS"),
    ("triage", "TRIAGE_COLUMNS"),
)
AREAS = ("messages", "sync", "senders", "triage", "posts", "alerts", "approvals", "tasks")
CONSTRUCTOR = "a store area must not define __init__: {name}"
DUPLICATE = "duplicate stored column: {name}"


@dataclass(frozen=True)
class Email:
    extracted: bool
    dated: bool
    due: str
    sent: bool
    unsubscribe: bool
    auth: int
    posted: bool
    answer: str
    approval_due: str
    task_sent: bool
    follows: int | None
    link_sent: bool


def plans() -> list[tuple[list[Email], bool]]:
    rng = random.Random(410)
    corpus = []
    for trial in range(TRIALS):
        emails = []
        for number in range(2 + trial % 4):
            answer = rng.choice(ANSWERS)
            earlier = [n for n, e in enumerate(emails) if e.answer not in ("none", "drop")]
            follows = (
                rng.choice(earlier) if earlier and answer == "none" and rng.random() < 0.6 else None
            )
            emails.append(
                Email(
                    extracted=rng.random() < 0.7,
                    dated=rng.random() < 0.5,
                    due=rng.choice(DUES),
                    sent=rng.random() < 0.5,
                    unsubscribe=rng.random() < 0.5,
                    auth=rng.randrange(3),
                    posted=rng.random() < 0.5,
                    answer=answer if number == 0 or follows is None else "none",
                    approval_due=rng.choice(DUES),
                    task_sent=rng.random() < 0.5,
                    follows=follows,
                    link_sent=rng.random() < 0.5,
                )
            )
        corpus.append((emails, trial % 3 == 0))
    return corpus


def oracle_self_check(corpus: list[tuple[list[Email], bool]]) -> None:
    emails = [email for chain, _ in corpus for email in chain]
    assert {email.due for email in emails} == set(DUES)
    assert {email.approval_due for email in emails if email.answer != "none"} == set(DUES)
    assert set(ANSWERS) <= {email.answer for email in emails}
    assert any(email.follows is not None for email in emails)
    assert {cleared for _, cleared in corpus} == {True, False}
    assert all(
        e.follows is None or chain[e.follows].answer not in ("none", "drop")
        for chain, _ in corpus
        for e in chain
    )


def make_due(kind: str):
    from mailroom.store import Due

    if kind == "none":
        return None
    return Due(date=date(2026, 11, 20), time=None if kind == "date" else time(17, 0))


def build(folder: Path, name: str, chain: list[Email], cleared: bool):
    """Write the chain through the public store, and return the store and the oracle."""
    from mailroom import clock, ids
    from mailroom.config import get_settings
    from mailroom.extractor import Extraction
    from mailroom.record import Record
    from mailroom.store import (
        Approval,
        Link,
        Post,
        StoredMessage,
        StoredTriage,
        Task,
        Verdict,
        open_store,
    )

    moment = [NOW]
    clock.now = lambda: moment[0]
    counter = itertools.count(1)
    ids.new_id = lambda: f"{next(counter):02d}" + "d" * 30
    os.environ["MAILROOM_DATA_DIR"] = str(folder / name)
    store = open_store(get_settings())
    items = [f"{n + 1:02d}" + "d" * 30 for n in range(len(chain))]
    records, verdicts = [], []
    for number, email in enumerate(chain):
        record = Record(
            provider="gmail",
            message_id=f"p{number}",
            thread_id=f"q{number}",
            received_at=NOW - timedelta(minutes=number),
            link=f"https://mail.google.com/mail/#all/p{number}",
            sender=f"probe{number}@example.test",
            sender_name=f"Probe Sender {number}",
            subject=f"Probe subject {number}",
            sent_at=NOW - timedelta(hours=1) if email.sent else None,
            body_text=f"Probe body {number}.",
            list_unsubscribe=email.unsubscribe,
            authentication_results=tuple(f"spf=pass {k}" for k in range(email.auth)),
        )
        extraction = Extraction(
            summary=f"Probe summary {number}.",
            actionable=True,
            urgent=False,
            title=f"Probe title {number}",
            deadline=None,
            suspicious=False,
            suspicion_reason="",
            confidence="high",
        )
        verdict = Verdict(
            outcome="extracted" if email.extracted else "rejected",
            trusted=email.unsubscribe,
            verified=email.sent,
            bulk=False,
            notify=True,
            extraction=extraction if email.extracted else None,
            reason="" if email.extracted else "timeout",
            dated=email.extracted and email.dated and email.due != "none",
            due=make_due(email.due) if email.extracted else None,
        )
        store.add(record)
        store.save_triage("gmail", record.message_id, verdict)
        records.append(record)
        verdicts.append(verdict)
    store.queue_notified()
    approvals = {}
    for number, email in enumerate(chain):
        item = items[number]
        if email.posted:
            store.mark_posted(item, f"9{number:017d}")
        if email.answer != "none":
            title = "" if email.answer == "drop" else f"Probe task {number}"
            answer = "edit" if email.answer == "change" else "yes"
            store.record_answer(item, answer, f"Probe task {number}")
            due = None if email.answer in ("nodeadline", "drop") else make_due(email.approval_due)
            if email.answer == "approve" and due is None:
                due = make_due("date")
            store.record_approval(item, email.answer, title, due)
            approvals[number] = Approval(item, email.answer, title, due, NOW)
    store.queue_approved()
    tasks = {}
    for number in approvals:
        if chain[number].answer == "drop":
            continue
        sent = chain[number].task_sent
        if sent:
            store.mark_task_sent(items[number], f"task-{number}")
        task_id = f"task-{number}" if sent else None
        tasks[number] = Task(
            items[number], "gmail", f"p{number}", NOW, task_id, NOW if sent else None
        )
    for number, email in enumerate(chain):
        if email.follows is not None:
            store.choose_card(items[number], "followup", items[email.follows])
            store.record_answer(items[number], "link", "")
    store.queue_linked()
    links = {}
    for number, email in enumerate(chain):
        if email.follows is None:
            continue
        target = tasks.get(email.follows)
        task_id = None if target is None else target.task_id
        sent = email.link_sent and task_id is not None
        if sent:
            store.mark_link_sent(items[number])
        links[number] = Link(
            items[number],
            "gmail",
            f"p{number}",
            items[email.follows],
            task_id,
            NOW,
            NOW if sent else None,
        )
    if cleared:
        moment[0] = LATER
        store.clear_expired_text()
    posts, stored, triaged = {}, {}, {}
    for number, email in enumerate(chain):
        follows = None if email.follows is None else items[email.follows]
        posts[number] = Post(
            items[number],
            "gmail",
            f"p{number}",
            NOW,
            f"9{number:017d}" if email.posted else None,
            NOW if email.posted else None,
            "followup" if follows else None,
            follows,
        )
        record = records[number]
        if cleared:
            record = replace(record, body_text="", authentication_results=())
        stored[number] = StoredMessage(record, NOW, LATER if cleared else None)
        verdict = verdicts[number]
        wiped = cleared and verdict.extraction is not None
        triaged[number] = StoredTriage(
            replace(verdict, extraction=None) if wiped else verdict, NOW, LATER if wiped else None
        )
    oracle = {
        "pending_posts": tuple(p for p in posts.values() if p.posted_at is None),
        "posts": posts,
        "pending_tasks": tuple(t for t in tasks.values() if t.task_id is None),
        "tasks": tasks,
        "pending_links": tuple(k for k in links.values() if k.sent_at is None and k.task_id),
        "links": links,
        "approvals": approvals,
        "messages": stored,
        "triage": triaged,
    }
    return store, items, oracle


def read_all(store, items: list[str], count: int) -> dict[str, object]:
    found = {
        "pending_posts": store.pending_posts(),
        "posts": {},
        "pending_tasks": store.pending_tasks(),
        "tasks": {},
        "pending_links": store.pending_links(),
        "links": {},
        "approvals": {},
        "messages": {},
        "triage": {},
    }
    for number in range(count):
        item, message_id = items[number], f"p{number}"
        post = store.post("gmail", message_id)
        if post != store.post_by_item(item):
            found["post-readers-differ"] = number
        found["posts"][number] = post
        for key, value in (
            ("tasks", store.task(item)),
            ("links", store.link(item)),
            ("approvals", store.approval(item)),
        ):
            if value is not None:
                found[key][number] = value
        found["messages"][number] = store.get("gmail", message_id)
        found["triage"][number] = store.triage("gmail", message_id)
    return found


def thread_ok(store, items: list[str], oracle: dict[str, object]) -> bool:
    for number in range(len(items)):
        approval = oracle["approvals"].get(number)
        wanted = None if approval is None or approval.outcome == "drop" else approval
        if store.approved_in_thread("gmail", f"q{number}") != wanted:
            return False
    return True


def shuffled(rng: random.Random):
    import importlib

    saved = []
    for area, name in PROJECTIONS:
        module = importlib.import_module(f"mailroom.store.{area}")
        columns = list(getattr(module, name))
        saved.append((module, name, tuple(columns)))
        rng.shuffle(columns)
        setattr(module, name, tuple(columns))
    return saved


def restore(saved) -> None:
    for module, name, columns in saved:
        setattr(module, name, columns)


def reader_trial(folder: Path, index: int, chain: list[Email], cleared: bool) -> list[str]:
    store, items, oracle = build(folder, f"chain-{index}", chain, cleared)
    broken: list[str] = []
    rng = random.Random(index)
    try:
        for attempt in range(SHUFFLES + 1):
            saved = shuffled(rng) if attempt else []
            try:
                found = read_all(store, items, len(chain))
                for key, wanted in oracle.items():
                    if found[key] != wanted:
                        broken.append(f"{key}{'-shuffled' if attempt else ''}")
                if not thread_ok(store, items, oracle):
                    broken.append(f"approved-in-thread{'-shuffled' if attempt else ''}")
            finally:
                restore(saved)
        broken += duplicate_check(store, items, rng)
    finally:
        store.close()
    return broken


def duplicate_check(store, items: list[str], rng: random.Random) -> list[str]:
    import importlib

    from mailroom.store import StoreError

    readers = {
        "POST_COLUMNS": (
            store.pending_posts,
            partial(store.post, "gmail", "p0"),
            partial(store.post_by_item, items[0]),
        ),
        "TASK_COLUMNS": (store.pending_tasks, partial(store.task, items[0])),
        "LINK_COLUMNS": (store.pending_links, partial(store.link, items[0])),
        "APPROVAL_COLUMNS": (
            partial(store.approval, items[0]),
            partial(store.approved_in_thread, "gmail", "q0"),
        ),
        "MESSAGE_COLUMNS": (partial(store.get, "gmail", "p0"),),
        "TRIAGE_COLUMNS": (partial(store.triage, "gmail", "p0"),),
    }
    broken = []
    for area, name in PROJECTIONS:
        module = importlib.import_module(f"mailroom.store.{area}")
        columns = list(getattr(module, name))
        repeated = rng.choice(columns)
        columns.insert(rng.randrange(len(columns) + 1), repeated)
        original = getattr(module, name)
        setattr(module, name, tuple(columns))
        try:
            for read in readers[name]:
                try:
                    read()
                    broken.append(f"duplicate-accepted:{name}")
                except StoreError as error:
                    if str(error) != DUPLICATE.format(name=repeated.rsplit(".", 1)[-1]):
                        broken.append(f"duplicate-message:{name}")
        finally:
            setattr(module, name, original)
    return broken


def constructor_check() -> list[str]:
    import importlib

    from mailroom.store import Store
    from mailroom.store.base import StoreBase

    rng = random.Random(4100)
    parents = [StoreBase, Store] + [
        getattr(importlib.import_module(f"mailroom.store.{area}"), cls)
        for area in AREAS
        for cls in dir(importlib.import_module(f"mailroom.store.{area}"))
        if cls.endswith("Store") and cls != "StoreBase"
    ]
    broken = []
    for parent in parents:
        name = f"Probe{rng.randrange(10**6)}"
        try:
            type(name, (parent,), {"__init__": lambda self: None})
            broken.append(f"constructor-accepted:{parent.__name__}")
        except TypeError as error:
            if str(error) != CONSTRUCTOR.format(name=name):
                broken.append(f"constructor-message:{parent.__name__}")
        plain = type(f"{name}Plain", (parent,), {"extra": lambda self: 1})
        if plain.__init__ is not StoreBase.__init__:
            broken.append(f"plain-constructor:{parent.__name__}")
    if len(parents) < 10:
        broken.append("areas-not-found")
    return broken


def lifecycle_check(folder: Path) -> list[str]:
    from mailroom.config import get_settings
    from mailroom.schema import MIGRATIONS
    from mailroom.store import open_store

    scripts: list[int] = []
    connects: list[int] = []
    real = sqlite3.connect

    class Counting(sqlite3.Connection):
        def executescript(self, script: str):  # type: ignore[override]
            scripts.append(1)
            return super().executescript(script)

    def connect(*args, **kwargs):
        connects.append(1)
        return real(*args, factory=Counting, **kwargs)

    broken = []
    os.environ["MAILROOM_DATA_DIR"] = str(folder / "lifecycle")
    with patch("sqlite3.connect", connect):
        for wanted in (len(MIGRATIONS), 0):
            scripts.clear()
            connects.clear()
            store = open_store(get_settings())
            if (len(connects), len(scripts)) != (1, wanted):
                broken.append(f"lifecycle:{len(connects)}x{len(scripts)}")
            store.close()
    return broken


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-only", action="store_true")
    args = parser.parse_args()
    corpus = plans()
    oracle_self_check(corpus)
    print("oracle self-check: ok")
    if args.oracle_only:
        print("FAILURES 0")
        return 0
    failures = 0
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04j-trials-") as scratch:
        folder = Path(scratch)
        for label, run in (
            ("one connection and one migration per open", lambda: lifecycle_check(folder)),
            ("store constructors refused at definition", constructor_check),
        ):
            try:
                broken = run()
            except Exception as error:
                broken = [f"raised {type(error).__name__}"]
            print(f"{label}: {'ok' if not broken else 'FAIL (' + ', '.join(broken) + ')'}")
            failures += bool(broken)
        counts: dict[str, int] = {}
        reached = 0
        for index, (chain, cleared) in enumerate(corpus):
            try:
                broken = reader_trial(folder, index, chain, cleared)
                reached += 1
            except Exception as error:
                broken = [f"raised {type(error).__name__}"]
            for name in broken:
                counts[name] = counts.get(name, 0) + 1
    print(f"trials reached: {reached} of {TRIALS}")
    if counts:
        detail = ", ".join(f"{name} x{count}" for name, count in sorted(counts.items()))
        print(f"reader invariants: FAIL ({detail})")
        failures += 1
    else:
        print(f"reader invariants across {TRIALS} seeded trials x {SHUFFLES} shuffles: ok")
    print(f"FAILURES {failures}")
    return int(bool(failures))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04j-") as folder:
        env = {key: value for key, value in os.environ.items() if not key.startswith("MAILROOM_")}
        env.update(
            HOME=folder,
            MAILROOM_DATA_DIR=str(Path(folder) / "data"),
            MAILROOM_TIME_ZONE="America/New_York",
        )
        with patch.dict(os.environ, env, clear=True):
            sys.exit(main())
