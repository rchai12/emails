"""Independent incomplete-chain probe: seeded damage to stored rows, synthetic data only."""

import argparse
import itertools
import os
import random
import sqlite3
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

OWNER = "444444444444444444"
TRIALS = 40
CARD_DAMAGE = ("none", "none", "messages", "triage", "followup")
TASK_DAMAGE = ("none", "none", "messages", "approvals")
ACTIONS = ("full", "trust", "yes", "edit", "notask", "mute", "link", "approve", "drop")
NOTICE = "Mailroom can't act on this email: its stored details are incomplete."
ALERT = "Mailroom kept item {item} unsent: its stored details are incomplete."
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
SUBJECT = "Probe invoice"
SENDER = "probe-billing@example.test"


def plans() -> list[tuple[list[str], list[str], list[str]]]:
    """Per trial: damage per card, damage per task, and the action pressed on each card."""
    rng = random.Random(409)
    corpus = []
    for trial in range(TRIALS):
        count = 3 + trial % 3
        cards = [rng.choice(CARD_DAMAGE) for _ in range(count)]
        cards[trial % count] = CARD_DAMAGE[2 + trial % 3]
        tasks = [rng.choice(TASK_DAMAGE) for _ in range(count)]
        tasks[(trial + 1) % count] = TASK_DAMAGE[2 + trial % 2]
        presses = [rng.choice(ACTIONS) for _ in range(count)]
        corpus.append((cards, tasks, presses))
    return corpus


def oracle_self_check(corpus: list[tuple[list[str], list[str], list[str]]]) -> None:
    kinds = {damage for cards, _, _ in corpus for damage in cards}
    assert kinds == set(CARD_DAMAGE), kinds
    assert {damage for _, tasks, _ in corpus for damage in tasks} == set(TASK_DAMAGE)
    assert all(any(d != "none" for d in cards) for cards, _, _ in corpus)
    assert all(any(d != "none" for d in tasks) for _, tasks, _ in corpus)
    assert len({tuple(cards) for cards, _, _ in corpus}) > TRIALS // 2


def remove(path: Path, sql: str) -> None:
    raw = sqlite3.connect(path)
    try:
        raw.execute(sql)
        raw.commit()
    finally:
        raw.close()


def setup(folder: Path, name: str, count: int):
    import keyring.core

    from mailroom import clock, ids
    from mailroom.config import get_settings
    from mailroom.record import Record
    from mailroom.store import DB_FILENAME, Verdict, open_store
    from tests.fakes import FakeDiscord, FakeKeychain

    clock.now = lambda: NOW
    counter = itertools.count(1)
    ids.new_id = lambda: f"{next(counter):03d}" + "c" * 29
    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    discord = FakeDiscord()
    keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
    os.environ["MAILROOM_DATA_DIR"] = str(folder / name)
    settings = get_settings()
    store = open_store(settings)
    verdict = Verdict(
        outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="timeout"
    )
    record = Record(
        provider="gmail",
        message_id="p0",
        thread_id="q0",
        received_at=NOW,
        link="https://mail.google.com/mail/#all/p0",
        sender=SENDER,
        sender_name="Probe Billing",
        subject=SUBJECT,
        sent_at=None,
        body_text="Probe body text.",
        list_unsubscribe=False,
        authentication_results=(),
    )
    for number in range(count):
        message_id = f"p{number}"
        store.add(replace(record, message_id=message_id, thread_id=f"q{number}"))
        store.save_triage("gmail", message_id, verdict)
    store.queue_notified()
    items = [store.post("gmail", f"p{number}").item_id for number in range(count)]
    return settings, store, discord, items, settings.data_dir / DB_FILENAME


def damage_card(path: Path, number: int, kind: str) -> None:
    where = f"message_id = 'p{number}'"
    if kind == "messages":
        remove(path, f"DELETE FROM messages WHERE {where}")
    elif kind == "triage":
        remove(path, f"DELETE FROM triage WHERE {where}")
    elif kind == "followup":
        remove(path, f"UPDATE posts SET card = 'followup', follows = '{'f' * 32}' WHERE {where}")


