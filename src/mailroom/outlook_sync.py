"""One read-only round of a live.com inbox, stored once each from a delta bookmark."""

from datetime import datetime
from typing import Literal

from mailroom import clock
from mailroom.gmail_sync import CATCH_UP_LIMIT, CATCH_UP_OVERLAP, FIRST_RUN, SyncResult
from mailroom.mime import parse_message
from mailroom.outlook import DeltaExpired, MessageGone, MessageRef, OutlookClient
from mailroom.record import LINK_LIMIT, Envelope, stored_id
from mailroom.store import Store, SyncState

INBOX_LINK = "https://outlook.live.com/mail/0/inbox"
WEB_LINK_PREFIX = "https://outlook.live.com/"


def sync_outlook(client: OutlookClient, store: Store) -> SyncResult:
    now = clock.now()
    state = store.sync_state("outlook", client.account)
    profile = client.profile()
    kind, refs, delta_link, offline_since, gap = _choose(client, state, now)
    stored = tuple(
        message_id
        for ref in refs
        if (message_id := _store_message(client, store, profile.inbox_id, ref)) is not None
    )
    store.save_sync_state("outlook", client.account, SyncState(bookmark=delta_link, synced_at=now))
    return SyncResult(
        account=client.account,
        kind=kind,
        stored=stored,
        offline_since=offline_since,
        gap=gap,
    )


def _choose(
    client: OutlookClient,
    state: SyncState | None,
    now: datetime,
) -> tuple[
    Literal["first", "delta", "catch_up"],
    tuple[MessageRef, ...],
    str,
    datetime | None,
    bool,
]:
    if state is None:
        found = client.first_delta(now - FIRST_RUN)
        return "first", found.added, found.delta_link, None, False
    try:
        found = client.next_delta(state.bookmark)
    except DeltaExpired:
        after = max(state.synced_at - CATCH_UP_OVERLAP, now - CATCH_UP_LIMIT)
        gap = now - state.synced_at > CATCH_UP_LIMIT
        found = client.first_delta(after)
        return "catch_up", found.added, found.delta_link, state.synced_at, gap
    return "delta", found.added, found.delta_link, None, False


def _store_message(
    client: OutlookClient, store: Store, inbox_id: str, ref: MessageRef
) -> str | None:
    kept = stored_id(client.account, ref.id)
    if store.get("outlook", kept) is not None:
        return None
    try:
        message = client.fetch(ref.id)
    except (MessageGone, ValueError):
        return None
    if message.folder_id != inbox_id:
        return None
    try:
        envelope = Envelope(
            provider="outlook",
            message_id=kept,
            thread_id=stored_id(client.account, message.thread_id),
            received_at=message.received_at,
            link=_web_link(message.web_link),
        )
    except ValueError:
        return None
    if store.add(parse_message(message.raw, envelope)):
        return kept
    return None


def _web_link(web_link: str) -> str:
    if (
        web_link.startswith(WEB_LINK_PREFIX)
        and len(web_link) <= LINK_LIMIT
        and web_link.isprintable()
        and " " not in web_link
    ):
        return web_link
    return INBOX_LINK
