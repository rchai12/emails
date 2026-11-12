import pytest

from mailroom.config import ConfigError, get_settings

CHANNEL_MESSAGE = "MAILROOM_DISCORD_CHANNEL_ID must be a Discord channel id (17 to 20 digits)"


def test_the_channel_defaults_to_empty_and_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert get_settings().discord_channel_id == ""
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    assert get_settings().discord_channel_id == "111111111111111111"


@pytest.mark.parametrize(
    "channel",
    [
        "1111111111111111",
        "111111111111111111111",
        "11111111111111111a",
        "１１１１１１１１１１１１１１１１１",
    ],
    ids=["too-short", "too-long", "letter", "wide-digits"],
)
def test_a_channel_that_is_not_an_id_is_refused_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, channel: str
) -> None:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", channel)
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == CHANNEL_MESSAGE
