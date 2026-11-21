"""Phase 4f given tests: the service restarts a failed Discord listener and keeps polling.

Every attempt is a scripted fake gateway. The poll loop's stop event runs one hook per wait,
in the main thread, so each round happens at a known point in the listener's script.
"""

import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock, service
from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.gateway import GatewayStopped
from mailroom.interactions import handle_interaction
from mailroom.keychain import KeychainUnavailable, SecretMissing
from mailroom.service import run_service
from mailroom.store import Store, open_store
from tests.fakes import FakeKeychain, FakeTasksApp
from tests.integration.test_service import GOOD, World, deliver

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
OWNER = "444444444444444444"
PRIVATE = "Your bill of $42.00"
THREAD = "mailroom-gateway"
STOPPED_TAIL = ". Buttons and commands won't answer until the service is restarted."
KEEPS_FAILING = (
    f"<@{OWNER}> The Discord listener has kept failing for 15 minutes (failed (RuntimeError)). "
    "It restarts on its own; buttons and commands may not answer until it does."
)
ANSWERING = "The Discord listener is answering again."


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


@pytest.fixture
def settings(now: Clock, monkeypatch: pytest.MonkeyPatch) -> Settings:
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


@pytest.fixture(autouse=True)
def opened(monkeypatch: pytest.MonkeyPatch) -> list[Store]:
    """Every store the service opens, in order; closing one records it in CLOSED."""
    stores: list[Store] = []
    CLOSED.clear()

    def tracking(found: Settings) -> Store:
        store = open_store(found)
        close = store.close

        def closing() -> None:
            CLOSED.add(id(store))
            close()

        store.close = closing  # type: ignore[method-assign]
        stores.append(store)
        return store

    monkeypatch.setattr("mailroom.service.open_store", tracking)
    return stores


@pytest.fixture
def world(fake_keychain: FakeKeychain) -> World:
    return World(fake_keychain, ("personal",))


def expect(event: threading.Event) -> None:
    assert event.wait(5), "the listener did not reach the expected point"


class Script:
    """Scripted listener attempts. A step is an exception to raise, "return", "hold" (run until
    stop), "fail-later" (run until `release[i]`, then raise RuntimeError(PRIVATE)), or a
    callable run with the attempt's store, settings and http before holding."""

    def __init__(self, *steps: object) -> None:
        self.steps = list(steps)
        self.calls = 0
        self.active = 0
        self.most = 0
        self.lock = threading.Lock()
        self.started = [threading.Event() for _ in range(len(steps) + 1)]
        self.release = [threading.Event() for _ in range(len(steps) + 1)]
        self.stores: list[Store] = []
        self.https: list[httpx.Client] = []
        self.threads: list[threading.Thread] = []
        self.earlier_closed: list[bool] = []

    def __call__(
        self, store: Store, settings: Settings, http: httpx.Client, *, stop: Callable[[], bool]
    ) -> None:
        with self.lock:
            index = self.calls
            self.calls += 1
            self.active += 1
            self.most = max(self.most, self.active)
            self.earlier_closed.append(all(client.is_closed for client in self.https))
            self.stores.append(store)
            self.https.append(http)
            self.threads.append(threading.current_thread())
        try:
            step = self.steps[index] if index < len(self.steps) else "hold"
            self.started[min(index, len(self.steps))].set()
            if step == "return":
                return
            if isinstance(step, BaseException):
                raise step
            if callable(step):
                step(store, settings, http)
                step = "hold"
            while not stop():
                if step == "fail-later" and self.release[index].is_set():
                    raise RuntimeError(PRIVATE)
                threading.Event().wait(0.001)
        finally:
            with self.lock:
                self.active -= 1


class Gate:
    """The restart wait. Records each delay; returns at once while open, and while closed waits
    for `opened` or the stop event. Returns whether the service is stopping."""

    def __init__(self, stop: threading.Event, *, opened: bool = True) -> None:
        self.stop = stop
        self.delays: list[float] = []
        self.entered = threading.Event()
        self.opened = threading.Event()
        if opened:
            self.opened.set()

    def __call__(self, seconds: float) -> bool:
        self.delays.append(seconds)
        self.entered.set()
        while not self.opened.is_set() and not self.stop.is_set():
            threading.Event().wait(0.001)
        return self.stop.is_set()


