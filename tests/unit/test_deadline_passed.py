from datetime import UTC, date, datetime, time

import pytest

from mailroom.deadlines import deadline_passed

ZONE = "America/New_York"
FIVE_PM = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)  # 17:00 on November 20 in New York
LATE = datetime(2026, 11, 21, 4, 59, tzinfo=UTC)  # 23:59 on November 20 in New York


@pytest.mark.parametrize(
    ("day", "at", "now", "passed"),
    [
        (date(2026, 11, 20), time(17, 0), FIVE_PM, True),
        (date(2026, 11, 20), time(17, 1), FIVE_PM, False),
        (date(2026, 11, 20), None, FIVE_PM, False),
        (date(2026, 11, 19), None, FIVE_PM, True),
        (date(2026, 11, 21), time(0, 0), FIVE_PM, False),
        (date(2026, 11, 20), None, LATE, False),
        (date(2026, 11, 20), time(23, 0), LATE, True),
    ],
    ids=[
        "at-the-minute",
        "a-minute-before",
        "later-today",
        "yesterday",
        "tomorrow-at-midnight",
        "local-day-not-utc",
        "earlier-tonight",
    ],
)
def test_a_deadline_has_passed_at_or_after_its_moment(
    day: date, at: time | None, now: datetime, passed: bool
) -> None:
    assert deadline_passed(day, at, ZONE, now) is passed
