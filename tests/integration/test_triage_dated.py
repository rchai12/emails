"""Triage decides 'clearly dated' with the rule from Phase 2b and stores it with the deadline."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time

import pytest

from mailroom.config import Settings, get_settings
from mailroom.store import Due, Store, open_store
from tests.integration.test_triage import GOOD, RECORD, run
from tests.support import fixed_times

ADDED = "2026-11-10T08:01:00+00:00"
NOW = "2026-11-10T08:04:00+00:00"
DECIDED = "2026-11-10T08:05:00+00:00"
NOV_20_5PM = Due(date=date(2026, 11, 20), time=time(17, 0))
NO_DEADLINE = {
    **GOOD,
    "has_deadline": False,
    "deadline_date": "",
    "deadline_time": "",
    "deadline_explicit": False,
    "deadline_quote": "",
}


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    return get_settings()


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


@pytest.mark.parametrize(
    ("reply", "now", "dated", "due"),
    [
        (GOOD, NOW, True, NOV_20_5PM),
        ({**GOOD, "confidence": "medium"}, NOW, False, NOV_20_5PM),
        ({**GOOD, "deadline_quote": "due by November 20 at 5 pm"}, NOW, False, NOV_20_5PM),
        (
            {**GOOD, "deadline_date": "2026-11-21"},
            NOW,
            False,
            Due(date=date(2026, 11, 21), time=time(17, 0)),
        ),
        ({**GOOD, "deadline_time": ""}, NOW, False, Due(date=date(2026, 11, 20), time=None)),
        (GOOD, "2026-11-20T22:00:00+00:00", False, NOV_20_5PM),
        (NO_DEADLINE, NOW, False, None),
        ({**GOOD, "title": "Pay\nnow"}, NOW, False, None),
    ],
    ids=[
        "clearly-dated",
        "medium-confidence",
        "quote-not-in-email",
        "model-date-differs",
        "model-missed-the-time",
        "past-at-triage-time",
        "no-deadline",
        "rejected-reply",
    ],
)
def test_triage_stores_the_decision_and_the_proposed_deadline(
    store: Store,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    reply: dict[str, object],
    now: str,
    dated: bool,
    due: Due | None,
) -> None:
    fixed_times(monkeypatch, ADDED, now, DECIDED)
    store.add(RECORD)
    verdict, _ = run(store, settings, reply)
    assert (verdict.dated, verdict.due) == (dated, due)
    found = store.triage("gmail", "m1")
    assert found.verdict == verdict
    assert found.decided_at == datetime(2026, 11, 10, 8, 5, tzinfo=UTC)


def test_a_dropped_message_reads_the_clock_once_and_proposes_nothing(
    store: Store, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_times(monkeypatch, ADDED, NOW, DECIDED)
    store.add(RECORD)
    store.set_sender_status("billing@example.test", "muted")
    verdict, fake = run(store, settings)
    assert (verdict.outcome, verdict.dated, verdict.due) == ("dropped", False, None)
    assert fake.requests == []
    assert store.triage("gmail", "m1").decided_at == datetime(2026, 11, 10, 8, 5, tzinfo=UTC)
