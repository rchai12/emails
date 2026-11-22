"""Login commands lend an open client and close it; reply errors never carry reply text."""

import json
import webbrowser
from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock, gmail_login, oauth, outlook_login
from tests.fakes import FakeKeychain
from tests.support import runner

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
LEAK = "secret-description-text"


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.mark.parametrize("provider", ["gmail", "outlook"])
def test_login_is_lent_the_open_client_and_a_crash_still_closes_it(
    monkeypatch: pytest.MonkeyPatch, fake_keychain: FakeKeychain, provider: str
) -> None:
    module = {"gmail": gmail_login, "outlook": outlook_login}[provider]
    made: list[httpx.Client] = []
    lent: list[tuple[httpx.Client, bool]] = []

    def new_http() -> httpx.Client:
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
        made.append(client)
        return client

    def login(account: str, http: httpx.Client, **_kwargs: object) -> str:
        lent.append((http, http.is_closed))
        raise RuntimeError("synthetic bug")

    monkeypatch.setattr(module, "new_http", new_http)
    monkeypatch.setattr(module, "login", login)
    monkeypatch.setattr(webbrowser, "open", lambda address: True)
    from mailroom.cli import app

    result = runner.invoke(app, [f"{provider}-login", "someone"], input="")
    assert isinstance(result.exception, RuntimeError)
    assert lent == [(made[0], False)]
    assert len(made) == 1
    assert made[0].is_closed


@pytest.mark.parametrize(
    ("module", "provider", "extra"),
    [
        (gmail_login, "gmail", {"client_secret": "s"}),
        (outlook_login, "outlook", {}),
    ],
)
def test_a_rejected_exchange_reports_only_the_status(
    module: object, provider: str, extra: dict[str, str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": LEAK})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(oauth.LoginError) as caught:
        module.exchange_code(
            http,
            "acct",
            client_id="c",
            code="code-1",
            verifier="v" * 64,
            redirect_uri="http://127.0.0.1:1",
            **extra,
        )
    assert str(caught.value) == f"{provider} login failed: acct (400)"
    assert LEAK not in str(caught.value)


def test_token_reply_sends_exactly_the_form_it_was_given() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"refresh_token": "r", "scope": "s"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    oauth.token_reply(http, "https://t.example.test/token", {"a": "1"}, provider="p", account="x")
    (request,) = seen
    assert request.content == b"a=1"
    assert "authorization" not in request.headers
    assert json.dumps(dict(request.headers)).count("secret") == 0
