import re
import socket
import threading
import time
import webbrowser
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock, gmail_login
from mailroom.gmail_login import (
    AUTH_URL,
    CALLBACK_TIMEOUT,
    CANCELLED_PAGE,
    DONE_PAGE,
    REQUEST_TIMEOUT_SECONDS,
    Callback,
    LoginError,
    code_challenge,
    consent_url,
    exchange_code,
    login,
    new_verifier,
)
from tests.fakes import FakeGmail, FakeKeychain
from tests.support import fixed_times, runner

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
VERIFIER = "dBjftJeZ4CVP-mJ92K9qpvP9mVKMmXl8CUjrKXH7aX0"
REDIRECT = "http://127.0.0.1:8123"
CLIENT_KEYS = {
    ("mailroom", "gmail.personal.client-id"): "client-id-1",
    ("mailroom", "gmail.personal.client-secret"): "client-secret-1",
}
WRITES = [
    ("mailroom", "gmail.personal.client-id"),
    ("mailroom", "gmail.personal.client-secret"),
    ("mailroom", "gmail.personal.refresh-token"),
]


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def visiting(*urls: str) -> tuple[threading.Thread, list[httpx.Response]]:
    """Open each address in turn from another thread, as a browser would."""
    responses: list[httpx.Response] = []

    def run() -> None:
        for url in urls:
            responses.append(httpx.get(url, trust_env=False, timeout=5))

    thread = threading.Thread(target=run)
    thread.start()
    return thread, responses


def http_for(fake: FakeGmail, handler: Callable | None = None) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler or fake.handler))


def granted(fake: FakeGmail) -> str:
    """A code from the fake consent page for VERIFIER and REDIRECT."""
    params = {
        "client_id": "client-id-1",
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "code_challenge": "8eK6BmXWareWe8koBOq1MXDWFug71WT6lkUjGKdnLI8",
        "code_challenge_method": "S256",
        "state": "state-1",
    }
    return httpx.URL(fake.consent(str(httpx.URL(AUTH_URL, params=params)))).params["code"]


def exchange(fake: FakeGmail, code: str, handler: Callable | None = None) -> str:
    return exchange_code(
        http_for(fake, handler),
        "personal",
        client_id="client-id-1",
        client_secret="client-secret-1",
        code=code,
        verifier=VERIFIER,
        redirect_uri=REDIRECT,
    )


class Browser:
    """Shows Google's consent page (the fake), then follows its redirect in the background."""

    def __init__(self, fake: FakeGmail, *, approve: bool = True) -> None:
        self.fake, self.approve = fake, approve
        self.opened: list[str] = []

    def __call__(self, url: str) -> bool:
        self.opened.append(url)
        visiting(self.fake.consent(url, approve=self.approve))
        return True


def asker(*answers: str) -> Callable[[str], str]:
    remaining = list(answers)

    def ask(label: str) -> str:
        ask.labels.append(label)
        return remaining.pop(0)

    ask.labels = []
    return ask


def test_the_names() -> None:
    assert AUTH_URL == "https://accounts.google.com/o/oauth2/v2/auth"
    assert CALLBACK_TIMEOUT == timedelta(minutes=5)
    assert REQUEST_TIMEOUT_SECONDS == 5.0
    assert DONE_PAGE == "Signed in to mailroom. You can close this tab."
    assert CANCELLED_PAGE == "Sign-in cancelled. You can close this tab."


# PKCE and the consent address


def test_a_verifier_is_random_and_within_the_pkce_rules() -> None:
    first, second = new_verifier(), new_verifier()
    assert re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", first)
    assert first != second


def test_the_challenge_is_the_unpadded_base64url_sha256() -> None:
    assert code_challenge(VERIFIER) == "8eK6BmXWareWe8koBOq1MXDWFug71WT6lkUjGKdnLI8"


def test_the_consent_address_asks_for_read_only_access_with_pkce() -> None:
    url = httpx.URL(consent_url("client-id-1", REDIRECT, "state-1", "challenge-1"))
    assert (url.scheme, url.host, url.path) == ("https", "accounts.google.com", "/o/oauth2/v2/auth")
    assert sorted(url.params.multi_items()) == [
        ("client_id", "client-id-1"),
        ("code_challenge", "challenge-1"),
        ("code_challenge_method", "S256"),
        ("redirect_uri", REDIRECT),
        ("response_type", "code"),
        ("scope", SCOPE),
        ("state", "state-1"),
    ]


# The local callback


