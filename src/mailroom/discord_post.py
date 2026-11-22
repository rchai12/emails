from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import httpx

from mailroom import __version__, clock, keychain
from mailroom import discord_layout as L
from mailroom.checkpoint import checkpoint_message, combined_message, followup_message
from mailroom.config import Settings
from mailroom.deadlines import deadline_passed
from mailroom.store import Post, Store, Verdict

TIMEOUT_SECONDS = 30.0


class DiscordUnavailable(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(f"discord unavailable ({detail})")


@dataclass(frozen=True)
class PostReport:
    posted: int
    waiting: int
    stopped: str
    skipped: int = 0


def open_discord_http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)


def send_messages[T](
    settings: Settings,
    http: httpx.Client,
    pending: Sequence[T],
    body: Callable[[T], dict[str, object]],
    mark: Callable[[T, str], object],
) -> PostReport:
    if not pending:
        return PostReport(posted=0, waiting=0, stopped="")
    token = keychain.get_secret(L.TOKEN_NAME)
    url = f"{L.API_URL}/channels/{settings.discord_channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": L.USER_AGENT.format(version=__version__),
    }
    posted = 0
    for index, item in enumerate(pending):
        payload = body(item)
        try:
            response = http.post(url, json=payload, headers=headers)
        except httpx.TransportError:
            return PostReport(posted, len(pending) - index, "network")
        if response.status_code != 200:
            return PostReport(posted, len(pending) - index, str(response.status_code))
        message_id = _message_id(response)
        if message_id is None:
            return PostReport(posted, len(pending) - index, "response")
        mark(item, message_id)
        posted += 1
    return PostReport(posted, 0, "")


def incomplete(store: Store, post: Post) -> bool:
    if store.get(post.provider, post.message_id) is None:
        return True
    if store.triage(post.provider, post.message_id) is None:
        return True
    return post.card == "followup" and store.approval(post.follows) is None


def keep(store: Store, item_id: str) -> None:
    store.queue_alert(f"incomplete:{item_id}", L.ALERT_INCOMPLETE.format(item=item_id), False)


def post_pending(store: Store, settings: Settings, http: httpx.Client) -> PostReport:
    if settings.discord_channel_id == "":
        raise DiscordUnavailable("not configured") from None
    store.queue_notified()

    def body(post: Post) -> dict[str, object]:
        stored = store.get(post.provider, post.message_id)
        triaged = store.triage(post.provider, post.message_id)
        record = stored.record
        verdict = triaged.verdict
        target = store.approved_in_thread(post.provider, record.thread_id)
        if target is None:
            wanted, follows = _wanted(verdict, settings), None
        else:
            wanted, follows = "followup", target.item_id
        store.choose_card(post.item_id, wanted, follows=follows)
        posted = store.post_by_item(post.item_id)
        if posted.card == "followup":
            task_title = store.approval(posted.follows).title
            return followup_message(record, verdict, post.item_id, task_title)
        if posted.card == "combined":
            return combined_message(record, verdict, post.item_id)
        return checkpoint_message(record, verdict, post.item_id)

    def mark(post: Post, message_id: str) -> None:
        store.mark_posted(post.item_id, message_id)

    pending = []
    kept = 0
    for post in store.pending_posts():
        if incomplete(store, post):
            keep(store, post.item_id)
            kept += 1
        else:
            pending.append(post)
    return replace(send_messages(settings, http, pending, body, mark), skipped=kept)


def _wanted(verdict: Verdict, settings: Settings) -> str:
    due = verdict.due
    if (
        verdict.dated
        and verdict.extraction is not None
        and due is not None
        and not deadline_passed(due.date, due.time, settings.time_zone, clock.now())
    ):
        return "combined"
    return "first"


def _message_id(response: httpx.Response) -> str | None:
    try:
        found = response.json()["id"]
    except (ValueError, TypeError, KeyError):
        found = None
    if isinstance(found, str):
        return found
    return None