def card_trial(folder: Path, index: int, cards: list[str], presses: list[str]) -> list[str]:
    import httpx

    from mailroom.discord_post import post_pending
    from mailroom.interactions import handle_interaction

    settings, store, discord, items, path = setup(folder, f"cards-{index}", len(cards))
    for number, kind in enumerate(cards):
        damage_card(path, number, kind)
    broken: list[str] = []
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    bad = {items[n] for n, kind in enumerate(cards) if kind != "none"}
    good = [item for item in items if item not in bad]
    for attempt in range(2):
        report = post_pending(store, settings, http)
        if (report.posted, report.waiting, report.stopped) != (
            len(good) if attempt == 0 else 0,
            0,
            "",
        ):
            broken.append("post-report")
        if report.skipped != len(bad):
            broken.append("skipped-count")
    nonces = [message["nonce"] for message in discord.messages]
    if nonces != [item[:25] for item in good]:
        broken.append("posted-set")
    if {post.item_id for post in store.pending_posts()} != bad:
        broken.append("kept-set")
    if any(store.post_by_item(item).discord_message_id is not None for item in bad):
        broken.append("marked-sent")
    alerts = sorted((a.key, a.text, a.ping) for a in store.pending_alerts())
    if alerts != sorted((f"incomplete:{i}", ALERT.format(item=i), False) for i in bad):
        broken.append("alerts")
    for item, action in zip(items, presses, strict=True):
        before = len(discord.callbacks)
        status = store.sender_status(SENDER)
        outcome = handle_interaction(discord.press(f"mr:{action}:{item}"), store, settings, http)
        replies = [body for _, body in discord.callbacks[before:]]
        if item in bad:
            notice = {
                "type": 4,
                "data": {"content": NOTICE, "flags": 64, "allowed_mentions": {"parse": []}},
            }
            if (outcome, replies) != ("incomplete", [notice]):
                broken.append("press-reply")
            if store.answer(item) is not None or store.approval(item) is not None:
                broken.append("press-recorded")
            if store.sender_status(SENDER) != status:
                broken.append("sender-changed")
        elif outcome == "incomplete":
            broken.append("complete-refused")
    texts = [a.text for a in store.pending_alerts()] + [
        str(body) for _, body in discord.callbacks if body.get("data", {}).get("content") == NOTICE
    ]
    if any(SUBJECT in text or SENDER in text for text in texts):
        broken.append("email-text")
    store.close()
    return broken


def task_trial(folder: Path, index: int, tasks: list[str]) -> list[str]:
    import json

    import httpx

    from mailroom.tasks_app import send_tasks
    from tests.fakes import FakeTasksApp

    os.environ["MAILROOM_TASKS_URL"] = FakeTasksApp.URL
    settings, store, _, items, path = setup(folder, f"tasks-{index}", len(tasks))
    for item in items:
        store.record_answer(item, "yes", "Pay the probe invoice")
        store.record_approval(item, "nodeadline", "Pay the probe invoice", None)
    store.queue_approved()
    for number, kind in enumerate(tasks):
        if kind == "messages":
            remove(path, f"DELETE FROM messages WHERE message_id = 'p{number}'")
        elif kind == "approvals":
            remove(path, f"DELETE FROM approvals WHERE item_id = '{items[number]}'")
    fake = FakeTasksApp()
    http = httpx.Client(transport=httpx.MockTransport(fake.handler))
    bad = {items[n] for n, kind in enumerate(tasks) if kind != "none"}
    good = [f"p{n}" for n, kind in enumerate(tasks) if kind == "none"]
    broken: list[str] = []
    for attempt in range(2):
        report = send_tasks(store, settings, http)
        wanted = (len(good) if attempt == 0 else 0, 0, "", len(bad))
        if (report.posted, report.waiting, report.stopped, report.skipped) != wanted:
            broken.append("task-report")
    if [json.loads(r.content)["message_id"] for r in fake.requests] != good:
        broken.append("task-sent-set")
    if {task.item_id for task in store.pending_tasks()} != bad:
        broken.append("task-kept-set")
    alerts = sorted((a.key, a.text, a.ping) for a in store.pending_alerts())
    if alerts != sorted((f"incomplete:{i}", ALERT.format(item=i), False) for i in bad):
        broken.append("task-alerts")
    store.close()
    os.environ.pop("MAILROOM_TASKS_URL")
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
    counts: dict[str, int] = {}
    reached = 0
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04i-trials-") as scratch:
        for index, (cards, tasks, presses) in enumerate(corpus):
            broken: list[str] = []
            for run in (
                partial(card_trial, Path(scratch), index, cards, presses),
                partial(task_trial, Path(scratch), index, tasks),
            ):
                try:
                    broken += run()
                except Exception as error:
                    broken.append(f"raised {type(error).__name__}")
            if not any(name.startswith("raised") for name in broken):
                reached += 1
            for name in broken:
                counts[name] = counts.get(name, 0) + 1
    print(f"trials reached: {reached} of {TRIALS}")
    if counts:
        detail = ", ".join(f"{name} x{count}" for name, count in sorted(counts.items()))
        print(f"incomplete-chain invariants: FAIL ({detail})")
        failures += 1
    else:
        print(f"incomplete-chain invariants across {TRIALS} seeded trials: ok")
    print(f"FAILURES {failures}")
    return int(bool(failures))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04i-") as folder:
        env = {key: value for key, value in os.environ.items() if not key.startswith("MAILROOM_")}
        env.update(
            HOME=folder,
            MAILROOM_DATA_DIR=str(Path(folder) / "data"),
            MAILROOM_TIME_ZONE="America/New_York",
            MAILROOM_DISCORD_CHANNEL_ID="111111111111111111",
            MAILROOM_DISCORD_OWNER_ID=OWNER,
        )
        with patch.dict(os.environ, env, clear=True):
            sys.exit(main())
