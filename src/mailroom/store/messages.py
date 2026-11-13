import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from mailroom import clock
from mailroom.record import Record
from mailroom.store.base import StoreBase

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

_CLEAR_TRIAGE = """
UPDATE triage
SET extraction = NULL, text_cleared_at = ?
WHERE extraction IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM messages
      WHERE messages.provider = triage.provider
        AND messages.message_id = triage.message_id
        AND messages.fetched_at <= ?
  )
"""


@dataclass(frozen=True)
class StoredMessage:
    record: Record
    fetched_at: datetime
    text_cleared_at: datetime | None


class MessageStore(StoreBase):
    def add(self, record: Record) -> bool:
        fetched_at = clock.now()
        sent_at = None if record.sent_at is None else self._stamp(record.sent_at)
        with self._write():
            cursor = self._connection.execute(
                _INSERT,
                (
                    record.provider,
                    record.message_id,
                    record.thread_id,
                    self._stamp(record.received_at),
                    record.link,
                    record.sender,
                    record.sender_name,
                    record.subject,
                    sent_at,
                    1 if record.list_unsubscribe else 0,
                    record.body_text,
                    json.dumps(list(record.authentication_results)),
                    self._stamp(fetched_at),
                ),
            )
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
            received_at=self._read_time(received_at),
            link=link,
            sender=sender,
            sender_name=sender_name,
            subject=subject,
            sent_at=None if sent_at is None else self._read_time(sent_at),
            body_text="" if body_text is None else body_text,
            list_unsubscribe=bool(list_unsubscribe),
            authentication_results=(
                () if authentication_results is None else tuple(json.loads(authentication_results))
            ),
        )
        return StoredMessage(
            record=record,
            fetched_at=self._read_time(fetched_at),
            text_cleared_at=None if text_cleared_at is None else self._read_time(text_cleared_at),
        )

    def clear_expired_text(self) -> int:
        now = clock.now()
        stamp = self._stamp(now)
        cutoff = self._stamp(now - TEXT_RETENTION)
        with self._write():
            cursor = self._connection.execute(_CLEAR, (stamp, cutoff))
            self._connection.execute(_CLEAR_TRIAGE, (stamp, cutoff))
        return cursor.rowcount
