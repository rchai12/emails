import re
from typing import Literal, cast

from mailroom.store.base import StoreBase

SENDER_MESSAGE = "invalid sender address"
STATUS_MESSAGE = "invalid sender status"

_SENDER = re.compile(r"[^@\s]+@[^@\s]+")
_STATUSES = ("trusted", "muted")


def _sender_address(address: str) -> str:
    lowered = address.lower()
    if _SENDER.fullmatch(lowered) is None or len(lowered) > 254:
        raise ValueError(SENDER_MESSAGE)
    return lowered


def _sender_status(status: str) -> Literal["trusted", "muted"]:
    if status not in _STATUSES:
        raise ValueError(STATUS_MESSAGE)
    return cast(Literal["trusted", "muted"], status)


class SenderStore(StoreBase):
    def sender_status(self, address: str) -> Literal["trusted", "muted"] | None:
        row = self._connection.execute(
            "SELECT status FROM senders WHERE address = ?",
            (_sender_address(address),),
        ).fetchone()
        if row is None:
            return None
        return _sender_status(row[0])

    def set_sender_status(self, address: str, status: Literal["trusted", "muted"] | None) -> None:
        lowered = _sender_address(address)
        with self._write():
            if status is None:
                self._connection.execute("DELETE FROM senders WHERE address = ?", (lowered,))
            else:
                stored = _sender_status(status)
                self._connection.execute(
                    """
                    INSERT INTO senders (address, status) VALUES (?, ?)
                    ON CONFLICT (address) DO UPDATE SET status = excluded.status
                    """,
                    (lowered, stored),
                )

    def senders(self, status: Literal["trusted", "muted"]) -> tuple[str, ...]:
        stored = _sender_status(status)
        rows = self._connection.execute(
            "SELECT address FROM senders WHERE status = ? ORDER BY address",
            (stored,),
        ).fetchall()
        return tuple(row[0] for row in rows)
