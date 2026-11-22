"""One read-only sync round for any mail source: first run, resume or catch-up, stored once each."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol

from mailroom import clock
from mailroom.mime import parse_message
from mailroom.record import Envelope, stored_id
from mailroom.store import Store, SyncState

FIRST_RUN = timedelta(days=3)
CATCH_UP_LIMIT = timedelta(days=14)
CATCH_UP_OVERLAP = timedelta(hours=1)


@dataclass(frozen=True)
class SyncResult:
    account: str
    kind: Literal["first", "history", "delta", "catch_up"]
    stored: tuple[str, ...]
    offline_since: datetime | None
    gap: bool


@dataclass(frozen=True)
class Page:
    ids: tuple[str, ...]
    bookmark: str


@dataclass(frozen=True)
class Fetched:
    raw: bytes
    thread_id: str
    received_at: datetime
    link: str


class Source(Protocol):
    provider: str
    account: str
    resumed: Literal["history", "delta"]

    def begin(self) -> None: ...

    def start(self, after: datetime) -> Page: ...

    def resume(self, bookmark: str) -> Page | None: ...

    def fetch(self, message_id: str) -> Fetched | None: ...


def run_round(source: Source, store: Store) -> SyncResult:
    now = clock.now()
    state = store.sync_state(source.provider, source.account)
    source.begin()
    kind: Literal["first", "history", "delta", "catch_up"]
    offline_since = None
    gap = False
    if state is None:
        kind = "first"
        page = source.start(now - FIRST_RUN)
    else:
        resumed = source.resume(state.bookmark)
        if resumed is not None:
            kind = source.resumed
            page = resumed
        else:
            kind = "catch_up"
            after = max(state.synced_at - CATCH_UP_OVERLAP, now - CATCH_UP_LIMIT)
            page = source.start(after)
            offline_since = state.synced_at
            gap = now - state.synced_at > CATCH_UP_LIMIT
    stored = tuple(
        kept
        for message_id in page.ids
        if (kept := _store_one(source, store, message_id)) is not None
    )
    store.save_sync_state(
        source.provider, source.account, SyncState(bookmark=page.bookmark, synced_at=now)
    )
    return SyncResult(
        account=source.account,
        kind=kind,
        stored=stored,
        offline_since=offline_since,
        gap=gap,
    )


def _store_one(source: Source, store: Store, message_id: str) -> str | None:
    kept = stored_id(source.account, message_id)
    if store.get(source.provider, kept) is not None:
        return None
    fetched = source.fetch(message_id)
    if fetched is None:
        return None
    try:
        envelope = Envelope(
            provider=source.provider,
            message_id=kept,
            thread_id=stored_id(source.account, fetched.thread_id),
            received_at=fetched.received_at,
            link=fetched.link,
        )
    except ValueError:
        return None
    if store.add(parse_message(fetched.raw, envelope)):
        return kept
    return None
