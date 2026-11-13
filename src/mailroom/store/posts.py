from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from mailroom import clock, ids
from mailroom.store.base import StoreBase


@dataclass(frozen=True)
class Post:
    item_id: str
    provider: str
    message_id: str
    queued_at: datetime
    discord_message_id: str | None
    posted_at: datetime | None
    card: str | None = None


@dataclass(frozen=True)
class Answer:
    item_id: str
    answer: Literal["yes", "edit", "notask", "mute"]
    title: str
    answered_at: datetime


def _read_post(row: tuple) -> Post:
    item_id, provider, message_id, queued_at, discord_message_id, posted_at, card = row
    return Post(
        item_id=item_id,
        provider=provider,
        message_id=message_id,
        queued_at=StoreBase._read_time(queued_at),
        discord_message_id=discord_message_id,
        posted_at=None if posted_at is None else StoreBase._read_time(posted_at),
        card=card,
    )


class PostStore(StoreBase):
    def queue_notified(self) -> int:
        queued_at = self._stamp(clock.now())
        with self._write():
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
        return len(rows)

    def pending_posts(self) -> tuple[Post, ...]:
        rows = self._connection.execute(
            """
            SELECT item_id, provider, message_id, queued_at, discord_message_id, posted_at, card
            FROM posts
            WHERE posted_at IS NULL
            ORDER BY queued_at, rowid
            """
        ).fetchall()
        return tuple(_read_post(row) for row in rows)

    def post(self, provider: str, message_id: str) -> Post | None:
        row = self._connection.execute(
            """
            SELECT item_id, provider, message_id, queued_at, discord_message_id, posted_at, card
            FROM posts
            WHERE provider = ? AND message_id = ?
            """,
            (provider, message_id),
        ).fetchone()
        if row is None:
            return None
        return _read_post(row)

    def mark_posted(self, item_id: str, discord_message_id: str) -> bool:
        posted_at = self._stamp(clock.now())
        with self._write():
            cursor = self._connection.execute(
                """
                UPDATE posts
                SET discord_message_id = ?, posted_at = ?
                WHERE item_id = ? AND posted_at IS NULL
                """,
                (discord_message_id, posted_at, item_id),
            )
        return cursor.rowcount == 1

    def post_by_item(self, item_id: str) -> Post | None:
        row = self._connection.execute(
            """
            SELECT item_id, provider, message_id, queued_at, discord_message_id, posted_at, card
            FROM posts
            WHERE item_id = ?
            """,
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return _read_post(row)

    def record_answer(self, item_id: str, answer: str, title: str) -> bool:
        answered_at = self._stamp(clock.now())
        with self._write():
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
        return cursor.rowcount == 1

    def choose_card(self, item_id: str, card: str) -> str | None:
        with self._write():
            self._connection.execute(
                """
                UPDATE posts SET card = ?
                WHERE item_id = ? AND card IS NULL
                """,
                (card, item_id),
            )
            row = self._connection.execute(
                "SELECT card FROM posts WHERE item_id = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            return None
        return row[0]

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
            answered_at=self._read_time(answered_at),
        )
