import json

import httpx
import pytest

from mailroom import discord_layout as L
from mailroom import discord_post
from mailroom.commands import register_commands
from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.keychain import SecretMissing
from tests.fakes import FakeDiscord, FakeKeychain
from tests.support import run

GUILD = "333333333333333333"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_GUILD_ID", GUILD)
    return get_settings()


@pytest.fixture
def discord(fake_keychain: FakeKeychain) -> FakeDiscord:
    fake = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    return fake


def client(discord: FakeDiscord) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(discord.handler))


def test_the_five_commands_replace_the_servers_commands(
    settings: Settings, discord: FakeDiscord
) -> None:
    assert register_commands(settings, client(discord)) == 5
    looked_up, replaced = discord.requests
    assert (looked_up.method, str(looked_up.url)) == (
        "GET",
        "https://discord.com/api/v10/applications/@me",
    )
    assert (replaced.method, str(replaced.url)) == (
        "PUT",
        f"https://discord.com/api/v10/applications/222222222222222222/guilds/{GUILD}/commands",
    )
    for request in (looked_up, replaced):
        assert request.headers["authorization"] == "Bot discord-token-test"
        assert request.headers["user-agent"] == "DiscordBot (mailroom, 0.1.0)"
    assert json.loads(replaced.content) == list(L.COMMANDS)
    assert [command["name"] for command in discord.commands] == [
        "trust",
        "untrust",
        "trusted",
        "unmute",
        "muted",
    ]


def test_registering_twice_leaves_the_same_five(settings: Settings, discord: FakeDiscord) -> None:
    register_commands(settings, client(discord))
    assert register_commands(settings, client(discord)) == 5
    assert (len(discord.commands), discord.created) == (5, 5)


@pytest.mark.parametrize(
    ("failure", "detail"),
    [
        (httpx.Response(401, json={"message": "401: Unauthorized", "code": 0}), "401"),
        (httpx.ConnectError("refused"), "network"),
    ],
    ids=["unauthorized", "network"],
)
def test_a_failure_names_only_the_status(
    settings: Settings, discord: FakeDiscord, failure: object, detail: str
) -> None:
    discord.failures.append(failure)
    with pytest.raises(DiscordUnavailable) as caught:
        register_commands(settings, client(discord))
    assert str(caught.value) == f"discord unavailable ({detail})"
    assert caught.value.__suppress_context__
    assert discord.commands == []


def test_a_server_that_is_not_the_bots_is_refused(
    monkeypatch: pytest.MonkeyPatch, discord: FakeDiscord
) -> None:
    monkeypatch.setenv("MAILROOM_DISCORD_GUILD_ID", "999999999999999999")
    with pytest.raises(DiscordUnavailable) as caught:
        register_commands(get_settings(), client(discord))
    assert str(caught.value) == "discord unavailable (404)"


def test_without_a_server_or_token_nothing_is_sent(
    settings: Settings, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    with pytest.raises(DiscordUnavailable) as caught:
        register_commands(
            get_settings().model_copy(update={"discord_guild_id": ""}), client(discord)
        )
    assert str(caught.value) == "discord unavailable (not configured)"
    fake_keychain.secrets.clear()
    with pytest.raises(SecretMissing):
        register_commands(settings, client(discord))
    assert discord.requests == []


def test_the_setup_command_registers_and_reports(
    settings: Settings, discord: FakeDiscord, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(discord_post, "open_discord_http", lambda: client(discord))
    result = run("discord-commands")
    assert (result.exit_code, result.output) == (0, "Registered 5 commands in your server.\n")


def test_the_setup_command_reports_a_failure_without_detail(
    monkeypatch: pytest.MonkeyPatch, discord: FakeDiscord
) -> None:
    monkeypatch.setattr(discord_post, "open_discord_http", lambda: client(discord))
    result = run("discord-commands")
    assert (result.exit_code, result.output) == (1, "discord unavailable (not configured)\n")
    assert discord.requests == []
