"""Independent lock-contention probe: seeded lock/operation scripts, synthetic data only."""

import argparse
import os
import random
import sqlite3
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

LOCKS = ("none", "read", "write", "exclusive")
OPS = ("mark", "read", "alert", "notify", "press")
WRITES = ("mark", "alert")
ADDRESSES = ("ana@example.test", "ben@example.test", "cy@example.test")
ALERT_KEYS = ("probe:a", "probe:b")
TRIALS = 40
STEPS = 14
WAIT = 0.02
BUSY_TEXT = "Mailroom is busy right now. Press again in a moment."


def scripts() -> list[list[tuple[str, str, int]]]:
    rng = random.Random(407)
    corpus = []
    for trial in range(TRIALS):
        steps = []
        for step in range(STEPS):
            lock = LOCKS[(trial + step) % len(LOCKS)] if step % 3 else rng.choice(LOCKS)
            op = OPS[(trial * 3 + step) % len(OPS)] if step % 2 else rng.choice(OPS)
            steps.append((lock, op, rng.randrange(6)))
        steps[-1] = ("none", "press", 0)
        corpus.append(steps)
    return corpus


def expected(lock: str, op: str, answered: bool, queued: bool = False) -> str:
    """The oracle: what one operation must do under one lock held by another connection.

    Queueing notified mail writes only while there is mail to queue; afterwards it only reads.
    """
    if lock == "none":
        if op == "press":
            return "already" if answered else "answered"
        return "ok"
    if lock == "exclusive":
        return "busy"
    if op == "press":
        return "already" if answered else "busy"
    writes = op in WRITES or (op == "notify" and not queued)
    return "busy" if writes else "ok"


def oracle_self_check(corpus: list[list[tuple[str, str, int]]]) -> None:
    assert len(corpus) == TRIALS
    pairs = [(lock, op) for steps in corpus for lock, op, _ in steps]
    assert all(pairs.count((lock, op)) >= 3 for lock in LOCKS for op in OPS)
    assert expected("none", "press", False) == "answered"
    assert expected("write", "press", False) == "busy"
    assert expected("read", "press", True) == "already"
    assert expected("exclusive", "read", False) == "busy"
    assert expected("read", "mark", False) == "busy"
    assert expected("write", "read", False) == "ok"
    assert expected("read", "notify", False) == "busy"
    assert expected("read", "notify", False, queued=True) == "ok"
    retried = 0
    for steps in corpus:
        assert steps[-1] == ("none", "press", 0)
        presses = [lock for lock, op, _ in steps if op == "press"]
        if presses.index("none") > 0:
            retried += 1
    assert retried >= 15


