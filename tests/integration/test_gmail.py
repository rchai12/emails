import base64
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.gmail import (
    BookmarkExpired,
    GmailAuthError,
    GmailClient,
    GmailUnavailable,
    History,
    MessageRef,
    Profile,
    RawMessage,
    open_gmail,
)
from tests.fakes import FakeGmail, FakeKeychain

RAW = b"From: Billing <billing@example.test>\r\nSubject: Bill\r\n\r\nPay by Friday.\r\n"
SECRETS = {
    ("mailroom", "gmail.personal.client-id"): "client-id-1",
    ("mailroom", "gmail.personal.client-secret"): "client-secret-1",
    ("mailroom", "gmail.personal.refresh-token"): "refresh-token-1",
}
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


@pytest.fixture
def gmail(fake_keychain: FakeKeychain, monkeypatch: pytest.MonkeyPatch) -> FakeGmail:
    fake_keychain.secrets.update(SECRETS)
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return FakeGmail()


def client_for(fake: FakeGmail) -> GmailClient:
    return GmailClient("personal", httpx.Client(transport=httpx.MockTransport(fake.handler)))


def calls(fake: FakeGmail) -> list[tuple[str, str]]:
    return [(request.method, request.url.path) for request in fake.requests]


def failing(response: httpx.Response | Exception, fake: FakeGmail) -> FakeGmail:
    fake.failures.append(response)
    return fake


# Account names and sign-in


@pytest.mark.parametrize("account", ["Personal", "a.b", "x" * 33], ids=["upper", "dot", "long"])
def test_an_invalid_account_is_refused(account: str) -> None:
    fake = FakeGmail()
    with pytest.raises(ValueError) as caught:
        GmailClient(account, httpx.Client(transport=httpx.MockTransport(fake.handler)))
    assert str(caught.value) == "invalid account name"
    assert fake.requests == []


def test_the_first_call_gets_a_token_from_the_keychain_secrets(
    gmail: FakeGmail, fake_keychain: FakeKeychain
) -> None:
    assert client_for(gmail).profile() == Profile(
        email_address="owner@example.test", history_id="1000"
    )
    assert calls(gmail) == [("POST", "/token"), ("GET", "/gmail/v1/users/me/profile")]
    token_request, api_request = gmail.requests
    assert str(token_request.url) == "https://oauth2.googleapis.com/token"
    assert dict(httpx.QueryParams(token_request.content.decode())) == {
        "client_id": "client-id-1",
        "client_secret": "client-secret-1",
        "refresh_token": "refresh-token-1",
        "grant_type": "refresh_token",
    }
    assert api_request.headers["authorization"] == "Bearer access-1"
    assert fake_keychain.calls == [
        ("mailroom", "gmail.personal.client-id"),
        ("mailroom", "gmail.personal.client-secret"),
        ("mailroom", "gmail.personal.refresh-token"),
    ]


