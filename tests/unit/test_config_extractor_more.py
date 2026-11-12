import pytest

from mailroom.config import EXTRACTOR_URL_MESSAGE, ConfigError, get_settings


@pytest.mark.parametrize(
    "url",
    ["http://[::1]", "http://[::1]:11434", "http://localhost"],
    ids=["ipv6", "ipv6-port", "localhost"],
)
def test_a_loopback_address_is_accepted(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_URL", url)
    assert get_settings().extractor_url == url


def test_a_user_name_in_the_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_URL", "http://reader@127.0.0.1:11434")
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == EXTRACTOR_URL_MESSAGE
    assert "reader" not in str(caught.value)


def test_https_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_URL", "https://127.0.0.1:11434")
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == EXTRACTOR_URL_MESSAGE
