from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from mailroom import clock
from mailroom.store.base import StoreBase
from mailroom.store.triage import Due, due_columns, read_due


@dataclass(frozen=True)
class Approval:
    item_id: str
    outcome: Literal["approve", "change", "nodeadline", "drop"]
    title: str
    due: Due | None
    decided_at: datetime


_INSERT = """
INSERT INTO approvals (
    item_id, outcome, title, deadline_date, deadline_time, decided_at
)
SELECT ?, ?, ?, ?, ?, ?
FROM answers
WHERE answers.item_id = ? AND answers.answer IN ('yes', 'edit')
ON CONFLICT DO NOTHING
"""


APPROVAL_COLUMNS: tuple[str, ...] = (
    "approvals.item_id",
    "approvals.outcome",
    "approvals.title",
    "approvals.deadline_date",
    "approvals.deadline_time",
    "approvals.decided_at",
)


class ApprovalStore(StoreBase):
    def record_approval(self, item_id: str, outcome: str, title: str, due: Due | None) -> bool:
        decided_at = self._stamp(clock.now())
        deadline_date, deadline_time = due_columns(due)
        with self._write():
            cursor = self._connection.execute(
                _INSERT,
                (item_id, outcome, title, deadline_date, deadline_time, decided_at, item_id),
            )
        return cursor.rowcount == 1

    def record_combined(self, item_id: str, outcome: str, title: str, due: Due | None) -> bool:
        decided_at = self._stamp(clock.now())
        answer = "edit" if outcome == "change" else "yes"
        deadline_date, deadline_time = due_columns(due)
        with self._write():
            added = self._connection.execute(
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
                (item_id, answer, title, decided_at, item_id),
            )
            if added.rowcount != 1:
                return False
            self._connection.execute(
                _INSERT,
                (item_id, outcome, title, deadline_date, deadline_time, decided_at, item_id),
            )
        return True

    def approved_in_thread(self, provider: str, thread_id: str) -> Approval | None:
        rows = self._select(
            APPROVAL_COLUMNS,
            """
            FROM approvals
            JOIN posts ON posts.item_id = approvals.item_id
            JOIN messages ON messages.provider = posts.provider
                          AND messages.message_id = posts.message_id
            WHERE approvals.outcome != 'drop'
              AND posts.provider = ?
              AND messages.thread_id = ?
            ORDER BY approvals.decided_at DESC, approvals.item_id DESC
            LIMIT 1
            """,
            (provider, thread_id),
        )
        return _approval(rows[0]) if rows else None

    def approval(self, item_id: str) -> Approval | None:
        rows = self._select(
            APPROVAL_COLUMNS,
            """
            FROM approvals
            WHERE item_id = ?
            """,
            (item_id,),
        )
        return _approval(rows[0]) if rows else None


def _approval(row: dict[str, object]) -> Approval:
    return Approval(
        item_id=row["item_id"],
        outcome=row["outcome"],
        title=row["title"],
        due=read_due(row["deadline_date"], row["deadline_time"]),
        decided_at=StoreBase._read_time(row["decided_at"]),
    )
