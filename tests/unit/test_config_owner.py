import pytest

from mailroom.config import ConfigError, get_settings

OWNER_MESSAGE = "MAILROOM_DISCORD_OWNER_ID must be a Discord user id (17 to 20 digits)"


def test_the_owner_defaults_to_empty_and_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert get_settings().discord_owner_id == ""
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    assert get_settings().discord_owner_id == "444444444444444444"


@pytest.mark.parametrize(
    "owner",
    ["4444", "44444444444444444a", "４４４４４４４４４４４４４４４４４"],
    ids=["too-short", "letter", "wide-digits"],
)
def test_an_owner_that_is_not_an_id_is_refused_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, owner: str
) -> None:
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", owner)
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == OWNER_MESSAGE
