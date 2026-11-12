import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal, cast

from mailroom import clock, ids
from mailroom.config import Settings, prepare_data_dir
from mailroom.extractor import Deadline, Extraction
from mailroom.record import Record
from mailroom.schema import MIGRATIONS

DB_FILENAME = "mailroom.sqlite3"
SCHEMA_MESSAGE = "unsupported schema version"
TEXT_RETENTION = timedelta(hours=24)
SENDER_MESSAGE = "invalid sender address"
STATUS_MESSAGE = "invalid sender status"

_SENDER = re.compile(r"[^@\s]+@[^@\s]+")
_STATUSES = ("trusted", "muted")

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

_TRIAGE_INSERT = """
INSERT INTO triage (
    provider, message_id, outcome, reason, trusted, verified, bulk, notify,
    extraction, decided_at, text_cleared_at
)
SELECT provider, message_id, ?, ?, ?, ?, ?, ?, ?, ?, NULL
FROM messages
WHERE provider = ? AND message_id = ? AND text_cleared_at IS NULL
ON CONFLICT DO NOTHING
"""


class StoreError(Exception):
    pass


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _read_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _dump_extraction(extraction: Extraction) -> str:
    deadline = extraction.deadline
    payload: dict[str, object] = {
        "summary": extraction.summary,
        "actionable": extraction.actionable,
        "urgent": extraction.urgent,
        "title": extraction.title,
        "deadline": None,
        "suspicious": extraction.suspicious,
        "suspicion_reason": extraction.suspicion_reason,
        "confidence": extraction.confidence,
    }
    if deadline is not None:
        payload["deadline"] = {
            "date": deadline.date.isoformat(),
            "time": None if deadline.time is None else deadline.time.isoformat(),
            "explicit": deadline.explicit,
            "quote": deadline.quote,
        }
    return json.dumps(payload)


def _load_extraction(text: str) -> Extraction:
    payload = json.loads(text)
    raw = payload["deadline"]
    deadline = None
    if raw is not None:
        raw_time = raw["time"]
        deadline = Deadline(
            date=date.fromisoformat(raw["date"]),
            time=None if raw_time is None else time.fromisoformat(raw_time),
            explicit=raw["explicit"],
            quote=raw["quote"],
        )
    return Extraction(
        summary=payload["summary"],
        actionable=payload["actionable"],
        urgent=payload["urgent"],
        title=payload["title"],
        deadline=deadline,
        suspicious=payload["suspicious"],
        suspicion_reason=payload["suspicion_reason"],
        confidence=payload["confidence"],
    )


def _sender_address(address: str) -> str:
    lowered = address.lower()
    if _SENDER.fullmatch(lowered) is None or len(lowered) > 254:
        raise ValueError(SENDER_MESSAGE)
    return lowered


def _sender_status(status: str) -> Literal["trusted", "muted"]:
    if status not in _STATUSES:
        raise ValueError(STATUS_MESSAGE)
    return cast(Literal["trusted", "muted"], status)


@dataclass(frozen=True)
class StoredMessage:
    record: Record
    fetched_at: datetime
    text_cleared_at: datetime | None


@dataclass(frozen=True)
class SyncState:
    bookmark: str
    synced_at: datetime


@dataclass(frozen=True)
class Verdict:
    outcome: Literal["dropped", "extracted", "rejected"]
    trusted: bool
    verified: bool
    bulk: bool
    notify: bool
    extraction: Extraction | None = None
    reason: str = ""


@dataclass(frozen=True)
class StoredTriage:
    verdict: Verdict
    decided_at: datetime
    text_cleared_at: datetime | None


@dataclass(frozen=True)
class Post:
    item_id: str
    provider: str
    message_id: str
    queued_at: datetime
    discord_message_id: str | None
    posted_at: datetime | None


