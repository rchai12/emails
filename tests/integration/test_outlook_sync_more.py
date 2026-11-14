"""A stored message the store declines is left out of the round's result."""

from collections.abc import Iterator
from datetime import datetime

import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.record import Record
from mailroom.store import Store, open_store
from tests.fakes import FakeGraph, FakeKeychain
from tests.integration.test_outlook_sync import NOW, deliver, sync


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    return now


@pytest.fixture
def graph(fake_keychain: FakeKeychain, moment: list[datetime]) -> FakeGraph:
    fake = FakeGraph()
    fake_keychain.secrets[("mailroom", "outlook.live.client-id")] = fake.client_id
    fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] = fake.refresh_token
    return fake


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def test_a_message_the_store_did_not_add_is_omitted(
    graph: FakeGraph, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    deliver(graph, 1)
    original = store.add

    def decline(record: Record) -> bool:
        assert original(record) is True
        return False

    monkeypatch.setattr(store, "add", decline)
    result = sync(graph, store)
    assert result.stored == ()
    assert result.kind == "first"
    assert store.get("outlook", "live/AAMk1=") is not None
    assert store.sync_state("outlook", "live") is not None
