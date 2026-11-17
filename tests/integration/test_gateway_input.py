"""Phase 4e contracts: untrusted wire shapes never become actions."""

import json
from copy import deepcopy

import httpx
import pytest

from mailroom.config import Settings
from mailroom.gateway import GatewayStopped, run_gateway
from mailroom.interactions import handle_interaction
from mailroom.store import Store
from tests.fakes import FakeDiscord, FakeGateway
from tests.integration.test_gateway import (
    GATEWAY,
    ITEM,
    RESUME_AT,
    Quarter,
    run,
)
from tests.integration.test_gateway import (
    gateway as gateway,
)
from tests.integration.test_gateway import (
    settings as settings,
)
from tests.integration.test_gateway import (
    store as store,
)


class Inject:
    def __init__(self, inner: object, raw: object, at: int) -> None:
        self.inner = inner
        self.raw = raw
        self.at = at
        self.calls = 0

    def recv(self, timeout: float | None = None) -> object:
        self.calls += 1
        if self.calls == self.at:
            if self.at == 1:
                self.inner.recv(timeout)  # Replace hello, rather than queueing a second hello.
            return self.raw
        return self.inner.recv(timeout)

    def send(self, message: str) -> None:
        self.inner.send(message)

    def close(self, code: int = 1000, reason: str = "") -> None:
        self.inner.close(code, reason)

    @property
    def close_code(self) -> int | None:
        return self.inner.close_code


def injected_run(
    gateway: FakeGateway, store: Store, settings: Settings, raw: object, at: int
) -> None:
    def connect(url: str) -> object:
        inner = gateway.connect(url)
        return Inject(inner, raw, at) if len(gateway.connections) == 1 else inner

    with httpx.Client(transport=httpx.MockTransport(FakeDiscord().handler)) as http:
        run_gateway(
            store,
            settings,
            http,
            connect=connect,
            sleep=gateway.sleep,
            rng=Quarter(),
            stop=lambda: gateway.done,
        )


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "null",
        "[]",
        '"text"',
        b"\xff",
        "{}",
        '{"op":true,"d":{"heartbeat_interval":41250}}',
        '{"op":11,"d":{"heartbeat_interval":41250}}',
        '{"op":10,"d":null}',
        '{"op":10,"d":{}}',
        '{"op":10,"d":{"heartbeat_interval":true}}',
        '{"op":10,"d":{"heartbeat_interval":0}}',
        '{"op":10,"d":{"heartbeat_interval":-1}}',
        '{"op":10,"d":{"heartbeat_interval":"41250"}}',
        '{"op":10,"d":{"heartbeat_interval":NaN}}',
        '{"op":10,"d":{"heartbeat_interval":Infinity}}',
        '{"op":10,"d":{"heartbeat_interval":1e100}}',
    ],
    ids=[
        "json",
        "null",
        "array",
        "scalar",
        "utf8",
        "no-op",
        "bool-op",
        "wrong-op",
        "data-null",
        "no-interval",
        "bool",
        "zero",
        "negative",
        "string",
        "nan",
        "inf",
        "overflow",
    ],
)
def test_bad_hello_reconnects_before_identify(
    gateway: FakeGateway, store: Store, settings: Settings, raw: object
) -> None:
    injected_run(gateway, store, settings, raw, 1)
    first, second = gateway.connections[:2]
    assert first.closed_with == 4000
    assert first.sent == []
    assert second.url == GATEWAY
    assert second.sent[0][1]["op"] == 2
    assert gateway.sleeps[0] == 1


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "null",
        "[]",
        b"\xff",
        "{}",
        '{"op":true}',
        '{"op":1.0}',
        '{"op":-1}',
        '{"op":11,"s":true}',
        '{"op":11,"s":-1}',
        '{"op":11,"s":"9"}',
        '{"op":0,"s":99,"t":"READY","d":null}',
        '{"op":0,"s":99,"t":"READY","d":{"session_id":0,"resume_gateway_url":"wss://gateway.discord.gg"}}',
        '{"op":0,"s":99,"t":null,"d":{}}',
        '{"op":9,"d":"true"}',
    ],
    ids=[
        "json",
        "null",
        "array",
        "utf8",
        "no-op",
        "bool-op",
        "float-op",
        "negative-op",
        "bool-seq",
        "negative-seq",
        "string-seq",
        "ready-null",
        "ready-id",
        "dispatch-name",
        "invalid-flag",
    ],
)
def test_bad_session_frame_resumes_without_poisoning_state(
    gateway: FakeGateway, store: Store, settings: Settings, raw: object
) -> None:
    injected_run(gateway, store, settings, raw, 3)
    first, second = gateway.connections[:2]
    assert first.closed_with == 4000
    assert second.url == RESUME_AT
    assert second.sent[0][1] == {
        "op": 6,
        "d": {"token": "discord-token-test", "session_id": "session-1", "seq": 1},
    }
    assert gateway.sleeps[0] == 1


@pytest.mark.parametrize("code", [1006, 4004])
def test_close_before_hello_uses_existing_close_policy(
    gateway: FakeGateway, store: Store, settings: Settings, code: int
) -> None:
    def connect(url: str) -> object:
        inner = gateway.connect(url)
        if len(gateway.connections) == 1:
            inner.close_code = code
            inner._outbox.clear()
        return inner

    with httpx.Client(transport=httpx.MockTransport(FakeDiscord().handler)) as http:
        args = dict(connect=connect, sleep=gateway.sleep, rng=Quarter(), stop=lambda: gateway.done)
        if code == 4004:
            with pytest.raises(GatewayStopped, match=r"^gateway stopped \(4004\)$"):
                run_gateway(store, settings, http, **args)
            assert len(gateway.connections) == 1
        else:
            run_gateway(store, settings, http, **args)
            assert gateway.connections[1].sent[0][1]["op"] == 2


