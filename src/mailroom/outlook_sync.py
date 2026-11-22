"""One read-only round of a live.com inbox, stored once each from a delta bookmark."""

from datetime import datetime
from typing import Literal

from mailroom import mail_sync
from mailroom.mail_sync import Fetched, Page, SyncResult
from mailroom.outlook import DeltaExpired, MessageGone, OutlookClient
from mailroom.record import LINK_LIMIT
from mailroom.store import Store

INBOX_LINK = "https://outlook.live.com/mail/0/inbox"
WEB_LINK_PREFIX = "https://outlook.live.com/"


class _Outlook:
    provider = "outlook"
    resumed: Literal["history", "delta"] = "delta"

    def __init__(self, client: OutlookClient) -> None:
        self._client = client
        self.account = client.account
        self._inbox_id = ""

    def begin(self) -> None:
        self._inbox_id = self._client.profile().inbox_id

    def start(self, after: datetime) -> Page:
        found = self._client.first_delta(after)
        return Page(tuple(ref.id for ref in found.added), found.delta_link)

    def resume(self, bookmark: str) -> Page | None:
        try:
            found = self._client.next_delta(bookmark)
        except DeltaExpired:
            return None
        return Page(tuple(ref.id for ref in found.added), found.delta_link)

    def fetch(self, message_id: str) -> Fetched | None:
        try:
            message = self._client.fetch(message_id)
        except (MessageGone, ValueError):
            return None
        if message.folder_id != self._inbox_id:
            return None
        return Fetched(
            message.raw, message.thread_id, message.received_at, _web_link(message.web_link)
        )


def sync_outlook(client: OutlookClient, store: Store) -> SyncResult:
    return mail_sync.run_round(_Outlook(client), store)


def _web_link(web_link: str) -> str:
    if (
        web_link.startswith(WEB_LINK_PREFIX)
        and len(web_link) <= LINK_LIMIT
        and web_link.isprintable()
        and " " not in web_link
    ):
        return web_link
    return INBOX_LINK
