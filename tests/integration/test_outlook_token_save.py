"""Phase 4h: behavior the given rotation tests leave unpinned."""

import json

import httpx
import pytest

from mailroom import outlook
from mailroom.config import Settings
from mailroom.keychain import KeychainUnavailable
from mailroom.outlook import OutlookClient, OutlookError
from mailroom.store import Store
from tests.fakes import FakeGraph
from tests.integration.test_outlook_rotation import TOKEN_NAME, SaveFails, client, failed
from tests.integration.test_outlook_rotation import graph as graph
from tests.integration.test_outlook_rotation import keychain as keychain
from tests.integration.test_service_outlook import BothWorld, posted
from tests.integration.test_service_rotation import (
    UNSAVED_ALERT,
    UNSAVED_LINE,
)
from tests.integration.test_service_rotation import moment as moment
from tests.integration.test_service_rotation import settings as settings
from tests.integration.test_service_rotation import store as store

SECRET = "refresh-token-private"


def token_client(body: dict[str, object], seen: list[str]) -> OutlookClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host or "")
        return httpx.Response(200, content=json.dumps(body))

    return OutlookClient("live", httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("reply", [{"refresh_token": "refresh-token-1"}, {}], ids=["same", "none"])
def test_a_reply_without_a_new_token_needs_no_write(
    keychain: SaveFails, graph: FakeGraph, reply: dict[str, str]
) -> None:
    seen: list[str] = []
    body = {"access_token": "access-x", "expires_in": 3600, **reply}
    token_client(body, seen)._ensure_token()
    assert keychain.tries == []
    assert seen == ["login.microsoftonline.com"]


def test_a_keychain_read_failure_is_reported_without_an_unsaved_error(
    graph: FakeGraph, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(name: str) -> str:
        raise KeychainUnavailable(f"keychain unavailable: {name}")

    monkeypatch.setattr(outlook.keychain, "get_secret", broken)
    error = failed(client(graph).profile)
    assert type(error) is KeychainUnavailable
    assert not isinstance(error, outlook.OutlookTokenUnsaved)


def test_one_account_holding_a_token_does_not_affect_another(
    keychain: SaveFails, graph: FakeGraph
) -> None:
    other = FakeGraph()
    keychain.secrets[("mailroom", "outlook.work.client-id")] = other.client_id
    keychain.secrets[("mailroom", "outlook.work.refresh-token")] = other.refresh_token
    held = client(graph)
    failed(held.profile)
    keychain.refuse = False
    work = OutlookClient("work", httpx.Client(transport=httpx.MockTransport(other.handler)))
    assert work.profile().email_address == "owner@example.test"
    assert keychain.secrets[TOKEN_NAME] == "refresh-token-1"


def test_an_unsaved_round_does_not_stop_gmail_in_the_same_round(
    store: Store, settings: Settings, keychain: SaveFails, moment: list
) -> None:
    world = BothWorld(keychain)
    lines = world.both_round(store, settings)
    assert UNSAVED_LINE in lines
    assert "gmail personal: ok" in lines
    assert store.sync_state("gmail", "personal") is not None
    assert posted(world) == [UNSAVED_ALERT]


def test_a_keychain_read_failure_in_a_round_raises_no_unsaved_alert(
    store: Store, settings: Settings, keychain: SaveFails, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = BothWorld(keychain, ())

    def broken(name: str) -> str:
        raise KeychainUnavailable(f"keychain unavailable: {name}")

    monkeypatch.setattr(outlook.keychain, "get_secret", broken)
    lines = world.both_round(store, settings)
    assert lines[0].startswith("outlook live: keychain unavailable")
    assert posted(world) == []
    assert not any(SECRET in line for line in lines)
    assert issubclass(outlook.OutlookTokenUnsaved, OutlookError)