def real_errors(folder: Path) -> list[sqlite3.Error]:
    found: list[sqlite3.Error] = []

    def catch(call) -> None:
        try:
            call()
        except sqlite3.Error as error:
            found.append(error)

    plain = sqlite3.connect(folder / "plain.sqlite3")
    plain.execute("CREATE TABLE t (x UNIQUE)")
    plain.executemany("INSERT INTO t VALUES (?)", [(1,), (2,)])
    plain.commit()
    cursor = plain.execute("SELECT x FROM t")
    cursor.fetchone()
    catch(lambda: plain.execute("DROP TABLE t"))
    cursor.close()
    catch(lambda: plain.execute("SELECT x FROM missing"))
    catch(lambda: plain.execute("INSERT INTO t VALUES (1)"))
    plain.close()
    reader = sqlite3.connect(f"file:{folder / 'plain.sqlite3'}?mode=ro", uri=True)
    catch(lambda: reader.execute("INSERT INTO t VALUES (3)"))
    reader.close()
    holder = sqlite3.connect(folder / "plain.sqlite3", timeout=0, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    other = sqlite3.connect(folder / "plain.sqlite3", timeout=0.01)
    catch(lambda: other.execute("SELECT x FROM t").fetchall())
    other.close()
    holder.execute("ROLLBACK")
    holder.close()
    return found


def classification(folder: Path) -> list[str]:
    from mailroom.store import is_busy

    broken = []
    errors = real_errors(folder)
    if len(errors) != 5:
        broken.append("error-corpus")
    for error in errors:
        name = getattr(error, "sqlite_errorname", "")
        want = name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED"))
        if is_busy(error) is not want:
            broken.append("classification")
    if is_busy(RuntimeError("database is locked")) or is_busy(sqlite3.OperationalError("x")):
        broken.append("classification")
    return broken


def run_trial(steps: list[tuple[str, str, int]], folder: Path, index: int) -> list[str]:
    """Runs one script against a real store; returns the names of the invariants it broke."""
    import httpx

    from mailroom import clock
    from mailroom.config import get_settings
    from mailroom.interactions import handle_interaction
    from mailroom.store import DB_FILENAME, is_busy, open_store
    from tests.fakes import FakeDiscord
    from tests.integration.test_interactions import RECORD, VERDICT

    os.environ["MAILROOM_DATA_DIR"] = str(folder / f"data-{index}")
    clock.now = lambda: datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
    settings = get_settings()
    store = open_store(settings)
    store.add(RECORD)
    store.save_triage("gmail", "m1", VERDICT)
    store.queue_notified()
    item = store.pending_posts()[0].item_id
    store.mark_posted(item, "1300000000000000001")
    for number in range(3):
        store.add(replace(RECORD, message_id=f"n{number}", thread_id=f"t{number}"))
        store.save_triage("gmail", f"n{number}", VERDICT)
    store.set_lock_wait(WAIT)
    path = settings.data_dir / DB_FILENAME
    holder = sqlite3.connect(path, timeout=0, isolation_level=None)
    discord = FakeDiscord()
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    senders: dict[str, str] = {}
    keys: set[str] = set()
    queued = False
    answered = False
    broken: list[str] = []

    def lock(kind: str) -> None:
        if kind == "read":
            holder.execute("BEGIN")
            holder.execute("SELECT count(*) FROM senders").fetchone()
        elif kind == "write":
            holder.execute("BEGIN IMMEDIATE")
        elif kind == "exclusive":
            holder.execute("BEGIN EXCLUSIVE")

    def unlocked() -> bool:
        other = sqlite3.connect(path, timeout=0, isolation_level=None)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.execute("ROLLBACK")
            return True
        except sqlite3.OperationalError:
            return False
        finally:
            other.close()

    for kind, op, pick in steps:
        want = expected(kind, op, answered, queued)
        address = ADDRESSES[pick % len(ADDRESSES)]
        status = ("muted", "trusted", None)[pick % 3]
        key = ALERT_KEYS[pick % len(ALERT_KEYS)]
        got = "ok"
        lock(kind)
        try:
            if op == "mark":
                store.set_sender_status(address, status)
            elif op == "read":
                store.senders("muted")
                store.sender_status(address)
            elif op == "alert":
                if store.queue_alert(key, "probe alert", False) is (key in keys):
                    broken.append("alert-return")
            elif op == "notify":
                if store.queue_notified() != (0 if queued else 3):
                    broken.append("notify-count")
            else:
                before = len(discord.callbacks)
                event = discord.press(f"mr:mute:{item}")
                try:
                    got = handle_interaction(event, store, settings, http)
                except Exception:
                    got = "press-raised"
                replies = [body for _, body in discord.callbacks[before:]]
                if got == "press-raised":
                    pass
                elif len(replies) != 1:
                    broken.append("press-replies")
                elif got == "busy" and replies[0].get("data", {}).get("content") != BUSY_TEXT:
                    broken.append("busy-reply")
                elif got == "busy" and replies[0]["data"].get("flags") != 64:
                    broken.append("busy-private")
        except sqlite3.OperationalError as error:
            got = "busy" if is_busy(error) else "other-error"
        except Exception:
            got = "other-error"
        finally:
            if holder.in_transaction:
                holder.execute("ROLLBACK")
        if got != want:
            broken.append(f"outcome-{kind}-{op}")
        if got in ("ok", "answered"):
            if op == "mark":
                if status is None:
                    senders.pop(address, None)
                else:
                    senders[address] = status
            elif op == "alert":
                keys.add(key)
            elif op == "notify":
                queued = True
            elif op == "press":
                answered = True
                senders["billing@example.test"] = "muted"
        if not unlocked():
            broken.append("leaked-lock")
            break
        muted = {a for a, s in senders.items() if s == "muted"}
        trusted = {a for a, s in senders.items() if s == "trusted"}
        if set(store.senders("muted")) != muted or set(store.senders("trusted")) != trusted:
            broken.append("senders-state")
        if {alert.key for alert in store.pending_alerts()} != keys:
            broken.append("alerts-state")
        if len(store.pending_posts()) != (3 if queued else 0):
            broken.append("posts-state")
        if (store.answer(item) is not None) != answered:
            broken.append("answer-state")
    mode = holder.execute("PRAGMA journal_mode").fetchone()[0]
    if mode != "delete":
        broken.append("journal-mode")
    holder.close()
    store.close()
    http.close()
    return broken


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-only", action="store_true")
    args = parser.parse_args()
    corpus = scripts()
    oracle_self_check(corpus)
    print("oracle self-check: ok")
    if args.oracle_only:
        print("FAILURES 0")
        return 0
    failures = 0
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04g-errors-") as scratch:
        try:
            broken = classification(Path(scratch))
        except Exception as error:
            broken = [f"raised {type(error).__name__}"]
    if broken:
        print(f"error classification: FAIL ({', '.join(sorted(set(broken)))})")
        failures += 1
    else:
        print("error classification on real SQLite errors: ok")
    counts: dict[str, int] = {}
    reached = 0
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04g-trials-") as scratch:
        for index, steps in enumerate(corpus):
            try:
                broken = run_trial(steps, Path(scratch), index)
                reached += 1
            except Exception as error:
                broken = [f"raised {type(error).__name__}"]
            for name in broken:
                counts[name] = counts.get(name, 0) + 1
    print(f"trials reached: {reached} of {TRIALS}")
    if counts:
        detail = ", ".join(f"{name} x{count}" for name, count in sorted(counts.items()))
        print(f"contention invariants: FAIL ({detail})")
        failures += 1
    else:
        print(f"contention invariants across {TRIALS} seeded scripts: ok")
    print(f"FAILURES {failures}")
    return int(bool(failures))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04g-") as folder:
        env = {key: value for key, value in os.environ.items() if not key.startswith("MAILROOM_")}
        env.update(
            HOME=folder,
            MAILROOM_DATA_DIR=str(Path(folder) / "data"),
            MAILROOM_DISCORD_CHANNEL_ID="111111111111111111",
            MAILROOM_DISCORD_OWNER_ID="444444444444444444",
        )
        with patch.dict(os.environ, env, clear=True):
            sys.exit(main())
