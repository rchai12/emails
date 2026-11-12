import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mailroom import clock
from mailroom.config import Settings, prepare_data_dir
from mailroom.record import Record
from mailroom.schema import MIGRATIONS

DB_FILENAME = "mailroom.sqlite3"
SCHEMA_MESSAGE = "unsupported schema version"
TEXT_RETENTION = timedelta(hours=24)

_INSERT = """
INSERT INTO messages (
    provider, message_id, thread_id, received_at, link,
    sender, sender_name, subject, sent_at, list_unsubscribe,
    body_text, authentication_results, fetched_at, text_cleared_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
ON CONFLICT DO NOTHING
"""

_SELECT = """
SELECT provider, message_id, thread_id, received_at, link,
       sender, sender_name, subject, sent_at, list_unsubscribe,
       body_text, authentication_results, fetched_at, text_cleared_at
FROM messages
WHERE provider = ? AND message_id = ?
"""

_CLEAR = """
UPDATE messages
SET body_text = NULL, authentication_results = NULL, text_cleared_at = ?
WHERE text_cleared_at IS NULL AND fetched_at <= ?
"""


class StoreError(Exception):
    pass


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _read_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class StoredMessage:
    record: Record
    fetched_at: datetime
    text_cleared_at: datetime | None


class Store:
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA secure_delete = ON")
        path.chmod(0o600)
        self._migrate()

    def _migrate(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version > len(MIGRATIONS):
            self.close()
            raise StoreError(f"{SCHEMA_MESSAGE}: {version}")
        for index in range(version, len(MIGRATIONS)):
            pragma = f"PRAGMA user_version = {index + 1};"
            script = "BEGIN;\n" + MIGRATIONS[index] + "\n" + pragma + "\nCOMMIT;"
            self._connection.executescript(script)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def add(self, record: Record) -> bool:
        fetched_at = clock.now()
        sent_at = None if record.sent_at is None else _stamp(record.sent_at)
        cursor = self._connection.execute(
            _INSERT,
            (
                record.provider,
                record.message_id,
                record.thread_id,
                _stamp(record.received_at),
                record.link,
                record.sender,
                record.sender_name,
                record.subject,
                sent_at,
                1 if record.list_unsubscribe else 0,
                record.body_text,
                json.dumps(list(record.authentication_results)),
                _stamp(fetched_at),
            ),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def get(self, provider: str, message_id: str) -> StoredMessage | None:
        row = self._connection.execute(_SELECT, (provider, message_id)).fetchone()
        if row is None:
            return None
        (
            found_provider,
            found_id,
            thread_id,
            received_at,
            link,
            sender,
            sender_name,
            subject,
            sent_at,
            list_unsubscribe,
            body_text,
            authentication_results,
            fetched_at,
            text_cleared_at,
        ) = row
        record = Record(
            provider=found_provider,
            message_id=found_id,
            thread_id=thread_id,
            received_at=_read_time(received_at),
            link=link,
            sender=sender,
            sender_name=sender_name,
            subject=subject,
            sent_at=None if sent_at is None else _read_time(sent_at),
            body_text="" if body_text is None else body_text,
            list_unsubscribe=bool(list_unsubscribe),
            authentication_results=(
                () if authentication_results is None else tuple(json.loads(authentication_results))
            ),
        )
        return StoredMessage(
            record=record,
            fetched_at=_read_time(fetched_at),
            text_cleared_at=None if text_cleared_at is None else _read_time(text_cleared_at),
        )

    def clear_expired_text(self) -> int:
        now = clock.now()
        cursor = self._connection.execute(_CLEAR, (_stamp(now), _stamp(now - TEXT_RETENTION)))
        self._connection.commit()
        return cursor.rowcount


def open_store(settings: Settings) -> Store:
    return Store(prepare_data_dir(settings) / DB_FILENAME)
