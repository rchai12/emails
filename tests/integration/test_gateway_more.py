"""Coverage for Gateway edges the given tests leave closed."""

from collections.abc import Iterator

import httpx
import pytest
from websockets.exceptions import ConnectionClosedError, WebSocketException
from websockets.frames import Close

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.gateway import GatewayStopped, gateway_url_allowed, run_gateway
from mailroom.store import Store, open_store
from tests.fakes import FakeDiscord, FakeGateway, FakeKeychain
from tests.integration.test_gateway import (
    GATEWAY,
    IDENTIFY,
    ITEM,
    RECORD,
    RESUME_AT,
    VERDICT,
    Quarter,
)
from tests.support import fixed_ids


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


def _http() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(FakeDiscord().handler))


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("wss://gateway.discord.gg", True),
        ("wss://gateway.discord.gg/", True),
        ("wss://GATEWAY.DISCORD.GG/?v=10&encoding=json", True),
        ("wss://gateway.discord.gg/?v=9&encoding=json", False),
        ("wss://gateway.discord.gg/?v=10&encoding=json#frag", False),
        ("wss://user:secret@gateway.discord.gg/?v=10&encoding=json", False),
        ("wss://gateway.discord.gg:99999/?v=10&encoding=json", False),
        ("wss://", False),
    ],
    ids=[
        "empty-path",
        "empty-query",
        "upper-case-host",
        "bad-query",
        "fragment",
        "password",
        "port-out-of-range",
        "missing-host",
    ],
)
def test_addresses_outside_the_given_cases(url: str, allowed: bool) -> None:
    assert gateway_url_allowed(url) is allowed


def test_no_hello_closes_with_4000_and_the_next_connection_resumes(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    gateway.until = 80
    gateway.plans.append({"then": ("close", 1006)})

    def connect(url: str) -> object:
        connection = gateway.connect(url)
        if len(gateway.connections) == 2:
            connection._outbox.clear()
        return connection

    run_gateway(
        store,
        settings,
        _http(),
        connect=connect,
        sleep=gateway.sleep,
        rng=Quarter(),
        stop=lambda: gateway.done,
    )
    assert gateway.connections[1].closed_with == 4000
    assert gateway.connections[1].sent == []
    assert gateway.connections[2].url == RESUME_AT
    assert gateway.connections[2].sent[0][1] == {
        "op": 6,
        "d": {"token": "discord-token-test", "session_id": "session-1", "seq": 1},
    }


def test_a_send_that_finds_the_socket_closed_resumes(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    class SendCloses:
        def __init__(self, inner: object) -> None:
            self.inner = inner
            self.sent = 0

        def recv(self, timeout: float | None = None) -> str:
            return self.inner.recv(timeout)

        def close(self, code: int = 1000, reason: str = "") -> None:
            self.inner.close(code, reason)

        @property
        def close_code(self) -> int | None:
            return self.inner.close_code

        def send(self, message: str) -> None:
            self.sent += 1
            if self.sent == 2:
                self.inner.close_code = 1006
                raise ConnectionClosedError(Close(1006, ""), None)
            self.inner.send(message)

    opened = {"n": 0}

    def connect(url: str) -> object:
        opened["n"] += 1
        connection = gateway.connect(url)
        if opened["n"] == 1:
            return SendCloses(connection)
        return connection

    run_gateway(
        store,
        settings,
        _http(),
        connect=connect,
        sleep=gateway.sleep,
        rng=Quarter(),
        stop=lambda: gateway.done,
    )
    assert gateway.sleeps[0] == 1
    assert len(gateway.connections) == 2
    assert gateway.connections[1].sent[0][1]["op"] == 6


def test_a_closed_identify_reconnects_without_a_session(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    class SendCloses:
        def __init__(self, inner: object) -> None:
            self.inner = inner

        def recv(self, timeout: float | None = None) -> str:
            return self.inner.recv(timeout)

        def close(self, code: int = 1000, reason: str = "") -> None:
            self.inner.close(code, reason)

        @property
        def close_code(self) -> int | None:
            return self.inner.close_code

        def send(self, message: str) -> None:
            self.inner.close_code = 1006
            raise ConnectionClosedError(Close(1006, ""), None)

    opened = {"n": 0}

    def connect(url: str) -> object:
        opened["n"] += 1
        connection = gateway.connect(url)
        if opened["n"] == 1:
            return SendCloses(connection)
        return connection

    run_gateway(
        store,
        settings,
        _http(),
        connect=connect,
        sleep=gateway.sleep,
        rng=Quarter(),
        stop=lambda: gateway.done,
    )
    assert gateway.sleeps[0] == 1
    assert gateway.connections[1].url == GATEWAY
    assert gateway.connections[1].sent[0][1] == IDENTIFY


def test_a_bad_frame_and_an_unknown_op_are_ignored(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    class Noise:
        def __init__(self, inner: object) -> None:
            self.inner = inner
            self.pending = ["{", '{"op": 99, "d": null}']
            self.saw_hello = False

        def recv(self, timeout: float | None = None) -> str:
            if self.saw_hello and self.pending:
                return self.pending.pop(0)
            raw = self.inner.recv(timeout)
            self.saw_hello = True
            return raw

        def send(self, message: str) -> None:
            self.inner.send(message)

        def close(self, code: int = 1000, reason: str = "") -> None:
            self.inner.close(code, reason)

    run_gateway(
        store,
        settings,
        _http(),
        connect=lambda url: Noise(gateway.connect(url)),
        sleep=gateway.sleep,
        rng=Quarter(),
        stop=lambda: gateway.done,
    )
    connection = gateway.connections[0]
    assert [(at, payload["op"], payload.get("d")) for at, payload in connection.sent] == [
        (0.0, 2, IDENTIFY["d"]),
        (10.3125, 1, 1),
        (51.5625, 1, 1),
        (92.8125, 1, 1),
    ]
    assert connection.closed_with == 1000


def test_stop_at_the_start_opens_nothing(
    gateway: FakeGateway, store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    run_gateway(
        store,
        settings,
        _http(),
        connect=gateway.connect,
        sleep=gateway.sleep,
        rng=Quarter(),
        stop=lambda: True,
    )
    assert gateway.connections == []
    assert gateway.sleeps == []
    assert fake_keychain.calls == [("mailroom", "discord.bot-token")]


def test_a_websocket_error_while_connecting_backs_off(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    attempts = {"n": 0}

    def connect(url: str) -> object:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise WebSocketException("down")
        return gateway.connect(url)

    run_gateway(
        store,
        settings,
        _http(),
        connect=connect,
        sleep=gateway.sleep,
        rng=Quarter(),
        stop=lambda: gateway.done,
    )
    assert gateway.sleeps == [1]
    assert len(gateway.connections) == 1
    assert gateway.connections[0].sent[0][1]["op"] == 2


def test_the_default_stop_runs_until_a_fatal_close(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    gateway.plans.append({"then": ("close", 4004)})
    with pytest.raises(GatewayStopped) as caught:
        run_gateway(
            store, settings, _http(), connect=gateway.connect, sleep=gateway.sleep, rng=Quarter()
        )
    assert str(caught.value) == "gateway stopped (4004)"
    assert len(gateway.connections) == 1
