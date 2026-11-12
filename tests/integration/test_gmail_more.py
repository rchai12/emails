from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock
from mailroom.gmail import GmailClient, GmailUnavailable
from tests.fakes import FakeGmail, FakeKeychain

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


def _token_client(fake: FakeGmail, response: httpx.Response) -> GmailClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://oauth2.googleapis.com/token":
            return response
        return fake.handler(request)

    return GmailClient("personal", httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(500, text="secret body"), "gmail unavailable: personal (500)"),
        (httpx.Response(400, text="secret body"), "gmail unavailable: personal (400)"),
        (
            httpx.Response(200, json={"expires_in": 3600, "token_type": "Bearer"}),
            "gmail unavailable: personal (response)",
        ),
        (
            httpx.Response(200, json={"access_token": "access-x", "expires_in": "3600"}),
            "gmail unavailable: personal (response)",
        ),
    ],
    ids=["status", "not-grant", "no-token", "expires"],
)
def test_a_bad_token_response_is_unavailable(
    response: httpx.Response, message: str, gmail: FakeGmail
) -> None:
    with pytest.raises(GmailUnavailable) as caught:
        _token_client(gmail, response).profile()
    assert str(caught.value) == message
    assert "secret" not in str(caught.value)
    assert "access-x" not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    assert gmail.requests == []


def test_fetch_rejects_raw_that_is_not_base64url(gmail: FakeGmail) -> None:
    client = client_for(gmail)
    client.profile()
    gmail.failures.append(
        httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "labelIds": ["INBOX"],
                "internalDate": "1794128400000",
                "raw": "abc*",
            },
        )
    )
    with pytest.raises(GmailUnavailable) as caught:
        client.fetch("m1")
    assert str(caught.value) == "gmail unavailable: personal (response)"
    assert "abc*" not in str(caught.value)


def test_a_history_page_without_history_id_is_rejected(gmail: FakeGmail) -> None:
    client = client_for(gmail)
    client.profile()
    gmail.failures.append(httpx.Response(200, json={"history": []}))
    with pytest.raises(GmailUnavailable) as caught:
        client.history("1000")
    assert str(caught.value) == "gmail unavailable: personal (response)"


def test_fetch_rejects_an_internal_date_that_is_not_an_integer(gmail: FakeGmail) -> None:
    client = client_for(gmail)
    client.profile()
    gmail.failures.append(
        httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "labelIds": ["INBOX"],
                "internalDate": "noon",
                "raw": "YQ",
            },
        )
    )
    with pytest.raises(GmailUnavailable) as caught:
        client.fetch("m1")
    assert str(caught.value) == "gmail unavailable: personal (response)"
    assert "noon" not in str(caught.value)
