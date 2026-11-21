"""Phase 4g: lock-wait branches the given tests leave open."""

import sqlite3
import threading
from types import SimpleNamespace

import httpx
import pytest

from mailroom import service
from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.interactions import handle_interaction
from tests.fakes import FakeDiscord, FakeKeychain
from tests.integration.test_service import World
from tests.integration.test_service_busy import (
    FIXED,
    PING,
    Clock,  # noqa: F401
    Lock,
    Steps,
    at,
    both,
    nothing,
    pings,
    posted,
    serve,
)
from tests.integration.test_service_busy import now as now
from tests.integration.test_service_busy import settings as settings
from tests.integration.test_service_busy import world as world

TOKEN = ("mailroom", "discord.bot-token")
PRIVATE = "SELECT secret FROM private_table"


def busy_error() -> sqlite3.OperationalError:
    error = sqlite3.OperationalError(PRIVATE)
    error.sqlite_errorcode = 5
    return error


def test_a_ping_without_a_bot_token_is_retried_on_a_later_busy_round(
    settings: Settings, world: World, now: object, fake_keychain: FakeKeychain
) -> None:
    lock = Lock(settings)
    token = fake_keychain.secrets[TOKEN]

    def lose_token() -> None:
        del fake_keychain.secrets[TOKEN]
        at(now, 16)()

    def restore() -> None:
        fake_keychain.secrets[TOKEN] = token
        at(now, 17)()

    try:
        hooks = [both(lock.hold, at(now, 1)), lose_token, restore, at(now, 18), nothing]
        serve(
            world,
            settings,
            Steps([*hooks[:3], both(lock.release, at(now, 19)), at(now, 20), at(now, 21)]),
        )
    finally:
        lock.close()
    assert posted(world) == [PING, FIXED]
    assert len([b for b in pings(world) if b["content"] == PING]) == 1


def test_a_ping_answered_with_an_error_status_is_retried_with_the_same_nonce(
    settings: Settings, world: World, now: object
) -> None:
    lock = Lock(settings)

    def refuse() -> None:
        at(now, 16)()
        world.discord.failures.append(httpx.Response(500))

    try:
        hooks = [
            both(lock.hold, at(now, 1)),
            refuse,
            at(now, 17),
            both(lock.release, at(now, 18)),
            at(now, 19),
            at(now, 20),
        ]
        serve(world, settings, Steps(hooks))
    finally:
        lock.close()
    tries = [b for b in pings(world) if b["content"] == PING]
    assert len(tries) == 2
    assert tries[0]["nonce"] == tries[1]["nonce"]
    assert posted(world) == [PING, FIXED]


def test_a_busy_end_of_episode_notice_keeps_the_episode_open(
    settings: Settings, world: World, now: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = Lock(settings)
    real = service.alerts.notice
    failures = [busy_error()]

    def notice(*args: object) -> None:
        if failures:
            raise failures.pop()
        real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(service.alerts, "notice", notice)
    try:
        hooks = [
            both(lock.hold, at(now, 1)),
            at(now, 16),
            both(lock.release, at(now, 17)),
            at(now, 18),
            at(now, 19),
            at(now, 20),
        ]
        serve(world, settings, Steps(hooks))
    finally:
        lock.close()
    assert posted(world) == [PING, FIXED]
    assert world.lines.count("store: ok") == 1
    assert not any(PRIVATE in line for line in world.lines)


def test_a_busy_error_from_listener_tracking_skips_only_that_round(
    settings: Settings, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    failures = [busy_error()]
    alive = threading.Event()

    def gateway(store: object, found: object, http: object, *, stop: object) -> None:
        alive.set()
        while not stop():  # type: ignore[operator]
            threading.Event().wait(0.001)

    def tracking(*args: object) -> None:
        if failures:
            raise failures.pop()

    monkeypatch.setattr(service, "_listener_alert", tracking)
    serve(world, settings, Steps([lambda: alive.wait(5), nothing, nothing, nothing]), gateway)
    assert world.lines.count("store: busy") == 1
    assert world.lines.count("store: ok") == 1
    assert not any(PRIVATE in line for line in world.lines)


def test_a_busy_reply_that_discord_refuses_reaches_a_direct_caller(settings: Settings) -> None:
    discord = FakeDiscord()
    event = discord.press("mr:notask:0123456789abcdef0123456789abcdef")

    def locked(item_id: str) -> None:
        raise busy_error()

    store = SimpleNamespace(post_by_item=locked)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as http:
        with pytest.raises(DiscordUnavailable):
            handle_interaction(event, store, settings, http)  # type: ignore[arg-type]
