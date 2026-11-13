import pytest

from mailroom.config import ConfigError, get_settings

ACCOUNTS_MESSAGE = "MAILROOM_GMAIL_ACCOUNTS must be account names separated by commas"
POLL_MESSAGE = "MAILROOM_POLL_SECONDS must be a whole number from 30 to 600"


def test_the_service_settings_default_to_no_accounts_and_a_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    assert (settings.gmail_accounts, settings.poll_seconds) == ((), 60)
    monkeypatch.setenv("MAILROOM_GMAIL_ACCOUNTS", "personal, work-2")
    monkeypatch.setenv("MAILROOM_POLL_SECONDS", "120")
    settings = get_settings()
    assert (settings.gmail_accounts, settings.poll_seconds) == (("personal", "work-2"), 120)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MAILROOM_GMAIL_ACCOUNTS", "Personal", ACCOUNTS_MESSAGE),
        ("MAILROOM_GMAIL_ACCOUNTS", "personal,,work", ACCOUNTS_MESSAGE),
        ("MAILROOM_GMAIL_ACCOUNTS", "personal,personal", ACCOUNTS_MESSAGE),
        ("MAILROOM_POLL_SECONDS", "29", POLL_MESSAGE),
        ("MAILROOM_POLL_SECONDS", "601", POLL_MESSAGE),
        ("MAILROOM_POLL_SECONDS", "1.5", POLL_MESSAGE),
    ],
    ids=["capital", "empty-name", "repeated", "too-often", "too-rare", "fraction"],
)
def test_a_bad_service_setting_is_refused_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == message
