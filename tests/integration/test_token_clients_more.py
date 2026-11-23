"""Token session edges the given tests leave open: dot segments, a missing secret, headers."""

import httpx
import pytest

from mailroom import token_http
from mailroom.gmail import GmailAuthError
from mailroom.outlook import OutlookUnavailable
from tests.fakes import FakeGmail, FakeGraph, FakeKeychain
from tests.integration.test_gmail import client_for as gmail_client
from tests.integration.test_gmail import gmail as gmail
from tests.integration.test_outlook import client as outlook_client
from tests.integration.test_outlook import graph as graph
from tests.integration.test_outlook import moment as moment

assert gmail and graph and moment

API = "https://api.example.test/v2/users/me"


def test_an_outlook_link_that_climbs_out_of_the_api_is_refused_unsent(graph: FakeGraph) -> None:
    link = "https://graph.microsoft.com/v1.0/me/mailFolders/../../x/messages/delta"
    with pytest.raises(OutlookUnavailable) as caught:
        outlook_client(graph).next_delta(link)
    assert str(caught.value) == "outlook unavailable: live (response)"
    assert graph.requests == []


def test_a_gmail_refresh_with_a_missing_secret_posts_nothing_and_recovers(
    gmail: FakeGmail, fake_keychain: FakeKeychain
) -> None:
    key = ("mailroom", "gmail.personal.client-secret")
    secret = fake_keychain.secrets.pop(key)
    client = gmail_client(gmail)
    with pytest.raises(GmailAuthError):
        client.profile()
    assert gmail.requests == []
    fake_keychain.secrets[key] = secret
    assert client.profile().email_address == "owner@example.test"
    assert [request.method for request in gmail.requests] == ["POST", "GET"]


@pytest.mark.parametrize("name", ["Authorization", "authorization"])
def test_a_client_header_never_replaces_the_bearer_token(name: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "access-1", "expires_in": 3600})
        return httpx.Response(200, json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    session = token_http.TokenSession(
        http,
        api_url=API,
        token_url="https://login.example.test/token",
        auth_codes=frozenset(),
        refresh=lambda: session.grant({"a": "b"}),
        auth_error=lambda: RuntimeError("auth"),
        unavailable=lambda detail: RuntimeError(str(detail)),
    )
    session.get(f"{API}/x", headers={name: "Bearer stolen", "Prefer": "p"})
    api = seen[-1]
    assert api.headers.get_list("authorization") == ["Bearer access-1"]
    assert api.headers["prefer"] == "p"


@pytest.mark.parametrize("url", ["https://api.example.test:bad/v2/users/me", "https://[::1/x"])
def test_a_malformed_address_is_refused_unsent(url: str) -> None:
    seen: list[httpx.Request] = []
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200))
    )
    session = token_http.TokenSession(
        http,
        api_url=API,
        token_url="https://login.example.test/token",
        auth_codes=frozenset(),
        refresh=lambda: pytest.fail("refreshed"),
        auth_error=lambda: RuntimeError("auth"),
        unavailable=lambda detail: RuntimeError(str(detail)),
    )
    with pytest.raises(RuntimeError, match="^response$"):
        session.get(url)
    assert seen == []
