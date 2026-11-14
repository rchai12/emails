"""The follow-up card: an email in a thread whose earlier email you approved as a task."""

from dataclasses import replace

import pytest

from mailroom.checkpoint import answered_message, followup_message
from tests.unit.test_checkpoint import (
    FROM,
    ITEM,
    LINK,
    OPEN,
    RECORD,
    SENDER_BUTTONS,
    SUBJECT,
    SUMMARY,
    VERDICT,
)

TASK = "Pay the October bill"
EXISTING = {"name": "Existing task", "value": "```\nPay the October bill\n```"}
FULL = {"type": 2, "style": 2, "label": "Show full text", "custom_id": f"mr:full:{ITEM}"}
FIRST_ROW = [
    FULL,
    {"type": 2, "style": 3, "label": "Add to task", "custom_id": f"mr:link:{ITEM}"},
    {"type": 2, "style": 1, "label": "New task", "custom_id": f"mr:yes:{ITEM}"},
    {"type": 2, "style": 2, "label": "Not a task", "custom_id": f"mr:notask:{ITEM}"},
]


def embed(fields: list[dict]) -> dict:
    return {
        "title": "Follow-up to a task?",
        "color": 0x5865F2,
        "fields": fields,
        "footer": {"text": "Gmail · Verified sender"},
    }


def test_the_follow_up_card_names_the_existing_task() -> None:
    assert followup_message(RECORD, VERDICT, ITEM, TASK) == {
        "embeds": [embed([FROM, SUBJECT, SUMMARY, EXISTING])],
        "components": [
            {"type": 1, "components": FIRST_ROW},
            {"type": 1, "components": [*SENDER_BUTTONS, OPEN]},
        ],
        "allowed_mentions": {"parse": []},
        "nonce": ITEM[:25],
        "enforce_nonce": True,
    }


def test_a_suspected_follow_up_warns_after_the_task_and_a_cleared_one_says_so() -> None:
    extraction = replace(VERDICT.extraction, suspicious=True, suspicion_reason="Odd link")
    fields = followup_message(RECORD, replace(VERDICT, extraction=extraction), ITEM, TASK)[
        "embeds"
    ][0]["fields"]
    assert fields[3:] == [
        EXISTING,
        {"name": "Suspected spam or phishing", "value": "```\nOdd link\n```"},
    ]
    cleared = followup_message(RECORD, replace(VERDICT, extraction=None), ITEM, TASK)
    assert cleared["embeds"][0]["fields"][2:] == [
        {"name": "Summary", "value": "The summary has expired."},
        EXISTING,
    ]


def test_the_existing_task_title_stays_inside_its_block() -> None:
    card = followup_message(RECORD, VERDICT, ITEM, "Pay `now` @everyone")
    assert card["embeds"][0]["fields"][3]["value"] == "```\nPay ˋnowˋ @everyone\n```"


@pytest.mark.parametrize(
    ("answer", "shown"),
    [
        ("link", "Added to the existing task"),
        ("notask", "Not a task"),
        ("mute", "Not a task; sender muted"),
    ],
    ids=["link", "notask", "mute"],
)
def test_an_answered_follow_up_keeps_its_card_and_shows_the_answer(answer: str, shown: str) -> None:
    assert answered_message(RECORD, VERDICT, ITEM, answer, "", task_title=TASK) == {
        "embeds": [
            embed([FROM, SUBJECT, SUMMARY, EXISTING, {"name": "Your answer", "value": shown}])
        ],
        "components": [{"type": 1, "components": [FULL, OPEN]}],
        "allowed_mentions": {"parse": []},
    }


def test_a_long_link_leaves_out_open_email() -> None:
    record = replace(RECORD, link="https://mail.google.com/mail/#all/" + "a" * 479)
    card = followup_message(record, VERDICT, ITEM, TASK)
    assert card["components"][1] == {"type": 1, "components": SENDER_BUTTONS}
    assert LINK not in str(card)
