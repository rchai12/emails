from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from mailroom.checkpoint import checkpoint_message
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
VERDICT = Verdict(
    outcome="extracted",
    trusted=False,
    verified=True,
    bulk=False,
    notify=True,
    extraction=EXTRACTION,
)
FROM = {"name": "From", "value": "```\nBilling Team <billing@example.test>\n```"}
SUBJECT = {"name": "Subject", "value": "```\nYour November bill\n```"}
SUMMARY = {
    "name": "Summary",
    "value": "```\nBilling says the November bill of $42.00 is due on November 20.\n```",
}
TASK = {"name": "Proposed task", "value": "```\nPay the November bill\n```"}
FIRST_ROW = {
    "type": 1,
    "components": [
        {"type": 2, "style": 2, "label": "Show full text", "custom_id": f"mr:full:{ITEM}"},
        {"type": 2, "style": 3, "label": "Yes", "custom_id": f"mr:yes:{ITEM}"},
        {"type": 2, "style": 1, "label": "Edit title", "custom_id": f"mr:edit:{ITEM}"},
        {"type": 2, "style": 2, "label": "Not a task", "custom_id": f"mr:notask:{ITEM}"},
    ],
}
SENDER_BUTTONS = [
    {"type": 2, "style": 4, "label": "Mute sender", "custom_id": f"mr:mute:{ITEM}"},
    {"type": 2, "style": 2, "label": "Trust sender", "custom_id": f"mr:trust:{ITEM}"},
]
OPEN = {"type": 2, "style": 5, "label": "Open email", "url": LINK}


def embed(message: dict) -> dict:
    (only,) = message["embeds"]
    return only


def test_the_whole_message_for_an_extracted_email() -> None:
    assert checkpoint_message(RECORD, VERDICT, ITEM) == {
        "embeds": [
            {
                "title": "Is this a task?",
                "color": 0x5865F2,
                "fields": [FROM, SUBJECT, SUMMARY, TASK],
                "footer": {"text": "Gmail · Verified sender"},
            }
        ],
        "components": [FIRST_ROW, {"type": 1, "components": [*SENDER_BUTTONS, OPEN]}],
        "allowed_mentions": {"parse": []},
        "nonce": "0123456789abcdef012345678",
        "enforce_nonce": True,
    }


def test_a_suspected_email_is_red_with_the_reason_last() -> None:
    suspected = replace(
        VERDICT,
        extraction=replace(EXTRACTION, suspicious=True, suspicion_reason="Asks for a password"),
    )
    shown = embed(checkpoint_message(RECORD, suspected, ITEM))
    assert shown["color"] == 0xED4245
    assert shown["fields"] == [
        FROM,
        SUBJECT,
        SUMMARY,
        TASK,
        {"name": "Suspected spam or phishing", "value": "```\nAsks for a password\n```"},
    ]


def test_an_email_the_model_could_not_read_is_grey_and_says_so() -> None:
    unread = Verdict(
        outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="title"
    )
    shown = embed(checkpoint_message(RECORD, unread, ITEM))
    assert shown["color"] == 0x99AAB5
    assert shown["fields"] == [
        FROM,
        SUBJECT,
        {"name": "Summary", "value": "The model couldn't read this email (title)."},
    ]


def test_an_expired_summary_is_grey_and_says_so() -> None:
    shown = embed(checkpoint_message(RECORD, replace(VERDICT, extraction=None), ITEM))
    assert shown["color"] == 0x99AAB5
    assert shown["fields"] == [
        FROM,
        SUBJECT,
        {"name": "Summary", "value": "The summary has expired."},
    ]


def test_no_task_field_without_a_title() -> None:
    plain = replace(VERDICT, extraction=replace(EXTRACTION, actionable=False, title=""))
    assert embed(checkpoint_message(RECORD, plain, ITEM))["fields"] == [FROM, SUBJECT, SUMMARY]


def test_email_text_stays_inside_code_blocks_and_cannot_close_them() -> None:
    record = replace(
        RECORD,
        sender_name="**Bank** @everyone",
        subject="Use `code` and [click](https://evil.test) <@123>",
    )
    extraction = replace(EXTRACTION, summary="```\n# Pay now\n```", title="`x`")
    shown = embed(checkpoint_message(record, replace(VERDICT, extraction=extraction), ITEM))
    assert shown["fields"] == [
        {"name": "From", "value": "```\n**Bank** @everyone <billing@example.test>\n```"},
        {
            "name": "Subject",
            "value": "```\nUse ˋcodeˋ and [click](https://evil.test) <@123>\n```",
        },
        {"name": "Summary", "value": "```\nˋˋˋ\n# Pay now\nˋˋˋ\n```"},
        {"name": "Proposed task", "value": "```\nˋxˋ\n```"},
    ]


def test_missing_sender_parts_and_subject_have_fixed_text() -> None:
    nameless = embed(checkpoint_message(replace(RECORD, sender_name="", subject=""), VERDICT, ITEM))
    unknown = embed(checkpoint_message(replace(RECORD, sender=""), VERDICT, ITEM))
    assert nameless["fields"][:2] == [
        {"name": "From", "value": "```\nbilling@example.test\n```"},
        {"name": "Subject", "value": "```\n(no subject)\n```"},
    ]
    assert unknown["fields"][0] == {
        "name": "From",
        "value": "```\nBilling Team <(no address)>\n```",
    }


@pytest.mark.parametrize(
    ("provider", "trusted", "verified", "bulk", "footer"),
    [
        ("gmail", True, True, False, "Gmail · Trusted sender"),
        ("outlook", False, False, False, "Outlook · Sender not verified"),
        ("yahoo", False, True, True, "Yahoo · Verified sender · Bulk mail"),
    ],
    ids=["trusted", "unverified", "bulk"],
)
def test_the_footer_names_the_provider_and_what_is_known_of_the_sender(
    provider: str, trusted: bool, verified: bool, bulk: bool, footer: str
) -> None:
    verdict = replace(VERDICT, trusted=trusted, verified=verified, bulk=bulk)
    shown = embed(checkpoint_message(replace(RECORD, provider=provider), verdict, ITEM))
    assert shown["footer"] == {"text": footer}


def test_a_link_too_long_for_a_button_is_left_out() -> None:
    fits = "https://mail.google.com/mail/#all/" + "a" * 478
    longer = fits + "a"
    assert len(fits) == 512
    kept = checkpoint_message(replace(RECORD, link=fits), VERDICT, ITEM)["components"][1]
    left_out = checkpoint_message(replace(RECORD, link=longer), VERDICT, ITEM)["components"][1]
    assert kept == {"type": 1, "components": [*SENDER_BUTTONS, {**OPEN, "url": fits}]}
    assert left_out == {"type": 1, "components": SENDER_BUTTONS}
