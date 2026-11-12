import re

import keyring
from keyring.errors import KeyringError

SERVICE = "mailroom"
NAME_MESSAGE = "invalid secret name"
_NAME = re.compile(r"[a-z][a-z0-9._-]{0,63}")


class KeychainError(Exception):
    pass


class SecretMissing(KeychainError):
    pass


class KeychainUnavailable(KeychainError):
    pass


def get_secret(name: str) -> str:
    if _NAME.fullmatch(name) is None:
        raise ValueError(NAME_MESSAGE)
    try:
        value = keyring.get_password(SERVICE, name)
    except KeyringError:
        raise KeychainUnavailable(f"keychain unavailable: {name}") from None
    if value is None or value == "":
        raise SecretMissing(f"secret not found: {name}")
    return value
