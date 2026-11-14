"""`mailroom outlook-login`: Microsoft sign-in in a browser, with PKCE; a read-only token kept."""

import webbrowser
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from typer.testing import CliRunner

from mailroom import clock, outlook_login
from mailroom.gmail_login import Callback, LoginError
from mailroom.outlook_login import (
    AUTH_URL,
    CLIENT_ID_LABEL,
    consent_url,
    exchange_code,
    login,
)
from tests.fakes import FakeGraph, FakeKeychain
from tests.integration.test_gmail_login import asker, visiting

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
SCOPE = "https://graph.microsoft.com/Mail.Read offline_access"
REDIRECT = "http://127.0.0.1:53682"
VERIFIER = "v" * 64
CHALLENGE = "w1TpKUdYE9hUAcNSeeSRFioHDxfUxuHho_JHAfZ_vDM"
CLIENT_ID = ("mailroom", "outlook.live.client-id")
REFRESH = ("mailroom", "outlook.live.refresh-token")
runner = CliRunner()


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def http_for(graph: FakeGraph, handler: Callable | None = None) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler or graph.handler))


class Browser:
    """Shows Microsoft's sign-in page (the fake), then follows its redirect in the background."""

    def __init__(self, graph: FakeGraph, *, approve: bool = True) -> None:
        self.graph, self.approve = graph, approve
        self.opened: list[str] = []

    def __call__(self, url: str) -> bool:
        self.opened.append(url)
        visiting(self.graph.consent(url, approve=self.approve))
        return True


def granted(graph: FakeGraph) -> str:
    """A code from the fake sign-in page for VERIFIER and REDIRECT."""
    url = consent_url("client-id-1", REDIRECT, "state-1", CHALLENGE)
    return httpx.URL(graph.consent(url)).params["code"]


def exchange(graph: FakeGraph, code: str, handler: Callable | None = None) -> str:
    return exchange_code(
        http_for(graph, handler),
        "live",
        client_id="client-id-1",
        code=code,
        verifier=VERIFIER,
        redirect_uri=REDIRECT,
    )


# The pieces


def test_the_sign_in_address_asks_personal_accounts_for_read_only_mail_with_pkce() -> None:
    assert AUTH_URL == "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
    assert CLIENT_ID_LABEL == "Microsoft app (client) ID"
    url = httpx.URL(consent_url("client-id-1", REDIRECT, "state-1", CHALLENGE))
    assert str(url.copy_with(query=None)) == AUTH_URL
    assert dict(url.params) == {
        "client_id": "client-id-1",
        "response_type": "code",
        "redirect_uri": REDIRECT,
        "response_mode": "query",
        "scope": SCOPE,
        "state": "state-1",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }


def test_the_code_is_exchanged_as_a_public_client_for_a_refresh_token() -> None:
    graph = FakeGraph()
    code = granted(graph)
    assert exchange(graph, code) == "refresh-token-from-code-1"
    (request,) = graph.requests
    assert dict(httpx.QueryParams(request.content.decode())) == {
        "client_id": "client-id-1",
        "scope": SCOPE,
        "code": code,
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
        "code_verifier": VERIFIER,
    }


@pytest.mark.parametrize(
    "scope",
    [
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/mail.read offline_access",
        "offline_access https://graph.microsoft.com/Mail.Read",
    ],
    ids=["mail-read", "lower-case", "with-offline-access"],
)
def test_a_read_only_grant_is_accepted(scope: str) -> None:
    graph = FakeGraph()
    graph.granted_scope = scope
    assert exchange(graph, granted(graph)) == "refresh-token-from-code-1"


@pytest.mark.parametrize(
    "scope",
    [
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/User.Read offline_access",
        "",
    ],
    ids=["read-write", "send-too", "no-mail-read", "empty"],
)
def test_any_other_grant_is_refused(scope: str) -> None:
    graph = FakeGraph()
    graph.granted_scope = scope
    with pytest.raises(LoginError) as caught:
        exchange(graph, granted(graph))
    assert str(caught.value) == "outlook login scope refused: live"


@pytest.mark.parametrize(
    ("answer", "detail"),
    [
        (httpx.Response(400, json={"error": "invalid_grant", "error_description": "x"}), "400"),
        (httpx.ConnectError("refused"), "network"),
        (httpx.Response(200, text="<html>"), "response"),
        (httpx.Response(200, json={"scope": SCOPE, "access_token": "a"}), "response"),
        (httpx.Response(200, json={"scope": 7, "refresh_token": "r"}), "response"),
    ],
    ids=["400", "network", "not-json", "no-refresh-token", "scope-not-text"],
)
def test_a_failed_exchange_says_only_why(answer: object, detail: str) -> None:
    graph = FakeGraph()

    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(answer, Exception):
            raise answer
        return answer

    with pytest.raises(LoginError) as caught:
        exchange(graph, "code-9", handler)
    assert str(caught.value) == f"outlook login failed: live ({detail})"
    assert caught.value.__suppress_context__


