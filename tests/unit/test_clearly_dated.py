from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import pytest

from mailroom.deadlines import CONFIDENCE, WINDOW, clearly_dated
from mailroom.extractor import Deadline, Extraction
from mailroom.record import Record

ZONE = "America/New_York"
NOW = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)  # 09:00 on Tuesday Nov 10 in New York
RECORD = Record(
    provider="gmail",
    message_id="personal/m1",
    thread_id="personal/t1",
    received_at=datetime(2026, 11, 10, 13, 1, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=datetime(2026, 11, 10, 13, 0, tzinfo=UTC),
    body_text="Your bill of $42.00 is due on November 20\nat 5 pm.  Thank you.",
    list_unsubscribe=False,
    authentication_results=(),
)
DEADLINE = Deadline(
    date=date(2026, 11, 20), time=time(17, 0), explicit=True, quote="due on November 20 at 5 pm"
)
EXTRACTION = Extraction(
    summary="Billing says the November bill of $42.00 is due on November 20.",
    actionable=True,
    urgent=False,
    title="Pay the November bill",
    deadline=DEADLINE,
    suspicious=False,
    suspicion_reason="",
    confidence="high",
)


def with_deadline(**changes: object) -> Extraction:
    return replace(EXTRACTION, deadline=replace(DEADLINE, **changes))


def test_the_constants() -> None:
    assert CONFIDENCE == "high"
    assert WINDOW == timedelta(days=366)


@pytest.mark.parametrize(
    ("record", "extraction", "now", "expected"),
    [
        (RECORD, EXTRACTION, NOW, True),
        (
            replace(RECORD, subject="Due November 20 at 5 pm", body_text="See the subject."),
            with_deadline(quote="Due November 20 at 5 pm"),
            NOW,
            True,
        ),
        (replace(RECORD, sent_at=None), EXTRACTION, NOW, True),
        (
            replace(
                RECORD,
                sent_at=datetime(2026, 11, 10, 3, 0, tzinfo=UTC),
                body_text="Please reply by Tuesday.",
            ),
            with_deadline(date=date(2026, 11, 10), time=None, quote="by Tuesday"),
            datetime(2026, 11, 10, 4, 0, tzinfo=UTC),
            True,
        ),
        (
            replace(RECORD, body_text="Renew by November 11, 2027."),
            with_deadline(date=date(2027, 11, 11), time=None, quote="by November 11, 2027"),
            NOW,
            True,
        ),
        (RECORD, replace(EXTRACTION, suspicious=True, suspicion_reason="Odd sender."), NOW, False),
        (RECORD, with_deadline(explicit=False), NOW, False),
        (RECORD, replace(EXTRACTION, confidence="medium"), NOW, False),
        (RECORD, replace(EXTRACTION, deadline=None), NOW, False),
        (RECORD, replace(EXTRACTION, actionable=False), NOW, False),
        (RECORD, replace(EXTRACTION, title=""), NOW, False),
        (RECORD, with_deadline(quote="Due on November 20 at 5 pm"), NOW, False),
        (RECORD, with_deadline(quote=""), NOW, False),
        (RECORD, with_deadline(date=date(2026, 11, 21)), NOW, False),
        (RECORD, with_deadline(time=None), NOW, False),
        (RECORD, with_deadline(time=time(18, 0)), NOW, False),
        (
            replace(RECORD, body_text="Due November 20 or November 21."),
            with_deadline(time=None, quote="Due November 20 or November 21"),
            NOW,
            False,
        ),
        (RECORD, EXTRACTION, datetime(2026, 11, 20, 22, 0, tzinfo=UTC), False),
        (
            replace(RECORD, body_text="Renew by November 12, 2027."),
            with_deadline(date=date(2027, 11, 12), time=None, quote="by November 12, 2027"),
            NOW,
            False,
        ),
        (
            replace(RECORD, body_text="It was due on November 9, 2026."),
            with_deadline(date=date(2026, 11, 9), time=None, quote="due on November 9, 2026"),
            datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
            False,
        ),
        (
            replace(
                RECORD,
                sent_at=datetime(2026, 11, 10, 3, 0, tzinfo=UTC),
                body_text="Please reply by Tuesday.",
            ),
            with_deadline(date=date(2026, 11, 17), time=None, quote="by Tuesday"),
            datetime(2026, 11, 10, 4, 0, tzinfo=UTC),
            False,
        ),
    ],
    ids=[
        "clearly-dated",
        "quote-from-subject",
        "received-time-when-not-sent",
        "local-sent-day",
        "last-day-of-window",
        "suspicious",
        "not-explicit",
        "medium-confidence",
        "no-deadline",
        "not-actionable",
        "no-title",
        "quote-not-in-email",
        "empty-quote",
        "model-date-differs",
        "model-missed-the-time",
        "model-time-differs",
        "quote-names-two-dates",
        "already-past",
        "past-the-window",
        "before-the-sent-day",
        "model-used-the-utc-day",
    ],
)
def test_only_an_email_meeting_every_condition_is_clearly_dated(
    record: Record, extraction: Extraction, now: datetime, expected: bool
) -> None:
    assert clearly_dated(record, extraction, ZONE, now) is expected
