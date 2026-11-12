from dataclasses import dataclass

import httpx

from mailroom import __version__, keychain
from mailroom import discord_layout as L
from mailroom.checkpoint import checkpoint_message
from mailroom.config import Settings
from mailroom.store import Store

TIMEOUT_SECONDS = 30.0


class DiscordUnavailable(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(f"discord unavailable ({detail})")


@dataclass(frozen=True)
class PostReport:
    posted: int
    waiting: int
    stopped: str


def open_discord_http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)


def post_pending(store: Store, settings: Settings, http: httpx.Client) -> PostReport:
    if settings.discord_channel_id == "":
        raise DiscordUnavailable("not configured") from None
    store.queue_notified()
    pending = store.pending_posts()
    if not pending:
        return PostReport(posted=0, waiting=0, stopped="")
    token = keychain.get_secret(L.TOKEN_NAME)
    url = f"{L.API_URL}/channels/{settings.discord_channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": L.USER_AGENT.format(version=__version__),
    }
    posted = 0
    for index, post in enumerate(pending):
        stored = store.get(post.provider, post.message_id)
        triaged = store.triage(post.provider, post.message_id)
        body = checkpoint_message(stored.record, triaged.verdict, post.item_id)
        try:
            response = http.post(url, json=body, headers=headers)
        except httpx.TransportError:
            return PostReport(posted, len(pending) - index, "network")
        if response.status_code != 200:
            return PostReport(posted, len(pending) - index, str(response.status_code))
        message_id = _message_id(response)
        if message_id is None:
            return PostReport(posted, len(pending) - index, "response")
        store.mark_posted(post.item_id, message_id)
        posted += 1
    return PostReport(posted, 0, "")


def _message_id(response: httpx.Response) -> str | None:
    try:
        found = response.json()["id"]
    except (ValueError, TypeError, KeyError):
        found = None
    if isinstance(found, str):
        return found
    return None
