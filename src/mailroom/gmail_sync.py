from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import quote

from mailroom import clock
from mailroom.gmail import BookmarkExpired, GmailClient, MessageGone, MessageRef
from mailroom.mime import parse_message
from mailroom.record import Envelope
from mailroom.store import Store, SyncState

FIRST_RUN = timedelta(days=3)
CATCH_UP_LIMIT = timedelta(days=14)
CATCH_UP_OVERLAP = timedelta(hours=1)
LINK = "https://mail.google.com/mail/?authuser={address}#all/{message_id}"


@dataclass(frozen=True)
class SyncResult:
    account: str
    kind: Literal["first", "history", "catch_up"]
    stored: tuple[str, ...]
    offline_since: datetime | None
    gap: bool


def sync_gmail(client: GmailClient, store: Store) -> SyncResult:
    now = clock.now()
    state = store.sync_state("gmail", client.account)
    profile = client.profile()
    kind, refs, bookmark, offline_since, gap = _choose(client, state, profile.history_id, now)
    stored = tuple(
        message_id
        for ref in refs
        if (message_id := _store_message(client, store, profile.email_address, ref)) is not None
    )
    store.save_sync_state("gmail", client.account, SyncState(bookmark=bookmark, synced_at=now))
    return SyncResult(
        account=client.account,
        kind=kind,
        stored=stored,
        offline_since=offline_since,
        gap=gap,
    )


def _choose(
    client: GmailClient,
    state: SyncState | None,
    history_id: str,
    now: datetime,
) -> tuple[
    Literal["first", "history", "catch_up"],
    tuple[MessageRef, ...],
    str,
    datetime | None,
    bool,
]:
    if state is None:
        return "first", client.list_inbox(now - FIRST_RUN), history_id, None, False
    try:
        found = client.history(state.bookmark)
    except BookmarkExpired:
        after = max(state.synced_at - CATCH_UP_OVERLAP, now - CATCH_UP_LIMIT)
        gap = now - state.synced_at > CATCH_UP_LIMIT
        return "catch_up", client.list_inbox(after), history_id, state.synced_at, gap
    return "history", found.added, found.history_id, None, False


def _store_message(client: GmailClient, store: Store, address: str, ref: MessageRef) -> str | None:
    if store.get("gmail", ref.id) is not None:
        return None
    try:
        message = client.fetch(ref.id)
    except (MessageGone, ValueError):
        return None
    labels = message.label_ids
    if "INBOX" not in labels or "SPAM" in labels or "TRASH" in labels:
        return None
    try:
        envelope = Envelope(
            provider="gmail",
            message_id=ref.id,
            thread_id=message.thread_id,
            received_at=message.internal_date,
            link=LINK.format(address=quote(address, safe="@"), message_id=ref.id),
        )
    except ValueError:
        return None
    if store.add(parse_message(message.raw, envelope)):
        return ref.id
    return None
