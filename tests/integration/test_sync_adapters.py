"""Adapter rules the shared round leaves to each provider, and the round's edges."""

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock, mail_sync
from mailroom.config import get_settings
from mailroom.gmail import GmailClient, GmailUnavailable
from mailroom.gmail_sync import sync_gmail
from mailroom.outlook import OutlookClient, OutlookUnavailable
from mailroom.outlook_sync import sync_outlook
from mailroom.store import Store, SyncState, open_store
from tests.fakes import FakeGmail, FakeGraph, FakeKeychain
from tests.integration.test_gmail_sync import SECRETS, bookmarked, deliver, fetched
from tests.integration.test_mail_sync import Scripted
from tests.integration.test_outlook_sync import deliver as deliver_mail

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


@pytest.fixture
def gmail(fake_keychain: FakeKeychain) -> FakeGmail:
    fake_keychain.secrets.update(SECRETS)
    return FakeGmail()


@pytest.fixture
def graph(fake_keychain: FakeKeychain) -> FakeGraph:
    fake = FakeGraph()
    fake_keychain.secrets[("mailroom", "outlook.live.client-id")] = fake.client_id
    fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] = fake.refresh_token
    return fake


def gmail_client(fake: FakeGmail, failing: str = "") -> GmailClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if failing and failing in request.url.path:
            return httpx.Response(503)
        return fake.handler(request)

    return GmailClient("personal", httpx.Client(transport=httpx.MockTransport(handler)))


def outlook_client(fake: FakeGraph, failing: str = "") -> OutlookClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if failing and failing in request.url.path:
            return httpx.Response(503)
        return fake.handler(request)

    return OutlookClient("live", httpx.Client(transport=httpx.MockTransport(handler)))


def gets(requests: list[httpx.Request]) -> list[str]:
    return [request.url.path for request in requests if request.method == "GET"]


def test_gmail_skips_mail_labelled_both_inbox_and_spam_after_fetching_it(
    gmail: FakeGmail, store: Store
) -> None:
    bookmarked(store, "1000")
    deliver(gmail, 1, "2026-11-12T08:00:00+00:00", labels=("INBOX", "SPAM"))
    result = sync_gmail(gmail_client(gmail), store)
    assert result.kind == "history"
    assert fetched(gmail) == ["m1"]
    assert result.stored == ()
    assert store.get("gmail", "personal/m1") is None


def test_gmail_reads_its_profile_before_resuming(gmail: FakeGmail, store: Store) -> None:
    bookmarked(store, "1000")
    sync_gmail(gmail_client(gmail), store)
    paths = gets(gmail.requests)
    assert paths[0].endswith("/profile")
    assert any("history" in path for path in paths[1:])


def test_outlook_reads_its_profile_before_resuming(graph: FakeGraph, store: Store) -> None:
    sync_outlook(outlook_client(graph), store)
    graph.requests.clear()
    sync_outlook(outlook_client(graph), store)
    paths = gets(graph.requests)
    assert "delta" not in paths[0]
    assert any("delta" in path for path in paths[1:])


def test_another_gmail_history_error_propagates_and_keeps_the_bookmark(
    gmail: FakeGmail, store: Store
) -> None:
    state = bookmarked(store, "1000")
    with pytest.raises(GmailUnavailable):
        sync_gmail(gmail_client(gmail, failing="history"), store)
    assert store.sync_state("gmail", "personal") == state


def test_another_outlook_delta_error_propagates_and_keeps_the_bookmark(
    graph: FakeGraph, store: Store
) -> None:
    deliver_mail(graph, 1, "2026-11-12T08:00:00Z")
    sync_outlook(outlook_client(graph), store)
    state = store.sync_state("outlook", "live")
    with pytest.raises(OutlookUnavailable):
        sync_outlook(outlook_client(graph, failing="delta"), store)
    assert store.sync_state("outlook", "live") == state


def test_a_message_the_store_refuses_is_not_counted_and_the_bookmark_is_saved(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    log: list[str] = []
    source = Scripted(log)
    source.listed = ["a", "b"]
    monkeypatch.setattr(store, "add", lambda record: False)
    result = mail_sync.run_round(source, store)
    assert result.stored == ()
    assert result.kind == "first"
    assert store.sync_state("yahoo", "family") == SyncState(bookmark="b2", synced_at=NOW)
