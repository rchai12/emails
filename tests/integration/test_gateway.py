from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.extractor import Extraction
from mailroom.gateway import GatewayStopped, run_gateway
from mailroom.keychain import SecretMissing
from mailroom.record import Record
from mailroom.store import Store, Verdict, open_store
from tests.fakes import FakeDiscord, FakeGateway, FakeKeychain
from tests.support import fixed_ids

ITEM = "0123456789abcdef0123456789abcdef"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
RESUME_AT = "wss://gateway-us-east1-b.discord.gg/?v=10&encoding=json"
IDENTIFY = {
    "op": 2,
    "d": {
        "token": "discord-token-test",
        "intents": 0,
        "properties": {"os": "macos", "browser": "mailroom", "device": "mailroom"},
    },
}
RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=None,
    body_text="Your bill is due.",
    list_unsubscribe=False,
    authentication_results=(),
)
VERDICT = Verdict(
    outcome="extracted",
    trusted=False,
    verified=True,
    bulk=False,
    notify=True,
    extraction=Extraction(
        summary="Billing says the bill is due.",
        actionable=True,
        urgent=False,
        title="Pay the bill",
        deadline=None,
        suspicious=False,
        suspicion_reason="",
        confidence="high",
    ),
)


class Quarter:
    def random(self) -> float:
        return 0.25


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch, fake_keychain: FakeKeychain) -> FakeGateway:
    fake = FakeGateway(until=100)
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    monkeypatch.setattr(clock, "now", fake.now)
    return fake


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, gateway: FakeGateway) -> Iterator[Store]:
    fixed_ids(monkeypatch, ITEM)
    with open_store(get_settings()) as opened:
        opened.add(RECORD)
        opened.save_triage("gmail", "m1", VERDICT)
        opened.queue_notified()
        opened.mark_posted(ITEM, "1300000000000000001")
        yield opened


def run(gateway: FakeGateway, store: Store, settings: Settings, discord: FakeDiscord) -> None:
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    run_gateway(
        store,
        settings,
        http,
        connect=gateway.connect,
        sleep=gateway.sleep,
        rng=Quarter(),
        stop=lambda: gateway.done,
    )


def frames(connection: object) -> list[tuple[float, int, object]]:
    return [(at, payload["op"], payload.get("d")) for at, payload in connection.sent]


