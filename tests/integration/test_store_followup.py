"""A follow-up post names the approved item it follows, chosen once; "link" is an answer."""

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.schema import MIGRATIONS
from mailroom.store import Answer, Approval, Due, Store, open_store
from tests.integration.test_store_posts import NOTIFY, RECORD
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
DUE = Due(date=date(2026, 11, 20), time=time(17, 0))
A, B, C, D = ("a" * 32, "b" * 32, "c" * 32, "d" * 32)


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    fixed_ids(monkeypatch, A, B, C, D)
    return now


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    """m1, m2 and m3 in thread t1, m4 in thread t2; posted in that order as a, b, c, d."""
    with open_store(get_settings()) as opened:
        for message_id, thread_id in (("m1", "t1"), ("m2", "t1"), ("m3", "t1"), ("m4", "t2")):
            opened.add(replace(RECORD, message_id=message_id, thread_id=thread_id))
            opened.save_triage("gmail", message_id, NOTIFY)
        opened.queue_notified()
        yield opened


def approve(store: Store, item: str, outcome: str = "approve", title: str = "Pay the bill") -> None:
    store.record_answer(item, "yes", "Pay the bill")
    due = DUE if outcome == "approve" else None
    assert store.record_approval(item, outcome, "" if outcome == "drop" else title, due)


def test_a_follow_up_card_and_its_target_are_chosen_once(store: Store) -> None:
    assert store.choose_card(B, "followup", follows=A) == "followup"
    assert store.choose_card(B, "first") == "followup"
    assert (store.post_by_item(B).card, store.post_by_item(B).follows) == ("followup", A)
    assert store.post_by_item(C).follows is None


@pytest.mark.parametrize(
    ("card", "follows"),
    [("followup", None), ("first", A), ("combined", A)],
    ids=["followup-without-target", "first-with-target", "combined-with-target"],
)
def test_half_a_follow_up_is_refused(store: Store, card: str, follows: str | None) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.choose_card(B, card, follows=follows)
    assert (store.post_by_item(B).card, store.post_by_item(B).follows) == (None, None)


def test_link_is_an_answer_that_closes_the_item(store: Store) -> None:
    assert store.record_answer(B, "link", "") is True
    assert store.answer(B) == Answer(item_id=B, answer="link", title="", answered_at=NOW)
    assert store.record_approval(B, "nodeadline", "Pay the bill", None) is False
    assert store.record_answer(B, "yes", "Pay the bill") is False


def test_the_thread_gives_its_latest_approved_item(store: Store, moment: list[datetime]) -> None:
    approve(store, A, title="Pay the October bill")
    assert store.approved_in_thread("gmail", "t1") == Approval(
        item_id=A, outcome="approve", title="Pay the October bill", due=DUE, decided_at=NOW
    )
    moment[0] = LATER
    approve(store, C, "nodeadline", title="Pay the November bill")
    assert store.approved_in_thread("gmail", "t1").item_id == C


def test_a_dropped_or_undecided_item_is_not_a_target(store: Store) -> None:
    approve(store, A, "drop")
    store.record_answer(B, "yes", "Pay the bill")
    store.record_answer(C, "notask", "")
    assert store.approved_in_thread("gmail", "t1") is None


def test_another_thread_or_provider_is_not_a_target(store: Store) -> None:
    approve(store, A)
    assert store.approved_in_thread("gmail", "t2") is None
    assert store.approved_in_thread("outlook", "t1") is None


def test_items_decided_at_the_same_moment_are_ordered_by_item(store: Store) -> None:
    approve(store, C)
    approve(store, A)
    assert store.approved_in_thread("gmail", "t1").item_id == C


def test_a_version_11_database_keeps_its_posts_and_answers(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("\n".join(MIGRATIONS[:11]) + "\nPRAGMA user_version = 11;")
    connection.execute(
        "INSERT INTO posts (item_id, provider, message_id, queued_at, discord_message_id,"
        " posted_at, card) VALUES ('item-1', 'gmail', 'personal/m1', '2026-11-10T08:00:00+00:00',"
        " '1300000000000000001', '2026-11-10T08:01:00+00:00', 'combined')"
    )
    connection.execute(
        "INSERT INTO answers VALUES ('item-1', 'yes', 'Pay the bill', '2026-11-10T08:02:00+00:00')"
    )
    connection.commit()
    connection.close()
    with Store(path) as store:
        post = store.post_by_item("item-1")
        assert (post.card, post.follows, post.discord_message_id) == (
            "combined",
            None,
            "1300000000000000001",
        )
        assert store.answer("item-1").title == "Pay the bill"
        assert store.record_answer("item-1", "link", "") is False
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (12,)
    finally:
        connection.close()
