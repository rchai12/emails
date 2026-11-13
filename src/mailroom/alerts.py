"""Discord alerts for problems that need the owner, and for their recovery."""

from datetime import timedelta

import httpx

from mailroom import __version__, clock, keychain
from mailroom import discord_layout as L
from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable, PostReport
from mailroom.store import Store

MODEL_WAIT = timedelta(minutes=15)


def track(
    store: Store,
    problem: str,
    failing: bool,
    *,
    wait: timedelta,
    raised: str,
    ping: bool,
    resolved: str,
) -> None:
    if failing:
        found = store.open_problem(problem)
        if not found.alerted and clock.now() - found.since >= wait:
            store.queue_alert(f"{problem}:{found.since.isoformat()}:raised", raised, ping)
            store.mark_alerted(problem)
        return
    found = store.close_problem(problem)
    if found is not None and found.alerted:
        store.queue_alert(f"{problem}:{found.since.isoformat()}:resolved", resolved, False)


def notice(store: Store, key: str, text: str) -> None:
    store.queue_alert(key, text, False)


def catch_up_text(account: str, offline: timedelta, count: int, gap: bool) -> str:
    text = L.ALERT_CATCH_UP.format(account=account, offline=_offline(offline), found=_found(count))
    if gap:
        text += L.ALERT_GAP
    return text


def post_alerts(store: Store, settings: Settings, http: httpx.Client) -> PostReport:
    if settings.discord_channel_id == "" or settings.discord_owner_id == "":
        raise DiscordUnavailable("not configured") from None
    pending = store.pending_alerts()
    if not pending:
        return PostReport(posted=0, waiting=0, stopped="")
    token = keychain.get_secret(L.TOKEN_NAME)
    url = f"{L.API_URL}/channels/{settings.discord_channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": L.USER_AGENT.format(version=__version__),
    }
    owner = settings.discord_owner_id
    posted = 0
    for index, alert in enumerate(pending):
        if alert.ping:
            body = {
                "content": f"<@{owner}> {alert.text}",
                "allowed_mentions": {"users": [owner]},
                "nonce": alert.alert_id[:25],
                "enforce_nonce": True,
            }
        else:
            body = {
                "content": alert.text,
                "allowed_mentions": {"parse": []},
                "nonce": alert.alert_id[:25],
                "enforce_nonce": True,
            }
        try:
            response = http.post(url, json=body, headers=headers)
        except httpx.TransportError:
            return PostReport(posted, len(pending) - index, "network")
        if response.status_code != 200:
            return PostReport(posted, len(pending) - index, str(response.status_code))
        message_id = _message_id(response)
        if message_id is None:
            return PostReport(posted, len(pending) - index, "response")
        store.mark_alert_posted(alert.alert_id, message_id)
        posted += 1
    return PostReport(posted, 0, "")


def _offline(offline: timedelta) -> str:
    if offline < timedelta(hours=1):
        return L.LESS_THAN_AN_HOUR
    if offline < timedelta(hours=48):
        hours = int(offline.total_seconds() // 3600)
        if hours == 1:
            return "1 hour"
        return f"{hours} hours"
    return f"{offline.days} days"


def _found(count: int) -> str:
    if count == 0:
        return "no new emails"
    if count == 1:
        return "1 new email"
    return f"{count} new emails"


def _message_id(response: httpx.Response) -> str | None:
    try:
        found = response.json()["id"]
    except (ValueError, TypeError, KeyError):
        found = None
    if isinstance(found, str):
        return found
    return None