class Steps(threading.Event):
    """The poll loop's stop event. Its nth wait runs hooks[n] and stops after the last hook.
    A wait from the listener's thread is an ordinary interruptible wait."""

    def __init__(self, *hooks: Callable[[], None]) -> None:
        super().__init__()
        self.hooks = list(hooks)
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


def noop() -> None:
    return None


def join_listener() -> None:
    for thread in threading.enumerate():
        if thread.name == THREAD:
            thread.join(timeout=5)
            assert not thread.is_alive()


def serve(world: World, settings: Settings, stop: Steps, script: Script, **extra: object) -> None:
    run_service(
        settings,
        say=world.lines.append,
        stop=stop,
        open_gmail=world.client,
        open_model_http=world.model_http,
        open_discord_http=world.discord_http,
        open_tasks_http=world.tasks_http,
        gateway=script,
        **extra,
    )


def posted(world: World) -> list[str]:
    return [message["content"] for message in world.discord.messages if message["content"]]


def gateway_lines(world: World) -> list[str]:
    return [line for line in world.lines if line.startswith("discord gateway: ")]


CLOSED: set[int] = set()


def is_closed(store: Store) -> bool:
    """Whether the service closed this store. A store opened on the listener's thread can't be
    queried from another one, open or not, so the service's `open_store` records each close."""
    return id(store) in CLOSED


# Recoverable failures restart


@pytest.mark.parametrize(
    ("failure", "line"),
    [
        pytest.param(RuntimeError(PRIVATE), "discord gateway: failed (RuntimeError)", id="bug"),
        pytest.param(
            sqlite3.OperationalError("database is locked"),
            "discord gateway: failed (OperationalError)",
            id="database",
        ),
        pytest.param(KeyError(PRIVATE), "discord gateway: failed (KeyError)", id="key-error"),
        pytest.param(
            KeychainUnavailable("keychain unavailable: discord.bot-token"),
            "discord gateway: keychain unavailable: discord.bot-token",
            id="keychain-locked",
        ),
        pytest.param("return", "discord gateway: ended", id="returned-early"),
    ],
)
def test_a_recoverable_failure_restarts_with_fresh_resources(
    world: World, settings: Settings, failure: object, line: str
) -> None:
    script = Script(failure, "hold")
    stop = Steps(lambda: expect(script.started[1]))
    gate = Gate(stop)
    serve(world, settings, stop, script, restart_wait=gate)
    assert script.calls == 2
    assert gate.delays == [1]
    assert gateway_lines(world) == [
        "discord gateway: running",
        line,
        "discord gateway: running",
    ]
    assert script.earlier_closed == [True, True]
    assert script.stores[0] is not script.stores[1]
    assert script.https[0] is not script.https[1]
    assert all(client.is_closed for client in script.https)
    assert all(is_closed(store) for store in script.stores)
    assert not any(PRIVATE in text for text in world.lines)
    with open_store(settings) as store:
        assert store.pending_alerts() == ()
    assert posted(world) == []


def test_a_listener_that_cannot_open_its_client_is_retried_and_its_store_closed(
    world: World, settings: Settings, opened: list[Store]
) -> None:
    opened_https: list[int] = []

    def open_discord_http() -> httpx.Client:
        opened_https.append(1)
        if len(opened_https) == 2:
            raise RuntimeError(PRIVATE)
        return world.discord_http()

    script = Script("hold")
    stop = Steps(lambda: expect(script.started[0]))
    gate = Gate(stop)
    run_service(
        settings,
        say=world.lines.append,
        stop=stop,
        open_gmail=world.client,
        open_model_http=world.model_http,
        open_discord_http=open_discord_http,
        open_tasks_http=world.tasks_http,
        gateway=script,
        restart_wait=gate,
    )
    assert script.calls == 1
    assert gate.delays == [1]
    assert "discord gateway: failed (RuntimeError)" in world.lines
    assert len(opened) == 3
    assert all(is_closed(store) for store in opened)
    assert not any(PRIVATE in text for text in world.lines)


