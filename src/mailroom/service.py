"""One process that polls mail and listens for Discord presses."""

import sqlite3
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from mailroom import (
    alerts,
    clock,
    discord_post,
    extractor,
    gmail,
    gmail_sync,
    ids,
    outlook,
    outlook_sync,
    tasks_app,
    triage,
)
from mailroom import discord_layout as L
from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable, PostReport
from mailroom.extractor import ModelUnavailable
from mailroom.gateway import GatewayStopped, run_gateway
from mailroom.gmail import GmailAuthError, GmailClient, GmailError
from mailroom.gmail_sync import SyncResult
from mailroom.keychain import KeychainError, KeychainUnavailable, SecretMissing
from mailroom.outlook import OutlookAuthError, OutlookClient, OutlookError, OutlookTokenUnsaved
from mailroom.store import Store, is_busy, open_store
from mailroom.tasks_app import TasksUnavailable

RESTART_SECONDS = (1, 2, 4, 8, 16, 32, 60)
LISTENER_WAIT = timedelta(minutes=15)
POLL_LOCK_SECONDS = 10.0
LISTENER_LOCK_SECONDS = 1.5
STORE_WAIT = timedelta(minutes=15)
_ACCOUNTS = "MAILROOM_GMAIL_ACCOUNTS or MAILROOM_OUTLOOK_ACCOUNTS"
_REQUIRED = (
    ("extractor_model", "MAILROOM_EXTRACTOR_MODEL"),
    ("time_zone", "MAILROOM_TIME_ZONE"),
    ("discord_channel_id", "MAILROOM_DISCORD_CHANNEL_ID"),
    ("discord_owner_id", "MAILROOM_DISCORD_OWNER_ID"),
)


class ServiceError(Exception):
    pass


class Health:
    def __init__(self, say: Callable[[str], None]) -> None:
        self._say = say
        self._states: dict[str, str] = {}
        self._lock = threading.Lock()

    def report(self, part: str, state: str) -> None:
        with self._lock:
            if self._states.get(part) == state:
                return
            self._states[part] = state
            self._say(f"{part}: {state}")


def run_round(
    store: Store,
    settings: Settings,
    mail_clients: Sequence[GmailClient | OutlookClient],
    model_http: httpx.Client,
    discord_http: httpx.Client,
    tasks_http: httpx.Client,
    health: Health,
) -> None:
    store.clear_expired_text()
    for client in mail_clients:
        if isinstance(client, OutlookClient):
            _outlook_account(store, client, health)
        else:
            _gmail_account(store, client, health)
    triaged = 0
    try:
        for provider, message_id in store.untriaged():
            triage.triage_message(store, provider, message_id, settings, model_http)
            triaged += 1
    except ModelUnavailable as error:
        health.report("triage", str(error))
        _model(store, True)
    else:
        health.report("triage", "ok")
        if triaged:
            _model(store, False)
    _tasks(
        store,
        _status(health, "tasks", lambda: tasks_app.send_tasks(store, settings, tasks_http)),
    )
    _status(
        health, "discord posting", lambda: discord_post.post_pending(store, settings, discord_http)
    )
    _status(health, "discord alerts", lambda: alerts.post_alerts(store, settings, discord_http))


def run_service(
    settings: Settings,
    *,
    say: Callable[[str], None],
    stop: threading.Event,
    open_gmail: Callable[[str], GmailClient] = gmail.open_gmail,
    open_outlook: Callable[[str], OutlookClient] = outlook.open_outlook,
    open_model_http: Callable[[], httpx.Client] = extractor.open_model_http,
    open_discord_http: Callable[[], httpx.Client] = discord_post.open_discord_http,
    open_tasks_http: Callable[[], httpx.Client] = tasks_app.open_tasks_http,
    gateway: Callable[..., None] = run_gateway,
    restart_wait: Callable[[float], bool] | None = None,
) -> None:
    missing = []
    if settings.gmail_accounts == () and settings.outlook_accounts == ():
        missing.append(_ACCOUNTS)
    missing.extend(
        label
        for attr, label in _REQUIRED
        if getattr(settings, attr) == "" or getattr(settings, attr) == ()
    )
    if missing:
        raise ServiceError("not configured: " + ", ".join(missing))
    health = Health(say)
    store = open_store(settings)
    store.set_lock_wait(POLL_LOCK_SECONDS)
    mail_clients: list[GmailClient | OutlookClient] = [
        open_gmail(account) for account in settings.gmail_accounts
    ]
    mail_clients.extend(open_outlook(account) for account in settings.outlook_accounts)
    model_http = open_model_http()
    discord_http = open_discord_http()
    tasks_http = open_tasks_http()
    health.report("discord gateway", "running")
    listener = _Listener(
        settings, health, stop, open_discord_http, gateway, restart_wait or stop.wait
    )
    thread = threading.Thread(target=listener.run, name="mailroom-gateway", daemon=True)
    thread.start()
    try:
        first = True
        previous = 0
        episode: _Episode | None = None
        while not stop.is_set():
            failures, running, reason = listener.snapshot()
            was, previous = previous, failures
            try:
                if not first and thread.is_alive():
                    _gateway(store, False, "")
                    healthy = failures == was and running
                    if healthy:
                        listener.reset()
                    _listener_alert(store, not healthy, reason)
                first = False
                run_round(
                    store, settings, mail_clients, model_http, discord_http, tasks_http, health
                )
                episode = _end_episode(store, health, episode)
            except sqlite3.OperationalError as error:
                if not is_busy(error):
                    raise
                health.report("store", "busy")
                episode = _busy_round(settings, discord_http, episode)
            stop.wait(settings.poll_seconds)
    finally:
        stop.set()
        thread.join(10)
        _close(store, mail_clients, model_http, discord_http, tasks_http)


