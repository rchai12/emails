from dataclasses import dataclass
from datetime import datetime

from mailroom import clock
from mailroom.store.base import StoreBase


@dataclass(frozen=True)
class Task:
    item_id: str
    provider: str
    message_id: str
    queued_at: datetime
    task_id: str | None
    sent_at: datetime | None


class TaskStore(StoreBase):
    def queue_approved(self) -> int:
        queued_at = self._stamp(clock.now())
        with self._write():
            cursor = self._connection.execute(
                """
                INSERT INTO tasks (item_id, provider, message_id, queued_at)
                SELECT approvals.item_id, posts.provider, posts.message_id, ?
                FROM approvals
                JOIN posts ON posts.item_id = approvals.item_id
                WHERE approvals.outcome != 'drop'
                  AND NOT EXISTS (
                      SELECT 1 FROM tasks WHERE tasks.item_id = approvals.item_id
                  )
                ON CONFLICT DO NOTHING
                """,
                (queued_at,),
            )
        return cursor.rowcount

    def pending_tasks(self) -> tuple[Task, ...]:
        rows = self._connection.execute(
            """
            SELECT item_id, provider, message_id, queued_at, task_id, sent_at
            FROM tasks
            WHERE task_id IS NULL
            ORDER BY queued_at, item_id
            """
        ).fetchall()
        return tuple(_read_task(row) for row in rows)

    def mark_task_sent(self, item_id: str, task_id: str) -> bool:
        sent_at = self._stamp(clock.now())
        with self._write():
            cursor = self._connection.execute(
                """
                UPDATE tasks
                SET task_id = ?, sent_at = ?
                WHERE item_id = ? AND task_id IS NULL
                """,
                (task_id, sent_at, item_id),
            )
        return cursor.rowcount == 1

    def task(self, item_id: str) -> Task | None:
        row = self._connection.execute(
            """
            SELECT item_id, provider, message_id, queued_at, task_id, sent_at
            FROM tasks
            WHERE item_id = ?
            """,
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return _read_task(row)


def _read_task(row: tuple) -> Task:
    item_id, provider, message_id, queued_at, task_id, sent_at = row
    return Task(
        item_id=item_id,
        provider=provider,
        message_id=message_id,
        queued_at=StoreBase._read_time(queued_at),
        task_id=task_id,
        sent_at=None if sent_at is None else StoreBase._read_time(sent_at),
    )
