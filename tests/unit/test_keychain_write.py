import pytest
from keyring.errors import KeyringLocked

from mailroom.keychain import KeychainUnavailable, get_secret, set_secret
from tests.fakes import FakeKeychain


def test_a_secret_is_stored_under_the_mailroom_service(fake_keychain: FakeKeychain) -> None:
    set_secret("gmail.personal.refresh-token", "value-1")
    assert fake_keychain.writes == [("mailroom", "gmail.personal.refresh-token")]
    assert get_secret("gmail.personal.refresh-token") == "value-1"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [("Gmail.token", "value-1", "invalid secret name"), ("gmail.token", "", "empty secret value")],
    ids=["name", "empty"],
)
def test_a_bad_name_or_an_empty_value_is_refused_before_the_keychain(
    fake_keychain: FakeKeychain, name: str, value: str, message: str
) -> None:
    with pytest.raises(ValueError) as caught:
        set_secret(name, value)
    assert str(caught.value) == message
    assert fake_keychain.writes == []


def test_a_keychain_failure_names_only_the_secret(fake_keychain: FakeKeychain) -> None:
    fake_keychain.error = KeyringLocked("locked value-1")
    with pytest.raises(KeychainUnavailable) as caught:
        set_secret("gmail.token", "value-1")
    assert str(caught.value) == "keychain unavailable: gmail.token"
    assert caught.value.__suppress_context__
