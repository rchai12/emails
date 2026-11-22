"""The sign-in parts both providers share live in `mailroom.oauth`, under no provider's name."""

import importlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from mailroom import clock, gmail_login, outlook_login
from tests.fakes import FakeGmail
from tests.integration.test_gmail_login import exchange, granted

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
URL = "https://login.example.test/token"
DATA = {"grant_type": "authorization_code", "code": "code-1", "code_verifier": "v" * 64}


def oauth():
    return importlib.import_module("mailroom.oauth")


@pytest.fixture
def expired(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first clock read sets the deadline, and every later read is past it."""
    moments = iter([NOW])
    monkeypatch.setattr(clock, "now", lambda: next(moments, NOW + timedelta(minutes=6)))


def test_the_shared_pieces_live_in_oauth_and_gmail_login_keeps_its_names() -> None:
    shared = oauth()
    assert shared.CALLBACK_TIMEOUT == timedelta(minutes=5)
    assert shared.REQUEST_TIMEOUT_SECONDS == 5.0
    assert shared.DONE_PAGE == "Signed in to mailroom. You can close this tab."
    assert shared.CANCELLED_PAGE == "Sign-in cancelled. You can close this tab."
    assert issubclass(shared.LoginError, Exception)
    assert gmail_login.LoginError is shared.LoginError
    assert gmail_login.new_verifier is shared.new_verifier
    assert gmail_login.code_challenge is shared.code_challenge
    for name in ("CALLBACK_TIMEOUT", "REQUEST_TIMEOUT_SECONDS", "DONE_PAGE", "CANCELLED_PAGE"):
        assert getattr(gmail_login, name) == getattr(shared, name)
    assert outlook_login.Callback is shared.Callback
    assert outlook_login.LoginError is shared.LoginError


def test_the_neutral_callback_requires_and_names_its_provider(expired: None) -> None:
    shared = oauth()
    with pytest.raises(TypeError):
        shared.Callback("live")
    with shared.Callback("live", provider="yahoo") as callback:
        assert callback.redirect_uri.startswith("http://127.0.0.1:")
        with pytest.raises(shared.LoginError) as caught:
            callback.wait("state-1")
    assert str(caught.value) == "yahoo login timed out: live"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_the_gmail_callback_still_defaults_to_gmail(expired: None) -> None:
    shared = oauth()
    assert issubclass(gmail_login.Callback, shared.Callback)
    with gmail_login.Callback("personal") as callback, pytest.raises(shared.LoginError) as caught:
        callback.wait("state-1")
    assert str(caught.value) == "gmail login timed out: personal"


def test_outlook_sign_in_loads_no_gmail_module() -> None:
    script = (
        "import sys, mailroom.oauth, mailroom.outlook_login;"
        "print(sorted(name for name in sys.modules if name.startswith('mailroom.gmail')))"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(path for path in sys.path if path)}
    found = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert found.stdout.strip() == "[]"


def reply(response: httpx.Response | Exception, requests: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_good_token_reply_gives_the_refresh_token_and_scope() -> None:
    requests: list[httpx.Request] = []
    body = {"access_token": "access-1", "refresh_token": "refresh-1", "scope": "read offline"}
    http = reply(httpx.Response(200, json=body), requests)
    found = oauth().token_reply(http, URL, DATA, provider="yahoo", account="family")
    assert found == ("refresh-1", "read offline")
    assert [(r.method, str(r.url)) for r in requests] == [("POST", URL)]
    assert parse_qs(requests[0].content.decode()) == {key: [value] for key, value in DATA.items()}


@pytest.mark.parametrize(
    ("response", "detail"),
    [
        (httpx.ConnectError("refused"), "network"),
        (httpx.ReadTimeout("slow"), "network"),
        (httpx.Response(400, json={"error": "invalid_grant"}), "400"),
        (httpx.Response(503), "503"),
        (httpx.Response(200, content=b"not json"), "response"),
        (httpx.Response(200, json=["refresh-1"]), "response"),
        (httpx.Response(200, json={"scope": "read"}), "response"),
        (httpx.Response(200, json={"refresh_token": "", "scope": "read"}), "response"),
        (httpx.Response(200, json={"refresh_token": 7, "scope": "read"}), "response"),
        (httpx.Response(200, json={"refresh_token": "refresh-1"}), "response"),
        (httpx.Response(200, json={"refresh_token": "refresh-1", "scope": ["read"]}), "response"),
    ],
    ids=[
        "refused",
        "timeout",
        "status-400",
        "status-503",
        "not-json",
        "not-object",
        "no-token",
        "empty-token",
        "token-not-text",
        "no-scope",
        "scope-not-text",
    ],
)
def test_a_bad_token_reply_is_one_constant_error(
    response: httpx.Response | Exception, detail: str
) -> None:
    shared = oauth()
    http = reply(response, [])
    with pytest.raises(shared.LoginError) as caught:
        shared.token_reply(http, URL, DATA, provider="yahoo", account="family")
    assert str(caught.value) == f"yahoo login failed: family ({detail})"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_gmail_now_refuses_an_empty_refresh_token() -> None:
    fake = FakeGmail()
    code = granted(fake)

    def handler(request: httpx.Request) -> httpx.Response:
        answer = fake.handler(request)
        body = json.loads(answer.content)
        return httpx.Response(200, json={**body, "refresh_token": ""})

    with pytest.raises(gmail_login.LoginError) as caught:
        exchange(fake, code, handler)
    assert str(caught.value) == "gmail login failed: personal (response)"
