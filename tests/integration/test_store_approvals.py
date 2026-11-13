"""The owner's checkpoint 2 decision, recorded once, only for an item answered Yes."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime, time

import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.store import Approval, Due, Store, open_store
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


@pytest.mark.parametrize(
    ("first", "outcome", "title", "due"),
    [
        ("yes", "approve", "Pay the bill", DUE),
        ("edit", "change", "Pay online", Due(date=date(2026, 11, 21), time=None)),
        ("yes", "change", "Pay the bill", None),
        ("yes", "nodeadline", "Pay the bill", None),
        ("edit", "drop", "", None),
    ],
    ids=["approve", "change-with-date", "change-without", "no-deadline", "drop"],
)
def test_a_decision_after_yes_is_recorded_once_and_read_back(
    store: Store, first: str, outcome: str, title: str, due: Due | None
) -> None:
    store.record_answer(ITEM, first, "Pay the bill")
    assert store.record_approval(ITEM, outcome, title, due) is True
    expected = Approval(item_id=ITEM, outcome=outcome, title=title, due=due, decided_at=NOW)
    assert store.approval(ITEM) == expected
    assert store.record_approval(ITEM, "drop", "", None) is False
    assert store.approval(ITEM) == expected


@pytest.mark.parametrize("first", [None, "notask", "mute"], ids=["unanswered", "notask", "mute"])
def test_nothing_is_recorded_without_a_yes(store: Store, first: str | None) -> None:
    if first is not None:
        store.record_answer(ITEM, first, "")
    assert store.record_approval(ITEM, "nodeadline", "Pay the bill", None) is False
    assert store.approval(ITEM) is None


def test_an_unknown_item_has_no_approval(store: Store) -> None:
    assert store.approval("b" * 32) is None
    assert store.record_approval("b" * 32, "nodeadline", "Pay the bill", None) is False


@pytest.mark.parametrize(
    ("outcome", "title", "due"),
    [
        ("approve", "Pay the bill", None),
        ("drop", "Pay the bill", None),
        ("change", "", None),
        ("nodeadline", "Pay the bill", DUE),
        ("drop", "", DUE),
        ("later", "Pay the bill", None),
    ],
    ids=[
        "approve-without-due",
        "drop-with-title",
        "change-without-title",
        "no-deadline-with-due",
        "drop-with-due",
        "unknown-outcome",
    ],
)
def test_a_decision_that_does_not_fit_is_refused(
    store: Store, outcome: str, title: str, due: Due | None
) -> None:
    store.record_answer(ITEM, "yes", "Pay the bill")
    with pytest.raises(sqlite3.IntegrityError):
        store.record_approval(ITEM, outcome, title, due)
    assert store.approval(ITEM) is None
