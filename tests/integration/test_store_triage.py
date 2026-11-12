from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from mailroom.config import get_settings
from mailroom.extractor import Deadline, Extraction
from mailroom.record import Record
from mailroom.store import Store, StoredTriage, Verdict, open_store
from tests.support import fixed_times

RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=datetime(2026, 11, 10, 7, 59, tzinfo=UTC),
    body_text="Your bill of $42.00 is due on November 20 at 5 pm.",
    list_unsubscribe=False,
    authentication_results=(),
)
EXTRACTION = Extraction(
    summary="Billing says the November bill of $42.00 is due on November 20.",
    actionable=True,
    urgent=False,
    title="Pay the November bill",
    deadline=Deadline(
        date=date(2026, 11, 20), time=time(17, 0), explicit=True, quote="due on November 20 at 5 pm"
    ),
    suspicious=False,
    suspicion_reason="",
    confidence="high",
)
EXTRACTED = Verdict(
    outcome="extracted",
    trusted=True,
    verified=True,
    bulk=False,
    notify=True,
    extraction=EXTRACTION,
)
DROPPED = Verdict(outcome="dropped", trusted=False, verified=False, bulk=True, notify=False)
REJECTED = Verdict(
    outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="timeout"
)


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


@pytest.mark.parametrize(
    "verdict",
    [
        EXTRACTED,
        replace(
            EXTRACTED,
            extraction=replace(
                EXTRACTION,
                deadline=replace(EXTRACTION.deadline, time=None, explicit=False),
            ),
        ),
        replace(
            EXTRACTED,
            trusted=False,
            verified=False,
            bulk=True,
            notify=False,
            extraction=replace(
                EXTRACTION,
                actionable=False,
                title="",
                deadline=None,
                suspicious=True,
                suspicion_reason="Asks you to confirm a password",
                confidence="low",
            ),
        ),
        DROPPED,
        REJECTED,
    ],
    ids=[
        "extracted",
        "deadline-without-time",
        "suspicious-without-deadline",
        "dropped",
        "rejected",
    ],
)
def test_a_verdict_is_stored_once_and_read_back(
    store: Store, monkeypatch: pytest.MonkeyPatch, verdict: Verdict
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:01:00+00:00",
        "2026-11-10T08:02:00+00:00",
        "2026-11-10T08:03:00+00:00",
    )
    other = DROPPED if verdict == REJECTED else REJECTED
    store.add(RECORD)
    assert store.triage("gmail", "m1") is None
    assert store.save_triage("gmail", "m1", verdict) is True
    assert store.save_triage("gmail", "m1", other) is False
    assert store.triage("gmail", "m1") == StoredTriage(
        verdict=verdict,
        decided_at=datetime(2026, 11, 10, 8, 2, tzinfo=UTC),
        text_cleared_at=None,
    )


def test_a_verdict_for_a_message_that_is_not_stored_is_refused(store: Store) -> None:
    store.add(replace(RECORD, provider="yahoo"))
    assert store.save_triage("gmail", "m1", EXTRACTED) is False
    assert store.triage("gmail", "m1") is None


def test_a_verdict_for_a_message_whose_text_is_cleared_is_refused(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:01:00+00:00",
        "2026-11-11T08:01:00+00:00",
        "2026-11-11T08:02:00+00:00",
    )
    store.add(RECORD)
    assert store.clear_expired_text() == 1
    assert store.save_triage("gmail", "m1", EXTRACTED) is False
    assert store.triage("gmail", "m1") is None