@dataclass
class _Episode:
    since: datetime
    nonce: str
    pinged: bool = False


def _end_episode(store: Store, health: Health, episode: _Episode | None) -> None:
    if episode is None:
        return None
    if episode.pinged:
        alerts.notice(store, f"store:{episode.since.isoformat()}:resolved", L.ALERT_STORE_FIXED)
    health.report("store", "ok")
    return None


def _busy_round(settings: Settings, http: httpx.Client, episode: _Episode | None) -> _Episode:
    if episode is None:
        episode = _Episode(clock.now(), ids.new_id()[:25])
    if not episode.pinged and clock.now() - episode.since >= STORE_WAIT:
        owner = settings.discord_owner_id

        def body(_: _Episode) -> dict[str, object]:
            return {
                "content": f"<@{owner}> {L.ALERT_STORE_BUSY}",
                "allowed_mentions": {"users": [owner]},
                "nonce": episode.nonce,
                "enforce_nonce": True,
            }

        def mark(found: _Episode, _id: str) -> None:
            found.pinged = True

        try:
            discord_post.send_messages(settings, http, [episode], body, mark)
        except KeychainError:
            pass
    return episode


class _Listener:
    """Runs the Discord listener on one thread, restarting it after a recoverable failure."""

    def __init__(
        self,
        settings: Settings,
        health: Health,
        stop: threading.Event,
        open_discord_http: Callable[[], httpx.Client],
        gateway: Callable[..., None],
        wait: Callable[[float], bool],
    ) -> None:
        self._settings = settings
        self._health = health
        self._stop = stop
        self._open_http = open_discord_http
        self._gateway = gateway
        self._wait = wait
        self._lock = threading.Lock()
        self._failures = 0
        self._streak = 0
        self._running = False
        self._reason = ""

    def snapshot(self) -> tuple[int, bool, str]:
        with self._lock:
            return self._failures, self._running, self._reason

    def reset(self) -> None:
        with self._lock:
            self._streak = 0

    def run(self) -> None:
        while not self._stop.is_set():
            self._health.report("discord gateway", "running")
            reason = self._attempt()
            if reason is None:
                return
            with self._lock:
                self._failures += 1
                self._streak += 1
                self._reason = reason
                delay = RESTART_SECONDS[min(self._streak - 1, 6)]
            self._health.report("discord gateway", reason)
            if self._wait(delay):
                return

    def _attempt(self) -> str | None:
        """Run one attempt; return the recoverable reason, or None to stop for good."""
        held: list[Store | httpx.Client] = []
        try:
            store = open_store(self._settings)
            held.append(store)
            store.set_lock_wait(LISTENER_LOCK_SECONDS)
            http = self._open_http()
            held.append(http)
            with self._lock:
                self._running = True
            self._gateway(store, self._settings, http, stop=self._stop.is_set)
        except (GatewayStopped, DiscordUnavailable, SecretMissing) as error:
            if len(held) < 2:
                return _reason(error)
            state = str(error)
            self._health.report("discord gateway", state)
            _gateway(store, True, state)
            return None
        except Exception as error:
            return _reason(error)
        finally:
            with self._lock:
                self._running = False
            for resource in reversed(held):
                resource.close()
        return None if self._stop.is_set() else "ended"


def _reason(error: Exception) -> str:
    if isinstance(error, KeychainUnavailable):
        return str(error)
    return f"failed ({type(error).__name__})"


def _listener_alert(store: Store, failing: bool, reason: str) -> None:
    alerts.track(
        store,
        "listener",
        failing,
        wait=LISTENER_WAIT,
        raised=L.ALERT_LISTENER.format(reason=reason),
        ping=True,
        resolved=L.ALERT_LISTENER_FIXED,
    )


