"""The normalized record every adapter produces, and what an adapter knows before parsing.

Triage reads only `Record`, so it never knows which provider a message came from. The fields an
adapter takes from its provider form the `Envelope`; `mailroom.mime.parse_message` adds the rest
from the raw message.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Provider = Literal["gmail", "outlook", "yahoo"]
PROVIDERS: tuple[str, ...] = ("gmail", "outlook", "yahoo")
ID_LIMIT = 1000
LINK_LIMIT = 2000
FIELD_MESSAGE = "invalid record field"


def _is_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= ID_LIMIT
        and value.isprintable()
        and " " not in value
    )


def _is_link(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("https://")
        and len(value) <= LINK_LIMIT
        and value.isprintable()
        and " " not in value
    )


def _is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.utcoffset() is not None


def _check_envelope(
    provider: object, message_id: object, thread_id: object, received_at: object, link: object
) -> None:
    checks = (
        ("provider", provider in PROVIDERS),
        ("message_id", _is_id(message_id)),
        ("thread_id", _is_id(thread_id)),
        ("received_at", _is_aware(received_at)),
        ("link", _is_link(link)),
    )
    for name, ok in checks:
        if not ok:
            raise ValueError(f"{FIELD_MESSAGE}: {name}")


@dataclass(frozen=True)
class Envelope:
    """What the adapter knows from the provider, before the raw message is parsed."""

    provider: Provider
    message_id: str
    thread_id: str
    received_at: datetime
    link: str

    def __post_init__(self) -> None:
        _check_envelope(self.provider, self.message_id, self.thread_id, self.received_at, self.link)


@dataclass(frozen=True)
class Record:
    """One email, as triage sees it. Every string field is untrusted plain text."""

    provider: Provider
    message_id: str
    thread_id: str
    received_at: datetime
    link: str
    sender: str
    sender_name: str
    subject: str
    sent_at: datetime | None
    body_text: str
    list_unsubscribe: bool
    authentication_results: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_envelope(self.provider, self.message_id, self.thread_id, self.received_at, self.link)
        if self.sent_at is not None and not _is_aware(self.sent_at):
            raise ValueError(f"{FIELD_MESSAGE}: sent_at")
