from datetime import datetime
from typing import Literal
from urllib.parse import quote

from mailroom import mail_sync
from mailroom.gmail import BookmarkExpired, GmailClient, MessageGone
from mailroom.mail_sync import (
    CATCH_UP_LIMIT,
    CATCH_UP_OVERLAP,
    FIRST_RUN,
    Fetched,
    Page,
    SyncResult,
)
from mailroom.store import Store

__all__ = [
    "CATCH_UP_LIMIT",
    "CATCH_UP_OVERLAP",
    "FIRST_RUN",
    "LINK",
    "SyncResult",
    "sync_gmail",
]

LINK = "https://mail.google.com/mail/?authuser={address}#all/{message_id}"


class _Gmail:
    provider = "gmail"
    resumed: Literal["history", "delta"] = "history"

    def __init__(self, client: GmailClient) -> None:
        self._client = client
        self.account = client.account
        self._history_id = ""
        self._address = ""

    def begin(self) -> None:
        profile = self._client.profile()
        self._history_id = profile.history_id
        self._address = profile.email_address

    def start(self, after: datetime) -> Page:
        refs = self._client.list_inbox(after)
        return Page(tuple(ref.id for ref in refs), self._history_id)

    def resume(self, bookmark: str) -> Page | None:
        try:
            found = self._client.history(bookmark)
        except BookmarkExpired:
            return None
        return Page(tuple(ref.id for ref in found.added), found.history_id)

    def fetch(self, message_id: str) -> Fetched | None:
        try:
            message = self._client.fetch(message_id)
        except (MessageGone, ValueError):
            return None
        labels = message.label_ids
        if "INBOX" not in labels or "SPAM" in labels or "TRASH" in labels:
            return None
        link = LINK.format(address=quote(self._address, safe="@"), message_id=message_id)
        return Fetched(message.raw, message.thread_id, message.internal_date, link)


def sync_gmail(client: GmailClient, store: Store) -> SyncResult:
    return mail_sync.run_round(_Gmail(client), store)
