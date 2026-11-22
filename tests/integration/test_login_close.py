"""Each login command closes the HTTP client it opened, on success and on every failure."""

import webbrowser
from datetime import UTC, datetime

import httpx
import pytest
from keyring.errors import KeyringError

from mailroom import clock, gmail_login, outlook_login
from tests.fakes import FakeGmail, FakeGraph, FakeKeychain
from tests.integration import test_gmail_login as gmail_case
from tests.integration import test_outlook_login as outlook_case
from tests.support import runner

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
PATHS = ("signed in", "cancelled", "keychain", "bad account")
CASES = {
    "gmail": (gmail_login, FakeGmail, gmail_case.Browser, gmail_case.CLIENT_KEYS, "personal"),
    "outlook": (
        outlook_login,
        FakeGraph,
        outlook_case.Browser,
        {outlook_case.CLIENT_ID: "client-id-1"},
        "live",
    ),
}
FAILURES = {
    "cancelled": "{provider} login cancelled: {account}",
    "keychain": "keychain unavailable: {provider}.{account}.client-id",
    "bad account": "invalid account name",
}


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("provider", sorted(CASES))
def test_the_login_command_closes_its_client(
    monkeypatch: pytest.MonkeyPatch, fake_keychain: FakeKeychain, provider: str, path: str
) -> None:
    module, fake_type, browser_type, keys, account = CASES[provider]
    fake = fake_type()
    fake_keychain.secrets.update(keys)
    if path == "keychain":
        fake_keychain.error = KeyringError("locked")
    opened: list[httpx.Client] = []

    def new_http() -> httpx.Client:
        client = httpx.Client(transport=httpx.MockTransport(fake.handler))
        opened.append(client)
        return client

    monkeypatch.setattr(module, "new_http", new_http)
    monkeypatch.setattr(webbrowser, "open", browser_type(fake, approve=path != "cancelled"))
    from mailroom.cli import app

    name = "Bad" if path == "bad account" else account
    result = runner.invoke(app, [f"{provider}-login", name], input="")
    if path == "signed in":
        assert result.exit_code == 0
        assert result.output.splitlines()[-1] == f"Signed in: {account} (owner@example.test)"
    else:
        assert result.exit_code == 1
        wanted = FAILURES[path].format(provider=provider, account=account)
        assert result.output.splitlines()[-1] == wanted
    assert len(opened) == 1
    assert opened[0].is_closed
