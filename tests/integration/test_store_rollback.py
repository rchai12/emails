"""A write that fails partway leaves nothing behind and holds no lock on the file."""

import sqlite3
from collections.abc import Iterator
from dataclasses import replace

import pytest

from mailroom import ids
from mailroom.config import get_settings
from mailroom.store import DB_FILENAME, Store, open_store
from tests.integration.test_store_posts import NOTIFY, RECORD


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def unlocked() -> bool:
    """True if another connection can take the write lock at once."""
    other = sqlite3.connect(get_settings().data_dir / DB_FILENAME, timeout=0, isolation_level=None)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.execute("ROLLBACK")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        other.close()


def notified(store: Store, *message_ids: str) -> None:
    for message_id in message_ids:
        store.add(replace(RECORD, message_id=message_id))
        store.save_triage("gmail", message_id, NOTIFY)


def test_a_write_that_fails_halfway_keeps_none_of_its_rows(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    notified(store, "m1", "m2")
    original = ids.new_id
    handed: list[str] = []

    def one_id() -> str:
        if handed:
            raise RuntimeError("no more ids")
        handed.append("a" * 32)
        return handed[0]

    monkeypatch.setattr(ids, "new_id", one_id)
    with pytest.raises(RuntimeError):
        store.queue_notified()
    assert store.pending_posts() == ()
    assert unlocked()
    monkeypatch.setattr(ids, "new_id", original)
    assert store.queue_notified() == 2


def test_a_write_the_database_refuses_releases_the_file(store: Store) -> None:
    store.add(RECORD)
    with pytest.raises(sqlite3.IntegrityError):
        store.save_triage("gmail", "m1", replace(NOTIFY, outcome="unknown"))
    assert unlocked()
    assert store.triage("gmail", "m1") is None
    assert store.save_triage("gmail", "m1", NOTIFY) is True


def test_a_good_write_is_committed_at_once(store: Store) -> None:
    store.add(RECORD)
    assert unlocked()
    with open_store(get_settings()) as other:
        assert other.get("gmail", "m1") is not None