class NoStore:
    def __getattr__(self, name: str) -> object:
        raise AssertionError("malformed input touched the store")


def call(event: object, settings: Settings) -> tuple[str, list[tuple[str, object]]]:
    requests = []

    def reply(request: httpx.Request) -> httpx.Response:
        requests.append((str(request.url), json.loads(request.content)))
        return httpx.Response(204)

    with httpx.Client(transport=httpx.MockTransport(reply)) as http:
        outcome = handle_interaction(event, NoStore(), settings, http)
    return outcome, requests


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("data",), None),
        (("data",), []),
        (("data", "custom_id"), 123),
        (("member",), None),
        (("member", "user"), []),
        (("member", "user", "id"), 444),
        (("channel_id",), None),
    ],
    ids=["data-null", "data-array", "custom-id", "member", "member-user", "user-id", "channel"],
)
def test_bad_component_acknowledges_without_reading_or_writing(
    settings: Settings, path: tuple[str, ...], value: object
) -> None:
    event = deepcopy(FakeDiscord().press(f"mr:notask:{ITEM}"))
    parent = event
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert call(event, settings) == (
        "ignored",
        [
            (
                "https://discord.com/api/v10/interactions/1400000000000000001/interaction-token-1/callback",
                {"type": 6},
            )
        ],
    )


@pytest.mark.parametrize(
    "components",
    [None, {}, [None], [{"component": None}], [{"component": {"custom_id": "title", "value": 12}}]],
)
def test_malformed_modal_container_acknowledges(settings: Settings, components: object) -> None:
    event = FakeDiscord().submit(f"mr:title:{ITEM}", "Synthetic title")
    event["data"]["components"] = components
    assert call(event, settings)[1] == [
        (
            "https://discord.com/api/v10/interactions/1400000000000000001/interaction-token-1/callback",
            {"type": 6},
        )
    ]


@pytest.mark.parametrize("options", [123, {}, [None], ["address"]])
def test_malformed_slash_options_get_private_constant_reply(
    settings: Settings, options: object
) -> None:
    event = FakeDiscord().command("trust", "sender@example.test")
    event["data"]["options"] = options
    assert call(event, settings) == (
        "ignored",
        [
            (
                "https://discord.com/api/v10/interactions/1400000000000000001/interaction-token-1/callback",
                {
                    "type": 4,
                    "data": {
                        "content": "This interaction is unavailable.",
                        "flags": 64,
                        "allowed_mentions": {"parse": []},
                    },
                },
            )
        ],
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", None),
        ("id", "../other"),
        ("id", "１２３"),
        ("token", None),
        ("token", ""),
        ("token", False),
        ("token", 12),
        ("token", []),
    ],
)
def test_unsafe_callback_address_never_sends(settings: Settings, field: str, value: object) -> None:
    event = FakeDiscord().press(f"mr:notask:{ITEM}")
    event[field] = value
    assert call(event, settings) == ("ignored", [])


@pytest.mark.parametrize("event", [None, [], "text", {}, {"type": True}, {"type": 999}])
def test_unaddressable_or_unknown_kind_is_ignored(settings: Settings, event: object) -> None:
    assert call(event, settings) == ("ignored", [])


def test_malformed_member_cannot_fall_back_to_owner(settings: Settings) -> None:
    event = FakeDiscord().press(f"mr:notask:{ITEM}")
    event["member"] = None
    event["user"] = {"id": "444444444444444444"}
    assert call(event, settings)[0] == "ignored"


def test_valid_owner_press_after_bad_event_still_works(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    discord = FakeDiscord()
    bad = discord.press(f"mr:notask:{ITEM}")
    bad["data"] = None
    gateway.events.extend(
        [("INTERACTION_CREATE", bad), ("INTERACTION_CREATE", discord.press(f"mr:notask:{ITEM}"))]
    )
    run(gateway, store, settings, discord)
    assert [body["type"] for _, body in discord.callbacks] == [6, 7]
    assert store.answer(ITEM).answer == "notask"


def test_unexpected_handler_bug_is_not_swallowed(
    gateway: FakeGateway, store: Store, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    class HandlerFault(Exception):
        pass

    def broken(*args: object) -> str:
        raise HandlerFault("synthetic bug")

    monkeypatch.setattr("mailroom.gateway.handle_interaction", broken)
    gateway.events.append(("INTERACTION_CREATE", FakeDiscord().press(f"mr:notask:{ITEM}")))
    with pytest.raises(HandlerFault):
        run(gateway, store, settings, FakeDiscord())


def test_opaque_token_is_escaped_as_one_callback_segment(settings: Settings) -> None:
    event = FakeDiscord().press(f"mr:notask:{ITEM}")
    event["data"] = None
    event["token"] = "synthetic/a?b%25"
    assert call(event, settings) == (
        "ignored",
        [
            (
                "https://discord.com/api/v10/interactions/1400000000000000001/"
                "synthetic%2Fa%3Fb%2525/callback",
                {"type": 6},
            )
        ],
    )