@dataclass(frozen=True)
class Answer:
    item_id: str
    answer: Literal["yes", "edit", "notask", "mute"]
    title: str
    answered_at: datetime


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

    def sync_state(self, provider: str, account: str) -> SyncState | None:
        row = self._connection.execute(
            "SELECT bookmark, synced_at FROM sync_state WHERE provider = ? AND account = ?",
            (provider, account),
        ).fetchone()
        if row is None:
            return None
        bookmark, synced_at = row
        return SyncState(bookmark=bookmark, synced_at=_read_time(synced_at))

    def save_sync_state(self, provider: str, account: str, state: SyncState) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO sync_state (provider, account, bookmark, synced_at)
            VALUES (?, ?, ?, ?)
            """,
            (provider, account, state.bookmark, _stamp(state.synced_at)),
        )
        self._connection.commit()

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
        self._connection.commit()

    def senders(self, status: Literal["trusted", "muted"]) -> tuple[str, ...]:
        stored = _sender_status(status)
        rows = self._connection.execute(
            "SELECT address FROM senders WHERE status = ? ORDER BY address",
            (stored,),
        ).fetchall()
        return tuple(row[0] for row in rows)

    def save_triage(self, provider: str, message_id: str, verdict: Verdict) -> bool:
        decided_at = _stamp(clock.now())
        cursor = self._connection.execute(
            _TRIAGE_INSERT,
            (
                verdict.outcome,
                verdict.reason,
                1 if verdict.trusted else 0,
                1 if verdict.verified else 0,
                1 if verdict.bulk else 0,
                1 if verdict.notify else 0,
                None if verdict.extraction is None else _dump_extraction(verdict.extraction),
                decided_at,
                provider,
                message_id,
            ),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def triage(self, provider: str, message_id: str) -> StoredTriage | None:
        row = self._connection.execute(
            """
            SELECT outcome, trusted, verified, bulk, notify, extraction, reason,
                   decided_at, text_cleared_at
            FROM triage
            WHERE provider = ? AND message_id = ?
            """,
            (provider, message_id),
        ).fetchone()
        if row is None:
            return None
        outcome, trusted, verified, bulk, notify, extraction, reason, decided_at, cleared = row
        return StoredTriage(
            verdict=Verdict(
                outcome=outcome,
                trusted=bool(trusted),
                verified=bool(verified),
                bulk=bool(bulk),
                notify=bool(notify),
                extraction=None if extraction is None else _load_extraction(extraction),
                reason=reason,
            ),
            decided_at=_read_time(decided_at),
            text_cleared_at=None if cleared is None else _read_time(cleared),
        )

    def untriaged(self) -> tuple[tuple[str, str], ...]:
        rows = self._connection.execute(
            """
            SELECT messages.provider, messages.message_id
            FROM messages
            LEFT JOIN triage
              ON triage.provider = messages.provider
             AND triage.message_id = messages.message_id
            WHERE messages.text_cleared_at IS NULL
              AND triage.message_id IS NULL
            ORDER BY messages.received_at, messages.provider, messages.message_id
            """
        ).fetchall()
        return tuple((provider, message_id) for provider, message_id in rows)

    def clear_expired_text(self) -> int:
        now = clock.now()
        stamp = _stamp(now)
        cutoff = _stamp(now - TEXT_RETENTION)
        cursor = self._connection.execute(_CLEAR, (stamp, cutoff))
        self._connection.execute(_CLEAR_TRIAGE, (stamp, cutoff))
        self._connection.commit()
        return cursor.rowcount

    def queue_notified(self) -> int:
        queued_at = _stamp(clock.now())
        rows = self._connection.execute(
            """
            SELECT provider, message_id
            FROM triage
            WHERE notify = 1
              AND NOT EXISTS (
                  SELECT 1 FROM posts
                  WHERE posts.provider = triage.provider
                    AND posts.message_id = triage.message_id
              )
            ORDER BY decided_at, provider, message_id
            """
        ).fetchall()
        for provider, message_id in rows:
            self._connection.execute(
                """
                INSERT INTO posts (
                    item_id, provider, message_id, queued_at,
                    discord_message_id, posted_at
                ) VALUES (?, ?, ?, ?, NULL, NULL)
                """,
                (ids.new_id(), provider, message_id, queued_at),
            )
        self._connection.commit()
        return len(rows)

    def pending_posts(self) -> tuple[Post, ...]:
        rows = self._connection.execute(
            """
            SELECT item_id, provider, message_id, queued_at, discord_message_id, posted_at
            FROM posts
            WHERE posted_at IS NULL
            ORDER BY queued_at, rowid
            """
        ).fetchall()
        return tuple(_read_post(row) for row in rows)

    def post(self, provider: str, message_id: str) -> Post | None:
        row = self._connection.execute(
            """
            SELECT item_id, provider, message_id, queued_at, discord_message_id, posted_at
            FROM posts
            WHERE provider = ? AND message_id = ?
            """,
            (provider, message_id),
        ).fetchone()
        if row is None:
            return None
        return _read_post(row)

    def mark_posted(self, item_id: str, discord_message_id: str) -> bool:
        posted_at = _stamp(clock.now())
        cursor = self._connection.execute(
            """
            UPDATE posts
            SET discord_message_id = ?, posted_at = ?
            WHERE item_id = ? AND posted_at IS NULL
            """,
            (discord_message_id, posted_at, item_id),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def post_by_item(self, item_id: str) -> Post | None:
        row = self._connection.execute(
            """
            SELECT item_id, provider, message_id, queued_at, discord_message_id, posted_at
            FROM posts
            WHERE item_id = ?
            """,
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return _read_post(row)

    def record_answer(self, item_id: str, answer: str, title: str) -> bool:
        answered_at = _stamp(clock.now())
        cursor = self._connection.execute(
            """
            INSERT INTO answers (item_id, answer, title, answered_at)
            SELECT ?, ?, ?, ?
            FROM posts
            WHERE posts.item_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM answers WHERE answers.item_id = posts.item_id
              )
            ON CONFLICT DO NOTHING
            """,
            (item_id, answer, title, answered_at, item_id),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def answer(self, item_id: str) -> Answer | None:
        row = self._connection.execute(
            """
            SELECT item_id, answer, title, answered_at
            FROM answers
            WHERE item_id = ?
            """,
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        found_id, stored_answer, title, answered_at = row
        return Answer(
            item_id=found_id,
            answer=stored_answer,
            title=title,
            answered_at=_read_time(answered_at),
        )


def _read_post(row: tuple) -> Post:
    item_id, provider, message_id, queued_at, discord_message_id, posted_at = row
    return Post(
        item_id=item_id,
        provider=provider,
        message_id=message_id,
        queued_at=_read_time(queued_at),
        discord_message_id=discord_message_id,
        posted_at=None if posted_at is None else _read_time(posted_at),
    )


def open_store(settings: Settings) -> Store:
    return Store(prepare_data_dir(settings) / DB_FILENAME)
