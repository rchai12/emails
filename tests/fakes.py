"""Fakes for systems tests must never reach. They import nothing from mailroom."""

from keyring.backend import KeyringBackend
from keyring.compat import properties


class FakeKeychain(KeyringBackend):
    """An in-memory keychain. `secrets` maps (service, name) to a value.

    `calls` records every (service, name) asked for. When `error` is set, every call raises it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.secrets: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, str]] = []
        self.error: Exception | None = None

    @properties.classproperty
    def priority(cls) -> float:
        return 0

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append((service, username))
        if self.error is not None:
            raise self.error
        return self.secrets.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        raise AssertionError("mailroom never writes to the keychain in this phase")

    def delete_password(self, service: str, username: str) -> None:
        raise AssertionError("mailroom never deletes from the keychain in this phase")
