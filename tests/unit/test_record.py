from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from mailroom.record import Envelope, Record

ENVELOPE = Envelope(
    provider="gmail",
    message_id="18c2f0a1b2c3d4e5",
    thread_id="18c2f0a1b2c3d4e0",
    received_at=datetime(2026, 11, 3, 14, 15, 5, tzinfo=UTC),
    link="https://mail.google.com/mail/u/0/#all/18c2f0a1b2c3d4e5",
)

RECORD = Record(
    provider="gmail",
    message_id="18c2f0a1b2c3d4e5",
    thread_id="18c2f0a1b2c3d4e0",
    received_at=datetime(2026, 11, 3, 14, 15, 5, tzinfo=UTC),
    link="https://mail.google.com/mail/u/0/#all/18c2f0a1b2c3d4e5",
    sender="billing@billing.example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=datetime(2026, 11, 3, 14, 15, tzinfo=UTC),
    body_text="Your bill of $42.00 is due on November 20.",
    list_unsubscribe=True,
    authentication_results=("mx.google.com; dmarc=pass header.from=billing.example.test",),
)


def test_valid_envelope_and_record_are_accepted() -> None:
    assert ENVELOPE.provider == "gmail"
    assert RECORD.sender == "billing@billing.example.test"
    assert replace(RECORD, sent_at=None).sent_at is None
    other_zone = datetime(2026, 11, 3, 9, 15, 5, tzinfo=timezone(timedelta(hours=-5)))
    assert replace(ENVELOPE, received_at=other_zone).received_at == ENVELOPE.received_at


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("provider", "hotmail", "invalid record field: provider"),
        ("message_id", "", "invalid record field: message_id"),
        ("message_id", "a b", "invalid record field: message_id"),
        ("message_id", "x" * 1001, "invalid record field: message_id"),
        ("thread_id", "line\n", "invalid record field: thread_id"),
        ("received_at", datetime(2026, 11, 3, 14, 15, 5), "invalid record field: received_at"),
        (
            "link",
            "http://mail.google.com/mail/u/0/#all/18c2f0a1b2c3d4e5",
            "invalid record field: link",
        ),
    ],
)
def test_an_invalid_envelope_field_is_named(field: str, value: object, message: str) -> None:
    with pytest.raises(ValueError) as caught:
        replace(ENVELOPE, **{field: value})
    assert str(caught.value) == message
    with pytest.raises(ValueError) as caught:
        replace(RECORD, **{field: value})
    assert str(caught.value) == message


def test_a_naive_sent_time_is_refused() -> None:
    with pytest.raises(ValueError) as caught:
        replace(RECORD, sent_at=datetime(2026, 11, 3, 14, 15))
    assert str(caught.value) == "invalid record field: sent_at"
