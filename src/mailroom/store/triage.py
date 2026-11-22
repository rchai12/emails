import json
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

from mailroom import clock
from mailroom.extractor import Deadline, Extraction
from mailroom.store.base import StoreBase

_TRIAGE_INSERT = """
INSERT INTO triage (
    provider, message_id, outcome, reason, trusted, verified, bulk, notify,
    extraction, decided_at, text_cleared_at, deadline_date, deadline_time, dated
)
SELECT provider, message_id, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?
FROM messages
WHERE provider = ? AND message_id = ? AND text_cleared_at IS NULL
ON CONFLICT DO NOTHING
"""


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


@dataclass(frozen=True)
class Due:
    date: date
    time: time | None


@dataclass(frozen=True)
class Verdict:
    outcome: Literal["dropped", "extracted", "rejected"]
    trusted: bool
    verified: bool
    bulk: bool
    notify: bool
    extraction: Extraction | None = None
    reason: str = ""
    dated: bool = False
    due: Due | None = None


def due_columns(due: Due | None) -> tuple[str | None, str | None]:
    if due is None:
        return None, None
    deadline_time = None if due.time is None else due.time.strftime("%H:%M")
    return due.date.isoformat(), deadline_time


def read_due(deadline_date: str | None, deadline_time: str | None) -> Due | None:
    if deadline_date is None:
        return None
    parsed = None if deadline_time is None else time.fromisoformat(deadline_time)
    return Due(date=date.fromisoformat(deadline_date), time=parsed)


TRIAGE_COLUMNS: tuple[str, ...] = (
    "outcome",
    "trusted",
    "verified",
    "bulk",
    "notify",
    "extraction",
    "reason",
    "decided_at",
    "text_cleared_at",
    "deadline_date",
    "deadline_time",
    "dated",
)


@dataclass(frozen=True)
class StoredTriage:
    verdict: Verdict
    decided_at: datetime
    text_cleared_at: datetime | None


class TriageStore(StoreBase):
    def save_triage(self, provider: str, message_id: str, verdict: Verdict) -> bool:
        decided_at = self._stamp(clock.now())
        deadline_date, deadline_time = due_columns(verdict.due)
        with self._write():
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
                    deadline_date,
                    deadline_time,
                    1 if verdict.dated else 0,
                    provider,
                    message_id,
                ),
            )
        return cursor.rowcount == 1

    def triage(self, provider: str, message_id: str) -> StoredTriage | None:
        rows = self._select(
            TRIAGE_COLUMNS,
            """
            FROM triage
            WHERE provider = ? AND message_id = ?
            """,
            (provider, message_id),
        )
        if not rows:
            return None
        row = rows[0]
        extraction = row["extraction"]
        cleared = row["text_cleared_at"]
        return StoredTriage(
            verdict=Verdict(
                outcome=row["outcome"],
                trusted=bool(row["trusted"]),
                verified=bool(row["verified"]),
                bulk=bool(row["bulk"]),
                notify=bool(row["notify"]),
                extraction=None if extraction is None else _load_extraction(extraction),
                reason=row["reason"],
                dated=bool(row["dated"]),
                due=read_due(row["deadline_date"], row["deadline_time"]),
            ),
            decided_at=self._read_time(row["decided_at"]),
            text_cleared_at=None if cleared is None else self._read_time(cleared),
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
