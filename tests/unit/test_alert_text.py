from datetime import timedelta

import pytest

from mailroom.alerts import catch_up_text


@pytest.mark.parametrize(
    ("offline", "count", "gap", "text"),
    [
        (timedelta(minutes=59), 0, False, "after less than an hour offline: no new emails."),
        (timedelta(hours=1), 1, False, "after 1 hour offline: 1 new email."),
        (timedelta(hours=47, minutes=59), 2, False, "after 47 hours offline: 2 new emails."),
        (timedelta(hours=48), 3, False, "after 2 days offline: 3 new emails."),
        (
            timedelta(days=20, hours=23),
            12,
            True,
            "after 20 days offline: 12 new emails. It was offline for more than 14 days, "
            "so check older mail in Gmail yourself.",
        ),
    ],
    ids=["minutes", "one-hour", "hours", "two-days", "past-the-limit"],
)
def test_the_catch_up_summary_reads_naturally(
    offline: timedelta, count: int, gap: bool, text: str
) -> None:
    assert catch_up_text("personal", offline, count, gap) == f"Gmail personal caught up {text}"
