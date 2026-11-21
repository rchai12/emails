"""Lock waits on one database file: a store waits its set time, then fails cleanly.

`Holder` is a second, raw connection on the same file, as another program would be. A write
lock (BEGIN IMMEDIATE) stops other writers; a read lock (an open read transaction) lets other
writers start but not commit. Every error here comes from SQLite itself.
"""

import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

import mailroom.store
from mailroom.config import get_settings
from mailroom.store import DB_FILENAME, Store, open_store
from tests.integration.test_store_rollback import notified, unlocked


def is_busy(error: BaseException) -> bool:
    """`mailroom.store.is_busy`, looked up when called so this file imports before it exists."""
    return mailroom.store.is_busy(error)


def database() -> Path:
    return get_settings().data_dir / DB_FILENAME


class Holder:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(
            database(), timeout=0, isolation_level=None, check_same_thread=False
        )

    def write_lock(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")

    def read_lock(self) -> None:
        self.connection.execute("BEGIN")
        self.connection.execute("SELECT count(*) FROM senders").fetchone()

    def release(self) -> None:
        self.connection.execute("ROLLBACK")


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


@pytest.fixture
def holder(store: Store) -> Iterator[Holder]:
    held = Holder()
    yield held
    held.connection.close()


def raised(call) -> BaseException:
    try:
        call()
    except Exception as error:
        return error
    raise AssertionError("nothing was raised")


# How long a store waits


def test_a_store_waits_its_lock_wait_then_raises_a_busy_error(store: Store, holder: Holder) -> None:
    holder.write_lock()
    store.set_lock_wait(0.3)
    started = time.monotonic()
    with pytest.raises(sqlite3.OperationalError) as caught:
        store.set_sender_status("sam@example.test", "muted")
    waited = time.monotonic() - started
    assert is_busy(caught.value)
    assert 0.25 <= waited < 4
    holder.release()
    assert unlocked()
    assert store.sender_status("sam@example.test") is None
    store.set_sender_status("sam@example.test", "muted")
    assert store.sender_status("sam@example.test") == "muted"


def test_a_lower_lock_wait_replaces_a_higher_one(store: Store, holder: Holder) -> None:
    holder.write_lock()
    store.set_lock_wait(10.0)
    store.set_lock_wait(0.05)
    started = time.monotonic()
    with pytest.raises(sqlite3.OperationalError):
        store.set_sender_status("sam@example.test", "trusted")
    assert time.monotonic() - started < 4
    holder.release()


def test_reads_go_on_while_another_connection_holds_the_write_lock(
    store: Store, holder: Holder
) -> None:
    store.set_sender_status("sam@example.test", "trusted")
    holder.write_lock()
    store.set_lock_wait(0.05)
    assert store.sender_status("sam@example.test") == "trusted"
    assert store.senders("trusted") == ("sam@example.test",)
    holder.release()


def test_the_file_keeps_its_rollback_journal(store: Store) -> None:
    store.set_lock_wait(1.5)
    store.set_sender_status("sam@example.test", "trusted")
    other = sqlite3.connect(database())
    try:
        assert other.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    finally:
        other.close()


# Contention that clears


def test_a_write_waits_for_a_lock_that_is_released_in_time(store: Store, holder: Holder) -> None:
    holder.write_lock()
    store.set_lock_wait(5.0)
    release = threading.Timer(0.2, holder.release)
    release.start()
    try:
        store.set_sender_status("sam@example.test", "muted")
    finally:
        release.join()
    assert store.sender_status("sam@example.test") == "muted"
    assert unlocked()


def test_two_stores_writing_at_once_both_finish() -> None:
    open_store(get_settings()).close()
    problems: list[str] = []

    def write(prefix: str) -> None:
        try:
            with open_store(get_settings()) as mine:
                mine.set_lock_wait(5.0)
                for number in range(40):
                    mine.set_sender_status(f"{prefix}{number}@example.test", "muted")
        except Exception as error:
            problems.append(type(error).__name__)

    threads = [threading.Thread(target=write, args=(prefix,)) for prefix in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert problems == []
    with open_store(get_settings()) as store:
        assert len(store.senders("muted")) == 80
    assert unlocked()


# A wait that runs out


def test_a_commit_that_cannot_finish_is_rolled_back_and_frees_the_file(
    store: Store, holder: Holder
) -> None:
    holder.read_lock()
    store.set_lock_wait(0.05)
    with pytest.raises(sqlite3.OperationalError) as caught:
        store.set_sender_status("sam@example.test", "muted")
    assert is_busy(caught.value)
    assert store.sender_status("sam@example.test") is None
    holder.release()
    assert unlocked()
    store.set_sender_status("sam@example.test", "trusted")
    assert store.sender_status("sam@example.test") == "trusted"


def test_a_many_row_write_that_runs_out_of_time_keeps_none_of_its_rows(
    store: Store, holder: Holder
) -> None:
    notified(store, "m1", "m2", "m3")
    holder.read_lock()
    store.set_lock_wait(0.05)
    with pytest.raises(sqlite3.OperationalError):
        store.queue_notified()
    assert store.pending_posts() == ()
    holder.release()
    assert unlocked()
    assert store.queue_notified() == 3


def test_a_store_that_ran_out_of_time_can_write_other_rows_next(
    store: Store, holder: Holder
) -> None:
    holder.write_lock()
    store.set_lock_wait(0.05)
    with pytest.raises(sqlite3.OperationalError):
        store.queue_alert("probe:raised", "first", False)
    holder.release()
    assert store.queue_alert("other:raised", "second", False)
    assert [alert.key for alert in store.pending_alerts()] == ["other:raised"]
    assert unlocked()


# Which errors are lock waits


def locked_table(folder: Path) -> BaseException:
    connection = sqlite3.connect(folder / "locked.sqlite3")
    connection.execute("CREATE TABLE t (x)")
    connection.executemany("INSERT INTO t VALUES (?)", [(1,), (2,)])
    connection.commit()
    cursor = connection.execute("SELECT x FROM t")
    cursor.fetchone()
    error = raised(lambda: connection.execute("DROP TABLE t"))
    cursor.close()
    connection.close()
    return error


def read_only(folder: Path) -> BaseException:
    path = folder / "read-only.sqlite3"
    sqlite3.connect(path).execute("CREATE TABLE t (x)").connection.close()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    error = raised(lambda: connection.execute("INSERT INTO t VALUES (1)"))
    connection.close()
    return error


def missing_table(folder: Path) -> BaseException:
    connection = sqlite3.connect(folder / "plain.sqlite3")
    error = raised(lambda: connection.execute("SELECT x FROM missing"))
    connection.close()
    return error


@pytest.mark.parametrize(
    ("make", "busy"),
    [(locked_table, True), (read_only, False), (missing_table, False)],
    ids=["table-locked", "read-only", "no-such-table"],
)
def test_sqlite_errors_are_told_apart_by_their_code(tmp_path: Path, make, busy: bool) -> None:
    error = make(tmp_path)
    assert isinstance(error, sqlite3.OperationalError)
    assert is_busy(error) is busy


def test_a_real_lock_wait_is_busy(store: Store, holder: Holder) -> None:
    holder.write_lock()
    store.set_lock_wait(0.05)
    error = raised(lambda: store.set_sender_status("sam@example.test", "muted"))
    holder.release()
    assert is_busy(error)


def coded(kind: type[Exception], code: int | None) -> Exception:
    error = kind("database is locked")
    if code is not None:
        error.sqlite_errorcode = code
    return error


@pytest.mark.parametrize(
    ("error", "busy"),
    [
        (coded(sqlite3.OperationalError, 5), True),
        (coded(sqlite3.OperationalError, 6), True),
        (coded(sqlite3.OperationalError, 517), True),
        (coded(sqlite3.OperationalError, 262), True),
        (coded(sqlite3.OperationalError, 1), False),
        (coded(sqlite3.OperationalError, 8), False),
        (coded(sqlite3.OperationalError, 13), False),
        (coded(sqlite3.OperationalError, None), False),
        (coded(sqlite3.IntegrityError, 5), False),
        (coded(sqlite3.DatabaseError, 5), False),
        (RuntimeError("database is locked"), False),
    ],
    ids=[
        "busy",
        "locked",
        "busy-snapshot",
        "locked-sharedcache",
        "error",
        "readonly",
        "full",
        "no-code",
        "integrity",
        "database-error",
        "not-sqlite",
    ],
)
def test_only_busy_and_locked_codes_count_as_lock_waits(error: Exception, busy: bool) -> None:
    assert is_busy(error) is busy
