import sqlite3
from collections.abc import Iterator

import pytest

from mailroom.config import get_settings
from mailroom.store import Store, Verdict, open_store
from tests.integration.test_store_triage import EXTRACTED, RECORD


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def test_an_inconsistent_verdict_is_refused(store: Store) -> None:
    store.add(RECORD)
    broken = Verdict(outcome="dropped", trusted=False, verified=False, bulk=False, notify=True)
    with pytest.raises(sqlite3.IntegrityError):
        store.save_triage("gmail", "m1", broken)
    assert store.triage("gmail", "m1") is None
    assert store.untriaged() == (("gmail", "m1"),)


def test_untriaged_is_empty_when_nothing_is_stored(store: Store) -> None:
    assert store.untriaged() == ()


def test_a_verdict_is_kept_under_its_own_provider(store: Store) -> None:
    store.add(RECORD)
    assert store.save_triage("gmail", "m1", EXTRACTED) is True
    assert store.triage("yahoo", "m1") is None
    found = store.triage("gmail", "m1")
    assert found is not None
    assert found.verdict == EXTRACTED
