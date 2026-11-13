"""Probe for phase 2a. Run from the repository root: .venv/bin/python docs/verification/probe-02a.py

Two stores on one file take random turns calling store methods. Each trial opens with two
notified emails and a `queue_notified` whose second id fails, a write that stops halfway. Some
calls get a refused input (a verdict outcome the schema forbids, a sender status that does not
exist); some run with
`ids.new_id` or `clock.now` set to fail after a random number of calls. After every call:
  - another connection can take the write lock at once (nothing is left uncommitted)
  - a call that raised left every table exactly as it was (read through a separate connection)
  - only the injected failure, or the refusal, was raised
Fakes only; everything lives in a temporary folder. Each check prints `ok` or `FAIL`; the last
line is `FAILURES N`.
"""

import os
import random
import sqlite3
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe02a-"))
os.environ["HOME"] = str(TMP / "home")

from mailroom import clock, ids  # noqa: E402
from mailroom.config import get_settings  # noqa: E402
from mailroom.record import Record  # noqa: E402
from mailroom.store import DB_FILENAME, SyncState, Verdict, open_store  # noqa: E402

FAILURES = 0
rng = random.Random(21)
START = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
REAL_IDS = ids.new_id
MOMENT = [START]
RECORD = Record(
    provider="gmail",
    message_id="personal/m0",
    thread_id="personal/t0",
    received_at=START,
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m0",
    sender="billing@example.test",
    sender_name="Billing",
    subject="Bill",
    sent_at=None,
    body_text="Your bill is due.",
    list_unsubscribe=False,
    authentication_results=(),
)
NOTIFY = Verdict("rejected", False, True, False, True, None, reason="timeout")
QUIET = Verdict("dropped", False, False, False, False)
BAD = Verdict("unknown", False, True, False, True, None, reason="timeout")


class Injected(Exception):
    pass


def check(name: str, fn) -> None:
    global FAILURES
    try:
        result = fn()
    except Exception as error:
        result = f"raised {type(error).__name__}"
    ok = result is True
    print(f"{name}: {'ok' if ok else 'FAIL ' + str(result)}")
    if not ok:
        FAILURES += 1


def raw(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path, timeout=0, isolation_level=None)


def unlocked(path: Path) -> bool:
    other = raw(path)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.execute("ROLLBACK")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        other.close()


def snapshot(path: Path) -> dict[str, list[tuple]]:
    other = raw(path)
    try:
        tables = [
            row[0]
            for row in other.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {t: other.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall() for t in tables}
    finally:
        other.close()


class FailingAfter:
    """Calls `real` `count` times, then raises `Injected`; `handed` counts the good calls."""

    def __init__(self, count: int, real) -> None:
        self.left, self.real, self.handed = count, real, 0

    def __call__(self):
        if self.left == 0:
            raise Injected
        self.left -= 1
        self.handed += 1
        return self.real()


def random_call(store) -> tuple[str, object, type[Exception] | None, bool]:
    """A store call, its name, the exception a refused input raises, and whether it must."""
    number = rng.randrange(6)
    message_id = f"personal/m{number}"
    kind = rng.randrange(12)
    if kind == 0:
        return "add", lambda: store.add(replace(RECORD, message_id=message_id)), None, False
    if kind == 1:
        verdict = rng.choice((NOTIFY, QUIET))
        call = lambda: store.save_triage("gmail", message_id, verdict)  # noqa: E731
        return "save_triage", call, None, False
    if kind == 2:
        call = lambda: store.save_triage("gmail", message_id, BAD)  # noqa: E731
        return "save_triage bad", call, sqlite3.IntegrityError, False
    if kind == 3:
        status = rng.choice(("trusted", "muted", None))
        address = f"s{number}@example.test"
        return "set_sender_status", lambda: store.set_sender_status(address, status), None, False
    if kind == 4:
        address = f"s{number}@example.test"
        return "bad status", lambda: store.set_sender_status(address, "loved"), ValueError, True
    if kind == 5:
        state = SyncState(bookmark=str(number), synced_at=START)
        call = lambda: store.save_sync_state("gmail", "personal", state)  # noqa: E731
        return "save_sync_state", call, None, False
    if kind == 6:
        return "queue_notified", store.queue_notified, None, False
    if kind == 7:
        pending = store.pending_posts()
        if pending:
            item = pending[0].item_id
            call = lambda: store.mark_posted(item, f"13{number:017d}")  # noqa: E731
            return "mark_posted", call, None, False
        return "clear_expired_text", store.clear_expired_text, None, False
    if kind == 8:
        key = rng.choice(("model", "gateway"))
        return "open_problem", lambda: store.open_problem(key), None, False
    if kind == 9:
        key = rng.choice(("model", "gateway"))
        return "close_problem", lambda: store.close_problem(key), None, False
    if kind == 10:
        key = f"alert-{number}"
        return "queue_alert", lambda: store.queue_alert(key, "Text.", False), None, False
    return "clear_expired_text", store.clear_expired_text, None, False


def failed_calls_change_nothing() -> object:
    reached = {"injected": 0, "refused": 0, "partial": 0}
    for trial in range(60):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"trial{trial}")
        path = TMP / f"trial{trial}" / DB_FILENAME
        MOMENT[0] = START
        with open_store(get_settings()) as first, open_store(get_settings()) as second:
            clock.now = lambda: MOMENT[0]
            for number in (8, 9):
                first.add(replace(RECORD, message_id=f"personal/m{number}"))
                first.save_triage("gmail", f"personal/m{number}", NOTIFY)
            for turn in range(80):
                MOMENT[0] += timedelta(hours=rng.choice((0, 1, 7)))
                store = rng.choice((first, second))
                name, call, refused, must = random_call(store)
                inject = rng.random()
                ids.new_id = REAL_IDS
                clock.now = lambda: MOMENT[0]
                handing = FailingAfter(rng.randrange(3), REAL_IDS)
                if turn == 0:
                    # Two notified rows wait, and the second id fails: a write that stops halfway.
                    name, call, refused, must = "queue_notified", store.queue_notified, None, False
                    handing = FailingAfter(1, REAL_IDS)
                    ids.new_id = handing
                elif inject < 0.25:
                    ids.new_id = handing
                elif inject < 0.35:
                    clock.now = FailingAfter(rng.randrange(2), lambda: MOMENT[0])
                before = snapshot(path)
                try:
                    call()
                    error = None
                except Exception as caught:
                    error = caught
                ids.new_id = REAL_IDS
                clock.now = lambda: MOMENT[0]
                if not unlocked(path):
                    return f"trial {trial} turn {turn}: {name} left the file locked"
                if error is None:
                    if must:
                        return f"trial {trial} turn {turn}: {name} was accepted"
                    continue
                if isinstance(error, Injected):
                    reached["injected"] += 1
                elif refused is not None and isinstance(error, refused):
                    reached["refused"] += 1
                else:
                    return f"trial {trial} turn {turn}: {name} raised {type(error).__name__}"
                after = snapshot(path)
                if after != before:
                    return f"trial {trial} turn {turn}: failed {name} changed the tables"
                if name == "queue_notified" and isinstance(error, Injected) and handing.handed:
                    reached["partial"] += 1
    if min(reached.values()) < 5:
        return f"too few failures reached: {reached}"
    return True


check("a failed call changes nothing and leaves the file unlocked", failed_calls_change_nothing)
print(f"FAILURES {FAILURES}")
