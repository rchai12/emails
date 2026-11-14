import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.gateway import GatewayStopped
from mailroom.gmail import GmailClient
from mailroom.service import Health, ServiceError, run_round, run_service
from mailroom.store import Store, open_store
from tests.fakes import FakeDiscord, FakeGmail, FakeKeychain, FakeOllama, FakeTasksApp

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
GOOD = {
    "summary": "Sam asks for the report by Friday.",
    "actionable": True,
    "urgent": False,
    "title": "Send Sam the report",
    "has_deadline": False,
    "deadline_date": "",
    "deadline_time": "",
    "deadline_explicit": False,
    "deadline_quote": "",
    "suspicious": False,
    "suspicion_reason": "",
    "confidence": "high",
}


def raw(number: int) -> bytes:
    return (
        f"From: Sam {number} <sam{number}@example.test>\r\n"
        f"Subject: Report {number}\r\n"
        "Date: Wed, 11 Nov 2026 08:00:00 +0000\r\n"
        f"\r\nCan you send the report? ({number})\r\n"
    ).encode()


def deliver(fake: FakeGmail, number: int) -> None:
    moment = NOW - timedelta(hours=1)
    fake.add_message(f"m{number}", raw(number), internal_ms=round(moment.timestamp() * 1000))


class World:
    """The fakes for one test: Gmail accounts, the model, Discord, the tasks app, and clients."""

    def __init__(self, keychain: FakeKeychain, accounts: tuple[str, ...]) -> None:
        self.gmail = {account: FakeGmail() for account in accounts}
        for account in accounts:
            for name, value in (
                ("client-id", "client-id-1"),
                ("client-secret", "client-secret-1"),
                ("refresh-token", "refresh-token-1"),
            ):
                keychain.secrets[("mailroom", f"gmail.{account}.{name}")] = value
        self.model = FakeOllama()
        self.discord = FakeDiscord()
        keychain.secrets[("mailroom", "discord.bot-token")] = self.discord.token
        self.tasks = FakeTasksApp()
        self.lines: list[str] = []

    def client(self, account: str) -> GmailClient:
        transport = httpx.MockTransport(self.gmail[account].handler)
        return GmailClient(account, httpx.Client(transport=transport))

    def model_http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.model.handler))

    def discord_http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.discord.handler))

    def tasks_http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.tasks.handler))

    def round(self, store: Store, settings: Settings) -> list[str]:
        before = len(self.lines)
        run_round(
            store,
            settings,
            [self.client(account) for account in self.gmail],
            self.model_http(),
            self.discord_http(),
            self.tasks_http(),
            self.health,
        )
        return self.lines[before:]

    @property
    def health(self) -> Health:
        if not hasattr(self, "_health"):
            self._health = Health(self.lines.append)
        return self._health


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


# One round


