import pytest

from mailroom.config import OUTLOOK_ACCOUNTS_MESSAGE, ConfigError, get_settings


def test_outlook_accounts_are_none_by_default_and_read_like_gmail_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert get_settings().outlook_accounts == ()
    monkeypatch.setenv("MAILROOM_OUTLOOK_ACCOUNTS", "live, work-2")
    assert get_settings().outlook_accounts == ("live", "work-2")
    monkeypatch.setenv("MAILROOM_OUTLOOK_ACCOUNTS", "")
    assert get_settings().outlook_accounts == ()


@pytest.mark.parametrize(
    "value",
    ["Live", "live,live", "live,,work", "a" * 33],
    ids=["upper", "twice", "empty-name", "long"],
)
def test_a_bad_outlook_account_list_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MAILROOM_OUTLOOK_ACCOUNTS", value)
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == OUTLOOK_ACCOUNTS_MESSAGE
    assert OUTLOOK_ACCOUNTS_MESSAGE == (
        "MAILROOM_OUTLOOK_ACCOUNTS must be account names separated by commas"
    )


def test_the_same_name_may_be_used_by_both_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_GMAIL_ACCOUNTS", "personal")
    monkeypatch.setenv("MAILROOM_OUTLOOK_ACCOUNTS", "personal")
    settings = get_settings()
    assert (settings.gmail_accounts, settings.outlook_accounts) == (("personal",), ("personal",))