def test_it_identifies_then_heartbeats_on_time_and_closes_when_stopped(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    run(gateway, store, settings, FakeDiscord())
    (connection,) = gateway.connections
    assert connection.url == GATEWAY
    assert frames(connection) == [
        (0.0, 2, IDENTIFY["d"]),
        (10.3125, 1, 1),
        (51.5625, 1, 1),
        (92.8125, 1, 1),
    ]
    assert connection.closed_with == 1000
    assert gateway.sleeps == []


def test_a_press_is_answered_and_other_events_are_ignored(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    discord = FakeDiscord()
    gateway.events.append(("MESSAGE_CREATE", {"id": "1", "content": "hello"}))
    gateway.events.append(("INTERACTION_CREATE", discord.press(f"mr:notask:{ITEM}")))
    run(gateway, store, settings, discord)
    ((_, reply),) = discord.callbacks
    assert reply["type"] == 7
    stored = store.answer(ITEM)
    assert stored is not None
    assert stored.answer == "notask"
    assert frames(gateway.connections[0])[1] == (10.3125, 1, 3)


def test_a_failed_reply_does_not_stop_the_listener(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    discord = FakeDiscord()
    discord.failures.append(httpx.Response(500, text="oops"))
    gateway.events.append(("INTERACTION_CREATE", discord.press(f"mr:notask:{ITEM}")))
    run(gateway, store, settings, discord)
    assert store.answer(ITEM) is not None
    assert [op for _, op, _ in frames(gateway.connections[0])] == [2, 1, 1, 1]


def test_a_heartbeat_asked_for_is_sent_at_once(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    gateway.plans.append({"then": ("heartbeat",)})
    run(gateway, store, settings, FakeDiscord())
    assert frames(gateway.connections[0])[:3] == [
        (0.0, 2, IDENTIFY["d"]),
        (0.0, 1, 1),
        (10.3125, 1, 1),
    ]


@pytest.mark.parametrize(
    ("plan", "closed_with"),
    [
        ({"no_ack": True}, 4000),
        ({"then": ("reconnect",)}, 4000),
        ({"then": ("close", 1006)}, None),
        ({"then": ("invalid", True)}, 4000),
    ],
    ids=["no-ack", "reconnect-asked", "dropped", "resumable-invalid-session"],
)
def test_a_lost_connection_resumes_after_a_second(
    gateway: FakeGateway, store: Store, settings: Settings, plan: dict, closed_with: int | None
) -> None:
    gateway.plans.append(plan)
    run(gateway, store, settings, FakeDiscord())
    first, second = gateway.connections[:2]
    assert first.closed_with == closed_with
    assert gateway.sleeps[0] == 1
    assert second.url == RESUME_AT
    _, payload = second.sent[0]
    assert payload == {
        "op": 6,
        "d": {"token": "discord-token-test", "session_id": "session-1", "seq": 1},
    }


@pytest.mark.parametrize(
    "then",
    [("invalid", False), ("close", 1000), ("close", 1001)],
    ids=["invalid-session", "closed-1000", "closed-1001"],
)
def test_an_ended_session_identifies_again(
    gateway: FakeGateway, store: Store, settings: Settings, then: tuple
) -> None:
    gateway.plans.append({"then": then})
    run(gateway, store, settings, FakeDiscord())
    second = gateway.connections[1]
    assert second.url == GATEWAY
    assert second.sent[0][1] == IDENTIFY


def test_a_resume_address_outside_discord_is_never_used(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    gateway.resume_url = "wss://gateway.discord.gg.evil.test"
    gateway.plans.append({"then": ("close", 1006)})
    run(gateway, store, settings, FakeDiscord())
    second = gateway.connections[1]
    assert second.url == GATEWAY
    assert second.sent[0][1] == IDENTIFY


@pytest.mark.parametrize("code", [4004, 4010, 4011, 4012, 4013, 4014])
def test_a_fatal_close_stops_with_its_code(
    gateway: FakeGateway, store: Store, settings: Settings, code: int
) -> None:
    gateway.plans.append({"then": ("close", code)})
    with pytest.raises(GatewayStopped) as caught:
        run(gateway, store, settings, FakeDiscord())
    assert str(caught.value) == f"gateway stopped ({code})"
    assert caught.value.__suppress_context__
    assert len(gateway.connections) == 1


def test_a_wrong_token_stops_without_echoing_it(
    gateway: FakeGateway, store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = "revoked-token-xyz"
    with pytest.raises(GatewayStopped) as caught:
        run(gateway, store, settings, FakeDiscord())
    assert str(caught.value) == "gateway stopped (4004)"


def test_failed_connections_back_off_and_a_session_resets_the_wait(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    gateway.until = 400
    gateway.plans.extend([{"refuse": True}] * 8 + [{"then": ("close", 1006)}])
    run(gateway, store, settings, FakeDiscord())
    assert gateway.sleeps == [1, 2, 4, 8, 16, 32, 60, 60, 1]
    assert len(gateway.connections) == 10
    assert gateway.connections[9].sent[0][1]["op"] == 6


@pytest.mark.parametrize("missing", ["owner", "channel"])
def test_without_an_owner_or_channel_nothing_connects(
    gateway: FakeGateway, store: Store, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setenv(
        "MAILROOM_DISCORD_CHANNEL_ID", "" if missing == "channel" else "111111111111111111"
    )
    monkeypatch.setenv(
        "MAILROOM_DISCORD_OWNER_ID", "" if missing == "owner" else "444444444444444444"
    )
    with pytest.raises(DiscordUnavailable) as caught:
        run(gateway, store, get_settings(), FakeDiscord())
    assert str(caught.value) == "discord unavailable (not configured)"
    assert gateway.connections == []


def test_without_a_token_nothing_connects(
    gateway: FakeGateway, store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    fake_keychain.secrets.clear()
    with pytest.raises(SecretMissing):
        run(gateway, store, settings, FakeDiscord())
    assert gateway.connections == []
