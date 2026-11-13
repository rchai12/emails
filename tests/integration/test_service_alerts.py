import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.gateway import GatewayStopped
from mailroom.gmail import GmailClient
from mailroom.service import Health, run_round, run_service
from mailroom.store import Store, SyncState, open_store
from tests.fakes import FakeDiscord, FakeGmail, FakeKeychain, FakeOllama

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
OWNER = "444444444444444444"
GOOD = {
    "summary": "Sam asks for the report.",
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


class Clock:
    def __init__(self) -> None:
        self.moment = NOW

    def __call__(self) -> datetime:
        return self.moment


def deliver(fake: FakeGmail, number: int, moment: datetime) -> None:
    raw = (
        f"From: Sam <sam{number}@example.test>\r\nSubject: Report {number}\r\n"
        f"\r\nCan you send the report? ({number})\r\n"
    ).encode()
    fake.add_message(f"m{number}", raw, internal_ms=round(moment.timestamp() * 1000))


class World:
    """One Gmail account, the model and Discord, with their clients (copied from 1l's tests)."""

    def __init__(self, keychain: FakeKeychain) -> None:
        self.keychain = keychain
        self.gmail = FakeGmail()
        for name, value in (
            ("client-id", "client-id-1"),
            ("client-secret", "client-secret-1"),
            ("refresh-token", "refresh-token-1"),
        ):
            keychain.secrets[("mailroom", f"gmail.personal.{name}")] = value
        self.model = FakeOllama()
        self.discord = FakeDiscord()
        keychain.secrets[("mailroom", "discord.bot-token")] = self.discord.token
        self.lines: list[str] = []
        self.health = Health(self.lines.append)

    def client(self, account: str = "personal") -> GmailClient:
        return GmailClient(account, httpx.Client(transport=httpx.MockTransport(self.gmail.handler)))

    def model_http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.model.handler))

    def discord_http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.discord.handler))

    def round(self, store: Store, settings: Settings) -> list[str]:
        before = len(self.lines)
        run_round(
            store, settings, [self.client()], self.model_http(), self.discord_http(), self.health
        )
        return self.lines[before:]

    def posted(self) -> list[str]:
        return [message["content"] for message in self.discord.messages if message["content"]]


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(clock, "now", fake)
    return fake


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, now: Clock) -> Settings:
    for name, value in (
        ("MAILROOM_GMAIL_ACCOUNTS", "personal"),
        ("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b"),
        ("MAILROOM_TIME_ZONE", "America/New_York"),
        ("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111"),
        ("MAILROOM_DISCORD_OWNER_ID", OWNER),
    ):
        monkeypatch.setenv(name, value)
    return get_settings()


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    with open_store(settings) as opened:
        yield opened


@pytest.fixture
def world(fake_keychain: FakeKeychain) -> World:
    return World(fake_keychain)


def test_a_revoked_gmail_token_pings_you_once_and_its_fix_is_announced(
    store: Store, settings: Settings, world: World, now: Clock
) -> None:
    world.keychain.secrets[("mailroom", "gmail.personal.refresh-token")] = "revoked"
    assert world.round(store, settings)[-1] == "discord alerts: ok"
    now.moment += timedelta(minutes=1)
    world.round(store, settings)
    assert world.posted() == [
        f"<@{OWNER}> Gmail sign-in needed for personal. Run: mailroom gmail-login personal"
    ]
    world.keychain.secrets[("mailroom", "gmail.personal.refresh-token")] = "refresh-token-1"
    now.moment += timedelta(minutes=1)
    world.round(store, settings)
    assert world.posted()[1:] == ["Gmail personal works again."]


def test_an_unreachable_model_is_announced_after_15_minutes_and_its_return_too(
    store: Store, settings: Settings, world: World, now: Clock
) -> None:
    deliver(world.gmail, 1, NOW - timedelta(minutes=30))
    for minute in (0, 5, 10, 14):
        now.moment = NOW + timedelta(minutes=minute)
        world.model.replies.append(httpx.ConnectError("refused"))
        world.round(store, settings)
    assert world.posted() == []
    now.moment = NOW + timedelta(minutes=15)
    world.model.replies.append(httpx.ConnectError("refused"))
    world.round(store, settings)
    assert world.posted() == [
        "The local model has been unreachable for 15 minutes. New mail is waiting; nothing is lost."
    ]
    now.moment = NOW + timedelta(minutes=16)
    world.model.replies.append(GOOD)
    world.round(store, settings)
    assert world.posted()[1:] == ["The local model is back. Waiting mail is being triaged."]


def test_a_catch_up_posts_one_summary(
    store: Store, settings: Settings, world: World, now: Clock
) -> None:
    store.save_sync_state("gmail", "personal", SyncState("900", NOW - timedelta(hours=5)))
    world.gmail.oldest_history_id = 950
    deliver(world.gmail, 1, NOW - timedelta(hours=1))
    world.model.replies.append(GOOD)
    world.round(store, settings)
    world.round(store, settings)
    assert world.posted() == ["Gmail personal caught up after 5 hours offline: 1 new email."]


def test_an_alert_that_cannot_be_posted_waits(
    store: Store, settings: Settings, world: World
) -> None:
    world.keychain.secrets[("mailroom", "gmail.personal.refresh-token")] = "revoked"
    world.discord.failures.append(httpx.Response(503, text="busy"))
    assert world.round(store, settings)[-1] == "discord alerts: waiting (503)"
    assert len(store.pending_alerts()) == 1
    assert world.round(store, settings)[-1] == "discord alerts: ok"
    assert store.pending_alerts() == ()


class Rounds(threading.Event):
    """Stops the service after `limit` waits. With `join`, the first wait lets a listener that
    is already ending finish, so its alert is queued before the next round posts."""

    def __init__(self, limit: int, join: bool) -> None:
        super().__init__()
        self.limit = limit
        self.join = join
        self.waits = 0

    def wait(self, timeout: float | None = None) -> bool:
        if self.join and self.waits == 0:
            for thread in threading.enumerate():
                if thread.name == "mailroom-gateway":
                    thread.join(timeout=5)
        self.waits += 1
        if self.waits >= self.limit:
            self.set()
        return self.is_set()


def serve(world: World, settings: Settings, rounds: int, gateway, *, join: bool = True) -> None:
    run_service(
        settings,
        say=world.lines.append,
        stop=Rounds(rounds, join),
        open_gmail=world.client,
        open_model_http=world.model_http,
        open_discord_http=world.discord_http,
        gateway=gateway,
    )


def test_a_stopped_listener_pings_you_and_a_later_live_one_is_announced(
    settings: Settings, world: World
) -> None:
    def stopped(store: Store, gateway_settings: Settings, http: httpx.Client, *, stop) -> None:
        raise GatewayStopped(4004)

    serve(world, settings, 3, stopped)
    assert world.posted() == [
        f"<@{OWNER}> The Discord listener stopped: gateway stopped (4004). Buttons and commands "
        "won't answer until the service is restarted."
    ]

    def live(store: Store, gateway_settings: Settings, http: httpx.Client, *, stop) -> None:
        while not stop():
            threading.Event().wait(0.001)

    serve(world, settings, 3, live, join=False)
    assert world.posted()[1:] == ["The Discord listener is running again."]


def test_a_listener_that_dies_at_once_is_never_called_running_again(
    settings: Settings, world: World
) -> None:
    def stopped(store: Store, gateway_settings: Settings, http: httpx.Client, *, stop) -> None:
        raise GatewayStopped(4004)

    serve(world, settings, 3, stopped)
    serve(world, settings, 3, stopped)
    assert len(world.posted()) == 1
