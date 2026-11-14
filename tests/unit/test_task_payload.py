"""What the tasks app receives: the approved title and deadline, and where the email is."""

from datetime import UTC, date, datetime, time

import pytest

from mailroom.store import Approval, Due, Task
from mailroom.tasks_app import task_key, task_payload

ITEM = "a" * 32
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
TASK = Task(ITEM, "gmail", "personal/m1", NOW, None, None)
LINK = "https://mail.google.com/mail/?authuser=owner@example.test#all/m1"
ZONE = "America/New_York"


def test_the_key_is_the_provider_and_the_message_id() -> None:
    assert task_key("gmail", "personal/m1") == "gmail:personal/m1"
    assert task_key("yahoo", "home/42") == "yahoo:home/42"


@pytest.mark.parametrize(
    ("outcome", "title", "due", "deadline"),
    [
        (
            "approve",
            "Pay the November bill",
            Due(date(2026, 11, 20), time(17, 0)),
            {"date": "2026-11-20", "time": "17:00", "time_zone": ZONE},
        ),
        (
            "change",
            "Pay online",
            Due(date(2026, 11, 13), None),
            {"date": "2026-11-13", "time": None, "time_zone": ZONE},
        ),
        ("change", "Pay online", None, None),
        ("nodeadline", "Pay the November bill", None, None),
    ],
    ids=["approve", "change-date-only", "change-no-deadline", "no-deadline"],
)
def test_the_payload_carries_only_the_approved_task_and_the_email_link(
    outcome: str, title: str, due: Due | None, deadline: dict | None
) -> None:
    approval = Approval(ITEM, outcome, title, due, NOW)
    assert task_payload(TASK, approval, LINK, ZONE) == {
        "source": "email",
        "title": title,
        "deadline": deadline,
        "provider": "gmail",
        "message_id": "personal/m1",
        "link": LINK,
    }
