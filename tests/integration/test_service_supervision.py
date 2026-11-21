"""Phase 4f: supervisor branches the given listener tests leave open."""

import threading

import pytest

from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.store import Store
from tests.fakes import FakeKeychain
from tests.integration.test_service import World
from tests.integration.test_service_listener import (
    PRIVATE,
    Gate,
    Script,
    Steps,
    expect,
    gateway_lines,
    is_closed,
    noop,
    serve,
)
from tests.integration.test_service_listener import now as now
from tests.integration.test_service_listener import opened as opened
from tests.integration.test_service_listener import settings as settings


@pytest.fixture
def world(fake_keychain: FakeKeychain) -> World:
    return World(fake_keychain, ("personal",))


def test_a_failure_while_the_stop_event_is_set_ends_without_another_attempt(
    world: World, settings: Settings
) -> None:
    stop = Steps(noop)

    def failing(*args: object, stop: object) -> None:
        stop_event.set()
        raise RuntimeError(PRIVATE)

    stop_event = stop
    gate = Gate(stop)
    serve(world, settings, stop, failing, restart_wait=gate)  # type: ignore[arg-type]
    assert "discord gateway: failed (RuntimeError)" in world.lines
    assert gate.delays == [1]
    assert not any(PRIVATE in line for line in world.lines)


def test_a_restart_wait_that_says_stop_ends_the_listener_with_the_event_clear(
    world: World, settings: Settings
) -> None:
    script = Script(RuntimeError(PRIVATE), "hold")
    delays: list[float] = []

    def wait(seconds: float) -> bool:
        delays.append(seconds)
        return True

    stop = Steps(lambda: _until(lambda: delays))
    serve(world, settings, stop, script, restart_wait=wait)
    assert script.calls == 1
    assert delays == [1]
    assert not script.threads[0].is_alive()


def test_a_store_that_will_not_open_is_retried(
    world: World, settings: Settings, monkeypatch: pytest.MonkeyPatch, opened: list[Store]
) -> None:
    real = __import__("mailroom.service", fromlist=["open_store"]).open_store
    calls: list[int] = []

    def flaky(found: Settings) -> Store:
        calls.append(1)
        if len(calls) == 2:
            raise OSError(PRIVATE)
        return real(found)

    monkeypatch.setattr("mailroom.service.open_store", flaky)
    script = Script("hold")
    stop = Steps(lambda: expect(script.started[0]))
    gate = Gate(stop)
    serve(world, settings, stop, script, restart_wait=gate)
    assert gate.delays == [1]
    assert "discord gateway: failed (OSError)" in world.lines
    assert not any(PRIVATE in line for line in world.lines)


def test_a_terminal_kind_raised_while_opening_is_only_recoverable(
    world: World, settings: Settings
) -> None:
    calls: list[int] = []

    def open_http() -> object:
        calls.append(1)
        if len(calls) == 2:
            raise DiscordUnavailable("not configured")
        return world.discord_http()

    script = Script("hold")
    stop = Steps(lambda: expect(script.started[0]))
    gate = Gate(stop)
    from mailroom.service import run_service

    run_service(
        settings,
        say=world.lines.append,
        stop=stop,
        open_gmail=world.client,
        open_model_http=world.model_http,
        open_discord_http=open_http,  # type: ignore[arg-type]
        open_tasks_http=world.tasks_http,
        gateway=script,
        restart_wait=gate,
    )
    assert gate.delays == [1]
    assert "discord gateway: failed (DiscordUnavailable)" in world.lines
    assert script.calls == 1
    assert "discord gateway: running" in gateway_lines(world)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_non_exception_is_not_caught_and_resources_close(
    world: World, settings: Settings, opened: list[Store]
) -> None:
    class Quit(BaseException):
        pass

    script = Script(Quit(), "hold")
    stop = Steps(lambda: _until(lambda: script.calls == 1))
    serve(world, settings, stop, script, restart_wait=Gate(stop))
    assert script.calls == 1
    assert script.https[0].is_closed
    assert is_closed(script.stores[0])


def test_the_listener_stays_untracked_once_its_thread_has_ended(
    world: World, settings: Settings
) -> None:
    from mailroom.gateway import GatewayStopped

    script = Script(GatewayStopped(4004))
    stop = Steps(lambda: _until(lambda: not _alive()), noop, noop)
    serve(world, settings, stop, script, restart_wait=Gate(stop))
    from mailroom.store import open_store

    with open_store(settings) as store:
        assert store.problem("listener") is None


def _alive() -> bool:
    return any(t.name == "mailroom-gateway" and t.is_alive() for t in threading.enumerate())


def _until(done: object) -> None:
    for _ in range(5000):
        if done():  # type: ignore[operator]
            return
        threading.Event().wait(0.001)
    raise AssertionError("the expected point was not reached")


def test_a_wait_that_returns_false_with_the_stop_event_set_starts_nothing_more(
    world: World, settings: Settings
) -> None:
    script = Script(RuntimeError(PRIVATE), "hold")
    holder: list[Steps] = []

    def wait(seconds: float) -> bool:
        holder[0].set()
        return False

    stop = Steps(lambda: _until(lambda: script.calls == 1))
    holder.append(stop)
    serve(world, settings, stop, script, restart_wait=wait)
    assert script.calls == 1
