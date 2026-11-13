from dataclasses import replace

import pytest

from mailroom.checkpoint import answered_message, checkpoint_message
from tests.unit.test_checkpoint import ITEM, RECORD, VERDICT


def footer(card: dict[str, object]) -> str:
    return card["embeds"][0]["footer"]["text"]


@pytest.mark.parametrize(
    ("provider", "message_id", "bulk", "expected"),
    [
        ("gmail", "personal/m1", False, "Gmail personal · Verified sender"),
        ("gmail", "work-2/m1", True, "Gmail work-2 · Verified sender · Bulk mail"),
        ("outlook", "school/AAMkAD=", False, "Outlook school · Verified sender"),
        ("gmail", "m1", False, "Gmail · Verified sender"),
        ("gmail", "Personal/m1", False, "Gmail · Verified sender"),
    ],
    ids=["personal", "bulk", "outlook", "bare-id", "not-an-account"],
)
def test_the_footer_names_the_account_the_email_came_to(
    provider: str, message_id: str, bulk: bool, expected: str
) -> None:
    record = replace(RECORD, provider=provider, message_id=message_id)
    card = checkpoint_message(record, replace(VERDICT, bulk=bulk), ITEM)
    assert footer(card) == expected


def test_the_answered_card_keeps_the_account() -> None:
    record = replace(RECORD, message_id="personal/m1")
    card = answered_message(record, VERDICT, ITEM, "notask", "")
    assert footer(card) == "Gmail personal · Verified sender"
