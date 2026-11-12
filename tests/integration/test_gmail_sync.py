from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.gmail import GmailAuthError, GmailClient, GmailError, GmailUnavailable, MessageGone
from mailroom.gmail_sync import (
    CATCH_UP_LIMIT,
    CATCH_UP_OVERLAP,
    FIRST_RUN,
    LINK,
    SyncResult,
    sync_gmail,
)
from mailroom.mime import parse_message
from mailroom.record import Envelope
from mailroom.store import Store, SyncState, open_store
from tests.fakes import FakeGmail, FakeKeychain

SECRETS = {
    ("mailroom", "gmail.personal.client-id"): "client-id-1",
    ("mailroom", "gmail.personal.client-secret"): "client-secret-1",
    ("mailroom", "gmail.personal.refresh-token"): "refresh-token-1",
}
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
MESSAGES = "/gmail/v1/users/me/messages"


def raw(number: int) -> bytes:
    return (
        f"From: Sender {number} <sender{number}@example.test>\r\n"
        f"Subject: Note {number}\r\n"
        "Date: Tue, 10 Nov 2026 07:59:00 +0000\r\n"
        f"\r\nBody {number}.\r\n"
    ).encode()


def ms(moment: str) -> int:
    return round(datetime.fromisoformat(moment).timestamp() * 1000)


def deliver(fake: FakeGmail, number: int, moment: str = "2026-11-10T08:00:00+00:00", **kw) -> None:
    fake.add_message(
        f"m{number}", raw(number), thread_id=f"t{number}", internal_ms=ms(moment), **kw
    )


@pytest.fixture
def gmail(fake_keychain: FakeKeychain, monkeypatch: pytest.MonkeyPatch) -> FakeGmail:
    fake_keychain.secrets.update(SECRETS)
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return FakeGmail()


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def client_for(fake: FakeGmail, handler=None) -> GmailClient:
    transport = httpx.MockTransport(handler or fake.handler)
    return GmailClient("personal", httpx.Client(transport=transport))


def sync(fake: FakeGmail, store: Store) -> SyncResult:
    return sync_gmail(client_for(fake), store)


def bookmarked(store: Store, bookmark: str, synced_at: datetime = NOW - timedelta(minutes=2)):
    state = SyncState(bookmark=bookmark, synced_at=synced_at)
    store.save_sync_state("gmail", "personal", state)
    return state


def api_calls(fake: FakeGmail) -> list[str]:
    return [request.url.path for request in fake.requests if request.method == "GET"]


def fetched(fake: FakeGmail) -> list[str]:
    prefix = MESSAGES + "/"
    return [path.removeprefix(prefix) for path in api_calls(fake) if path.startswith(prefix)]


def params(fake: FakeGmail, path: str) -> list[dict[str, str]]:
    return [dict(request.url.params) for request in fake.requests if request.url.path == path]


def later(monkeypatch: pytest.MonkeyPatch, minutes: int) -> datetime:
    moment = NOW + timedelta(minutes=minutes)
    monkeypatch.setattr(clock, "now", lambda: moment)
    return moment


def test_the_names() -> None:
    assert FIRST_RUN == timedelta(days=3)
    assert CATCH_UP_LIMIT == timedelta(days=14)
    assert CATCH_UP_OVERLAP == timedelta(hours=1)
    assert LINK == "https://mail.google.com/mail/?authuser={address}#all/{message_id}"


def test_fetching_a_deleted_message_raises_message_gone(gmail: FakeGmail) -> None:
    with pytest.raises(MessageGone) as caught:
        client_for(gmail).fetch("m9")
    assert isinstance(caught.value, GmailError)
    assert str(caught.value) == "gmail message gone: personal"
    assert caught.value.__suppress_context__


# The first sync


