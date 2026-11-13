from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.store import Store, open_store
from tests.integration.test_store_posts import NOTIFY, RECORD
from tests.support import fixed_ids

ITEM = "a" * 32
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    fixed_ids(monkeypatch, ITEM)
    with open_store(get_settings()) as opened:
        opened.add(RECORD)
        opened.save_triage("gmail", "m1", NOTIFY)
        opened.queue_notified()
        yield opened


def test_an_unknown_item_has_no_card_to_choose(store: Store) -> None:
    assert store.choose_card("b" * 32, "first") is None
    assert store.post_by_item("b" * 32) is None
    assert store.pending_posts()[0].card is None
