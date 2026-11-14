"""Approved tasks queued once per email, and the tasks app's id kept once it is sent."""

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.schema import MIGRATIONS
from mailroom.store import Due, Store, Task, open_store
from tests.integration.test_store_posts import NOTIFY, RECORD
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
DUE = Due(date=date(2026, 11, 20), time=time(17, 0))


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    fixed_ids(monkeypatch, "a" * 32, "b" * 32, "c" * 32)
    return now


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        for message_id in ("m1", "m2", "m3"):
            opened.add(replace(RECORD, message_id=message_id))
            opened.save_triage("gmail", message_id, NOTIFY)
        opened.queue_notified()
        yield opened


def item(store: Store, message_id: str) -> str:
    return store.post("gmail", message_id).item_id


def decide(store: Store, message_id: str, outcome: str, due: Due | None = None) -> str:
    found = item(store, message_id)
    store.record_answer(found, "yes", "Pay the bill")
    title = "" if outcome == "drop" else "Pay the bill"
    assert store.record_approval(found, outcome, title, due) is True
    return found


@pytest.mark.parametrize(
    ("outcome", "due"),
    [("approve", DUE), ("change", None), ("nodeadline", None)],
    ids=["approve", "change", "no-deadline"],
)
def test_an_approved_item_is_queued_once_with_its_email(
    store: Store, outcome: str, due: Due | None
) -> None:
    found = decide(store, "m1", outcome, due)
    assert store.queue_approved() == 1
    assert store.pending_tasks() == (Task(found, "gmail", "m1", NOW, None, None),)
    assert store.queue_approved() == 0
    assert len(store.pending_tasks()) == 1


def test_a_dropped_undecided_or_closed_item_is_not_queued(store: Store) -> None:
    decide(store, "m1", "drop")
    store.record_answer(item(store, "m2"), "yes", "Pay the bill")
    store.record_answer(item(store, "m3"), "notask", "")
    assert store.queue_approved() == 0
    assert store.pending_tasks() == ()


def test_a_combined_decision_is_queued_like_any_other(store: Store) -> None:
    found = item(store, "m2")
    assert store.record_combined(found, "approve", "Pay the bill", DUE) is True
    assert store.queue_approved() == 1
    assert store.pending_tasks() == (Task(found, "gmail", "m2", NOW, None, None),)


def test_a_sent_task_keeps_its_id_and_leaves_the_queue(
    store: Store, moment: list[datetime]
) -> None:
    found = decide(store, "m1", "approve", DUE)
    store.queue_approved()
    moment[0] = LATER
    assert store.mark_task_sent(found, "task-7") is True
    assert store.mark_task_sent(found, "task-8") is False
    assert store.task(found) == Task(found, "gmail", "m1", NOW, "task-7", LATER)
    assert store.pending_tasks() == ()
    assert store.queue_approved() == 0


def test_an_unknown_or_unqueued_item_records_nothing(store: Store) -> None:
    found = decide(store, "m1", "approve", DUE)
    assert store.mark_task_sent(found, "task-1") is False
    assert store.mark_task_sent("d" * 32, "task-1") is False
    assert (store.task(found), store.task("d" * 32)) == (None, None)


def test_pending_tasks_come_in_queue_order_then_by_item(
    store: Store, moment: list[datetime]
) -> None:
    decide(store, "m3", "nodeadline")
    store.queue_approved()
    moment[0] = LATER
    decide(store, "m2", "nodeadline")
    decide(store, "m1", "nodeadline")
    assert store.queue_approved() == 2
    assert [(task.item_id, task.queued_at) for task in store.pending_tasks()] == [
        ("c" * 32, NOW),
        ("a" * 32, LATER),
        ("b" * 32, LATER),
    ]


@pytest.mark.parametrize("task_id", ["", "t" * 101], ids=["empty", "too-long"])
def test_a_task_id_the_schema_refuses_is_not_recorded(store: Store, task_id: str) -> None:
    found = decide(store, "m1", "approve", DUE)
    store.queue_approved()
    with pytest.raises(sqlite3.IntegrityError):
        store.mark_task_sent(found, task_id)
    assert store.task(found).task_id is None
    assert len(store.pending_tasks()) == 1


def test_a_version_10_database_gains_an_empty_tasks_table(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("\n".join(MIGRATIONS[:10]) + "\nPRAGMA user_version = 10;")
    connection.close()
    with Store(path) as store:
        assert store.pending_tasks() == ()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (13,)
    finally:
        connection.close()
