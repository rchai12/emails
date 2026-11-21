"""Phase 4e: interaction body validation."""

from copy import deepcopy

import httpx
import pytest

from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.interactions import handle_interaction
from mailroom.store import Store
from tests.fakes import FakeDiscord, FakeGateway
from tests.integration.test_gateway import ITEM, run
from tests.integration.test_gateway import gateway as gateway
from tests.integration.test_gateway import settings as settings
from tests.integration.test_gateway import store as store
from tests.integration.test_gateway_input import NoStore, call

CALLBACK = (
    "https://discord.com/api/v10/interactions/1400000000000000001/interaction-token-1/callback"
)
UNAVAILABLE = {
    "type": 4,
    "data": {
        "content": "This interaction is unavailable.",
        "flags": 64,
        "allowed_mentions": {"parse": []},
    },
}


def test_a_lone_surrogate_token_is_unaddressable(settings: Settings) -> None:
    event = FakeDiscord().press(f"mr:notask:{ITEM}")
    event["token"] = "\ud800"
    assert call(event, settings) == ("ignored", [])


@pytest.mark.parametrize("identifier", ["", "1" * 21, 5])
def test_bad_ids_never_send(settings: Settings, identifier: object) -> None:
    event = FakeDiscord().press(f"mr:notask:{ITEM}")
    event["id"] = identifier
    assert call(event, settings) == ("ignored", [])


@pytest.mark.parametrize("value", [123, [], None])
def test_a_bad_command_name_gets_the_private_reply(settings: Settings, value: object) -> None:
    event = FakeDiscord().command("trust", "sender@example.test")
    event["data"]["name"] = value
    assert call(event, settings) == ("ignored", [(CALLBACK, UNAVAILABLE)])


def test_a_bad_option_name_gets_the_private_reply(settings: Settings) -> None:
    event = FakeDiscord().command("trust", "sender@example.test")
    event["data"]["options"] = [{"name": 5, "value": "x"}]
    assert call(event, settings) == ("ignored", [(CALLBACK, UNAVAILABLE)])


def test_a_command_without_options_passes_the_shape_check(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    event = discord.command("trusted")
    assert handle_interaction(event, store, settings, http) != "ignored"


@pytest.mark.parametrize(
    "path",
    [("channel_id",), ("member", "user", "id"), ("data", "custom_id")],
)
def test_empty_strings_are_malformed(settings: Settings, path: tuple[str, ...]) -> None:
    event = deepcopy(FakeDiscord().press(f"mr:notask:{ITEM}"))
    parent = event
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = "" if path[-1] != "custom_id" else 5
    assert call(event, settings) == ("ignored", [(CALLBACK, {"type": 6})])


def test_a_direct_message_uses_the_top_level_user(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    event = discord.press(f"mr:notask:{ITEM}")
    event["user"] = event.pop("member")["user"]
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    assert handle_interaction(event, store, settings, http) == "answered"


def test_no_user_at_all_is_malformed(settings: Settings) -> None:
    event = FakeDiscord().press(f"mr:notask:{ITEM}")
    del event["member"]
    assert call(event, settings) == ("ignored", [(CALLBACK, {"type": 6})])


def test_the_malformed_reply_failure_reaches_direct_callers(settings: Settings) -> None:
    event = FakeDiscord().press(f"mr:notask:{ITEM}")
    event["data"] = None
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as http:
        with pytest.raises(DiscordUnavailable):
            handle_interaction(event, NoStore(), settings, http)


def test_the_malformed_reply_failure_does_not_stop_the_gateway(
    gateway: FakeGateway, store: Store, settings: Settings
) -> None:
    discord = FakeDiscord()
    bad = discord.press(f"mr:notask:{ITEM}")
    bad["data"] = None
    discord.failures.append(httpx.Response(500))
    gateway.events.extend(
        [("INTERACTION_CREATE", bad), ("INTERACTION_CREATE", discord.press(f"mr:notask:{ITEM}"))]
    )
    run(gateway, store, settings, discord)
    assert store.answer(ITEM).answer == "notask"


def test_an_empty_component_list_is_still_a_bad_title(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    event = discord.submit(f"mr:title:{ITEM}", "Synthetic title")
    event["data"]["components"] = []
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    assert handle_interaction(event, store, settings, http) == "bad-title"
    assert [body["type"] for _, body in discord.callbacks] == [4]
