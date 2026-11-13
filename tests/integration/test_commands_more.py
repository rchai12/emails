"""Coverage for command edges the given tests leave closed."""

from collections.abc import Iterator

import httpx
import pytest

from mailroom import discord_post
from mailroom.commands import register_commands
from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.store import Store, open_store
from tests.fakes import FakeDiscord, FakeKeychain
from tests.integration.test_commands import use
from tests.support import run

GUILD = "333333333333333333"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


@pytest.fixture
def guild(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_GUILD_ID", GUILD)
    return get_settings()


@pytest.fixture
def discord(fake_keychain: FakeKeychain) -> FakeDiscord:
    fake = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    return fake


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        opened.set_sender_status("trusted@example.test", "trusted")
        opened.set_sender_status("muted@example.test", "muted")
        yield opened


def test_an_application_without_a_string_id_is_a_bad_response(
    guild: Settings, discord: FakeDiscord
) -> None:
    discord.failures.append(httpx.Response(200, json={"id": 222222222222222222}))
    with pytest.raises(DiscordUnavailable) as caught:
        register_commands(guild, httpx.Client(transport=httpx.MockTransport(discord.handler)))
    assert str(caught.value) == "discord unavailable (response)"
    assert discord.commands == []


def test_a_command_list_that_is_not_a_list_is_a_bad_response(
    guild: Settings, discord: FakeDiscord
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, json={"ok": True})
        return discord.handler(request)

    with pytest.raises(DiscordUnavailable) as caught:
        register_commands(guild, httpx.Client(transport=httpx.MockTransport(handler)))
    assert str(caught.value) == "discord unavailable (response)"
    assert discord.commands == []


def test_a_body_that_is_not_json_is_a_bad_response(guild: Settings, discord: FakeDiscord) -> None:
    discord.failures.append(httpx.Response(200, text="nope"))
    with pytest.raises(DiscordUnavailable) as caught:
        register_commands(guild, httpx.Client(transport=httpx.MockTransport(discord.handler)))
    assert str(caught.value) == "discord unavailable (response)"
    assert discord.commands == []


def test_an_address_option_that_is_not_a_string(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    event = discord.command("trust", "sam@example.test")
    event["data"]["options"] = [{"type": 3, "name": "address", "value": 12}]
    outcome, reply = use(store, settings, event, discord)
    assert outcome == "bad-address"
    assert reply["data"]["content"] == "That is not an email address."
    assert store.senders("trusted") == ("trusted@example.test",)
    assert store.senders("muted") == ("muted@example.test",)


def test_an_address_command_without_the_address_option(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    event = discord.command("untrust")
    event["data"]["options"] = [{"type": 3, "name": "note", "value": "trusted@example.test"}]
    outcome, _ = use(store, settings, event, discord)
    assert outcome == "bad-address"
    assert store.sender_status("trusted@example.test") == "trusted"


def test_the_setup_command_reports_a_missing_token(
    monkeypatch: pytest.MonkeyPatch, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    monkeypatch.setenv("MAILROOM_DISCORD_GUILD_ID", GUILD)
    fake_keychain.secrets.clear()
    monkeypatch.setattr(
        discord_post,
        "open_discord_http",
        lambda: httpx.Client(transport=httpx.MockTransport(discord.handler)),
    )
    result = run("discord-commands")
    assert (result.exit_code, result.output) == (1, "secret not found: discord.bot-token\n")
    assert discord.requests == []


def test_a_direct_message_uses_the_user_id(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    event = discord.command("trust", "Sam@Example.TEST")
    event["user"] = event["member"]["user"]
    del event["member"]
    outcome, reply = use(store, settings, event, discord)
    assert outcome == "trusted"
    assert reply["data"]["flags"] == 64
    assert store.sender_status("sam@example.test") == "trusted"
