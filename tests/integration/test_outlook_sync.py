"""Outlook sync: the delta link as bookmark, inbox only, once each, and a catch-up on expiry."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.gmail_sync import SyncResult
from mailroom.outlook import OutlookAuthError, OutlookClient, OutlookUnavailable
from mailroom.outlook_sync import INBOX_LINK, sync_outlook
from mailroom.store import Store, SyncState, open_store
from tests.fakes import FakeGraph, FakeKeychain

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
DELTA = "https://graph.microsoft.com/v1.0/me/mailFolders('inbox')/messages/delta"


def raw(number: int) -> bytes:
    return (
        f"From: Sender {number} <sender{number}@example.test>\r\n"
        f"Subject: Note {number}\r\n"
        "Date: Thu, 12 Nov 2026 07:59:00 +0000\r\n"
        f"\r\nBody {number}.\r\n"
    ).encode()


def deliver(graph: FakeGraph, number: int, received: str = "2026-11-12T08:00:00Z", **kw) -> None:
    graph.add_message(f"AAMk{number}=", raw(number), received=received, **kw)


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


def sync(graph: FakeGraph, store: Store) -> SyncResult:
    client = OutlookClient("live", httpx.Client(transport=httpx.MockTransport(graph.handler)))
    return sync_outlook(client, store)


def fetched(graph: FakeGraph) -> list[str]:
    return [r.url.path for r in graph.requests if r.url.path.endswith("/$value")]


def first_filter(graph: FakeGraph) -> str:
    deltas = [r for r in graph.requests if "$filter" in r.url.params]
    return deltas[-1].url.params["$filter"]


def test_a_first_run_reads_three_days_of_the_inbox(graph: FakeGraph, store: Store) -> None:
    deliver(graph, 1, "2026-11-09T08:00:00Z")
    deliver(graph, 2, "2026-11-11T08:00:00Z")
    deliver(graph, 3, "2026-11-13T08:00:00Z")
    deliver(graph, 4, "2026-11-12T08:00:00Z", folder="junkemail")
    assert sync(graph, store) == SyncResult(
        account="live",
        kind="first",
        stored=("live/AAMk2=", "live/AAMk3="),
        offline_since=None,
        gap=False,
    )
    assert first_filter(graph) == "receivedDateTime ge 2026-11-10T09:00:00Z"
    assert store.sync_state("outlook", "live") == SyncState(
        bookmark=f"{DELTA}?$deltatoken=d3", synced_at=NOW
    )


def test_a_stored_email_carries_the_outlook_envelope(graph: FakeGraph, store: Store) -> None:
    deliver(graph, 1, conversation_id="conversation-7")
    sync(graph, store)
    record = store.get("outlook", "live/AAMk1=").record
    assert (record.provider, record.message_id, record.thread_id) == (
        "outlook",
        "live/AAMk1=",
        "live/conversation-7",
    )
    assert record.received_at == datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    assert record.link == "https://outlook.live.com/owa/?ItemID=AAMk1=&exvsurl=1"
    assert (record.sender, record.subject) == ("sender1@example.test", "Note 1")


def test_a_later_round_reads_only_new_mail_from_the_bookmark(
    graph: FakeGraph, store: Store, moment: list[datetime]
) -> None:
    deliver(graph, 1)
    sync(graph, store)
    deliver(graph, 2)
    moment[0] = NOW + timedelta(minutes=1)
    assert sync(graph, store) == SyncResult("live", "delta", ("live/AAMk2=",), None, False)
    assert str(graph.requests[-3].url) == f"{DELTA}?$deltatoken=d1"
    assert store.sync_state("outlook", "live") == SyncState(
        bookmark=f"{DELTA}?$deltatoken=d2", synced_at=NOW + timedelta(minutes=1)
    )
    assert fetched(graph) == ["/v1.0/me/messages/AAMk1=/$value", "/v1.0/me/messages/AAMk2=/$value"]


def test_mail_moved_out_of_the_inbox_before_its_fetch_is_skipped(
    graph: FakeGraph, store: Store
) -> None:
    sync(graph, store)
    deliver(graph, 1)
    graph.move("AAMk1=", "junkemail")
    assert sync(graph, store).stored == ()
    assert store.get("outlook", "live/AAMk1=") is None


def test_mail_moved_into_the_inbox_counts_as_new(graph: FakeGraph, store: Store) -> None:
    sync(graph, store)
    deliver(graph, 1, folder="junkemail")
    graph.move("AAMk1=", "inbox")
    assert sync(graph, store).stored == ("live/AAMk1=",)


def test_a_message_listed_again_is_not_fetched_again(graph: FakeGraph, store: Store) -> None:
    sync(graph, store)
    deliver(graph, 1)
    sync(graph, store)
    graph.move("AAMk1=", "junkemail")
    graph.move("AAMk1=", "inbox")
    assert sync(graph, store).stored == ()
    assert fetched(graph) == ["/v1.0/me/messages/AAMk1=/$value"]


def test_a_message_deleted_before_its_fetch_is_skipped(graph: FakeGraph, store: Store) -> None:
    sync(graph, store)
    deliver(graph, 1)
    deliver(graph, 2)
    graph.delete("AAMk1=")
    assert sync(graph, store).stored == ("live/AAMk2=",)


def test_an_expired_bookmark_catches_up_from_the_last_round_with_an_hour_overlap(
    graph: FakeGraph, store: Store, moment: list[datetime]
) -> None:
    deliver(graph, 1, "2026-11-13T08:00:00Z")
    sync(graph, store)
    graph.expire_deltas()
    deliver(graph, 2, "2026-11-14T08:00:00Z")
    moment[0] = NOW + timedelta(days=2)
    assert sync(graph, store) == SyncResult(
        account="live", kind="catch_up", stored=("live/AAMk2=",), offline_since=NOW, gap=False
    )
    assert first_filter(graph) == "receivedDateTime ge 2026-11-13T08:00:00Z"
    assert fetched(graph) == ["/v1.0/me/messages/AAMk1=/$value", "/v1.0/me/messages/AAMk2=/$value"]
    assert store.sync_state("outlook", "live").bookmark == f"{DELTA}?$deltatoken=d2"


def test_a_catch_up_after_more_than_14_days_reads_14_days_and_says_so(
    graph: FakeGraph, store: Store, moment: list[datetime]
) -> None:
    sync(graph, store)
    graph.expire_deltas()
    moment[0] = NOW + timedelta(days=20)
    result = sync(graph, store)
    assert (result.kind, result.offline_since, result.gap) == ("catch_up", NOW, True)
    assert first_filter(graph) == "receivedDateTime ge 2026-11-19T09:00:00Z"


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (httpx.Response(503), OutlookUnavailable),
        (httpx.Response(401), OutlookAuthError),
    ],
    ids=["unavailable", "signed-out"],
)
def test_a_failed_round_keeps_the_bookmark_and_the_next_one_stores_the_mail(
    graph: FakeGraph, store: Store, moment: list[datetime], failure: object, error: type
) -> None:
    sync(graph, store)
    before = store.sync_state("outlook", "live")
    deliver(graph, 1)
    graph.failures.append(failure)
    if error is OutlookAuthError:
        graph.failures.append(httpx.Response(401))
    moment[0] = NOW + timedelta(minutes=1)
    with pytest.raises(error):
        sync(graph, store)
    assert store.sync_state("outlook", "live") == before
    moment[0] = NOW + timedelta(minutes=2)
    assert sync(graph, store).stored == ("live/AAMk1=",)


@pytest.mark.parametrize(
    "web_link",
    [
        "http://outlook.live.com/owa/?ItemID=AAMk1=",
        "https://evil.example.test/owa/?ItemID=AAMk1=",
        "https://outlook.live.com.evil.example.test/owa/",
        "https://outlook.live.com/owa/?ItemID=" + "a" * 2000,
        "https://outlook.live.com/owa/?ItemID=AAMk 1",
    ],
    ids=["http", "other-host", "lookalike-host", "too-long", "space"],
)
def test_an_odd_web_link_is_replaced_by_the_inbox_link(
    graph: FakeGraph, store: Store, web_link: str
) -> None:
    deliver(graph, 1)
    graph.messages["AAMk1="]["webLink"] = web_link
    assert sync(graph, store).stored == ("live/AAMk1=",)
    assert store.get("outlook", "live/AAMk1=").record.link == INBOX_LINK
    assert INBOX_LINK == "https://outlook.live.com/mail/0/inbox"


def test_a_message_whose_thread_cannot_be_stored_is_skipped(graph: FakeGraph, store: Store) -> None:
    deliver(graph, 1, conversation_id="conversation 1")
    deliver(graph, 2)
    assert sync(graph, store).stored == ("live/AAMk2=",)
