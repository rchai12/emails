"""Which card a post got, chosen once; and a combined decision, recorded as both answers at once."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.schema import MIGRATIONS
from mailroom.store import Answer, Approval, Due, Store, open_store
from tests.integration.test_store_posts import NOTIFY, RECORD
from tests.support import fixed_ids

ITEM = "a" * 32
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
DUE = Due(date=date(2026, 11, 20), time=time(17, 0))


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    fixed_ids(monkeypatch, ITEM)
    with open_store(get_settings()) as opened:
        opened.add(RECORD)
        opened.save_triage("gmail", "m1", NOTIFY)
        opened.queue_notified()
        yield opened


def test_a_card_is_chosen_once_and_kept(store: Store) -> None:
    assert store.pending_posts()[0].card is None
    assert store.choose_card(ITEM, "combined") == "combined"
    assert store.choose_card(ITEM, "first") == "combined"
    assert store.pending_posts()[0].card == "combined"
    store.mark_posted(ITEM, "1300000000000000001")
    assert store.post_by_item(ITEM).card == "combined"


def test_an_unknown_card_is_refused(store: Store) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.choose_card(ITEM, "second")
    assert store.pending_posts()[0].card is None


@pytest.mark.parametrize(
    ("outcome", "title", "due", "answer"),
    [
        ("approve", "Pay the bill", DUE, "yes"),
        ("nodeadline", "Pay the bill", None, "yes"),
        ("change", "Pay online", Due(date=date(2026, 11, 21), time=None), "edit"),
        ("change", "Pay online", None, "edit"),
    ],
    ids=["approve", "no-deadline", "change-with-date", "change-without"],
)
def test_a_combined_decision_records_both_answers_at_once(
    store: Store, outcome: str, title: str, due: Due | None, answer: str
) -> None:
    assert store.record_combined(ITEM, outcome, title, due) is True
    assert store.answer(ITEM) == Answer(item_id=ITEM, answer=answer, title=title, answered_at=NOW)
    assert store.approval(ITEM) == Approval(
        item_id=ITEM, outcome=outcome, title=title, due=due, decided_at=NOW
    )


@pytest.mark.parametrize("first", ["yes", "notask"], ids=["yes", "notask"])
def test_an_item_already_answered_records_nothing_more(store: Store, first: str) -> None:
    store.record_answer(ITEM, first, "Pay the bill" if first == "yes" else "")
    assert store.record_combined(ITEM, "approve", "Pay it", DUE) is False
    assert store.answer(ITEM).answer == first
    assert store.approval(ITEM) is None


def test_an_unknown_item_records_nothing(store: Store) -> None:
    assert store.record_combined("b" * 32, "nodeadline", "Pay the bill", None) is False
    assert (store.answer("b" * 32), store.approval("b" * 32)) == (None, None)


def test_a_decision_the_schema_refuses_keeps_neither_answer(store: Store) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.record_combined(ITEM, "approve", "Pay the bill", None)
    assert (store.answer(ITEM), store.approval(ITEM)) == (None, None)


def test_a_version_9_database_gains_the_card_column_unset(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("\n".join(MIGRATIONS[:9]) + "\nPRAGMA user_version = 9;")
    connection.execute(
        "INSERT INTO posts (item_id, provider, message_id, queued_at, discord_message_id,"
        " posted_at) VALUES ('item-1', 'gmail', 'personal/m1', '2026-11-10T08:00:00+00:00',"
        " '1300000000000000001', '2026-11-10T08:01:00+00:00')"
    )
    connection.commit()
    connection.close()
    with Store(path) as store:
        assert store.post_by_item("item-1").card is None
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (12,)
    finally:
        connection.close()
