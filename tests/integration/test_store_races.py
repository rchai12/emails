"""Two stores on one file, as `mailroom run` has (the round's and the listener's).

The other store writes the same key while the first is inside its call: the fake clock runs that
write on the first store's clock read, which every insert makes before writing.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.store import Problem, Store, open_store

THEIRS = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
MINE = datetime(2026, 11, 13, 9, 5, tzinfo=UTC)


@pytest.fixture
def stores() -> Iterator[tuple[Store, Store]]:
    with open_store(get_settings()) as mine, open_store(get_settings()) as theirs:
        yield mine, theirs


def race(monkeypatch: pytest.MonkeyPatch, other_write: Callable[[], object]) -> None:
    """The first clock read runs `other_write` (which reads THEIRS), then returns MINE."""
    raced: list[bool] = []

    def now() -> datetime:
        if raced:
            return THEIRS
        raced.append(True)
        other_write()
        return MINE

    monkeypatch.setattr(clock, "now", now)


def test_opening_a_problem_another_store_just_opened_returns_theirs(
    stores: tuple[Store, Store], monkeypatch: pytest.MonkeyPatch
) -> None:
    mine, theirs = stores
    race(monkeypatch, lambda: theirs.open_problem("model"))
    expected = Problem(key="model", since=THEIRS, alerted=False)
    assert mine.open_problem("model") == expected
    assert (mine.problem("model"), theirs.problem("model")) == (expected, expected)


def test_queueing_an_alert_another_store_just_queued_keeps_theirs(
    stores: tuple[Store, Store], monkeypatch: pytest.MonkeyPatch
) -> None:
    mine, theirs = stores
    race(monkeypatch, lambda: theirs.queue_alert("model:raised", "Their text.", True))
    assert mine.queue_alert("model:raised", "My text.", False) is False
    (alert,) = mine.pending_alerts()
    assert (alert.key, alert.text, alert.ping, alert.queued_at) == (
        "model:raised",
        "Their text.",
        True,
        THEIRS,
    )
    assert theirs.queue_alert("other:raised", "Still writable.", False) is True


def test_closing_a_problem_is_one_statement_and_happens_once(
    stores: tuple[Store, Store], monkeypatch: pytest.MonkeyPatch
) -> None:
    mine, theirs = stores
    monkeypatch.setattr(clock, "now", lambda: THEIRS)
    theirs.open_problem("model")

    def read_first(key: str) -> None:
        raise AssertionError("close_problem read the problem before deleting it")

    monkeypatch.setattr(mine, "problem", read_first)
    assert mine.close_problem("model") == Problem(key="model", since=THEIRS, alerted=False)
    assert mine.close_problem("model") is None
    assert theirs.close_problem("model") is None
    assert theirs.problem("model") is None
