from datetime import date, time

import pytest

from mailroom.deadlines import read_deadline

SENT = date(2026, 11, 10)  # a Tuesday
NOV_20 = date(2026, 11, 20)  # a Friday


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("due on November 20", (NOV_20, None)),
        ("by Nov. 20th, 2026", (NOV_20, None)),
        ("pay by 20 November", (NOV_20, None)),
        ("the 20th of November", (NOV_20, None)),
        ("20 November 2026", (NOV_20, None)),
        ("Nov 20 2026", (NOV_20, None)),
        ("NOVEMBER 20", (NOV_20, None)),
        ("deadline 2026-11-20", (NOV_20, None)),
        ("Payment may be made by Nov 20", (NOV_20, None)),
        ("Nov 20 (November 20)", (NOV_20, None)),
        ("Sept 30", (date(2027, 9, 30), None)),
        ("January 5", (date(2027, 1, 5), None)),
        ("December 1, 2025", (date(2025, 12, 1), None)),
        ("due November 20 at 5 pm", (NOV_20, time(17, 0))),
        ("by 5:30PM on Nov 20", (NOV_20, time(17, 30))),
        ("by 9 a.m. on November 20", (NOV_20, time(9, 0))),
        ("Nov 20 at 12 am", (NOV_20, time(0, 0))),
        ("Nov 20 at 12 pm", (NOV_20, time(12, 0))),
        ("Nov 20 by noon", (NOV_20, time(12, 0))),
        ("Nov 20 at midday", (NOV_20, time(12, 0))),
        ("Nov 20 17:00", (NOV_20, time(17, 0))),
        ("Nov 20 at 00:30", (NOV_20, time(0, 30))),
        ("by Friday", (date(2026, 11, 13), None)),
        ("this Friday", (date(2026, 11, 13), None)),
        ("by Fri", (date(2026, 11, 13), None)),
        ("by Monday", (date(2026, 11, 16), None)),
        ("by Thursday, Nov. 12", (date(2026, 11, 12), None)),
        ("Friday, November 20", (NOV_20, None)),
        ("today by 5 pm", (SENT, time(17, 0))),
        ("tomorrow", (date(2026, 11, 11), None)),
        ("tomorrow (Wednesday)", (date(2026, 11, 11), None)),
    ],
    ids=[
        "month-day",
        "abbreviation-ordinal-year",
        "day-month",
        "day-of-month",
        "day-month-year",
        "year-without-comma",
        "capitals",
        "iso",
        "may-is-a-verb",
        "same-date-twice",
        "sept-rolls-to-next-year",
        "january-rolls-to-next-year",
        "stated-year-kept",
        "with-pm",
        "minutes-pm-no-space",
        "dotted-am",
        "12-am",
        "12-pm",
        "noon",
        "midday",
        "24-hour",
        "24-hour-after-midnight",
        "weekday",
        "this-weekday",
        "weekday-abbreviation",
        "weekday-next-week",
        "weekday-matching-date",
        "weekday-matching-far-date",
        "today",
        "tomorrow",
        "tomorrow-matching-weekday",
    ],
)
def test_a_quote_naming_one_deadline_is_read(
    quote: str, expected: tuple[date, time | None]
) -> None:
    assert read_deadline(quote, SENT) == expected


@pytest.mark.parametrize(
    "quote",
    [
        "",
        "soon",
        "next week",
        "11/20",
        "the 20th",
        "November 20 or November 21",
        "next Friday",
        "by Tuesday",
        "Friday or Monday",
        "Thursday, November 20",
        "tomorrow (Friday)",
        "February 30",
        "Feb 29",
        "Nov 32",
        "0000-01-01",
        "Nov 20 at 5:00",
        "Nov 20 at 5 pm or 6 pm",
        "Nov 20 at 13 pm",
        "Nov 20 at midnight",
        "by Sat",
        "Nov ٢٠",
        "Nоvember 20",
    ],
    ids=[
        "empty",
        "vague",
        "next-week",
        "numeric",
        "day-alone",
        "two-dates",
        "next-weekday",
        "sent-weekday",
        "two-weekdays",
        "weekday-mismatch",
        "tomorrow-mismatch",
        "no-such-day",
        "no-leap-day-next-year",
        "day-out-of-range",
        "year-zero",
        "ambiguous-24-hour",
        "two-times",
        "pm-hour-too-big",
        "midnight",
        "sat-not-read",
        "arabic-indic-digits",
        "cyrillic-o",
    ],
)
def test_a_quote_that_names_no_single_readable_deadline_gives_none(quote: str) -> None:
    assert read_deadline(quote, SENT) is None


@pytest.mark.parametrize(
    ("sent", "quote", "expected"),
    [
        (date(9999, 12, 31), "by Friday", None),
        (date(9999, 12, 31), "tomorrow", None),
        (date(9999, 12, 31), "January 5", None),
        (date(1, 1, 1), "December 31", (date(1, 12, 31), None)),
        (SENT, "9999-12-31", (date(9999, 12, 31), None)),
    ],
    ids=[
        "weekday-past-the-end",
        "tomorrow-past-the-end",
        "next-year-past-the-end",
        "year-one",
        "max",
    ],
)
def test_dates_at_the_ends_of_the_calendar_never_raise(
    sent: date, quote: str, expected: tuple[date, time | None] | None
) -> None:
    assert read_deadline(quote, sent) == expected
