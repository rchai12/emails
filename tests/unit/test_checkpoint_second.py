from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from mailroom.checkpoint import approved_message, checkpoint2_message
from mailroom.store import Approval, Due
from tests.unit.test_checkpoint import FROM, ITEM, LINK, RECORD, SUBJECT, VERDICT

DUE = Due(date=date(2026, 11, 20), time=time(17, 0))
PROPOSED = replace(VERDICT, due=DUE)
TITLE = "Pay the November bill"
TASK = {"name": "Proposed task", "value": "```\nPay the November bill\n```"}
FOOTER = {"text": "Gmail · Verified sender"}
LINK_ROW = {"type": 1, "components": [{"type": 2, "style": 5, "label": "Open email", "url": LINK}]}
DECIDED = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def button(action: str, label: str, style: int) -> dict:
    return {"type": 2, "style": style, "label": label, "custom_id": f"mr:{action}:{ITEM}"}


FULL = button("full", "Show full text", 2)
APPROVE = button("approve", "Approve", 3)
CHANGE = button("change", "Edit", 1)
NO_DEADLINE = button("nodeadline", "No deadline", 2)
DROP = button("drop", "Not a task", 2)


def fields(card: dict) -> list[dict]:
    return card["embeds"][0]["fields"]


def test_checkpoint_2_shows_the_title_the_deadline_and_its_evidence() -> None:
    assert checkpoint2_message(RECORD, PROPOSED, ITEM, TITLE) == {
        "embeds": [
            {
                "title": "Confirm the deadline",
                "color": 0x5865F2,
                "fields": [
                    FROM,
                    SUBJECT,
                    TASK,
                    {"name": "Deadline", "value": "Friday 2026-11-20 at 17:00"},
                    {"name": "Evidence", "value": "```\ndue on November 20 at 5 pm\n```"},
                ],
                "footer": FOOTER,
            }
        ],
        "components": [
            {"type": 1, "components": [FULL, APPROVE, CHANGE, NO_DEADLINE, DROP]},
            LINK_ROW,
        ],
        "allowed_mentions": {"parse": []},
    }


@pytest.mark.parametrize(
    ("verdict", "deadline", "evidence"),
    [
        (VERDICT, "No deadline proposed.", None),
        (
            replace(PROPOSED, extraction=None),
            "Friday 2026-11-20 at 17:00",
            "The evidence has expired.",
        ),
        (
            replace(PROPOSED, due=Due(date=date(2026, 11, 20), time=None)),
            "Friday 2026-11-20",
            "```\ndue on November 20 at 5 pm\n```",
        ),
    ],
    ids=["no-proposal", "evidence-expired", "no-time"],
)
def test_the_deadline_and_evidence_follow_what_is_known(
    verdict, deadline: str, evidence: str | None
) -> None:
    shown = fields(checkpoint2_message(RECORD, verdict, ITEM, TITLE))
    assert shown[3] == {"name": "Deadline", "value": deadline}
    assert shown[4:] == ([] if evidence is None else [{"name": "Evidence", "value": evidence}])


def test_without_a_proposal_there_is_nothing_to_approve() -> None:
    card = checkpoint2_message(RECORD, VERDICT, ITEM, TITLE)
    assert card["components"][0] == {"type": 1, "components": [FULL, CHANGE, NO_DEADLINE, DROP]}


def test_a_suspected_email_keeps_its_warning_and_colour() -> None:
    extraction = replace(VERDICT.extraction, suspicious=True, suspicion_reason="Odd `sender`.")
    card = checkpoint2_message(RECORD, replace(PROPOSED, extraction=extraction), ITEM, TITLE)
    assert card["embeds"][0]["color"] == 0xED4245
    assert fields(card)[-1] == {
        "name": "Suspected spam or phishing",
        "value": "```\nOdd ˋsenderˋ.\n```",
    }


def test_a_title_cannot_break_out_of_its_block() -> None:
    card = checkpoint2_message(RECORD, PROPOSED, ITEM, "Pay ```now``` @everyone")
    assert fields(card)[2] == {
        "name": "Proposed task",
        "value": "```\nPay ˋˋˋnowˋˋˋ @everyone\n```",
    }


def test_a_link_too_long_for_a_button_leaves_one_row() -> None:
    long_link = "https://mail.google.com/mail/#all/" + "a" * 479
    card = checkpoint2_message(replace(RECORD, link=long_link), PROPOSED, ITEM, TITLE)
    assert len(card["components"]) == 1


@pytest.mark.parametrize(
    ("approval", "shown"),
    [
        (
            Approval(ITEM, "approve", TITLE, DUE, DECIDED),
            [TASK, {"name": "Deadline", "value": "Friday 2026-11-20 at 17:00"}, "Approved"],
        ),
        (
            Approval(ITEM, "change", "Pay online", None, DECIDED),
            [
                {"name": "Proposed task", "value": "```\nPay online\n```"},
                {"name": "Deadline", "value": "No deadline"},
                "Approved with your changes",
            ],
        ),
        (
            Approval(ITEM, "nodeadline", TITLE, None, DECIDED),
            [TASK, {"name": "Deadline", "value": "No deadline"}, "Approved without a deadline"],
        ),
        (Approval(ITEM, "drop", "", None, DECIDED), ["Not a task"]),
    ],
    ids=["approve", "change", "no-deadline", "drop"],
)
def test_the_decided_card_shows_the_decision_and_keeps_only_reading(
    approval: Approval, shown: list
) -> None:
    card = approved_message(RECORD, PROPOSED, ITEM, approval)
    *middle, last = shown
    assert card == {
        "embeds": [
            {
                "title": "Confirm the deadline",
                "color": 0x5865F2,
                "fields": [FROM, SUBJECT, *middle, {"name": "Your answer", "value": last}],
                "footer": FOOTER,
            }
        ],
        "components": [
            {
                "type": 1,
                "components": [FULL, {"type": 2, "style": 5, "label": "Open email", "url": LINK}],
            }
        ],
        "allowed_mentions": {"parse": []},
    }
