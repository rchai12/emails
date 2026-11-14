"""Coverage for service edges the given tests leave closed."""

import sqlite3
import threading
from collections.abc import Iterator

import httpx
import pytest

from mailroom import clock, gmail_sync
from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.gmail import GmailClient
from mailroom.keychain import SecretMissing
from mailroom.service import run_service
from mailroom.store import Store, open_store
from tests.fakes import FakeKeychain, FakeTasksApp
from tests.integration.test_service import GOOD, NOW, Rounds, World, deliver, serve


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    for name, value in (
        ("MAILROOM_GMAIL_ACCOUNTS", "personal"),
        ("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b"),
        ("MAILROOM_TIME_ZONE", "America/New_York"),
        ("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111"),
        ("MAILROOM_DISCORD_OWNER_ID", "444444444444444444"),
        ("MAILROOM_TASKS_URL", FakeTasksApp.URL),
    ):
        monkeypatch.setenv(name, value)
    return get_settings()


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    with open_store(settings) as opened:
        yield opened


def test_an_empty_accounts_value_means_no_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_GMAIL_ACCOUNTS", "")
    assert get_settings().gmail_accounts == ()


def test_a_gmail_500_is_reported_and_the_round_goes_on(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("work", "personal"))
    world.gmail["work"].failures.append(httpx.Response(500, json={"error": {"code": 500}}))
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    assert world.round(store, settings) == [
        "gmail work: gmail unavailable: work (500)",
        "gmail personal: ok",
        "triage: ok",
        "tasks: ok",
        "discord posting: ok",
        "discord alerts: ok",
    ]
    assert len(world.discord.messages) == 1


def test_a_listener_that_cannot_reach_discord_is_reported_once(
    settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))

    def gateway(
        listener_store: Store, gateway_settings: Settings, http: httpx.Client, *, stop
    ) -> None:
        raise DiscordUnavailable("not configured")

    serve(world, settings, Rounds(2), gateway)
    assert world.lines.count("discord gateway: discord unavailable (not configured)") == 1


def test_a_listener_missing_its_secret_is_reported_once(
    settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))

    def gateway(
        listener_store: Store, gateway_settings: Settings, http: httpx.Client, *, stop
    ) -> None:
        raise SecretMissing("secret not found: discord.bot-token")

    serve(world, settings, Rounds(2), gateway)
    assert world.lines.count("discord gateway: secret not found: discord.bot-token") == 1


def test_an_unexpected_round_error_stops_the_listener_and_closes_everything(
    settings: Settings, fake_keychain: FakeKeychain, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(fake_keychain, ("personal",))
    started = threading.Event()
    seen: dict[str, object] = {}
    gmail_clients: list[GmailClient] = []
    https: list[httpx.Client] = []
    stores: list[Store] = []
    real_open = open_store

    def tracking(found: Settings) -> Store:
        opened = real_open(found)
        stores.append(opened)
        return opened

    def gateway(
        listener_store: Store, gateway_settings: Settings, http: httpx.Client, *, stop
    ) -> None:
        seen["thread"] = threading.current_thread()
        seen["http"] = http
        started.set()
        while not stop():
            threading.Event().wait(0.001)

    def open_gmail(account: str) -> GmailClient:
        client = world.client(account)
        gmail_clients.append(client)
        return client

    def open_model_http() -> httpx.Client:
        http = world.model_http()
        https.append(http)
        return http

    def open_discord_http() -> httpx.Client:
        http = world.discord_http()
        https.append(http)
        return http

    def boom(client: GmailClient, found: Store) -> None:
        assert started.wait(2)
        raise RuntimeError("private subject")

    monkeypatch.setattr(gmail_sync, "sync_gmail", boom)
    monkeypatch.setattr("mailroom.service.open_store", tracking)
    stop = threading.Event()
    with pytest.raises(RuntimeError, match="private subject"):
        run_service(
            settings,
            say=world.lines.append,
            stop=stop,
            open_gmail=open_gmail,
            open_model_http=open_model_http,
            open_discord_http=open_discord_http,
            gateway=gateway,
        )
    assert stop.is_set()
    thread = seen["thread"]
    assert isinstance(thread, threading.Thread)
    assert not thread.is_alive()
    listener_http = seen["http"]
    assert isinstance(listener_http, httpx.Client)
    assert listener_http.is_closed
    assert len(stores) == 2
    for opened in stores:
        with pytest.raises(sqlite3.ProgrammingError):
            opened.get("gmail", "m1")
    assert gmail_clients
    assert all(client.http.is_closed for client in gmail_clients)
    assert https
    assert all(http.is_closed for http in https)
    assert not any("private subject" in line for line in world.lines)