def test_the_callback_listens_on_loopback_only_until_closed() -> None:
    with Callback("personal") as callback:
        assert re.fullmatch(r"http://127\.0\.0\.1:\d+", callback.redirect_uri)
        port = httpx.URL(callback.redirect_uri).port
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


def test_the_callback_returns_the_code_quietly(capsys: pytest.CaptureFixture[str]) -> None:
    with Callback("personal") as callback:
        thread, responses = visiting(f"{callback.redirect_uri}/?state=state-1&code=code-1&scope=x")
        assert callback.wait("state-1") == "code-1"
    thread.join()
    assert responses[0].status_code == 200
    assert responses[0].text == DONE_PAGE
    assert responses[0].headers["content-type"].startswith("text/plain")
    assert capsys.readouterr() == ("", "")


def test_requests_that_are_not_the_callback_are_refused_and_ignored(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with Callback("personal") as callback:
        base = callback.redirect_uri
        thread, responses = visiting(
            f"{base}/favicon.ico",
            f"{base}/?state=other&code=code-9",
            f"{base}/?code=code-9",
            f"{base}/?state=state-1&code=",
            f"{base}/?state=state-1&code=code-9&code=code-8",
            f"{base}/?state=state-1&code=code-1",
        )
        assert callback.wait("state-1") == "code-1"
    thread.join()
    assert [response.status_code for response in responses] == [404, 400, 400, 400, 400, 200]
    assert not any("code-9" in response.text for response in responses)
    assert capsys.readouterr() == ("", "")


def test_a_refused_consent_cancels_the_login() -> None:
    with Callback("personal") as callback:
        thread, responses = visiting(f"{callback.redirect_uri}/?error=access_denied&state=state-1")
        with pytest.raises(LoginError) as caught:
            callback.wait("state-1")
    thread.join()
    assert str(caught.value) == "gmail login cancelled: personal"
    assert (responses[0].status_code, responses[0].text) == (200, CANCELLED_PAGE)


def test_the_wait_ends_five_minutes_after_it_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_times(monkeypatch, "2026-11-12T09:00:00+00:00", "2026-11-12T09:05:00+00:00")
    with Callback("personal") as callback, pytest.raises(LoginError) as caught:
        callback.wait("state-1")
    assert str(caught.value) == "gmail login timed out: personal"


def test_an_idle_connection_does_not_hold_up_the_callback() -> None:
    with Callback("personal", request_timeout=0.2) as callback:
        port = httpx.URL(callback.redirect_uri).port
        idle = socket.create_connection(("127.0.0.1", port), timeout=5)
        threading.Timer(3, idle.close).start()
        thread, _ = visiting(f"{callback.redirect_uri}/?state=state-1&code=code-1")
        started = time.monotonic()
        assert callback.wait("state-1") == "code-1"
        assert time.monotonic() - started < 2
    thread.join()


# Exchanging the code


def test_the_code_is_exchanged_for_a_refresh_token() -> None:
    fake = FakeGmail()
    assert exchange(fake, granted(fake)) == "refresh-token-from-code-1"
    request = fake.requests[-1]
    assert (request.method, str(request.url)) == ("POST", "https://oauth2.googleapis.com/token")
    assert dict(httpx.QueryParams(request.content.decode())) == {
        "code": "code-1",
        "client_id": "client-id-1",
        "client_secret": "client-secret-1",
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
        "code_verifier": VERIFIER,
    }
    assert "authorization" not in request.headers


@pytest.mark.parametrize(
    "scope",
    ["", f"{SCOPE} https://www.googleapis.com/auth/gmail.modify", "https://mail.google.com/"],
    ids=["none", "extra", "full"],
)
def test_a_token_for_any_scope_but_read_only_is_refused(scope: str) -> None:
    fake = FakeGmail()
    fake.granted_scope = scope
    with pytest.raises(LoginError) as caught:
        exchange(fake, granted(fake))
    assert str(caught.value) == "gmail login scope refused: personal"


@pytest.mark.parametrize(
    ("answer", "detail"),
    [
        (None, "400"),
        (httpx.ConnectError("refused client-secret-1"), "network"),
        (httpx.Response(200, text="code-1 not json"), "response"),
        (httpx.Response(200, json={"access_token": "a", "scope": SCOPE}), "response"),
    ],
    ids=["rejected", "network", "not-json", "no-refresh-token"],
)
def test_a_failed_exchange_says_only_why(answer: object, detail: str) -> None:
    fake = FakeGmail()
    code = granted(fake) if answer is not None else "code-unknown"

    def handler(request: httpx.Request) -> httpx.Response:
        if answer is None:
            return fake.handler(request)
        if isinstance(answer, Exception):
            raise answer
        return answer

    with pytest.raises(LoginError) as caught:
        exchange(fake, code, handler)
    assert str(caught.value) == f"gmail login failed: personal ({detail})"
    assert caught.value.__suppress_context__


# The whole login


def test_a_first_login_asks_for_the_client_and_stores_three_secrets(
    fake_keychain: FakeKeychain,
) -> None:
    fake = FakeGmail()
    browser, ask = Browser(fake), asker("client-id-1", "client-secret-1")
    assert login("personal", http_for(fake), ask=ask, open_browser=browser) == "owner@example.test"
    assert ask.labels == ["Gmail OAuth client ID", "Gmail OAuth client secret"]
    assert len(browser.opened) == 1
    assert fake_keychain.writes == WRITES
    assert fake_keychain.secrets == {
        **CLIENT_KEYS,
        ("mailroom", "gmail.personal.refresh-token"): "refresh-token-from-code-1",
    }
    assert fake.requests[-1].url.path == "/gmail/v1/users/me/profile"


def test_a_later_login_reuses_the_stored_client(fake_keychain: FakeKeychain) -> None:
    fake_keychain.secrets.update(CLIENT_KEYS)
    fake = FakeGmail()
    assert login("personal", http_for(fake), ask=asker(), open_browser=Browser(fake)) == (
        "owner@example.test"
    )
    assert fake_keychain.writes == [("mailroom", "gmail.personal.refresh-token")]


def test_a_new_client_replaces_the_stored_one(fake_keychain: FakeKeychain) -> None:
    fake_keychain.secrets[("mailroom", "gmail.personal.client-id")] = "client-id-0"
    fake_keychain.secrets[("mailroom", "gmail.personal.client-secret")] = "client-secret-0"
    fake = FakeGmail()
    ask = asker("client-id-1", "client-secret-1")
    login("personal", http_for(fake), ask=ask, open_browser=Browser(fake), new_client=True)
    assert fake_keychain.writes == WRITES
    assert fake_keychain.secrets[("mailroom", "gmail.personal.client-secret")] == "client-secret-1"


def test_a_cancelled_login_stores_nothing(fake_keychain: FakeKeychain) -> None:
    fake = FakeGmail()
    browser = Browser(fake, approve=False)
    with pytest.raises(LoginError):
        login(
            "personal",
            http_for(fake),
            ask=asker("client-id-1", "client-secret-1"),
            open_browser=browser,
        )
    assert fake_keychain.writes == []
    assert fake.requests == []


def test_an_invalid_account_is_refused_before_anything(fake_keychain: FakeKeychain) -> None:
    fake = FakeGmail()
    browser, ask = Browser(fake), asker()
    with pytest.raises(ValueError) as caught:
        login("Personal", http_for(fake), ask=ask, open_browser=browser)
    assert str(caught.value) == "invalid account name"
    assert (ask.labels, browser.opened, fake_keychain.calls) == ([], [], [])


# The command


def command(monkeypatch: pytest.MonkeyPatch, fake: FakeGmail, browser: Browser, typed: str):
    monkeypatch.setattr(gmail_login, "new_http", lambda: http_for(fake))
    monkeypatch.setattr(webbrowser, "open", browser)
    from mailroom.cli import app

    return runner.invoke(app, ["gmail-login", "personal"], input=typed)


def test_the_command_signs_in_and_names_the_account(
    monkeypatch: pytest.MonkeyPatch, fake_keychain: FakeKeychain
) -> None:
    fake = FakeGmail()
    browser = Browser(fake)
    result = command(monkeypatch, fake, browser, "client-id-1\nclient-secret-1\n")
    assert result.exit_code == 0
    assert browser.opened[0] in result.output
    assert "client-secret-1" not in result.output
    assert result.output.splitlines()[-1] == "Signed in: personal (owner@example.test)"


def test_the_command_reports_a_failure_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, fake_keychain: FakeKeychain
) -> None:
    fake_keychain.secrets.update(CLIENT_KEYS)
    fake = FakeGmail()
    result = command(monkeypatch, fake, Browser(fake, approve=False), "")
    assert result.exit_code == 1
    assert result.output.splitlines()[-1] == "gmail login cancelled: personal"
    assert fake_keychain.writes == []
