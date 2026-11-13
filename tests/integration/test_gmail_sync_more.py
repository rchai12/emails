from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.gmail import GmailUnavailable, MessageGone
from mailroom.gmail_sync import sync_gmail
from mailroom.record import Record
from mailroom.store import Store, open_store
from tests.fakes import FakeGmail, FakeKeychain
from tests.integration.test_gmail_sync import client_for, deliver, sync

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
SECRETS = {
    ("mailroom", "gmail.personal.client-id"): "client-id-1",
    ("mailroom", "gmail.personal.client-secret"): "client-secret-1",
    ("mailroom", "gmail.personal.refresh-token"): "refresh-token-1",
}


@pytest.fixture
def gmail(fake_keychain: FakeKeychain, monkeypatch: pytest.MonkeyPatch) -> FakeGmail:
    fake_keychain.secrets.update(SECRETS)
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return FakeGmail()


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def test_a_missing_profile_is_unavailable(gmail: FakeGmail, store: Store) -> None:
    gmail.failures.append(httpx.Response(404))
    with pytest.raises(GmailUnavailable) as caught:
        sync(gmail, store)
    assert str(caught.value) == "gmail unavailable: personal (404)"
    assert not isinstance(caught.value, MessageGone)
    assert store.sync_state("gmail", "personal") is None


def test_a_message_the_store_did_not_add_is_omitted(
    gmail: FakeGmail, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    deliver(gmail, 1)
    original = store.add

    def decline(record: Record) -> bool:
        assert original(record) is True
        return False

    monkeypatch.setattr(store, "add", decline)
    assert sync_gmail(client_for(gmail), store).stored == ()
    assert store.get("gmail", "personal/m1") is not None
