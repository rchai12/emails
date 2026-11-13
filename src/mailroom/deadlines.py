import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mailroom.extractor import Extraction
from mailroom.record import Record

CONFIDENCE = "high"
WINDOW = timedelta(days=366)

_FLAGS = re.ASCII | re.IGNORECASE
_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tues": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thurs": 3,
    "thur": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sunday": 6,
}
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WEEKDAY = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))
_EDGE = r"(?<![A-Za-z0-9])"
_END = r"(?![A-Za-z0-9])"
_DAY = rf"([0-9]{{1,2}})(?:st|nd|rd|th)?{_END}"
_YEAR = rf"([0-9]{{4}}){_END}"
_MONTH_DAY = re.compile(
    rf"{_EDGE}({_MONTH})\.?{_END}\s+{_DAY}(?:(?:,\s+|\s+){_YEAR})?",
    _FLAGS,
)
_DAY_MONTH = re.compile(
    rf"{_EDGE}{_DAY}\s+(?:{_EDGE}of{_END}\s+)?({_MONTH})\.?{_END}(?:\s+{_YEAR})?",
    _FLAGS,
)
_ISO = re.compile(rf"{_EDGE}([0-9]{{4}})-([0-9]{{2}})-([0-9]{{2}}){_END}", _FLAGS)
_NAMED_DAY = re.compile(rf"{_EDGE}(today|tonight|tomorrow){_END}", _FLAGS)
_WEEKDAY_WORD = re.compile(rf"{_EDGE}({_WEEKDAY})\.?{_END}", _FLAGS)
_CLOCK = re.compile(
    rf"{_EDGE}([0-9]{{1,2}})(?::([0-9]{{2}}))?\s*(a\.m\.|a\.m|p\.m\.|p\.m|am|pm){_END}",
    _FLAGS,
)
_HOUR = re.compile(
    rf"{_EDGE}([0-9]{{1,2}}):([0-9]{{2}})"
    rf"(?!\s*(?:a\.m\.|a\.m|p\.m\.|p\.m|am|pm){_END}){_END}",
    _FLAGS,
)
_NAMED_TIME = re.compile(rf"{_EDGE}(noon|midday|midnight){_END}", _FLAGS)
_NEXT = re.compile(rf"{_EDGE}next{_END}\s+$", _FLAGS)


class _Unreadable(Exception):
    pass


def _spaces(quote: str) -> str:
    return "".join(" " if character.isspace() else character for character in quote)


def _day(text: str) -> int:
    number = int(text)
    if not 1 <= number <= 31:
        raise _Unreadable
    return number


def _resolve(sent_day: date, month: int, day: int, year: str | None) -> date:
    if year is None:
        numbered = sent_day.year
        if (month, day) < (sent_day.month, sent_day.day):
            numbered += 1
    else:
        numbered = int(year)
    return date(numbered, month, day)


def _dates(quote: str, sent_day: date) -> list[date]:
    found: list[date] = []
    for match in _MONTH_DAY.finditer(quote):
        found.append(
            _resolve(
                sent_day, _MONTHS[match.group(1).lower()], _day(match.group(2)), match.group(3)
            )
        )
    for match in _DAY_MONTH.finditer(quote):
        found.append(
            _resolve(
                sent_day, _MONTHS[match.group(2).lower()], _day(match.group(1)), match.group(3)
            )
        )
    for match in _ISO.finditer(quote):
        found.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    for match in _NAMED_DAY.finditer(quote):
        name = match.group(1).lower()
        if name == "tomorrow":
            found.append(sent_day + timedelta(days=1))
        else:
            found.append(sent_day)
    return found


def _weekdays(quote: str) -> list[int]:
    found: list[int] = []
    for match in _WEEKDAY_WORD.finditer(quote):
        if _NEXT.search(quote[: match.start()]):
            raise _Unreadable
        found.append(_WEEKDAYS[match.group(1).lower()])
    return found


def _hours(hour: int, minute: int, suffix: str) -> time:
    if minute > 59 or not 1 <= hour <= 12:
        raise _Unreadable
    if hour == 12:
        hour = 0
    if suffix[0].lower() == "p":
        hour += 12
    return time(hour, minute)


def _times(quote: str) -> list[time]:
    found: list[time] = []
    for match in _CLOCK.finditer(quote):
        minute = 0 if match.group(2) is None else int(match.group(2))
        found.append(_hours(int(match.group(1)), minute, match.group(3)))
    for match in _HOUR.finditer(quote):
        hour = int(match.group(1))
        minute = int(match.group(2))
        if minute > 59 or not (hour == 0 or 13 <= hour <= 23):
            raise _Unreadable
        found.append(time(hour, minute))
    for match in _NAMED_TIME.finditer(quote):
        name = match.group(1).lower()
        if name == "midnight":
            raise _Unreadable
        found.append(time(12, 0))
    return found


def _read(quote: str, sent_day: date) -> tuple[date, time | None] | None:
    text = _spaces(quote)
    dates = set(_dates(text, sent_day))
    weekdays = set(_weekdays(text))
    times = set(_times(text))
    if len(times) > 1 or len(dates) > 1:
        return None
    clock = None if not times else next(iter(times))
    if len(dates) == 1:
        found = next(iter(dates))
        if any(day != found.weekday() for day in weekdays):
            return None
        return found, clock
    if len(weekdays) != 1:
        return None
    (weekday,) = weekdays
    ahead = (weekday - sent_day.weekday()) % 7
    if ahead == 0:
        return None
    return sent_day + timedelta(days=ahead), clock


def read_deadline(quote: str, sent_day: date) -> tuple[date, time | None] | None:
    try:
        return _read(quote, sent_day)
    except (ValueError, OverflowError, _Unreadable):
        return None


def _holds(quote: str, subject: str, body: str) -> bool:
    folded = " ".join(quote.split())
    return folded != "" and (
        folded in " ".join(subject.split()) or folded in " ".join(body.split())
    )


def _still_ahead(
    deadline_date: date, deadline_time: time | None, zone: ZoneInfo, now: datetime
) -> bool:
    local = now.astimezone(zone)
    if deadline_time is None:
        return deadline_date >= local.date()
    moment = datetime.combine(deadline_date, deadline_time, tzinfo=zone)
    return moment > local


def clearly_dated(record: Record, extraction: Extraction, time_zone: str, now: datetime) -> bool:
    deadline = extraction.deadline
    if (
        not extraction.actionable
        or extraction.title == ""
        or extraction.suspicious
        or extraction.confidence != CONFIDENCE
        or deadline is None
        or not deadline.explicit
        or not _holds(deadline.quote, record.subject, record.body_text)
    ):
        return False
    zone = ZoneInfo(time_zone)
    sent_day = (record.sent_at or record.received_at).astimezone(zone).date()
    if read_deadline(deadline.quote, sent_day) != (deadline.date, deadline.time):
        return False
    if not sent_day <= deadline.date <= sent_day + WINDOW:
        return False
    return _still_ahead(deadline.date, deadline.time, zone, now)
