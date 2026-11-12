from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from mailroom.checkpoint import answered_message
from mailroom.extractor import Deadline, Extraction
from mailroom.record import Record
from mailroom.store import Verdict

ITEM = "0123456789abcdef0123456789abcdef"
LINK = "https://mail.google.com/mail/?authuser=owner@example.test#all/m1"
RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
    link=LINK,
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=None,
    body_text="Your bill is due.",
    list_unsubscribe=False,
    authentication_results=(),
)
VERDICT = Verdict(
    outcome="extracted",
    trusted=False,
    verified=True,
    bulk=False,
    notify=True,
    extraction=Extraction(
        summary="Billing says the bill is due.",
        actionable=True,
        urgent=False,
        title="Pay the bill",
        deadline=Deadline(date(2026, 11, 20), time(17, 0), True, "due November 20"),
        suspicious=False,
        suspicion_reason="",
        confidence="high",
    ),
)
FIELDS = [
    {"name": "From", "value": "```\nBilling Team <billing@example.test>\n```"},
    {"name": "Subject", "value": "```\nYour November bill\n```"},
    {"name": "Summary", "value": "```\nBilling says the bill is due.\n```"},
    {"name": "Proposed task", "value": "```\nPay the bill\n```"},
]
FULL = {"type": 2, "style": 2, "label": "Show full text", "custom_id": f"mr:full:{ITEM}"}
OPEN = {"type": 2, "style": 5, "label": "Open email", "url": LINK}


def test_an_answered_card_shows_the_answer_and_keeps_only_reading_buttons() -> None:
    assert answered_message(RECORD, VERDICT, ITEM, "edit", "Pay the `bill` online") == {
        "embeds": [
            {
                "title": "Is this a task?",
                "color": 0x5865F2,
                "fields": [
                    *FIELDS,
                    {
                        "name": "Your answer",
                        "value": "Yes, with your title\n```\nPay the ˋbillˋ online\n```",
                    },
                ],
                "footer": {"text": "Gmail · Verified sender"},
            }
        ],
        "components": [{"type": 1, "components": [FULL, OPEN]}],
        "allowed_mentions": {"parse": []},
    }


@pytest.mark.parametrize(
    ("answer", "text"),
    [
        ("yes", "Yes, it's a task\n```\nPay the bill\n```"),
        ("notask", "Not a task"),
        ("mute", "Not a task; sender muted"),
    ],
    ids=["yes", "not-a-task", "mute"],
)
def test_each_answer_has_its_own_text(answer: str, text: str) -> None:
    title = "Pay the bill" if answer == "yes" else ""
    (embed,) = answered_message(RECORD, VERDICT, ITEM, answer, title)["embeds"]
    assert embed["fields"][-1] == {"name": "Your answer", "value": text}


def test_an_answered_card_with_a_long_link_keeps_only_show_full_text() -> None:
    record = replace(RECORD, link="https://mail.google.com/mail/#all/" + "a" * 479)
    assert answered_message(record, VERDICT, ITEM, "notask", "")["components"] == [
        {"type": 1, "components": [FULL]}
    ]
