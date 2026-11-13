"""The proposed deadline and the clearly-dated decision, kept with the verdict past 24 hours."""

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from mailroom.config import get_settings
from mailroom.schema import MIGRATIONS
from mailroom.store import Due, Store, Verdict, open_store
from tests.integration.test_store_triage import DROPPED, EXTRACTED, EXTRACTION, RECORD, REJECTED
from tests.support import fixed_times

DUE = Due(date=date(2026, 11, 20), time=time(17, 0))
DATED = replace(EXTRACTED, dated=True, due=DUE)


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def test_due_lives_with_the_verdict_and_defaults_to_nothing() -> None:
    assert Due.__module__ == "mailroom.store.triage"
    plain = Verdict("dropped", False, False, False, False)
    assert (plain.dated, plain.due) == (False, None)


@pytest.mark.parametrize(
    "verdict",
    [
        DATED,
        replace(EXTRACTED, due=Due(date=date(2026, 11, 20), time=None)),
        replace(EXTRACTED, due=DUE),
        EXTRACTED,
        DROPPED,
        REJECTED,
    ],
    ids=["dated", "due-without-time", "due-not-dated", "no-due", "dropped", "rejected"],
)
def test_a_saved_verdict_reads_back_with_its_deadline(store: Store, verdict: Verdict) -> None:
    store.add(RECORD)
    assert store.save_triage("gmail", "m1", verdict) is True
    assert store.triage("gmail", "m1").verdict == verdict


@pytest.mark.parametrize(
    "verdict",
    [
        replace(EXTRACTED, dated=True),
        replace(DROPPED, due=DUE),
        replace(REJECTED, due=DUE),
    ],
    ids=["dated-without-due", "due-on-dropped", "due-on-rejected"],
)
def test_a_deadline_that_does_not_fit_the_verdict_is_refused(
    store: Store, verdict: Verdict
) -> None:
    store.add(RECORD)
    with pytest.raises(sqlite3.IntegrityError):
        store.save_triage("gmail", "m1", verdict)
    assert store.triage("gmail", "m1") is None


def test_clearing_the_text_keeps_the_deadline_and_the_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-11T08:00:00+00:00",
    )
    with open_store(get_settings()) as store:
        store.add(RECORD)
        store.save_triage("gmail", "m1", DATED)
        assert store.clear_expired_text() == 1
        found = store.triage("gmail", "m1")
    assert found.verdict == replace(DATED, extraction=None)
    assert found.text_cleared_at == datetime(2026, 11, 11, 8, 0, tzinfo=UTC)


def test_the_quote_leaves_the_file_and_the_date_stays(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-11T08:00:00+00:00",
    )
    marked = replace(EXTRACTION, deadline=replace(EXTRACTION.deadline, quote="ZQX-QUOTE-2C"))
    with open_store(get_settings()) as store:
        store.add(RECORD)
        store.save_triage("gmail", "m1", replace(DATED, extraction=marked))
        store.clear_expired_text()
    path = tmp_path / "data" / "mailroom.sqlite3"
    assert b"ZQX-QUOTE-2C" not in path.read_bytes()
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("SELECT deadline_date, deadline_time, dated FROM triage")
        assert row.fetchall() == [("2026-11-20", "17:00", 1)]
    finally:
        connection.close()


def test_a_version_7_database_gains_the_columns_with_nothing_proposed(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript("\n".join(MIGRATIONS[:7]) + "\nPRAGMA user_version = 7;")
    connection.execute(
        "INSERT INTO triage (provider, message_id, outcome, reason, trusted, verified, bulk,"
        " notify, extraction, decided_at, text_cleared_at)"
        " VALUES ('gmail', 'personal/m1', 'dropped', '', 0, 1, 1, 0, NULL,"
        " '2026-11-10T08:00:00+00:00', NULL)"
    )
    connection.commit()
    connection.close()
    with Store(path) as store:
        found = store.triage("gmail", "personal/m1")
    assert found.verdict == Verdict("dropped", False, True, True, False)
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (8,)
    finally:
        connection.close()
