"""Follow-ups added to a task: queued once, sent only once that task has its id in the app."""

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.schema import MIGRATIONS
from mailroom.store import Link, Store, open_store
from tests.integration.test_store_posts import NOTIFY, RECORD
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
A, B, C, D = ("a" * 32, "b" * 32, "c" * 32, "d" * 32)


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    fixed_ids(monkeypatch, A, B, C, D)
    return now


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    """m1 (a) approved, its task queued; m2 (b), m3 (c) and m4 (d) are follow-ups of a."""
    with open_store(get_settings()) as opened:
        for message_id in ("m1", "m2", "m3", "m4"):
            opened.add(replace(RECORD, message_id=message_id))
            opened.save_triage("gmail", message_id, NOTIFY)
        opened.queue_notified()
        opened.record_answer(A, "yes", "Pay the bill")
        opened.record_approval(A, "nodeadline", "Pay the bill", None)
        opened.queue_approved()
        for item in (B, C, D):
            opened.choose_card(item, "followup", follows=A)
        yield opened


def test_a_linked_follow_up_is_queued_once_with_its_task(store: Store) -> None:
    store.mark_task_sent(A, "task-1")
    store.record_answer(B, "link", "")
    assert store.queue_linked() == 1
    assert store.pending_links() == (Link(B, "gmail", "m2", A, "task-1", NOW, None),)
    assert store.queue_linked() == 0
    assert len(store.pending_links()) == 1


def test_other_answers_on_a_follow_up_are_not_queued(store: Store) -> None:
    store.mark_task_sent(A, "task-1")
    store.record_answer(B, "yes", "Pay the bill again")
    store.record_answer(C, "notask", "")
    assert store.queue_linked() == 0
    assert store.pending_links() == ()


def test_a_link_waits_until_its_task_has_an_id(store: Store) -> None:
    store.record_answer(B, "link", "")
    assert store.queue_linked() == 1
    assert store.pending_links() == ()
    assert store.link(B) == Link(B, "gmail", "m2", A, None, NOW, None)
    store.mark_task_sent(A, "task-1")
    assert [link.task_id for link in store.pending_links()] == ["task-1"]


def test_a_sent_link_leaves_the_queue(store: Store, moment: list[datetime]) -> None:
    store.mark_task_sent(A, "task-1")
    store.record_answer(B, "link", "")
    store.queue_linked()
    moment[0] = LATER
    assert store.mark_link_sent(B) is True
    assert store.mark_link_sent(B) is False
    assert store.link(B) == Link(B, "gmail", "m2", A, "task-1", NOW, LATER)
    assert store.pending_links() == ()
    assert store.queue_linked() == 0


def test_an_unknown_or_unqueued_link_records_nothing(store: Store) -> None:
    store.record_answer(B, "link", "")
    assert store.mark_link_sent(B) is False
    assert store.mark_link_sent("e" * 32) is False
    assert (store.link(B), store.link("e" * 32)) == (None, None)


def test_pending_links_come_in_queue_order_then_by_item(
    store: Store, moment: list[datetime]
) -> None:
    store.mark_task_sent(A, "task-1")
    store.record_answer(D, "link", "")
    store.queue_linked()
    moment[0] = LATER
    store.record_answer(C, "link", "")
    store.record_answer(B, "link", "")
    assert store.queue_linked() == 2
    assert [(link.item_id, link.queued_at) for link in store.pending_links()] == [
        (D, NOW),
        (B, LATER),
        (C, LATER),
    ]


def test_a_version_12_database_gains_an_empty_links_table(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("\n".join(MIGRATIONS[:12]) + "\nPRAGMA user_version = 12;")
    connection.close()
    with Store(path) as store:
        assert store.pending_links() == ()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (13,)
    finally:
        connection.close()
