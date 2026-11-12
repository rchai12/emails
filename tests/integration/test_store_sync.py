import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from mailroom.config import get_settings
from mailroom.schema import MIGRATIONS
from mailroom.store import Store, SyncState, open_store

STATE = SyncState(bookmark="1007", synced_at=datetime(2026, 11, 11, 9, 0, 0, 250, tzinfo=UTC))


def test_a_version_1_database_gains_the_sync_table(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(MIGRATIONS[0] + "\nPRAGMA user_version = 1;")
    connection.close()
    with Store(path) as store:
        assert store.sync_state("gmail", "personal") is None
        store.save_sync_state("gmail", "personal", STATE)
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,)
        assert connection.execute("SELECT * FROM sync_state").fetchall() == [
            ("gmail", "personal", "1007", "2026-11-11T09:00:00.000250+00:00")
        ]
    finally:
        connection.close()


def test_a_saved_state_is_read_back_in_utc() -> None:
    eastern = timezone(timedelta(hours=-5))
    with open_store(get_settings()) as store:
        store.save_sync_state(
            "gmail",
            "personal",
            SyncState(bookmark="1007", synced_at=datetime(2026, 11, 11, 4, 0, 0, 250, eastern)),
        )
    with open_store(get_settings()) as store:
        state = store.sync_state("gmail", "personal")
    assert state == STATE
    assert state.synced_at.utcoffset() == timedelta(0)


def test_saving_again_replaces_the_state() -> None:
    later = SyncState(bookmark="1012", synced_at=datetime(2026, 11, 11, 9, 2, tzinfo=UTC))
    with open_store(get_settings()) as store:
        store.save_sync_state("gmail", "personal", STATE)
        store.save_sync_state("gmail", "personal", later)
        assert store.sync_state("gmail", "personal") == later


def test_each_provider_and_account_has_its_own_state() -> None:
    with open_store(get_settings()) as store:
        store.save_sync_state("gmail", "personal", STATE)
        assert store.sync_state("gmail", "work") is None
        assert store.sync_state("outlook", "personal") is None
        assert store.sync_state("gmail", "personal") == STATE
