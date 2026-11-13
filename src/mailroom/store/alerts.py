from dataclasses import dataclass
from datetime import datetime
from typing import cast

from mailroom import clock, ids
from mailroom.store.base import StoreBase


@dataclass(frozen=True)
class Problem:
    key: str
    since: datetime
    alerted: bool


@dataclass(frozen=True)
class Alert:
    alert_id: str
    key: str
    text: str
    ping: bool
    queued_at: datetime
    discord_message_id: str | None
    posted_at: datetime | None


def _read_problem(row: tuple) -> Problem:
    key, since, alerted = row
    return Problem(key=key, since=StoreBase._read_time(since), alerted=bool(alerted))


def _read_alert(row: tuple) -> Alert:
    alert_id, key, text, ping, queued_at, discord_message_id, posted_at = row
    return Alert(
        alert_id=alert_id,
        key=key,
        text=text,
        ping=bool(ping),
        queued_at=StoreBase._read_time(queued_at),
        discord_message_id=discord_message_id,
        posted_at=None if posted_at is None else StoreBase._read_time(posted_at),
    )


class AlertStore(StoreBase):
    def problem(self, key: str) -> Problem | None:
        row = self._connection.execute(
            "SELECT key, since, alerted FROM problems WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return _read_problem(row)

    def open_problem(self, key: str) -> Problem:
        since = self._stamp(clock.now())
        with self._write():
            self._connection.execute(
                """
                INSERT INTO problems (key, since, alerted) VALUES (?, ?, 0)
                ON CONFLICT (key) DO NOTHING
                """,
                (key, since),
            )
            found = self.problem(key)
        return cast(Problem, found)

    def mark_alerted(self, key: str) -> None:
        with self._write():
            self._connection.execute("UPDATE problems SET alerted = 1 WHERE key = ?", (key,))

    def close_problem(self, key: str) -> Problem | None:
        with self._write():
            cursor = self._connection.execute(
                "DELETE FROM problems WHERE key = ? RETURNING key, since, alerted",
                (key,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return _read_problem(row)

    def queue_alert(self, key: str, text: str, ping: bool) -> bool:
        alert_id = ids.new_id()
        queued_at = self._stamp(clock.now())
        with self._write():
            cursor = self._connection.execute(
                """
                INSERT INTO alerts (
                    alert_id, key, text, ping, queued_at, discord_message_id, posted_at
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
                ON CONFLICT (key) DO NOTHING
                """,
                (alert_id, key, text, int(ping), queued_at),
            )
        return cursor.rowcount == 1

    def pending_alerts(self) -> tuple[Alert, ...]:
        rows = self._connection.execute(
            """
            SELECT alert_id, key, text, ping, queued_at, discord_message_id, posted_at
            FROM alerts
            WHERE posted_at IS NULL
            ORDER BY queued_at, rowid
            """
        ).fetchall()
        return tuple(_read_alert(row) for row in rows)

    def mark_alert_posted(self, alert_id: str, discord_message_id: str) -> bool:
        posted_at = self._stamp(clock.now())
        with self._write():
            cursor = self._connection.execute(
                """
                UPDATE alerts
                SET discord_message_id = ?, posted_at = ?
                WHERE alert_id = ? AND posted_at IS NULL
                """,
                (discord_message_id, posted_at, alert_id),
            )
        return cursor.rowcount == 1
