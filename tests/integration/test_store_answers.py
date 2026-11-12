import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from mailroom.config import get_settings
from mailroom.record import Record
from mailroom.store import Answer, Post, Store, Verdict, open_store
from tests.support import fixed_ids, fixed_times

RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=None,
    body_text="Your bill is due.",
    list_unsubscribe=False,
    authentication_results=(),
)
UNREAD = Verdict(
    outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="timeout"
)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    fixed_ids(monkeypatch, "item-1")
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:00:01+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-10T09:00:00+00:00",
        "2026-11-10T09:05:00+00:00",
        "2026-11-10T09:10:00+00:00",
    )
    with open_store(get_settings()) as opened:
        opened.add(RECORD)
        opened.save_triage("gmail", "m1", UNREAD)
        opened.queue_notified()
        yield opened


def test_the_first_answer_is_kept(store: Store) -> None:
    assert store.answer("item-1") is None
    assert store.record_answer("item-1", "edit", "Pay the bill") is True
    assert store.record_answer("item-1", "notask", "") is False
    assert store.record_answer("item-9", "notask", "") is False
    assert store.answer("item-1") == Answer(
        item_id="item-1",
        answer="edit",
        title="Pay the bill",
        answered_at=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
    )
    assert store.answer("item-9") is None


def test_a_post_is_found_by_its_item_id(store: Store) -> None:
    assert store.post_by_item("item-1") == Post(
        item_id="item-1",
        provider="gmail",
        message_id="m1",
        queued_at=datetime(2026, 11, 10, 8, 1, tzinfo=UTC),
        discord_message_id=None,
        posted_at=None,
    )
    assert store.post_by_item("item-9") is None


@pytest.mark.parametrize(
    ("answer", "title"),
    [("yes", ""), ("notask", "A title"), ("later", "")],
    ids=["yes-without-title", "not-a-task-with-title", "unknown-answer"],
)
def test_an_inconsistent_answer_is_refused_by_the_table(
    store: Store, answer: str, title: str
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.record_answer("item-1", answer, title)  # type: ignore[arg-type]
    assert store.answer("item-1") is None