def test_the_extraction_is_cleared_with_the_email_text(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:30:00+00:00",
        "2026-11-10T08:31:00+00:00",
        "2026-11-10T08:32:00+00:00",
        "2026-11-10T08:33:00+00:00",
        "2026-11-11T08:15:00+00:00",
        "2026-11-11T08:45:00+00:00",
    )
    store.add(RECORD)
    store.add(replace(RECORD, message_id="m2"))
    store.add(replace(RECORD, message_id="m3"))
    store.save_triage("gmail", "m1", EXTRACTED)
    store.save_triage("gmail", "m2", EXTRACTED)
    assert store.clear_expired_text() == 1
    assert store.triage("gmail", "m1") == StoredTriage(
        verdict=replace(EXTRACTED, extraction=None),
        decided_at=datetime(2026, 11, 10, 8, 32, tzinfo=UTC),
        text_cleared_at=datetime(2026, 11, 11, 8, 15, tzinfo=UTC),
    )
    assert store.triage("gmail", "m2") == StoredTriage(
        verdict=EXTRACTED,
        decided_at=datetime(2026, 11, 10, 8, 33, tzinfo=UTC),
        text_cleared_at=None,
    )
    assert store.clear_expired_text() == 2
    cleared = store.triage("gmail", "m2")
    assert cleared is not None
    assert cleared.verdict.extraction is None
    assert cleared.text_cleared_at == datetime(2026, 11, 11, 8, 45, tzinfo=UTC)


def test_a_verdict_without_an_extraction_is_kept_as_it_is(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:00:01+00:00",
        "2026-11-10T08:30:00+00:00",
        "2026-11-10T08:30:01+00:00",
        "2026-11-11T09:00:00+00:00",
    )
    store.add(RECORD)
    store.add(replace(RECORD, message_id="m2"))
    store.save_triage("gmail", "m1", DROPPED)
    store.save_triage("gmail", "m2", REJECTED)
    assert store.clear_expired_text() == 2
    assert store.triage("gmail", "m1") == StoredTriage(
        verdict=DROPPED, decided_at=datetime(2026, 11, 10, 8, 30, tzinfo=UTC), text_cleared_at=None
    )
    assert store.triage("gmail", "m2") == StoredTriage(
        verdict=REJECTED,
        decided_at=datetime(2026, 11, 10, 8, 30, 1, tzinfo=UTC),
        text_cleared_at=None,
    )


def test_cleared_extraction_text_is_gone_from_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-11T08:00:00+00:00",
    )
    marked = replace(
        EXTRACTION,
        summary="ZQX-SUMMARY-8 " * 10,
        title="ZQX-TITLE-8",
        deadline=replace(EXTRACTION.deadline, quote="ZQX-QUOTE-8"),
        suspicious=True,
        suspicion_reason="ZQX-REASON-8",
    )
    with open_store(get_settings()) as store:
        store.add(RECORD)
        store.save_triage("gmail", "m1", replace(EXTRACTED, extraction=marked))
        assert store.clear_expired_text() == 1
    content = (tmp_path / "data" / "mailroom.sqlite3").read_bytes()
    for marker in [b"ZQX-SUMMARY-8", b"ZQX-TITLE-8", b"ZQX-QUOTE-8", b"ZQX-REASON-8"]:
        assert marker not in content


def test_untriaged_lists_messages_with_text_and_no_verdict_oldest_first(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:00:01+00:00",
        "2026-11-10T08:00:02+00:00",
        "2026-11-11T07:00:00+00:00",
        "2026-11-11T07:00:01+00:00",
        "2026-11-11T07:00:02+00:00",
        "2026-11-11T08:30:00+00:00",
    )
    store.add(replace(RECORD, message_id="old"))
    store.add(replace(RECORD, message_id="done"))
    store.save_triage("gmail", "done", DROPPED)
    store.add(
        replace(RECORD, message_id="late", received_at=datetime(2026, 11, 11, 6, 0, tzinfo=UTC))
    )
    store.add(replace(RECORD, message_id="b", received_at=datetime(2026, 11, 11, 5, 0, tzinfo=UTC)))
    store.add(
        replace(
            RECORD,
            provider="yahoo",
            message_id="a",
            received_at=datetime(2026, 11, 11, 5, 0, tzinfo=UTC),
        )
    )
    assert store.untriaged() == (
        ("gmail", "old"),
        ("gmail", "b"),
        ("yahoo", "a"),
        ("gmail", "late"),
    )
    assert store.clear_expired_text() == 2
    assert store.untriaged() == (("gmail", "b"), ("yahoo", "a"), ("gmail", "late"))
