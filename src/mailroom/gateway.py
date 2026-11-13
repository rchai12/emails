"""Discord Gateway client: identify, heartbeat, and deliver button presses."""

import json
import logging
import random
import time
import urllib.parse
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
import websockets.exceptions
import websockets.sync.client

from mailroom import __version__, clock, keychain
from mailroom import discord_layout as L
from mailroom import gateway_protocol as P
from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.interactions import handle_interaction
from mailroom.store import Store

GATEWAY_URL_MESSAGE = "refused a Gateway address outside discord.gg"
_QUERY = P.QUERY.removeprefix("?")


class _Silent(logging.LoggerAdapter):
    def isEnabledFor(self, level: int) -> bool:
        return False


_LOGGER = _Silent(logging.getLogger("mailroom.gateway"), {})
_RNG = random.SystemRandom()


class GatewayStopped(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"gateway stopped ({code})")


class _Live:
    def __init__(self) -> None:
        self.session_id: str | None = None
        self.resume_at: str | None = None
        self.seq: int | None = None
        self.tries: int = 0

    def forget(self) -> None:
        self.session_id = None
        self.resume_at = None
        self.seq = None


def gateway_url_allowed(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "wss" or host is None or not host.lower().endswith(P.HOST_SUFFIX):
        return False
    if port is not None or parts.password is not None or parts.username is not None:
        return False
    if parts.fragment or parts.path not in ("", "/"):
        return False
    return parts.query in ("", _QUERY)


def open_gateway(url: str) -> websockets.sync.client.ClientConnection:
    if not gateway_url_allowed(url):
        raise ValueError(GATEWAY_URL_MESSAGE)
    return websockets.sync.client.connect(
        url,
        user_agent_header=L.USER_AGENT.format(version=__version__),
        proxy=None,
        compression=None,
        ping_interval=None,
        open_timeout=P.OPEN_TIMEOUT_SECONDS,
        max_size=P.MAX_FRAME_BYTES,
        logger=_LOGGER,
    )


def _keep_running() -> bool:
    return False


def run_gateway(
    store: Store,
    settings: Settings,
    http: httpx.Client,
    *,
    connect: Callable[[str], Any] = open_gateway,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random = _RNG,
    stop: Callable[[], bool] = _keep_running,
) -> None:
    if settings.discord_owner_id == "" or settings.discord_channel_id == "":
        raise DiscordUnavailable("not configured") from None
    token = keychain.get_secret(L.TOKEN_NAME)
    state = _Live()
    started = False
    while not stop():
        if started:
            sleep(P.BACKOFF_SECONDS[min(state.tries, 6)])
            state.tries += 1
        started = True
        url = state.resume_at if state.resume_at is not None else P.GATEWAY_URL
        try:
            connection = connect(url)
        except (OSError, TimeoutError, websockets.exceptions.WebSocketException):
            continue
        if _session(connection, state, token, store, settings, http, stop, rng) == "stop":
            return


def _session(
    connection: Any,
    state: _Live,
    token: str,
    store: Store,
    settings: Settings,
    http: httpx.Client,
    stop: Callable[[], bool],
    rng: random.Random,
) -> str:
    opened = _read_hello(connection)
    if opened is None:
        return "resume"
    interval_ms, arrived = opened
    if state.resume_at is None:
        state.seq = None
        payload: dict[str, Any] = {
            "op": P.IDENTIFY,
            "d": {"token": token, "intents": P.INTENTS, "properties": P.PROPERTIES},
        }
    else:
        payload = {
            "op": P.RESUME,
            "d": {"token": token, "session_id": state.session_id, "seq": state.seq},
        }
    action = _transmit(connection, state, payload)
    if action is not None:
        return action
    return _loop(connection, state, store, settings, http, stop, rng, interval_ms, arrived)


def _read_hello(connection: Any) -> tuple[float, datetime] | None:
    deadline = clock.now() + timedelta(seconds=P.OPEN_TIMEOUT_SECONDS)
    while True:
        remaining = (deadline - clock.now()).total_seconds()
        if remaining <= 0:
            connection.close(P.RESUME_CLOSE)
            return None
        try:
            raw = connection.recv(timeout=min(remaining, P.POLL_SECONDS))
        except TimeoutError:
            continue
        return json.loads(raw)["d"]["heartbeat_interval"], clock.now()


def _loop(
    connection: Any,
    state: _Live,
    store: Store,
    settings: Settings,
    http: httpx.Client,
    stop: Callable[[], bool],
    rng: random.Random,
    interval_ms: float,
    arrived: datetime,
) -> str:
    interval = timedelta(milliseconds=interval_ms)
    due = arrived + timedelta(milliseconds=interval_ms * rng.random())
    awaiting = False
    # The first heartbeat waits until a frame has arrived, so its seq is that frame's.
    seen = False
    while True:
        if stop():
            connection.close(1000)
            return "stop"
        if seen and clock.now() >= due:
            if awaiting:
                connection.close(P.RESUME_CLOSE)
                return "resume"
            action = _transmit(connection, state, {"op": P.HEARTBEAT, "d": state.seq})
            if action is not None:
                return action
            awaiting = True
            due += interval
        remaining = (due - clock.now()).total_seconds()
        try:
            raw = connection.recv(timeout=min(remaining, P.POLL_SECONDS))
        except TimeoutError:
            continue
        except websockets.exceptions.ConnectionClosed:
            return _after_close(connection, state)
        seen = True
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        action, awaiting = _frame(payload, connection, state, store, settings, http, awaiting)
        if action is not None:
            return action


def _frame(
    payload: dict[str, Any],
    connection: Any,
    state: _Live,
    store: Store,
    settings: Settings,
    http: httpx.Client,
    awaiting: bool,
) -> tuple[str | None, bool]:
    sequence = payload.get("s")
    if sequence is not None:
        state.seq = sequence
    op = payload.get("op")
    if op == P.DISPATCH:
        _dispatch(payload, state, store, settings, http)
        return None, awaiting
    if op == P.HEARTBEAT:
        return _transmit(connection, state, {"op": P.HEARTBEAT, "d": state.seq}), True
    if op == P.HEARTBEAT_ACK:
        return None, False
    if op == P.RECONNECT:
        connection.close(P.RESUME_CLOSE)
        return "resume", awaiting
    if op == P.INVALID_SESSION:
        connection.close(P.RESUME_CLOSE)
        if payload.get("d") is True:
            return "resume", awaiting
        state.forget()
        return "ended", awaiting
    return None, awaiting


def _dispatch(
    payload: dict[str, Any], state: _Live, store: Store, settings: Settings, http: httpx.Client
) -> None:
    name = payload.get("t")
    if name == "READY":
        state.tries = 0
        data = payload["d"]
        resume_at = str(data["resume_gateway_url"]).rstrip("/") + "/" + P.QUERY
        if gateway_url_allowed(resume_at):
            state.session_id = data["session_id"]
            state.resume_at = resume_at
        else:
            state.session_id = None
            state.resume_at = None
    elif name == "RESUMED":
        state.tries = 0
    elif name == "INTERACTION_CREATE":
        try:
            handle_interaction(payload["d"], store, settings, http)
        except DiscordUnavailable:
            pass


def _transmit(connection: Any, state: _Live, payload: dict[str, Any]) -> str | None:
    try:
        connection.send(json.dumps(payload))
    except websockets.exceptions.ConnectionClosed:
        return _after_close(connection, state)
    return None


def _after_close(connection: Any, state: _Live) -> str:
    code = connection.close_code
    if code in P.FATAL_CLOSES:
        raise GatewayStopped(code) from None
    if code in P.SESSION_ENDING_CLOSES:
        state.forget()
        return "ended"
    return "resume"
