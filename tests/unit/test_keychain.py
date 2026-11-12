import keyring.core
import pytest
from keyring.errors import KeyringError, KeyringLocked

from mailroom.keychain import (
    NAME_MESSAGE,
    SERVICE,
    KeychainError,
    KeychainUnavailable,
    SecretMissing,
    get_secret,
)
from tests.fakes import FakeKeychain


def test_the_service_name_is_mailroom() -> None:
    assert SERVICE == "mailroom"


def test_a_stored_secret_is_returned(fake_keychain: FakeKeychain) -> None:
    fake_keychain.secrets[("mailroom", "gmail.token")] = "value-1"
    assert get_secret("gmail.token") == "value-1"
    assert fake_keychain.calls == [("mailroom", "gmail.token")]


def test_a_missing_secret_names_only_its_key(fake_keychain: FakeKeychain) -> None:
    with pytest.raises(SecretMissing) as raised:
        get_secret("gmail.token")
    assert str(raised.value) == "secret not found: gmail.token"
    assert isinstance(raised.value, KeychainError)


def test_an_empty_secret_is_missing(fake_keychain: FakeKeychain) -> None:
    fake_keychain.secrets[("mailroom", "gmail.token")] = ""
    with pytest.raises(SecretMissing) as raised:
        get_secret("gmail.token")
    assert str(raised.value) == "secret not found: gmail.token"


@pytest.mark.parametrize(
    "error",
    [KeyringError("backend said value-1"), KeyringLocked("locked, value-1")],
    ids=["error", "locked"],
)
def test_a_keychain_failure_hides_the_backend_text(
    fake_keychain: FakeKeychain, error: Exception
) -> None:
    fake_keychain.error = error
    with pytest.raises(KeychainUnavailable) as raised:
        get_secret("gmail.token")
    assert str(raised.value) == "keychain unavailable: gmail.token"
    assert isinstance(raised.value, KeychainError)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


def test_without_a_fake_the_real_keychain_is_never_reached() -> None:
    with pytest.raises(KeychainUnavailable) as raised:
        get_secret("gmail.token")
    assert str(raised.value) == "keychain unavailable: gmail.token"


@pytest.mark.parametrize(
    "name",
    ["", "Gmail", "gmail token", "gmail/token", "../gmail", "-gmail", "a" * 65],
    ids=["empty", "capital", "space", "slash", "dots", "dash-first", "too-long"],
)
def test_an_invalid_name_is_refused_before_the_keychain(
    fake_keychain: FakeKeychain, name: str
) -> None:
    with pytest.raises(ValueError) as raised:
        get_secret(name)
    assert str(raised.value) == NAME_MESSAGE == "invalid secret name"
    assert fake_keychain.calls == []


@pytest.mark.parametrize(
    "name",
    ["gmail.token", "yahoo.app-password", "discord_bot", "a" * 64],
    ids=["dot", "dash", "underscore", "longest"],
)
def test_valid_names(fake_keychain: FakeKeychain, name: str) -> None:
    fake_keychain.secrets[("mailroom", name)] = "value-1"
    assert get_secret(name) == "value-1"


def test_the_backend_is_looked_up_on_each_call(
    fake_keychain: FakeKeychain, monkeypatch: pytest.MonkeyPatch
) -> None:
    replaced = FakeKeychain()
    replaced.secrets[("mailroom", "gmail.token")] = "value-2"
    monkeypatch.setattr(keyring.core, "_keyring_backend", replaced)
    assert get_secret("gmail.token") == "value-2"
    assert fake_keychain.calls == []
