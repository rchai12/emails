"""Discord alerts for problems that need the owner, and for their recovery."""

from datetime import timedelta

import httpx

from mailroom import clock
from mailroom import discord_layout as L
from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable, PostReport, send_messages
from mailroom.store import Alert, Store

MODEL_WAIT = timedelta(minutes=15)
TASKS_WAIT = timedelta(minutes=15)


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


def catch_up_text(
    account: str, offline: timedelta, count: int, gap: bool, provider: str = "gmail"
) -> str:
    name = L.PROVIDER_NAMES[provider]
    text = L.ALERT_CATCH_UP.format(
        provider=name, account=account, offline=_offline(offline), found=_found(count)
    )
    if gap:
        text += L.ALERT_GAP.format(provider=name)
    return text


def post_alerts(store: Store, settings: Settings, http: httpx.Client) -> PostReport:
    if settings.discord_channel_id == "" or settings.discord_owner_id == "":
        raise DiscordUnavailable("not configured") from None
    owner = settings.discord_owner_id

    def body(alert: Alert) -> dict[str, object]:
        if alert.ping:
            content = f"<@{owner}> {alert.text}"
            mentions: dict[str, object] = {"users": [owner]}
        else:
            content = alert.text
            mentions = {"parse": []}
        return {
            "content": content,
            "allowed_mentions": mentions,
            "nonce": alert.alert_id[:25],
            "enforce_nonce": True,
        }

    return send_messages(
        settings,
        http,
        store.pending_alerts(),
        body,
        lambda alert, message_id: store.mark_alert_posted(alert.alert_id, message_id),
    )


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
