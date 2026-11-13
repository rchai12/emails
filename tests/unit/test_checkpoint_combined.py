from dataclasses import replace
from datetime import date, time

from mailroom.checkpoint import combined_message
from mailroom.store import Due
from tests.unit.test_checkpoint import FROM, ITEM, LINK, RECORD, SUBJECT, SUMMARY, VERDICT

DATED = replace(VERDICT, dated=True, due=Due(date=date(2026, 11, 20), time=time(17, 0)))


def button(action: str, label: str, style: int) -> dict:
    return {"type": 2, "style": style, "label": label, "custom_id": f"mr:{action}:{ITEM}"}


FIRST_ROW = [
    button("full", "Show full text", 2),
    button("approve", "Approve", 3),
    button("change", "Edit", 1),
    button("nodeadline", "No deadline", 2),
    button("notask", "Not a task", 2),
]
SECOND_ROW = [button("mute", "Mute sender", 4), button("trust", "Trust sender", 2)]
OPEN = {"type": 2, "style": 5, "label": "Open email", "url": LINK}


def test_the_combined_card_shows_everything_on_one_card() -> None:
    assert combined_message(RECORD, DATED, ITEM) == {
        "embeds": [
            {
                "title": "Approve this task?",
                "color": 0x5865F2,
                "fields": [
                    FROM,
                    SUBJECT,
                    SUMMARY,
                    {"name": "Proposed task", "value": "```\nPay the November bill\n```"},
                    {"name": "Deadline", "value": "Friday 2026-11-20 at 17:00"},
                    {"name": "Evidence", "value": "```\ndue on November 20 at 5 pm\n```"},
                ],
                "footer": {"text": "Gmail · Verified sender"},
            }
        ],
        "components": [
            {"type": 1, "components": FIRST_ROW},
            {"type": 1, "components": [*SECOND_ROW, OPEN]},
        ],
        "allowed_mentions": {"parse": []},
        "nonce": ITEM[:25],
        "enforce_nonce": True,
    }


def test_a_date_without_a_time_and_a_long_link() -> None:
    verdict = replace(DATED, due=Due(date=date(2026, 11, 20), time=None))
    long_link = "https://mail.google.com/mail/#all/" + "a" * 479
    card = combined_message(replace(RECORD, link=long_link), verdict, ITEM)
    assert card["embeds"][0]["fields"][4] == {"name": "Deadline", "value": "Friday 2026-11-20"}
    assert card["components"][1] == {"type": 1, "components": SECOND_ROW}


def test_email_text_stays_inside_its_blocks() -> None:
    extraction = replace(
        DATED.extraction,
        summary="See `this` @everyone",
        title="Pay ```now```",
        deadline=replace(DATED.extraction.deadline, quote="by `Friday`"),
    )
    fields = combined_message(RECORD, replace(DATED, extraction=extraction), ITEM)["embeds"][0][
        "fields"
    ]
    assert [field["value"] for field in fields[2:6:3]] == [
        "```\nSee ˋthisˋ @everyone\n```",
        "```\nby ˋFridayˋ\n```",
    ]
    assert fields[3]["value"] == "```\nPay ˋˋˋnowˋˋˋ\n```"
