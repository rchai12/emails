import pytest

from mailroom.config import ConfigError, get_settings

GUILD_MESSAGE = "MAILROOM_DISCORD_GUILD_ID must be a Discord server id (17 to 20 digits)"


def test_the_server_defaults_to_empty_and_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert get_settings().discord_guild_id == ""
    monkeypatch.setenv("MAILROOM_DISCORD_GUILD_ID", "333333333333333333")
    assert get_settings().discord_guild_id == "333333333333333333"


@pytest.mark.parametrize(
    "guild",
    ["3333", "33333333333333333a", "３３３３３３３３３３３３３３３３３"],
    ids=["too-short", "letter", "wide-digits"],
)
def test_a_server_that_is_not_an_id_is_refused_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, guild: str
) -> None:
    monkeypatch.setenv("MAILROOM_DISCORD_GUILD_ID", guild)
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == GUILD_MESSAGE
