from dataclasses import dataclass
from datetime import datetime

from mailroom.store.base import StoreBase


@dataclass(frozen=True)
class SyncState:
    bookmark: str
    synced_at: datetime


class SyncStore(StoreBase):
    def sync_state(self, provider: str, account: str) -> SyncState | None:
        row = self._connection.execute(
            "SELECT bookmark, synced_at FROM sync_state WHERE provider = ? AND account = ?",
            (provider, account),
        ).fetchone()
        if row is None:
            return None
        bookmark, synced_at = row
        return SyncState(bookmark=bookmark, synced_at=self._read_time(synced_at))

    def save_sync_state(self, provider: str, account: str, state: SyncState) -> None:
        with self._write():
            self._connection.execute(
                """
                INSERT OR REPLACE INTO sync_state (provider, account, bookmark, synced_at)
                VALUES (?, ?, ?, ?)
                """,
                (provider, account, state.bookmark, self._stamp(state.synced_at)),
            )
