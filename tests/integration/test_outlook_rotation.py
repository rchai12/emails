"""A rotated refresh token the Keychain will not save is held, never lost, and saved first.

Graph issues a new refresh token on every refresh and retires the one before. `SaveFails` is
the fake Keychain with writes that fail while `refuse` is set; reads keep working. The client
keeps the new token in memory, reads no mail with it, and saves it before anything else on its
next call. A new client (a restart) only has the Keychain's old token, which Graph refuses.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import keyring.core
import keyring.errors
import pytest

import mailroom.outlook
from mailroom import clock
from mailroom.outlook import OutlookAuthError, OutlookClient, OutlookError, Profile
from tests.fakes import FakeGraph, FakeKeychain

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
TOKEN_NAME = ("mailroom", "outlook.live.refresh-token")
UNSAVED_TEXT = "outlook new sign-in not saved: live"


def unsaved_error() -> type[Exception]:
    """`mailroom.outlook.OutlookTokenUnsaved`, looked up when called so this file imports first."""
    return mailroom.outlook.OutlookTokenUnsaved


class SaveFails(FakeKeychain):
    """The fake Keychain; while `refuse` is set every write fails as an unavailable Keychain."""

    def __init__(self) -> None:
        super().__init__()
        self.refuse = True
        self.tries: list[tuple[str, str]] = []

    def set_password(self, service: str, username: str, password: str) -> None:
        self.tries.append((service, username))
        if self.refuse:
            raise keyring.errors.KeyringError("synthetic write failure")
        super().set_password(service, username, password)


@pytest.fixture
def keychain(monkeypatch: pytest.MonkeyPatch) -> Iterator[SaveFails]:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    fake = SaveFails()
    monkeypatch.setattr(keyring.core, "_keyring_backend", fake)
    yield fake


@pytest.fixture
def graph(keychain: SaveFails) -> FakeGraph:
    fake = FakeGraph()
    keychain.secrets[("mailroom", "outlook.live.client-id")] = fake.client_id
    keychain.secrets[TOKEN_NAME] = fake.refresh_token
    return fake


def client(graph: FakeGraph) -> OutlookClient:
    return OutlookClient("live", httpx.Client(transport=httpx.MockTransport(graph.handler)))


def sent_tokens(graph: FakeGraph) -> list[str]:
    """The refresh token each token request carried, in order."""
    return [
        dict(httpx.QueryParams(request.content.decode()))["refresh_token"]
        for request in graph.requests
        if request.url.host == "login.microsoftonline.com"
    ]


def graph_calls(graph: FakeGraph) -> list[httpx.Request]:
    return [request for request in graph.requests if request.url.host == "graph.microsoft.com"]


def failed(call) -> Exception:
    try:
        call()
    except Exception as error:
        return error
    raise AssertionError("nothing was raised")


def test_a_new_token_the_keychain_refuses_is_reported_as_unsaved(
    graph: FakeGraph, keychain: SaveFails
) -> None:
    error = failed(client(graph).profile)
    assert type(error) is unsaved_error()
    assert isinstance(error, OutlookError)
    assert not isinstance(error, OutlookAuthError)
    assert str(error) == UNSAVED_TEXT
    assert error.__cause__ is None
    assert error.__suppress_context__
    assert "refresh-token" not in repr(error.args)
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-1"


def test_no_mail_is_read_with_the_access_token_of_an_unsaved_refresh(graph: FakeGraph) -> None:
    outlook = client(graph)
    assert type(failed(outlook.profile)) is unsaved_error()
    assert graph_calls(graph) == []
    assert graph.issued == ["access-1"]


def test_the_next_call_tries_the_save_again_before_any_request(
    graph: FakeGraph, keychain: SaveFails
) -> None:
    outlook = client(graph)
    failed(outlook.profile)
    requests = len(graph.requests)
    error = failed(outlook.profile)
    assert type(error) is unsaved_error()
    assert str(error) == UNSAVED_TEXT
    assert len(graph.requests) == requests
    assert keychain.tries == [TOKEN_NAME, TOKEN_NAME]


def test_each_call_tries_the_save_once(graph: FakeGraph, keychain: SaveFails) -> None:
    outlook = client(graph)
    for _ in range(5):
        failed(outlook.profile)
    assert keychain.tries == [TOKEN_NAME] * 5
    assert sent_tokens(graph) == ["refresh-token-1"]


def test_once_the_keychain_works_the_held_token_is_saved_and_used(
    graph: FakeGraph, keychain: SaveFails
) -> None:
    outlook = client(graph)
    failed(outlook.profile)
    failed(outlook.profile)
    keychain.refuse = False
    assert outlook.profile() == Profile("owner@example.test", "inbox-folder-1")
    assert sent_tokens(graph) == ["refresh-token-1", "refresh-token-2"]
    assert keychain.writes == [TOKEN_NAME, TOKEN_NAME]
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-3" == graph.refresh_token
    outlook.profile()
    assert keychain.writes == [TOKEN_NAME, TOKEN_NAME]
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-3"


def test_a_saved_token_is_not_saved_again_when_the_refresh_after_it_fails(
    graph: FakeGraph, keychain: SaveFails
) -> None:
    outlook = client(graph)
    assert type(failed(outlook.profile)) is unsaved_error()
    keychain.refuse = False
    graph.token_failures.append(httpx.Response(503))
    assert str(failed(outlook.profile)) == "outlook unavailable: live (503)"
    assert keychain.writes == [TOKEN_NAME]
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-2"
    outlook.profile()
    assert keychain.writes == [TOKEN_NAME, TOKEN_NAME]
    assert sent_tokens(graph) == ["refresh-token-1", "refresh-token-2", "refresh-token-2"]


def test_the_saved_call_reads_mail_with_a_fresh_access_token(
    graph: FakeGraph, keychain: SaveFails
) -> None:
    outlook = client(graph)
    failed(outlook.profile)
    keychain.refuse = False
    outlook.profile()
    assert graph.issued == ["access-1", "access-2"]
    assert {call.headers["authorization"] for call in graph_calls(graph)} == {"Bearer access-2"}


def test_the_retired_token_is_never_sent_again(graph: FakeGraph, keychain: SaveFails) -> None:
    outlook = client(graph)
    for _ in range(3):
        failed(outlook.profile)
    keychain.refuse = False
    outlook.profile()
    assert sent_tokens(graph).count("refresh-token-1") == 1


def test_a_later_rotation_that_cannot_be_saved_holds_the_newer_token(
    graph: FakeGraph, keychain: SaveFails, monkeypatch: pytest.MonkeyPatch
) -> None:
    keychain.refuse = False
    outlook = client(graph)
    outlook.profile()
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-2"
    later = [NOW.replace(hour=11)]
    monkeypatch.setattr(clock, "now", lambda: later[0])
    keychain.refuse = True
    assert type(failed(outlook.profile)) is unsaved_error()
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-2"
    keychain.refuse = False
    outlook.profile()
    assert sent_tokens(graph) == ["refresh-token-1", "refresh-token-2", "refresh-token-3"]
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-4" == graph.refresh_token


def test_a_restart_before_the_save_needs_sign_in(graph: FakeGraph, keychain: SaveFails) -> None:
    assert type(failed(client(graph).profile)) is unsaved_error()
    keychain.refuse = False
    restarted = failed(client(graph).profile)
    assert type(restarted) is OutlookAuthError
    assert str(restarted) == "outlook sign-in needed: live"
    assert sent_tokens(graph) == ["refresh-token-1", "refresh-token-1"]
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-1"
