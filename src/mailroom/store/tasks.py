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


@dataclass(frozen=True)
class Link:
    item_id: str
    provider: str
    message_id: str
    task_item_id: str
    task_id: str | None
    queued_at: datetime
    sent_at: datetime | None


TASK_COLUMNS: tuple[str, ...] = (
    "item_id",
    "provider",
    "message_id",
    "queued_at",
    "task_id",
    "sent_at",
)
LINK_COLUMNS: tuple[str, ...] = (
    "links.item_id",
    "links.provider",
    "links.message_id",
    "links.task_item_id",
    "tasks.task_id",
    "links.queued_at",
    "links.sent_at",
)


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
        rows = self._select(
            TASK_COLUMNS,
            """
            FROM tasks
            WHERE task_id IS NULL
            ORDER BY queued_at, item_id
            """,
        )
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
        rows = self._select(
            TASK_COLUMNS,
            """
            FROM tasks
            WHERE item_id = ?
            """,
            (item_id,),
        )
        return _read_task(rows[0]) if rows else None

    def queue_linked(self) -> int:
        queued_at = self._stamp(clock.now())
        with self._write():
            cursor = self._connection.execute(
                """
                INSERT INTO links (item_id, provider, message_id, task_item_id, queued_at)
                SELECT posts.item_id, posts.provider, posts.message_id, posts.follows, ?
                FROM answers
                JOIN posts ON posts.item_id = answers.item_id
                WHERE answers.answer = 'link'
                  AND posts.follows IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM links WHERE links.item_id = answers.item_id
                  )
                ON CONFLICT DO NOTHING
                """,
                (queued_at,),
            )
        return cursor.rowcount

    def pending_links(self) -> tuple[Link, ...]:
        rows = self._select(
            LINK_COLUMNS,
            """
            FROM links
            JOIN tasks ON tasks.item_id = links.task_item_id
            WHERE links.sent_at IS NULL AND tasks.task_id IS NOT NULL
            ORDER BY links.queued_at, links.item_id
            """,
        )
        return tuple(_read_link(row) for row in rows)

    def mark_link_sent(self, item_id: str) -> bool:
        sent_at = self._stamp(clock.now())
        with self._write():
            cursor = self._connection.execute(
                """
                UPDATE links
                SET sent_at = ?
                WHERE item_id = ? AND sent_at IS NULL
                """,
                (sent_at, item_id),
            )
        return cursor.rowcount == 1

    def link(self, item_id: str) -> Link | None:
        rows = self._select(
            LINK_COLUMNS,
            """
            FROM links
            LEFT JOIN tasks ON tasks.item_id = links.task_item_id
            WHERE links.item_id = ?
            """,
            (item_id,),
        )
        return _read_link(rows[0]) if rows else None


def _read_task(row: dict[str, object]) -> Task:
    sent_at = row["sent_at"]
    return Task(
        item_id=row["item_id"],
        provider=row["provider"],
        message_id=row["message_id"],
        queued_at=StoreBase._read_time(row["queued_at"]),
        task_id=row["task_id"],
        sent_at=None if sent_at is None else StoreBase._read_time(sent_at),
    )


def _read_link(row: dict[str, object]) -> Link:
    sent_at = row["sent_at"]
    return Link(
        item_id=row["item_id"],
        provider=row["provider"],
        message_id=row["message_id"],
        task_item_id=row["task_item_id"],
        task_id=row["task_id"],
        queued_at=StoreBase._read_time(row["queued_at"]),
        sent_at=None if sent_at is None else StoreBase._read_time(sent_at),
    )
