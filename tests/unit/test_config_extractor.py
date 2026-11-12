import pytest

from mailroom.config import ConfigError, get_settings

URL_MESSAGE = (
    "MAILROOM_EXTRACTOR_URL must be http:// on 127.0.0.1, localhost or [::1], with no path"
)


def test_the_extractor_settings_default_to_a_local_ollama() -> None:
    settings = get_settings()
    assert settings.extractor_url == "http://127.0.0.1:11434"
    assert (settings.extractor_model, settings.time_zone) == ("", "")


def test_the_extractor_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_URL", "http://localhost:8080")
    monkeypatch.setenv("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    settings = get_settings()
    assert (settings.extractor_url, settings.extractor_model, settings.time_zone) == (
        "http://localhost:8080",
        "qwen-test:27b",
        "America/New_York",
    )


@pytest.mark.parametrize(
    "url",
    ["http://192.0.2.1:11434", "http://127.0.0.1:11434/api", "http://127.0.0.1:99999"],
    ids=["other-host", "path", "bad-port"],
)
def test_a_model_address_off_this_machine_is_refused(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_URL", url)
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == URL_MESSAGE


def test_an_unknown_time_zone_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "Mars/Base")
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == "MAILROOM_TIME_ZONE must be an IANA time zone name"
