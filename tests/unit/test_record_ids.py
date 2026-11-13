import re

import pytest

from mailroom import config, gmail
from mailroom.record import ACCOUNT_PATTERN, FIELD_MESSAGE, account_of, stored_id


def test_the_account_pattern_is_the_one_settings_check() -> None:
    assert ACCOUNT_PATTERN == "[a-z][a-z0-9-]{0,31}"
    assert config._ACCOUNT.pattern == ACCOUNT_PATTERN
    assert gmail._ACCOUNT.pattern == ACCOUNT_PATTERN


@pytest.mark.parametrize(
    ("account", "provider_id", "expected"),
    [
        ("personal", "18c4f2a9b0d1e2f3", "personal/18c4f2a9b0d1e2f3"),
        ("work-2", "t1", "work-2/t1"),
        ("a" * 32, "m1", "a" * 32 + "/m1"),
        ("personal", "a/b", "personal/a/b"),
    ],
    ids=["gmail-id", "hyphen-and-digit", "longest-account", "slash-in-provider-id"],
)
def test_a_stored_id_is_the_account_a_slash_and_the_provider_id(
    account: str, provider_id: str, expected: str
) -> None:
    assert stored_id(account, provider_id) == expected


@pytest.mark.parametrize(
    "account",
    ["", "Personal", "2nd", "-work", "a" * 33, "my/mail", "per sonal", "personal\n"],
    ids=[
        "empty",
        "capital",
        "digit-first",
        "hyphen-first",
        "too-long",
        "slash",
        "space",
        "newline",
    ],
)
def test_a_stored_id_refuses_an_account_settings_would_refuse(account: str) -> None:
    with pytest.raises(ValueError) as caught:
        stored_id(account, "m1")
    assert str(caught.value) == f"{FIELD_MESSAGE}: account"
    assert re.fullmatch(ACCOUNT_PATTERN, account) is None


@pytest.mark.parametrize(
    ("message_id", "expected"),
    [
        ("personal/18c4f2a9b0d1e2f3", "personal"),
        ("work-2/a/b", "work-2"),
        ("a" * 32 + "/m1", "a" * 32),
        ("m1", None),
        ("/m1", None),
        ("Personal/m1", None),
        ("a" * 33 + "/m1", None),
        ("personal/", "personal"),
    ],
    ids=[
        "stored",
        "first-slash-only",
        "longest-account",
        "bare-provider-id",
        "empty-account",
        "capital",
        "too-long",
        "empty-provider-id",
    ],
)
def test_the_account_is_read_back_from_a_stored_id(message_id: str, expected: str | None) -> None:
    assert account_of(message_id) == expected