def _status(health: Health, part: str, call: Callable[[], PostReport]) -> PostReport | None:
    try:
        report = call()
    except (DiscordUnavailable, KeychainError, TasksUnavailable) as error:
        health.report(part, str(error))
        return None
    if report.stopped:
        health.report(part, f"waiting ({report.stopped})")
        return report
    health.report(part, L.INCOMPLETE_STATE.format(count=report.skipped) if report.skipped else "ok")
    return report


def _tasks(store: Store, report: PostReport | None) -> None:
    if report is None or (not report.stopped and report.posted == 0):
        return
    alerts.track(
        store,
        "tasks",
        bool(report.stopped),
        wait=alerts.TASKS_WAIT,
        raised=L.ALERT_TASKS,
        ping=False,
        resolved=L.ALERT_TASKS_FIXED,
    )


def _gmail_account(store: Store, client: GmailClient, health: Health) -> None:
    try:
        result = gmail_sync.sync_gmail(client, store)
    except GmailAuthError as error:
        health.report(f"gmail {client.account}", str(error))
        _gmail(store, client.account, True)
    except (GmailError, KeychainError) as error:
        health.report(f"gmail {client.account}", str(error))
    else:
        health.report(f"gmail {client.account}", "ok")
        _gmail(store, client.account, False)
        _catch_up(store, client.account, result)


def _outlook_account(store: Store, client: OutlookClient, health: Health) -> None:
    try:
        result = outlook_sync.sync_outlook(client, store)
    except OutlookAuthError as error:
        health.report(f"outlook {client.account}", str(error))
        _outlook(store, client.account, True)
    except OutlookTokenUnsaved as error:
        health.report(f"outlook {client.account}", str(error))
        _outlook_token(store, client.account, True)
    except (OutlookError, KeychainError) as error:
        health.report(f"outlook {client.account}", str(error))
    else:
        health.report(f"outlook {client.account}", "ok")
        _outlook(store, client.account, False)
        _outlook_token(store, client.account, False)
        _catch_up(store, client.account, result, "outlook")


def _gmail(store: Store, account: str, failing: bool) -> None:
    alerts.track(
        store,
        f"gmail-auth:{account}",
        failing,
        wait=timedelta(0),
        raised=L.ALERT_GMAIL_AUTH.format(account=account),
        ping=True,
        resolved=L.ALERT_GMAIL_FIXED.format(account=account),
    )


def _outlook(store: Store, account: str, failing: bool) -> None:
    alerts.track(
        store,
        f"outlook-auth:{account}",
        failing,
        wait=timedelta(0),
        raised=L.ALERT_OUTLOOK_AUTH.format(account=account),
        ping=True,
        resolved=L.ALERT_OUTLOOK_FIXED.format(account=account),
    )


def _outlook_token(store: Store, account: str, failing: bool) -> None:
    alerts.track(
        store,
        f"outlook-token:{account}",
        failing,
        wait=timedelta(0),
        raised=L.ALERT_OUTLOOK_UNSAVED.format(account=account),
        ping=True,
        resolved=L.ALERT_OUTLOOK_SAVED.format(account=account),
    )


def _catch_up(store: Store, account: str, result: SyncResult, provider: str = "gmail") -> None:
    if result.kind == "catch_up" and result.offline_since is not None:
        offline = result.offline_since
        if provider == "gmail":
            key = f"catch-up:{account}:{offline.isoformat()}"
        else:
            key = f"catch-up:{provider}:{account}:{offline.isoformat()}"
        alerts.notice(
            store,
            key,
            alerts.catch_up_text(
                account, clock.now() - offline, len(result.stored), result.gap, provider
            ),
        )


def _model(store: Store, failing: bool) -> None:
    alerts.track(
        store,
        "model",
        failing,
        wait=alerts.MODEL_WAIT,
        raised=L.ALERT_MODEL,
        ping=False,
        resolved=L.ALERT_MODEL_FIXED,
    )


def _gateway(store: Store, failing: bool, reason: str) -> None:
    alerts.track(
        store,
        "gateway",
        failing,
        wait=timedelta(0),
        raised=L.ALERT_GATEWAY.format(reason=reason),
        ping=True,
        resolved=L.ALERT_GATEWAY_FIXED,
    )


def _close(
    store: Store,
    mail_clients: Sequence[GmailClient | OutlookClient],
    model_http: httpx.Client,
    discord_http: httpx.Client,
    tasks_http: httpx.Client,
) -> None:
    store.close()
    for client in mail_clients:
        client.http.close()
    model_http.close()
    discord_http.close()
    tasks_http.close()