def test_a_first_sync_stores_the_last_three_days_of_inbox_mail(
    gmail: FakeGmail, store: Store
) -> None:
    deliver(gmail, 1, "2026-11-08T08:59:59+00:00")
    deliver(gmail, 2, "2026-11-08T09:00:01+00:00")
    deliver(gmail, 3, labels=("SENT",))
    deliver(gmail, 4)
    assert sync(gmail, store) == SyncResult(
        account="personal", kind="first", stored=("m4", "m2"), offline_since=None, gap=False
    )
    assert store.sync_state("gmail", "personal") == SyncState(bookmark="1004", synced_at=NOW)
    assert params(gmail, MESSAGES)[0]["q"] == "after:1794128400"
    assert fetched(gmail) == ["m4", "m2"]
    assert store.get("gmail", "m1") is None


def test_a_first_sync_reads_the_bookmark_before_listing(gmail: FakeGmail, store: Store) -> None:
    deliver(gmail, 1)
    sync(gmail, store)
    assert api_calls(gmail) == ["/gmail/v1/users/me/profile", MESSAGES, MESSAGES + "/m1"]


def test_the_stored_record_comes_from_gmail_and_the_parser(gmail: FakeGmail, store: Store) -> None:
    gmail.email_address = "owner+mail@example.test"
    deliver(gmail, 1, "2026-11-10T08:00:00.123+00:00")
    sync(gmail, store)
    envelope = Envelope(
        provider="gmail",
        message_id="m1",
        thread_id="t1",
        received_at=datetime(2026, 11, 10, 8, 0, 0, 123_000, tzinfo=UTC),
        link="https://mail.google.com/mail/?authuser=owner%2Bmail@example.test#all/m1",
    )
    assert store.get("gmail", "m1").record == parse_message(raw(1), envelope)


# Later syncs


