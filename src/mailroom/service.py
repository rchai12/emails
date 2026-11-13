"""One process that polls mail and listens for Discord presses."""

import threading
from collections.abc import Callable, Sequence

import httpx

from mailroom import discord_post, extractor, gmail, gmail_sync, triage
from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.extractor import ModelUnavailable
from mailroom.gateway import GatewayStopped, run_gateway
from mailroom.gmail import GmailClient, GmailError
from mailroom.keychain import KeychainError
from mailroom.store import Store, open_store

_REQUIRED = (
    ("gmail_accounts", "MAILROOM_GMAIL_ACCOUNTS"),
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
    gmail_clients: Sequence[GmailClient],
    model_http: httpx.Client,
    discord_http: httpx.Client,
    health: Health,
) -> None:
    store.clear_expired_text()
    for client in gmail_clients:
        try:
            gmail_sync.sync_gmail(client, store)
        except (GmailError, KeychainError) as error:
            health.report(f"gmail {client.account}", str(error))
        else:
            health.report(f"gmail {client.account}", "ok")
    try:
        for provider, message_id in store.untriaged():
            triage.triage_message(store, provider, message_id, settings, model_http)
    except ModelUnavailable as error:
        health.report("triage", str(error))
    else:
        health.report("triage", "ok")
    try:
        report = discord_post.post_pending(store, settings, discord_http)
    except (DiscordUnavailable, KeychainError) as error:
        health.report("discord posting", str(error))
    else:
        if report.stopped:
            health.report("discord posting", f"waiting ({report.stopped})")
        else:
            health.report("discord posting", "ok")


def run_service(
    settings: Settings,
    *,
    say: Callable[[str], None],
    stop: threading.Event,
    open_gmail: Callable[[str], GmailClient] = gmail.open_gmail,
    open_model_http: Callable[[], httpx.Client] = extractor.open_model_http,
    open_discord_http: Callable[[], httpx.Client] = discord_post.open_discord_http,
    gateway: Callable[..., None] = run_gateway,
) -> None:
    missing = [
        label
        for attr, label in _REQUIRED
        if getattr(settings, attr) == "" or getattr(settings, attr) == ()
    ]
    if missing:
        raise ServiceError("not configured: " + ", ".join(missing))
    health = Health(say)
    store = open_store(settings)
    gmail_clients = [open_gmail(account) for account in settings.gmail_accounts]
    model_http = open_model_http()
    discord_http = open_discord_http()
    health.report("discord gateway", "running")
    thread = threading.Thread(
        target=_listen,
        name="mailroom-gateway",
        args=(settings, health, stop, open_discord_http, gateway),
        daemon=True,
    )
    thread.start()
    try:
        while not stop.is_set():
            run_round(store, settings, gmail_clients, model_http, discord_http, health)
            stop.wait(settings.poll_seconds)
    finally:
        stop.set()
        thread.join(10)
        _close(store, gmail_clients, model_http, discord_http)


def _listen(
    settings: Settings,
    health: Health,
    stop: threading.Event,
    open_discord_http: Callable[[], httpx.Client],
    gateway: Callable[..., None],
) -> None:
    store = open_store(settings)
    http = open_discord_http()
    try:
        gateway(store, settings, http, stop=stop.is_set)
    except (GatewayStopped, DiscordUnavailable, KeychainError) as error:
        health.report("discord gateway", str(error))
    except Exception as error:
        health.report("discord gateway", f"failed ({type(error).__name__})")
    finally:
        http.close()
        store.close()


def _close(
    store: Store,
    gmail_clients: Sequence[GmailClient],
    model_http: httpx.Client,
    discord_http: httpx.Client,
) -> None:
    store.close()
    for client in gmail_clients:
        client.http.close()
    model_http.close()
    discord_http.close()
