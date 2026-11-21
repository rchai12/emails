"""Phase 4e: Gateway frame validation and recovery."""

import json

import pytest

from mailroom.config import Settings
from mailroom.store import Store
from tests.fakes import FakeDiscord, FakeGateway
from tests.integration.test_gateway import GATEWAY, RESUME_AT, run
from tests.integration.test_gateway import gateway as gateway
from tests.integration.test_gateway import settings as settings
from tests.integration.test_gateway import store as store
from tests.integration.test_gateway_input import injected_run

DEEP = "[" * 100000 + "]" * 100000
HUGE = '{"op":10,"d":{"heartbeat_interval":' + "9" * 5000 + "}}"


@pytest.mark.parametrize(
    "raw",
    [
        DEEP,
        HUGE,
        '{"op":10,"d":{"heartbeat_interval":0.0001}}',
        '{"op":10,"d":{"heartbeat_interval":1e20}}',
        '{"op":10,"s":3,"d":{"heartbeat_interval":41250}}',
        '{"op":10,"t":"X","d":{"heartbeat_interval":41250}}',
    ],
    ids=["deep", "huge-int", "sub-microsecond", "overflow", "seq", "name"],
)
def test_more_bad_hellos_reconnect_before_identify(
    gateway: FakeGateway, store: Store, settings: Settings, raw: str
) -> None:
    injected_run(gateway, store, settings, raw, 1)
    first, second = gateway.connections[:2]
    assert first.closed_with == 4000
    assert first.sent == []
    assert second.url == GATEWAY


@pytest.mark.parametrize(
    "raw",
    [
        DEEP,
        '{"op":11,"t":"READY"}',
        '{"op":11,"s":1}',
        '{"op":0,"s":-1,"t":"X","d":{}}',
        '{"op":0,"s":1.0,"t":"X","d":{}}',
        '{"op":0,"s":99,"t":"","d":{}}',
        '{"op":0,"s":99,"t":5,"d":{}}',
        '{"op":0,"s":99,"t":"X","d":[]}',
        '{"op":0,"s":99,"t":"READY","d":{"session_id":"","resume_gateway_url":"wss://gateway.discord.gg"}}',
        '{"op":0,"s":99,"t":"READY","d":{"session_id":"x","resume_gateway_url":5}}',
        '{"op":0,"s":99,"t":"READY","d":{"session_id":"x"}}',
        '{"op":9,"d":null}',
        '{"op":9}',
    ],
)
def test_more_bad_frames_resume_with_the_last_good_state(
    gateway: FakeGateway, store: Store, settings: Settings, raw: str
) -> None:
    injected_run(gateway, store, settings, raw, 3)
    first, second = gateway.connections[:2]
    assert first.closed_with == 4000
    assert second.url == RESUME_AT
    assert second.sent[0][1]["d"]["seq"] == 1


def test_a_valid_fractional_interval_and_utf8_bytes_are_accepted(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    raw = json.dumps({"op": 10, "d": {"heartbeat_interval": 41250.5}}).encode()
    injected_run(gateway, store, settings, raw, 1)
    assert len(gateway.connections) == 1
    assert gateway.connections[0].sent[0][1]["op"] == 2


def test_an_unknown_dispatch_and_invalid_session_false_are_still_handled(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    injected_run(gateway, store, settings, '{"op":9,"d":false}', 3)
    first, second = gateway.connections[:2]
    assert first.closed_with == 4000
    assert second.url == GATEWAY


def test_a_ready_with_a_foreign_resume_address_still_clears_resume(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    gateway.resume_url = "wss://elsewhere.example.test"
    gateway.plans = [{"then": ("close", 1006)}]
    run(gateway, store, settings, FakeDiscord())
    assert gateway.connections[1].url == GATEWAY