def test_restart_waits_back_off_to_a_cap(world: World, settings: Settings) -> None:
    script = Script(*(RuntimeError(PRIVATE) for _ in range(9)), "hold")
    stop = Steps(lambda: expect(script.started[9]))
    gate = Gate(stop)
    serve(world, settings, stop, script, restart_wait=gate)
    assert gate.delays == [1, 2, 4, 8, 16, 32, 60, 60, 60]
    assert script.calls == 10


def test_a_listener_that_survives_a_round_resets_the_backoff(
    world: World, settings: Settings
) -> None:
    script = Script(RuntimeError(PRIVATE), RuntimeError(PRIVATE), "fail-later", "hold")

    def fail_third() -> None:
        script.release[2].set()
        expect(script.started[3])

    stop = Steps(lambda: expect(script.started[2]), noop, fail_third)
    gate = Gate(stop)
    serve(world, settings, stop, script, restart_wait=gate)
    assert gate.delays == [1, 2, 1]


def test_only_one_listener_runs_at_a_time_on_one_thread(world: World, settings: Settings) -> None:
    script = Script(*(RuntimeError(PRIVATE) for _ in range(5)), "hold")

    def count_threads() -> None:
        expect(script.started[5])
        assert [thread.name for thread in threading.enumerate()].count(THREAD) == 1

    stop = Steps(count_threads)
    serve(world, settings, stop, script, restart_wait=Gate(stop))
    assert script.most == 1
    assert len({id(thread) for thread in script.threads}) == 1
    assert script.threads[0].name == THREAD
    assert script.threads[0] is not threading.current_thread()
    assert script.earlier_closed == [True] * 6


def test_a_later_press_works_after_a_handler_failure(world: World, settings: Settings) -> None:
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    pressed = threading.Event()
    outcomes: list[str] = []

    def press(store: Store, found: Settings, http: httpx.Client) -> None:
        event = world.discord.command("trust", "sam@example.test")
        outcomes.append(handle_interaction(event, store, found, http))
        pressed.set()

    script = Script(RuntimeError(PRIVATE), press)
    stop = Steps(lambda: expect(pressed))
    serve(world, settings, stop, script, restart_wait=Gate(stop))
    assert outcomes == ["trusted"]
    assert len(world.discord.callbacks) == 1
    with open_store(settings) as store:
        assert store.sender_status("sam@example.test") == "trusted"
    assert len(world.discord.messages) == 1
    assert "gmail personal: ok" in world.lines
    assert not any(PRIVATE in text for text in world.lines)


# Terminal outcomes stay stopped


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        pytest.param(GatewayStopped(4004), "gateway stopped (4004)", id="fatal-close"),
        pytest.param(
            DiscordUnavailable("not configured"),
            "discord unavailable (not configured)",
            id="not-configured",
        ),
        pytest.param(
            SecretMissing("secret not found: discord.bot-token"),
            "secret not found: discord.bot-token",
            id="missing-token",
        ),
    ],
)
def test_a_terminal_outcome_is_alerted_and_never_restarted(
    world: World, settings: Settings, failure: Exception, reason: str
) -> None:
    script = Script(failure, "hold")
    stop = Steps(join_listener, noop)
    gate = Gate(stop)
    serve(world, settings, stop, script, restart_wait=gate)
    assert script.calls == 1
    assert gate.delays == []
    assert gateway_lines(world) == ["discord gateway: running", f"discord gateway: {reason}"]
    assert posted(world) == [f"<@{OWNER}> The Discord listener stopped: {reason}{STOPPED_TAIL}"]
    assert script.https[0].is_closed
    assert is_closed(script.stores[0])


def test_a_terminal_outcome_after_restarts_stays_stopped(world: World, settings: Settings) -> None:
    script = Script(RuntimeError(PRIVATE), GatewayStopped(4004), "hold")
    stop = Steps(join_listener, noop)
    gate = Gate(stop)
    serve(world, settings, stop, script, restart_wait=gate)
    assert script.calls == 2
    assert gate.delays == [1]
    assert posted(world) == [
        f"<@{OWNER}> The Discord listener stopped: gateway stopped (4004){STOPPED_TAIL}"
    ]