def test_the_callback_names_its_provider() -> None:
    graph = FakeGraph()
    with Callback("live", provider="outlook") as callback:
        url = consent_url("client-id-1", callback.redirect_uri, "state-1", CHALLENGE)
        thread, _ = visiting(graph.consent(url, approve=False))
        with pytest.raises(LoginError) as caught:
            callback.wait("state-1")
        thread.join()
    assert str(caught.value) == "outlook login cancelled: live"


# The whole login


def test_a_first_login_asks_for_the_client_id_and_keeps_the_token(
    fake_keychain: FakeKeychain,
) -> None:
    graph = FakeGraph()
    browser, ask = Browser(graph), asker("client-id-1")
    assert login("live", http_for(graph), ask=ask, open_browser=browser) == "owner@example.test"
    assert ask.labels == ["Microsoft app (client) ID"]
    assert len(browser.opened) == 1
    assert fake_keychain.writes == [CLIENT_ID, REFRESH, REFRESH]
    assert fake_keychain.secrets == {CLIENT_ID: "client-id-1", REFRESH: "refresh-token-3"}
    assert graph.requests[-1].url.path == "/v1.0/me/mailFolders/inbox"


def test_a_later_login_reuses_the_stored_client_id(fake_keychain: FakeKeychain) -> None:
    fake_keychain.secrets[CLIENT_ID] = "client-id-1"
    graph = FakeGraph()
    assert login("live", http_for(graph), ask=asker(), open_browser=Browser(graph)) == (
        "owner@example.test"
    )
    assert fake_keychain.writes == [REFRESH, REFRESH]


def test_a_new_client_replaces_the_stored_one(fake_keychain: FakeKeychain) -> None:
    fake_keychain.secrets[CLIENT_ID] = "client-id-0"
    graph = FakeGraph()
    ask = asker("client-id-1")
    login("live", http_for(graph), ask=ask, open_browser=Browser(graph), new_client=True)
    assert ask.labels == ["Microsoft app (client) ID"]
    assert fake_keychain.secrets[CLIENT_ID] == "client-id-1"


def test_a_cancelled_login_stores_nothing(fake_keychain: FakeKeychain) -> None:
    graph = FakeGraph()
    with pytest.raises(LoginError) as caught:
        login(
            "live",
            http_for(graph),
            ask=asker("client-id-1"),
            open_browser=Browser(graph, approve=False),
        )
    assert str(caught.value) == "outlook login cancelled: live"
    assert fake_keychain.writes == []
    assert graph.requests == []


def test_a_refused_grant_stores_nothing(fake_keychain: FakeKeychain) -> None:
    graph = FakeGraph()
    graph.granted_scope = "https://graph.microsoft.com/Mail.ReadWrite"
    with pytest.raises(LoginError):
        login("live", http_for(graph), ask=asker("client-id-1"), open_browser=Browser(graph))
    assert fake_keychain.writes == []


def test_an_invalid_account_is_refused_before_anything(fake_keychain: FakeKeychain) -> None:
    graph = FakeGraph()
    browser, ask = Browser(graph), asker()
    with pytest.raises(ValueError) as caught:
        login("Live", http_for(graph), ask=ask, open_browser=browser)
    assert str(caught.value) == "invalid account name"
    assert (ask.labels, browser.opened, fake_keychain.calls) == ([], [], [])


# The command


def command(monkeypatch: pytest.MonkeyPatch, graph: FakeGraph, browser: Browser, typed: str):
    monkeypatch.setattr(outlook_login, "new_http", lambda: http_for(graph))
    monkeypatch.setattr(webbrowser, "open", browser)
    from mailroom.cli import app

    return runner.invoke(app, ["outlook-login", "live"], input=typed)


def test_the_command_signs_in_and_names_the_account(
    monkeypatch: pytest.MonkeyPatch, fake_keychain: FakeKeychain
) -> None:
    graph = FakeGraph()
    browser = Browser(graph)
    result = command(monkeypatch, graph, browser, "client-id-1\n")
    assert result.exit_code == 0
    assert "Opening Microsoft sign-in. If no browser opens, visit:" in result.output
    assert browser.opened[0] in result.output
    assert "refresh-token" not in result.output
    assert result.output.splitlines()[-1] == "Signed in: live (owner@example.test)"


def test_the_command_reports_a_failure_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, fake_keychain: FakeKeychain
) -> None:
    fake_keychain.secrets[CLIENT_ID] = "client-id-1"
    graph = FakeGraph()
    result = command(monkeypatch, graph, Browser(graph, approve=False), "")
    assert result.exit_code == 1
    assert result.output.splitlines()[-1] == "outlook login cancelled: live"
    assert fake_keychain.writes == []