def test_a_later_sync_stores_new_inbox_mail_from_history(
    gmail: FakeGmail, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    deliver(gmail, 1)
    sync(gmail, store)
    deliver(gmail, 2)
    deliver(gmail, 3, labels=("SENT",))
    moment = later(monkeypatch, 2)
    assert sync(gmail, store) == SyncResult(
        account="personal", kind="history", stored=("m2",), offline_since=None, gap=False
    )
    assert store.sync_state("gmail", "personal") == SyncState(bookmark="1003", synced_at=moment)
    assert params(gmail, "/gmail/v1/users/me/history")[0]["startHistoryId"] == "1001"
    assert fetched(gmail) == ["m1", "m2"]


def test_a_sync_with_nothing_new_only_moves_the_time(
    gmail: FakeGmail, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    deliver(gmail, 1)
    sync(gmail, store)
    moment = later(monkeypatch, 1)
    assert sync(gmail, store).stored == ()
    assert store.sync_state("gmail", "personal") == SyncState(bookmark="1001", synced_at=moment)
    assert fetched(gmail) == ["m1"]


def test_mail_moved_out_of_spam_is_stored(gmail: FakeGmail, store: Store) -> None:
    bookmarked(store, "1000")
    deliver(gmail, 1, labels=("SPAM",))
    gmail.messages["m1"]["labelIds"] = []
    gmail.add_labels("m1", "INBOX")
    assert sync(gmail, store).stored == ("m1",)
    assert store.sync_state("gmail", "personal").bookmark == "1002"


def test_a_stored_message_is_not_fetched_again(gmail: FakeGmail, store: Store) -> None:
    deliver(gmail, 1)
    sync(gmail, store)
    gmail.add_labels("m1", "INBOX")
    assert sync(gmail, store).stored == ()
    assert fetched(gmail) == ["m1"]
    assert store.sync_state("gmail", "personal").bookmark == "1002"


# What is skipped


@pytest.mark.parametrize(
    "labels", [["UNREAD"], ["SPAM"], ["INBOX", "TRASH"]], ids=["archived", "spam", "trash"]
)
def test_mail_that_left_the_inbox_before_fetch_is_skipped(
    gmail: FakeGmail, store: Store, labels: list[str]
) -> None:
    bookmarked(store, "1000")
    deliver(gmail, 1)
    deliver(gmail, 2)
    gmail.messages["m1"]["labelIds"] = labels
    assert sync(gmail, store).stored == ("m2",)
    assert store.get("gmail", "m1") is None
    assert store.sync_state("gmail", "personal").bookmark == "1002"


def test_a_message_deleted_before_fetch_is_skipped(gmail: FakeGmail, store: Store) -> None:
    bookmarked(store, "1000")
    deliver(gmail, 1)
    deliver(gmail, 2)
    del gmail.messages["m1"]
    assert sync(gmail, store).stored == ("m2",)
    assert fetched(gmail) == ["m1", "m2"]
    assert store.sync_state("gmail", "personal").bookmark == "1002"


@pytest.mark.parametrize(
    ("message_id", "thread_id", "fetches"),
    [("m 1", "t1", ["m2"]), ("m1", "t 1", ["m1", "m2"])],
    ids=["message-id", "thread-id"],
)
def test_a_message_with_an_unusable_id_is_skipped(
    gmail: FakeGmail, store: Store, message_id: str, thread_id: str, fetches: list[str]
) -> None:
    bookmarked(store, "1000")
    gmail.add_message(message_id, raw(1), thread_id=thread_id, internal_ms=ms(NOW.isoformat()))
    deliver(gmail, 2)
    assert sync(gmail, store).stored == ("m2",)
    assert fetched(gmail) == fetches
    assert store.get("gmail", message_id) is None
    assert store.sync_state("gmail", "personal").bookmark == "1002"


# Catching up


@pytest.mark.parametrize(
    ("offline", "after", "gap"),
    [
        (timedelta(days=2), "after:1794211200", False),
        (timedelta(days=14), "after:1793178000", False),
        (timedelta(days=20), "after:1793178000", True),
    ],
    ids=["2-days", "14-days", "20-days"],
)
def test_an_expired_bookmark_catches_up(
    gmail: FakeGmail, store: Store, offline: timedelta, after: str, gap: bool
) -> None:
    state = bookmarked(store, "900", NOW - offline)
    gmail.oldest_history_id = 950
    deliver(gmail, 1)
    deliver(gmail, 2, "2026-11-10T09:00:00+00:00")
    store.add(parse_message(raw(2), store_envelope("m2")))
    assert sync(gmail, store) == SyncResult(
        account="personal",
        kind="catch_up",
        stored=("m1",),
        offline_since=state.synced_at,
        gap=gap,
    )
    assert params(gmail, MESSAGES)[0]["q"] == after
    assert fetched(gmail) == ["m1"]
    assert store.sync_state("gmail", "personal") == SyncState(bookmark="1002", synced_at=NOW)


def store_envelope(message_id: str) -> Envelope:
    return Envelope(
        provider="gmail",
        message_id=message_id,
        thread_id="t0",
        received_at=NOW,
        link=f"https://mail.google.com/mail/?authuser=owner@example.test#all/{message_id}",
    )


# Failures


def test_a_failed_sync_keeps_the_bookmark_and_what_it_stored(
    gmail: FakeGmail, store: Store
) -> None:
    deliver(gmail, 1)
    deliver(gmail, 2, "2026-11-10T09:00:00+00:00")

    def failing(request: httpx.Request) -> httpx.Response:
        if request.url.path == MESSAGES + "/m1":
            return httpx.Response(503)
        return gmail.handler(request)

    with pytest.raises(GmailUnavailable) as caught:
        sync_gmail(client_for(gmail, failing), store)
    assert str(caught.value) == "gmail unavailable: personal (503)"
    assert store.get("gmail", "m2") is not None
    assert store.sync_state("gmail", "personal") is None
    assert sync(gmail, store).stored == ("m1",)
    assert fetched(gmail) == ["m2", "m1"]


@pytest.mark.parametrize("failure", ["sign-in", "unavailable"])
def test_an_error_stops_the_sync_and_keeps_the_bookmark(
    gmail: FakeGmail, store: Store, fake_keychain: FakeKeychain, failure: str
) -> None:
    state = bookmarked(store, "1000")
    deliver(gmail, 1)
    if failure == "sign-in":
        del fake_keychain.secrets[("mailroom", "gmail.personal.refresh-token")]
        expected: type[GmailError] = GmailAuthError
    else:
        gmail.failures.append(httpx.Response(500))
        expected = GmailUnavailable
    with pytest.raises(expected):
        sync(gmail, store)
    assert store.sync_state("gmail", "personal") == state
    assert store.get("gmail", "m1") is None