# Shutdown


def test_shutdown_interrupts_the_default_restart_wait(
    world: World, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "RESTART_SECONDS", (30, 30, 30, 30, 30, 30, 30))
    script = Script(RuntimeError(PRIVATE), "hold")

    def failed() -> None:
        for _ in range(5000):
            if "discord gateway: failed (RuntimeError)" in world.lines:
                return
            threading.Event().wait(0.001)
        raise AssertionError("the listener did not report its failure")

    stop = Steps(failed)
    serve(world, settings, stop, script)
    assert script.calls == 1
    assert script.threads[0].name == THREAD
    assert not script.threads[0].is_alive()


def test_a_stop_during_the_restart_wait_starts_no_new_listener(
    world: World, settings: Settings
) -> None:
    script = Script(RuntimeError(PRIVATE), "hold")
    stop = Steps(noop)
    gate = Gate(stop, opened=False)
    stop.hooks[0] = lambda: expect(gate.entered)
    serve(world, settings, stop, script, restart_wait=gate)
    assert gate.delays == [1]
    assert script.calls == 1
    assert not script.threads[0].is_alive()


# Alerts


def test_a_listener_failing_for_15_minutes_pings_once_and_announces_recovery(
    world: World, settings: Settings, now: Clock
) -> None:
    script = Script("fail-later", "hold")
    stop = Steps(noop)
    gate = Gate(stop, opened=False)

    def fail() -> None:
        script.release[0].set()
        expect(gate.entered)
        now.moment = NOW + timedelta(minutes=1)

    def almost() -> None:
        now.moment = NOW + timedelta(minutes=15, seconds=59)

    def late() -> None:
        now.moment = NOW + timedelta(minutes=16)

    def recover() -> None:
        gate.opened.set()
        expect(script.started[1])
        now.moment = NOW + timedelta(minutes=17)

    stop.hooks = [fail, almost, late, recover, noop]
    serve(world, settings, stop, script, restart_wait=gate)
    assert posted(world) == [KEEPS_FAILING, ANSWERING]
    assert gate.delays == [1]
    assert not any(PRIVATE in text for text in posted(world))
    with open_store(settings) as store:
        assert store.pending_alerts() == ()


def test_a_listener_that_recovers_within_a_round_sends_no_alert(
    world: World, settings: Settings, now: Clock
) -> None:
    script = Script("fail-later", "hold")

    def fail() -> None:
        script.release[0].set()
        expect(script.started[1])

    def later() -> None:
        now.moment = NOW + timedelta(hours=1)

    stop = Steps(fail, later, noop)
    serve(world, settings, stop, script, restart_wait=Gate(stop))
    assert posted(world) == []
    with open_store(settings) as store:
        assert store.pending_alerts() == ()
        assert store.problem("listener") is None


def test_a_listener_still_failing_when_the_service_stops_sends_no_recovery(
    world: World, settings: Settings, now: Clock
) -> None:
    script = Script("fail-later", "hold")
    stop = Steps(noop)
    gate = Gate(stop, opened=False)

    def fail() -> None:
        script.release[0].set()
        expect(gate.entered)

    def late() -> None:
        now.moment = NOW + timedelta(minutes=20)

    stop.hooks = [fail, late, noop, noop]
    serve(world, settings, stop, script, restart_wait=gate)
    assert posted(world) == [KEEPS_FAILING]
    assert script.calls == 1


def test_a_listener_that_fails_between_every_round_still_alerts(
    world: World, settings: Settings, now: Clock
) -> None:
    script = Script("fail-later", "fail-later", "fail-later", "fail-later", "hold")

    def fail(index: int) -> Callable[[], None]:
        def hook() -> None:
            script.release[index].set()
            expect(script.started[index + 1])
            now.moment = NOW + timedelta(minutes=5 * (index + 1))

        return hook

    stop = Steps(fail(0), fail(1), fail(2), fail(3), noop, noop)
    gate = Gate(stop)
    serve(world, settings, stop, script, restart_wait=gate)
    assert posted(world) == [KEEPS_FAILING, ANSWERING]
    assert gate.delays == [1, 2, 4, 8]
