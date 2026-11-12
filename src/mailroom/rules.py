from dataclasses import dataclass
from typing import Literal

from mailroom.record import Record
from mailroom.sender_auth import verified
from mailroom.store import Store


@dataclass(frozen=True)
class Screening:
    action: Literal["drop", "extract"]
    trusted: bool
    verified: bool
    bulk: bool


def screen(record: Record, store: Store) -> Screening:
    is_verified = verified(record)
    status = None if record.sender == "" else store.sender_status(record.sender)
    return Screening(
        action="drop" if status == "muted" else "extract",
        trusted=status == "trusted" and is_verified,
        verified=is_verified,
        bulk=record.list_unsubscribe,
    )