def test_a_round_syncs_triages_and_posts(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    assert world.round(store, settings) == [
        "gmail personal: ok",
        "triage: ok",
        "tasks: ok",
        "discord posting: ok",
        "discord alerts: ok",
    ]
    assert store.untriaged() == ()
    (message,) = world.discord.messages
    assert store.post("gmail", "personal/m1").discord_message_id == message["id"]


def test_status_lines_are_said_only_when_a_part_changes(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    world.round(store, settings)
    assert world.round(store, settings) == []


def test_one_broken_account_does_not_stop_the_others(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("work", "personal"))
    fake_keychain.secrets[("mailroom", "gmail.work.refresh-token")] = "revoked-token"
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    assert world.round(store, settings) == [
        "gmail work: gmail sign-in needed: work",
        "gmail personal: ok",
        "triage: ok",
        "tasks: ok",
        "discord posting: ok",
        "discord alerts: ok",
    ]
    assert len([message for message in world.discord.messages if message["embeds"]]) == 1


def test_a_missing_gmail_secret_asks_for_sign_in(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    del fake_keychain.secrets[("mailroom", "gmail.personal.refresh-token")]
    assert world.round(store, settings)[0] == "gmail personal: gmail sign-in needed: personal"


def test_an_unreachable_model_leaves_mail_for_the_next_round(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    deliver(world.gmail["personal"], 1)
    deliver(world.gmail["personal"], 2)
    world.model.replies.append(httpx.ConnectError("refused"))
    assert world.round(store, settings) == [
        "gmail personal: ok",
        "triage: model unavailable (network)",
        "tasks: ok",
        "discord posting: ok",
        "discord alerts: ok",
    ]
    assert len(world.model.requests) == 1
    assert len(store.untriaged()) == 2
    world.model.replies.extend([GOOD, GOOD])
    assert world.round(store, settings) == ["triage: ok"]
    assert store.untriaged() == ()
    assert len(world.discord.messages) == 2


def test_a_discord_failure_leaves_posts_queued(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    world.discord.failures.append(httpx.Response(503, text="busy"))
    assert world.round(store, settings)[-2] == "discord posting: waiting (503)"
    assert len(store.pending_posts()) == 1
    assert world.round(store, settings) == ["discord posting: ok"]
    assert store.pending_posts() == ()


def test_a_missing_bot_token_is_reported_and_posting_waits(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    del fake_keychain.secrets[("mailroom", "discord.bot-token")]
    assert world.round(store, settings)[-2] == (
        "discord posting: secret not found: discord.bot-token"
    )
    assert len(store.pending_posts()) == 1


def test_each_round_clears_text_older_than_a_day(
    store: Store, settings: Settings, fake_keychain: FakeKeychain, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(fake_keychain, ("personal",))
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    world.round(store, settings)
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(hours=24))
    world.round(store, settings)
    stored = store.get("gmail", "personal/m1")
    assert stored is not None
    assert stored.text_cleared_at == NOW + timedelta(hours=24)


# The service


class Rounds(threading.Event):
    """A stop event whose wait counts rounds and stops the service after `limit` of them."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit
        self.waits: list[float | None] = []

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout)
        if len(self.waits) >= self.limit:
            self.set()
        return self.is_set()


def serve(world: World, settings: Settings, stop: threading.Event, gateway) -> None:
    run_service(
        settings,
        say=world.lines.append,
        stop=stop,
        open_gmail=world.client,
        open_model_http=world.model_http,
        open_discord_http=world.discord_http,
        open_tasks_http=world.tasks_http,
        gateway=gateway,
    )


def test_the_service_polls_every_interval_and_listens_on_its_own_thread(
    settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    seen: dict[str, object] = {}

    def gateway(store: Store, gateway_settings: Settings, http: httpx.Client, *, stop) -> None:
        seen.update(thread=threading.current_thread(), store=store)
        store.sender_status("someone@example.test")
        while not stop():
            threading.Event().wait(0.001)

    stop = Rounds(3)
    serve(world, settings, stop, gateway)
    assert stop.waits == [60, 60, 60]
    assert seen["thread"] is not threading.current_thread()
    assert seen["thread"].name == "mailroom-gateway"
    assert not seen["thread"].is_alive()
    assert len(world.discord.messages) == 1
    assert world.lines[:5] == [
        "discord gateway: running",
        "gmail personal: ok",
        "triage: ok",
        "tasks: ok",
        "discord posting: ok",
    ]
    assert not any("failed" in line for line in world.lines)


def test_a_stopped_gateway_is_reported_once_and_polling_goes_on(
    settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    calls: list[int] = []

    def gateway(store: Store, gateway_settings: Settings, http: httpx.Client, *, stop) -> None:
        calls.append(1)
        raise GatewayStopped(4004)

    stop = Rounds(4)
    serve(world, settings, stop, gateway)
    assert calls == [1]
    assert world.lines.count("discord gateway: gateway stopped (4004)") == 1
    assert len(stop.waits) == 4


def test_an_unexpected_gateway_error_names_only_its_type(
    settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))

    def gateway(store: Store, gateway_settings: Settings, http: httpx.Client, *, stop) -> None:
        raise KeyError("Your bill of $42.00")

    serve(world, settings, Rounds(2), gateway)
    assert "discord gateway: failed (KeyError)" in world.lines
    assert not any("$42.00" in line for line in world.lines)


def test_the_service_refuses_to_start_without_its_settings(
    monkeypatch: pytest.MonkeyPatch, fake_keychain: FakeKeychain
) -> None:
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    world = World(fake_keychain, ())
    with pytest.raises(ServiceError) as caught:
        serve(world, get_settings(), Rounds(1), lambda *args, **kwargs: None)
    assert str(caught.value) == (
        "not configured: MAILROOM_GMAIL_ACCOUNTS, MAILROOM_EXTRACTOR_MODEL, "
        "MAILROOM_DISCORD_CHANNEL_ID, MAILROOM_DISCORD_OWNER_ID"
    )
    assert world.lines == []