def test_the_token_is_reused_until_a_minute_before_it_expires(
    gmail: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> None:
    moment = [NOW]
    monkeypatch.setattr(clock, "now", lambda: moment[0])
    client = client_for(gmail)
    client.profile()
    moment[0] = NOW + timedelta(seconds=3538)
    client.profile()
    moment[0] = NOW + timedelta(seconds=3539)
    client.profile()
    assert gmail.issued == ["access-1", "access-2"]
    assert [r.headers["authorization"] for r in gmail.requests if r.method == "GET"] == [
        "Bearer access-1",
        "Bearer access-1",
        "Bearer access-2",
    ]
    assert calls(gmail) == [
        ("POST", "/token"),
        ("GET", "/gmail/v1/users/me/profile"),
        ("GET", "/gmail/v1/users/me/profile"),
        ("POST", "/token"),
        ("GET", "/gmail/v1/users/me/profile"),
    ]


@pytest.mark.parametrize("case", ["revoked", "missing"])
def test_a_refresh_token_that_does_not_work_needs_sign_in(
    case: str, gmail: FakeGmail, fake_keychain: FakeKeychain
) -> None:
    if case == "revoked":
        gmail.refresh_token = "refresh-token-2"
    else:
        del fake_keychain.secrets[("mailroom", "gmail.personal.refresh-token")]
    with pytest.raises(GmailAuthError) as caught:
        client_for(gmail).profile()
    assert str(caught.value) == "gmail sign-in needed: personal"
    assert caught.value.__suppress_context__ is True
    assert ("GET", "/gmail/v1/users/me/profile") not in calls(gmail)


def test_a_rejected_access_token_is_refreshed_once(gmail: FakeGmail) -> None:
    client = client_for(gmail)
    client.profile()
    gmail.invalidate_tokens()
    assert client.profile().history_id == "1000"
    assert calls(gmail) == [
        ("POST", "/token"),
        ("GET", "/gmail/v1/users/me/profile"),
        ("GET", "/gmail/v1/users/me/profile"),
        ("POST", "/token"),
        ("GET", "/gmail/v1/users/me/profile"),
    ]
    assert gmail.requests[-1].headers["authorization"] == "Bearer access-2"


def test_a_second_rejection_needs_sign_in(gmail: FakeGmail) -> None:
    unauthorized = httpx.Response(401, json={"error": {"code": 401, "status": "UNAUTHENTICATED"}})
    gmail.failures.extend([unauthorized, unauthorized])
    with pytest.raises(GmailAuthError) as caught:
        client_for(gmail).profile()
    assert str(caught.value) == "gmail sign-in needed: personal"
    assert calls(gmail) == [
        ("POST", "/token"),
        ("GET", "/gmail/v1/users/me/profile"),
        ("POST", "/token"),
        ("GET", "/gmail/v1/users/me/profile"),
    ]


# History


def test_history_follows_pages_and_keeps_messages_added_to_the_inbox(gmail: FakeGmail) -> None:
    gmail.add_message("m1", RAW)
    gmail.add_message("m2", RAW, labels=("SENT",))
    gmail.add_message("m3", RAW, thread_id="t1")
    gmail.add_labels("m2", "INBOX")
    gmail.add_labels("m1", "STARRED")
    gmail.add_message("m4", RAW)
    gmail.add_labels("m3", "INBOX")
    gmail.page_size = 2
    assert client_for(gmail).history("1000") == History(
        added=(
            MessageRef(id="m1", thread_id="m1"),
            MessageRef(id="m3", thread_id="t1"),
            MessageRef(id="m2", thread_id="m2"),
            MessageRef(id="m4", thread_id="m4"),
        ),
        history_id="1007",
    )
    pages = [request for request in gmail.requests if request.url.path.endswith("/history")]
    assert len(pages) == 3
    first = pages[0].url.params
    assert first.get("startHistoryId") == "1000"
    assert first.get("labelId") == "INBOX"
    assert first.get_list("historyTypes") == ["messageAdded", "labelAdded"]
    assert first.get("maxResults") == "500"
    assert "pageToken" not in first
    assert [page.url.params.get("pageToken") for page in pages[1:]] == ["2", "4"]


def test_no_new_history_returns_the_same_bookmark(gmail: FakeGmail) -> None:
    assert client_for(gmail).history("1000") == History(added=(), history_id="1000")


def test_an_expired_bookmark_is_reported(gmail: FakeGmail) -> None:
    gmail.oldest_history_id = 500
    with pytest.raises(BookmarkExpired) as caught:
        client_for(gmail).history("499")
    assert str(caught.value) == "gmail history expired: personal"


# Listing and fetching


def test_list_inbox_returns_inbox_mail_after_a_moment_newest_first(gmail: FakeGmail) -> None:
    gmail.add_message("old", RAW, internal_ms=1_794_038_400_000)
    gmail.add_message("a", RAW, internal_ms=1_794_218_400_000)
    gmail.add_message("b", RAW, thread_id="t9", internal_ms=1_794_310_200_000)
    gmail.add_message("junk", RAW, labels=("SPAM",), internal_ms=1_794_310_200_001)
    gmail.add_message("sent", RAW, labels=("SENT",), internal_ms=1_794_310_200_002)
    gmail.page_size = 1
    after = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    assert client_for(gmail).list_inbox(after) == (
        MessageRef(id="b", thread_id="t9"),
        MessageRef(id="a", thread_id="a"),
    )
    pages = [request for request in gmail.requests if request.url.path.endswith("/messages")]
    assert len(pages) == 2
    assert pages[0].url.params.get("q") == "after:1794128400"
    assert pages[0].url.params.get_list("labelIds") == ["INBOX"]
    assert pages[0].url.params.get("maxResults") == "500"


def test_list_inbox_with_nothing_new_is_empty(gmail: FakeGmail) -> None:
    assert client_for(gmail).list_inbox(NOW) == ()


def test_fetch_returns_the_raw_message(gmail: FakeGmail) -> None:
    gmail.add_message("m1", RAW, thread_id="t1", internal_ms=1_794_128_400_123)
    assert client_for(gmail).fetch("m1") == RawMessage(
        id="m1",
        thread_id="t1",
        label_ids=("INBOX", "UNREAD"),
        internal_date=datetime(2026, 11, 8, 9, 0, 0, 123_000, tzinfo=UTC),
        raw=RAW,
    )
    assert gmail.requests[-1].url.path == "/gmail/v1/users/me/messages/m1"
    assert dict(gmail.requests[-1].url.params) == {"format": "raw"}


def test_fetch_accepts_padded_base64(gmail: FakeGmail) -> None:
    padded = base64.urlsafe_b64encode(RAW).decode()
    assert padded.endswith("=")
    body = {
        "id": "m1",
        "threadId": "t1",
        "labelIds": ["INBOX"],
        "internalDate": "1794128400000",
        "raw": padded,
    }
    client = client_for(gmail)
    client.profile()
    gmail.failures.append(httpx.Response(200, json=body))
    assert client.fetch("m1").raw == RAW


@pytest.mark.parametrize("message_id", ["", "../profile", "m1/x", "m 1"])
def test_an_unsafe_message_id_is_refused_before_any_request(
    message_id: str, gmail: FakeGmail
) -> None:
    with pytest.raises(ValueError) as caught:
        client_for(gmail).fetch(message_id)
    assert str(caught.value) == "invalid message id"
    assert gmail.requests == []


# Failures


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx.Response(500, text="secret body"), "gmail unavailable: personal (500)"),
        (httpx.Response(503), "gmail unavailable: personal (503)"),
        (httpx.Response(429), "gmail unavailable: personal (429)"),
        (httpx.Response(403, json={"error": {"code": 403}}), "gmail unavailable: personal (403)"),
        (httpx.ConnectError("refused"), "gmail unavailable: personal (network)"),
        (httpx.ReadTimeout("slow"), "gmail unavailable: personal (network)"),
        (httpx.Response(200, text="not json"), "gmail unavailable: personal (response)"),
        (httpx.Response(200, json={"emailAddress": "x"}), "gmail unavailable: personal (response)"),
    ],
    ids=["500", "503", "429", "403", "connect", "timeout", "not-json", "missing-field"],
)
def test_a_failing_service_is_unavailable(
    failure: httpx.Response | Exception, message: str, gmail: FakeGmail
) -> None:
    with pytest.raises(GmailUnavailable) as caught:
        client_for(failing(failure, gmail)).profile()
    assert str(caught.value) == message
    assert caught.value.__suppress_context__ is True


def test_only_read_calls_reach_google(gmail: FakeGmail) -> None:
    gmail.add_message("m1", RAW)
    client = client_for(gmail)
    client.profile()
    client.history("1000")
    client.list_inbox(NOW - timedelta(days=3))
    client.fetch("m1")
    assert {(request.method, request.url.host) for request in gmail.requests} == {
        ("POST", "oauth2.googleapis.com"),
        ("GET", "gmail.googleapis.com"),
    }
    assert calls(gmail) == [
        ("POST", "/token"),
        ("GET", "/gmail/v1/users/me/profile"),
        ("GET", "/gmail/v1/users/me/history"),
        ("GET", "/gmail/v1/users/me/messages"),
        ("GET", "/gmail/v1/users/me/messages/m1"),
    ]


def test_open_gmail_ignores_proxy_settings_and_times_out() -> None:
    client = open_gmail("personal")
    assert client.account == "personal"
    assert client.http.timeout == httpx.Timeout(30.0)
    assert client.http.trust_env is False
    assert client.http.follow_redirects is False
