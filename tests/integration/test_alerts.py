from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from mailroom import clock
from mailroom.alerts import notice, track
from mailroom.config import get_settings
from mailroom.store import Problem, Store, open_store

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
WAIT = timedelta(minutes=15)


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
def store(now: Clock) -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def queued(store: Store) -> list[tuple[str, bool]]:
    return [(alert.text, alert.ping) for alert in store.pending_alerts()]


def model(store: Store, failing: bool) -> None:
    track(store, "model", failing, wait=WAIT, raised="down", ping=False, resolved="up")


def test_a_problem_alerts_once_after_it_has_lasted_long_enough(store: Store, now: Clock) -> None:
    model(store, True)
    now.moment += timedelta(minutes=14, seconds=59)
    model(store, True)
    assert queued(store) == []
    now.moment += timedelta(seconds=1)
    model(store, True)
    now.moment += timedelta(minutes=5)
    model(store, True)
    assert queued(store) == [("down", False)]
    assert store.problem("model") == Problem(key="model", since=NOW, alerted=True)


def test_an_immediate_problem_alerts_in_the_same_call(store: Store) -> None:
    track(store, "gateway", True, wait=timedelta(0), raised="stopped", ping=True, resolved="ok")
    assert queued(store) == [("stopped", True)]


def test_a_fixed_problem_says_so_only_if_it_was_announced(store: Store, now: Clock) -> None:
    model(store, True)
    now.moment += WAIT
    model(store, True)
    model(store, False)
    assert queued(store) == [("down", False), ("up", False)]
    assert store.problem("model") is None
    track(store, "brief", True, wait=WAIT, raised="brief down", ping=False, resolved="brief up")
    track(store, "brief", False, wait=WAIT, raised="brief down", ping=False, resolved="brief up")
    assert store.problem("brief") is None
    assert len(queued(store)) == 2


def test_a_problem_that_returns_is_announced_again(store: Store, now: Clock) -> None:
    for _ in range(2):
        model(store, True)
        now.moment += WAIT
        model(store, True)
        now.moment += timedelta(minutes=1)
        model(store, False)
        now.moment += timedelta(minutes=1)
    assert queued(store) == [("down", False), ("up", False), ("down", False), ("up", False)]


def test_success_without_a_problem_queues_nothing(store: Store) -> None:
    model(store, False)
    assert (queued(store), store.problem("model")) == ([], None)


def test_a_notice_is_queued_once_per_key(store: Store) -> None:
    notice(store, "catch-up:personal:1", "caught up")
    notice(store, "catch-up:personal:1", "caught up")
    notice(store, "catch-up:personal:2", "caught up again")
    assert queued(store) == [("caught up", False), ("caught up again", False)]


def test_problems_and_alerts_survive_a_restart(now: Clock) -> None:
    with open_store(get_settings()) as store:
        track(store, "gateway", True, wait=timedelta(0), raised="stopped", ping=True, resolved="ok")
    now.moment += timedelta(hours=1)
    with open_store(get_settings()) as store:
        track(
            store, "gateway", False, wait=timedelta(0), raised="stopped", ping=True, resolved="ok"
        )
        assert queued(store) == [("stopped", True), ("ok", False)]
