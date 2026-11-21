"""Phase 4g given tests: a poll round that meets a locked database is skipped, not fatal.

Another connection holds the file's write lock between rounds, as another program would. The
poll loop's stop event runs one hook per wait in the main thread, so each round happens at a
known point: a hook may take or release the lock and move the clock. The listener is a fake
gateway that waits for the stop and never touches the store.
"""

import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from mailroom import clock, service
from mailroom.config import Settings, get_settings
from mailroom.service import run_service
from mailroom.store import DB_FILENAME, Store, open_store
from tests.fakes import FakeKeychain, FakeTasksApp
from tests.integration.test_service import GOOD, World, deliver

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
OWNER = "444444444444444444"
THREAD = "mailroom-gateway"
PING = (
    f"<@{OWNER}> Mailroom's database has been locked by another program for 15 minutes, so "
    "mail checks are being skipped. Close whatever has it open; checks resume on their own."
)
FIXED = "Mailroom's database is free again. Mail checks have resumed."


class Clock:
    def __init__(self) -> None:
        self.moment = NOW

    def __call__(self) -> datetime:
        return self.moment


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(clock, "now", fake)
    return fake


def configure(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name, value in (
        ("MAILROOM_GMAIL_ACCOUNTS", "personal"),
        ("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b"),
        ("MAILROOM_TIME_ZONE", "America/New_York"),
        ("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111"),
        ("MAILROOM_DISCORD_OWNER_ID", OWNER),
        ("MAILROOM_TASKS_URL", FakeTasksApp.URL),
    ):
        monkeypatch.setenv(name, value)
    return get_settings()


@pytest.fixture
def settings(now: Clock, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings with both lock waits cut to 0.05 s, so a skipped round takes no time."""
    configure(monkeypatch)
    monkeypatch.setattr(service, "POLL_LOCK_SECONDS", 0.05)
    monkeypatch.setattr(service, "LISTENER_LOCK_SECONDS", 0.05)
    return get_settings()


@pytest.fixture
def world(fake_keychain: FakeKeychain) -> World:
    return World(fake_keychain, ("personal",))


class Lock:
    """Another program's connection to the database, holding its write lock while `held`."""

    def __init__(self, settings: Settings) -> None:
        open_store(settings).close()
        self.connection = sqlite3.connect(
            settings.data_dir / DB_FILENAME, timeout=0, isolation_level=None
        )

    def hold(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")

    def release(self) -> None:
        self.connection.execute("ROLLBACK")

    def close(self) -> None:
        if self.connection.in_transaction:
            self.release()
        self.connection.close()


class Steps(threading.Event):
    """The poll loop's stop event: wait n runs hooks[n] and stops after the last hook."""

    def __init__(self, hooks: list[Callable[[], None]]) -> None:
        super().__init__()
        self.hooks = hooks
        self.waits = 0

    def wait(self, timeout: float | None = None) -> bool:
        if threading.current_thread().name == THREAD:
            return super().wait(timeout)
        hook = self.hooks[self.waits]
        self.waits += 1
        hook()
        if self.waits >= len(self.hooks):
            self.set()
        return self.is_set()


def holding(store: Store, settings: Settings, http, *, stop) -> None:
    while not stop():
        threading.Event().wait(0.001)


def serve(world: World, settings: Settings, stop: threading.Event, gateway=holding) -> None:
    run_service(
        settings,
        say=world.lines.append,
        stop=stop,
        open_gmail=world.client,
        open_model_http=world.model_http,
        open_discord_http=world.discord_http,
        open_tasks_http=world.tasks_http,
        gateway=gateway,
    )


def pings(world: World) -> list[dict]:
    """Every channel message request the fake Discord saw about the database, in order."""
    bodies = []
    for request in world.discord.requests:
        if request.url.path.endswith("/messages") and request.method == "POST":
            body = json.loads(request.content)
            if "database" in body.get("content", ""):
                bodies.append(body)
    return bodies


def posted(world: World) -> list[str]:
    return [m["content"] for m in world.discord.messages if "database" in m["content"]]


def at(now: Clock, minutes: int) -> Callable[[], None]:
    def move() -> None:
        now.moment = NOW + timedelta(minutes=minutes)

    return move


def both(*hooks: Callable[[], None]) -> Callable[[], None]:
    def run() -> None:
        for hook in hooks:
            hook()

    return run


def nothing() -> None:
    return None


# The waits


def test_the_poll_store_waits_ten_seconds_and_each_listener_store_one_and_a_half(
    now: Clock, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (service.POLL_LOCK_SECONDS, service.LISTENER_LOCK_SECONDS) == (10.0, 1.5)
    assert service.STORE_WAIT == timedelta(minutes=15)
    found = configure(monkeypatch)
    waits: list[tuple[str, float]] = []
    listening = threading.Event()

    def tracking(found: Settings) -> Store:
        store = open_store(found)
        set_lock_wait = store.set_lock_wait

        def recording(seconds: float) -> None:
            waits.append((threading.current_thread().name, seconds))
            set_lock_wait(seconds)

        store.set_lock_wait = recording  # type: ignore[method-assign]
        return store

    def gateway(store: Store, found: Settings, http, *, stop) -> None:
        listening.set()
        holding(store, found, http, stop=stop)

    monkeypatch.setattr("mailroom.service.open_store", tracking)
    serve(world, found, Steps([lambda: listening.wait(5), nothing]), gateway)
    assert listening.is_set()
    assert waits == [("MainThread", 10.0), (THREAD, 1.5)]


# A round that meets the lock


def test_a_round_that_meets_a_locked_file_is_skipped_and_the_next_one_catches_up(
    settings: Settings, world: World
) -> None:
    lock = Lock(settings)
    deliver(world.gmail["personal"], 1)
    world.model.replies.extend([GOOD, GOOD])

    def take() -> None:
        deliver(world.gmail["personal"], 2)
        lock.hold()

    try:
        stop = Steps([take, lock.release, nothing])
        serve(world, settings, stop)
    finally:
        lock.close()
    assert stop.waits == 3
    assert world.lines.count("store: busy") == 1
    assert world.lines.count("store: ok") == 1
    assert world.lines.index("store: busy") < world.lines.index("store: ok")
    assert len([m for m in world.discord.messages if m["embeds"]]) == 2
    assert posted(world) == []
    assert not any("failed" in line for line in world.lines)


def test_an_untroubled_service_reports_no_store_line(settings: Settings, world: World) -> None:
    serve(world, settings, Steps([nothing, nothing, nothing]))
    assert not any(line.startswith("store:") for line in world.lines)


def test_a_lock_shorter_than_fifteen_minutes_sends_no_alert(
    settings: Settings, world: World, now: Clock
) -> None:
    lock = Lock(settings)
    try:
        hooks = [both(lock.hold, at(now, 1)), at(now, 15), both(lock.release, at(now, 16))]
        serve(world, settings, Steps([*hooks, at(now, 17)]))
    finally:
        lock.close()
    assert pings(world) == []
    assert world.lines.count("store: busy") == 1
    assert world.lines.count("store: ok") == 1


def test_a_file_locked_for_fifteen_minutes_pings_once_and_says_when_it_clears(
    settings: Settings, world: World, now: Clock
) -> None:
    lock = Lock(settings)
    try:
        hooks = [
            both(lock.hold, at(now, 1)),
            at(now, 11),
            at(now, 16),
            at(now, 21),
            both(lock.release, at(now, 26)),
            at(now, 27),
            at(now, 28),
        ]
        serve(world, settings, Steps(hooks))
    finally:
        lock.close()
    assert posted(world) == [PING, FIXED]
    first = pings(world)[0]
    assert first["allowed_mentions"] == {"users": [OWNER]}
    assert first["enforce_nonce"] is True
    assert isinstance(first["nonce"], str) and 0 < len(first["nonce"]) <= 25
    assert pings(world)[1]["allowed_mentions"] == {"parse": []}
    assert world.lines.count("store: busy") == 1
    assert world.lines.count("store: ok") == 1
    with open_store(settings) as store:
        assert store.pending_alerts() == ()


def test_a_lost_ping_reply_is_retried_with_the_same_nonce_and_posts_once(
    settings: Settings, world: World, now: Clock
) -> None:
    lock = Lock(settings)

    def lose() -> None:
        now.moment = NOW + timedelta(minutes=16)
        world.discord.failures.append("lost-reply")

    try:
        hooks = [
            both(lock.hold, at(now, 1)),
            lose,
            at(now, 17),
            at(now, 18),
            both(lock.release, at(now, 19)),
            at(now, 20),
            at(now, 21),
        ]
        serve(world, settings, Steps(hooks))
    finally:
        lock.close()
    tries = [body for body in pings(world) if body["content"] == PING]
    assert len(tries) == 2
    assert tries[0]["nonce"] == tries[1]["nonce"]
    assert posted(world) == [PING, FIXED]


def test_a_new_lock_after_one_clears_starts_a_new_fifteen_minutes(
    settings: Settings, world: World, now: Clock
) -> None:
    lock = Lock(settings)
    try:
        hooks = [
            both(lock.hold, at(now, 1)),
            at(now, 16),
            both(lock.release, at(now, 17)),
            at(now, 18),
            both(lock.hold, at(now, 19)),
            at(now, 30),
            at(now, 34),
            both(lock.release, at(now, 35)),
            at(now, 36),
            at(now, 37),
        ]
        serve(world, settings, Steps(hooks))
    finally:
        lock.close()
    assert posted(world) == [PING, FIXED, PING, FIXED]
    nonces = [body["nonce"] for body in pings(world) if body["content"] == PING]
    assert len(set(nonces)) == 2
    assert world.lines.count("store: busy") == 2


def test_the_listener_is_not_restarted_while_rounds_are_skipped(
    settings: Settings, world: World, now: Clock
) -> None:
    lock = Lock(settings)
    seen: list[int] = []
    alive = threading.Event()

    def gateway(store: Store, found: Settings, http, *, stop) -> None:
        seen.append(1)
        alive.set()
        holding(store, found, http, stop=stop)

    try:
        hooks = [both(lock.hold, lambda: alive.wait(5)), at(now, 5), lock.release, nothing]
        serve(world, settings, Steps(hooks), gateway)
    finally:
        lock.close()
    assert seen == [1]
    assert "discord gateway: running" in world.lines
    assert not any(line.startswith("discord gateway: failed") for line in world.lines)


# Errors that are not lock waits


def real_error() -> sqlite3.OperationalError:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("SELECT x FROM missing")
    except sqlite3.OperationalError as error:
        return error
    finally:
        connection.close()
    raise AssertionError("no error")


def test_a_database_error_that_is_not_a_lock_wait_still_stops_the_service(
    settings: Settings, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = real_error()
    threads: list[threading.Thread] = []

    def gateway(store: Store, found: Settings, http, *, stop) -> None:
        threads.append(threading.current_thread())
        holding(store, found, http, stop=stop)

    def broken(self: Store) -> int:
        raise error

    monkeypatch.setattr("mailroom.store.Store.clear_expired_text", broken)
    with pytest.raises(sqlite3.OperationalError) as caught:
        serve(world, settings, Steps([nothing, nothing]), gateway)
    assert caught.value is error
    assert not any(line.startswith("store:") for line in world.lines)
    assert all(not thread.is_alive() for thread in threads)
