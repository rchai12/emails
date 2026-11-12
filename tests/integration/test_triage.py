from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time

import httpx
import pytest

from mailroom.config import Settings, get_settings
from mailroom.extractor import Deadline, Extraction, ModelUnavailable
from mailroom.record import Record
from mailroom.store import Store, StoredTriage, Verdict, open_store
from mailroom.triage import triage_message
from tests.fakes import FakeOllama
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
    body_text="Your bill of $42.00 is due on November 20 at 5 pm.\nPay online.",
    list_unsubscribe=False,
    authentication_results=("mx.google.com; dmarc=pass header.from=example.test",),
)
GOOD = {
    "summary": "Billing says the November bill of $42.00 is due on November 20.",
    "actionable": True,
    "urgent": False,
    "title": "Pay the November bill",
    "has_deadline": True,
    "deadline_date": "2026-11-20",
    "deadline_time": "17:00",
    "deadline_explicit": True,
    "deadline_quote": "due on November 20 at 5 pm",
    "suspicious": False,
    "suspicion_reason": "",
    "confidence": "high",
}
NEWSLETTER = {
    **GOOD,
    "summary": "A newsletter about November offers.",
    "actionable": False,
    "title": "",
    "has_deadline": False,
    "deadline_date": "",
    "deadline_time": "",
    "deadline_explicit": False,
    "deadline_quote": "",
}
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


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    return get_settings()


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    fixed_times(monkeypatch, "2026-11-10T08:01:00+00:00", "2026-11-10T08:05:00+00:00")
    with open_store(get_settings()) as opened:
        yield opened


def run(
    store: Store, settings: Settings, *replies: object, message_id: str = "m1"
) -> tuple[Verdict | None, FakeOllama]:
    fake = FakeOllama()
    fake.replies.extend(replies)
    http = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return triage_message(store, "gmail", message_id, settings, http), fake


def stored(store: Store, verdict: Verdict) -> bool:
    return store.triage("gmail", "m1") == StoredTriage(
        verdict=verdict, decided_at=datetime(2026, 11, 10, 8, 5, tzinfo=UTC), text_cleared_at=None
    )


def test_a_new_message_is_screened_extracted_decided_and_stored(
    store: Store, settings: Settings
) -> None:
    store.add(RECORD)
    verdict, fake = run(store, settings, GOOD)
    assert verdict == Verdict(
        outcome="extracted",
        trusted=False,
        verified=True,
        bulk=False,
        notify=True,
        extraction=EXTRACTION,
    )
    assert stored(store, verdict)
    assert len(fake.requests) == 1


def test_a_trusted_sender_is_marked_trusted(store: Store, settings: Settings) -> None:
    store.add(RECORD)
    store.set_sender_status("billing@example.test", "trusted")
    verdict, _ = run(store, settings, NEWSLETTER)
    assert verdict is not None
    assert (verdict.trusted, verdict.verified, verdict.notify) == (True, True, True)


def test_a_sure_non_task_is_stored_but_not_notified(store: Store, settings: Settings) -> None:
    store.add(replace(RECORD, list_unsubscribe=True))
    verdict, _ = run(store, settings, {**NEWSLETTER, "confidence": "medium"})
    assert verdict is not None
    assert (verdict.outcome, verdict.bulk, verdict.notify) == ("extracted", True, False)
    assert stored(store, verdict)


def test_mail_from_a_muted_sender_is_dropped_without_a_model_call(
    store: Store, settings: Settings
) -> None:
    store.add(RECORD)
    store.set_sender_status("billing@example.test", "muted")
    verdict, fake = run(store, settings)
    assert verdict == Verdict(
        outcome="dropped", trusted=False, verified=True, bulk=False, notify=False
    )
    assert stored(store, verdict)
    assert fake.requests == []


def test_an_unreadable_reply_is_stored_by_field_name_and_notified(
    store: Store, settings: Settings
) -> None:
    store.add(RECORD)
    verdict, _ = run(store, settings, {**GOOD, "title": "Pay\nnow"})
    assert verdict == Verdict(
        outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="title"
    )
    assert stored(store, verdict)


def test_a_message_already_triaged_is_not_sent_to_the_model_again(
    store: Store, settings: Settings
) -> None:
    store.add(RECORD)
    first, _ = run(store, settings, GOOD)
    again, fake = run(store, settings)
    assert again == first
    assert fake.requests == []


def test_an_unavailable_model_stores_nothing(store: Store, settings: Settings) -> None:
    store.add(RECORD)
    with pytest.raises(ModelUnavailable):
        run(store, settings, httpx.ConnectError("refused"))
    assert store.triage("gmail", "m1") is None
    assert store.untriaged() == (("gmail", "m1"),)


def test_a_message_that_is_not_stored_is_not_triaged(store: Store, settings: Settings) -> None:
    store.add(RECORD)
    verdict, fake = run(store, settings, message_id="m2")
    assert verdict is None
    assert fake.requests == []
    assert store.triage("gmail", "m2") is None


def test_a_message_whose_text_is_cleared_is_not_triaged(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_times(monkeypatch, "2026-11-10T08:01:00+00:00", "2026-11-11T08:01:00+00:00")
    with open_store(get_settings()) as store:
        store.add(RECORD)
        assert store.clear_expired_text() == 1
        verdict, fake = run(store, settings, GOOD)
        assert verdict is None
        assert fake.requests == []
        assert store.triage("gmail", "m1") is None
