"""Probe for phase 2b. Run from the repository root: .venv/bin/python docs/verification/probe-02b.py

1. Reading: a random deadline (a date up to 300 days after a random sent day, with or without a
   time) is written in a random accepted form from this probe's own tables and set among filler
   words. `read_deadline` must return exactly that date and time.
2. One change: the same quote with a second date, `next` before a weekday, a weekday that does
   not match, or a 12-hour time without am/pm must read as None.
3. Junk: random strings of month names, weekdays, digits, punctuation and other scripts never
   raise, and any date read without a stated year lies within a year of the sent day.
4. The rule: an email built around a read-back quote (its spacing changed at random) is clearly
   dated; the same email with one condition broken is not.
Pure functions only; no files, no network. Each check prints `ok` or `FAIL`; the last line is
`FAILURES N`.
"""

import random
import re
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mailroom.extractor import Deadline, Extraction  # noqa: E402
from mailroom.record import Record  # noqa: E402

FAILURES = 0
rng = random.Random(22)
MONTHS = [
    ("January", "Jan"),
    ("February", "Feb"),
    ("March", "Mar"),
    ("April", "Apr"),
    ("May", "May"),
    ("June", "Jun"),
    ("July", "Jul"),
    ("August", "Aug"),
    ("September", "Sept"),
    ("October", "Oct"),
    ("November", "Nov"),
    ("December", "Dec"),
]
WEEKDAYS = [
    ("Monday", "Mon"),
    ("Tuesday", "Tue"),
    ("Wednesday", "Wed"),
    ("Thursday", "Thu"),
    ("Friday", "Fri"),
    ("Saturday", "Saturday"),
    ("Sunday", "Sunday"),
]
FILLER = ["please", "pay", "the", "invoice", "due", "by", "your", "account", "thanks", "on"]
ZONE = "America/New_York"


def check(name: str, fn) -> None:
    global FAILURES
    try:
        result = fn()
    except Exception as error:
        result = f"raised {type(error).__name__}"
    ok = result is True
    print(f"{name}: {'ok' if ok else 'FAIL ' + str(result)}")
    if not ok:
        FAILURES += 1


def ordinal(day: int) -> str:
    if day in (11, 12, 13):
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def render_date(when: date, with_year: bool) -> str:
    full, short = MONTHS[when.month - 1]
    month = rng.choice((full, short, short + ".", full.upper()))
    day = rng.choice((str(when.day), ordinal(when.day)))
    year = f"{rng.choice((', ', ' '))}{when.year}" if with_year else ""
    form = rng.randrange(4)
    if form == 0:
        return f"{month} {day}{year}"
    if form == 1:
        return f"{day} {month}{year.replace(',', '')}"
    if form == 2:
        return f"{day} of {month}{year.replace(',', '')}"
    return when.isoformat()


def render_time(when: time) -> str:
    if when == time(12, 0) and rng.random() < 0.3:
        return rng.choice(("noon", "midday"))
    hour12 = when.hour % 12 or 12
    suffix = (
        rng.choice(("am", "AM", "a.m.")) if when.hour < 12 else rng.choice(("pm", "PM", "p.m."))
    )
    minutes = f":{when.minute:02d}" if when.minute or rng.random() < 0.3 else ""
    if when.hour >= 13 and rng.random() < 0.4:
        return f"{when.hour}:{when.minute:02d}"
    return f"{hour12}{minutes}{rng.choice(('', ' '))}{suffix}"


def random_deadline(sent: date) -> tuple[str, date, time | None]:
    """A quote naming one deadline, with the date and time it names."""
    ahead = rng.randrange(1, 300)
    when = sent + timedelta(days=ahead)
    if ahead <= 6 and rng.random() < 0.5:
        full, short = WEEKDAYS[when.weekday()]
        text = f"{rng.choice(('by', 'this', 'on'))} {rng.choice((full, short))}"
    elif ahead == 1 and rng.random() < 0.5:
        text = "tomorrow"
    else:
        text = render_date(when, rng.random() < 0.5)
        if rng.random() < 0.3:
            text = f"{WEEKDAYS[when.weekday()][0]}, {text}"
    clock_time = None
    if rng.random() < 0.5:
        clock_time = time(rng.randrange(24), rng.choice((0, 15, 30, 45)))
        text = f"{text} at {render_time(clock_time)}"
    words = rng.sample(FILLER, rng.randrange(0, 4))
    return " ".join([*words, text, *rng.sample(FILLER, rng.randrange(0, 3))]), when, clock_time


def random_sent() -> date:
    return date(2000, 1, 1) + timedelta(days=rng.randrange(90 * 365))


# Self-check of the tables, on known values.
assert (
    ordinal(1) == "1st"
    and ordinal(12) == "12th"
    and ordinal(22) == "22nd"
    and ordinal(23) == "23rd"
)
assert WEEKDAYS[date(2026, 11, 13).weekday()][0] == "Friday"
for _ in range(500):
    sent = random_sent()
    quote, when, clock_time = random_deadline(sent)
    assert sent < when <= sent + timedelta(days=300)
    assert "next" not in quote.lower()
print("oracle self-check: ok")


def quotes_read_back() -> object:
    from mailroom.deadlines import read_deadline

    for _ in range(4000):
        sent = random_sent()
        quote, when, clock_time = random_deadline(sent)
        found = read_deadline(quote, sent)
        if found != (when, clock_time):
            return f"{quote!r} sent {sent}: {found}, want {(when, clock_time)}"
    return True


def one_change_reads_none() -> object:
    from mailroom.deadlines import read_deadline

    reached = {"second-date": 0, "next": 0, "weekday": 0, "ambiguous-time": 0}
    for _ in range(3000):
        sent = random_sent()
        when = sent + timedelta(days=rng.randrange(7, 300))
        base = render_date(when, True)
        change = rng.choice(sorted(reached))
        if change == "second-date":
            other = when + timedelta(days=rng.randrange(1, 30))
            quote = f"{base} or {render_date(other, True)}"
        elif change == "next":
            ahead = sent + timedelta(days=rng.randrange(1, 7))
            quote = f"next {WEEKDAYS[ahead.weekday()][0]}"
        elif change == "weekday":
            wrong = WEEKDAYS[(when.weekday() + rng.randrange(1, 7)) % 7][0]
            quote = f"{wrong}, {base}"
        else:
            quote = f"{base} at {rng.randrange(1, 13)}:{rng.choice(('00', '30'))}"
        reached[change] += 1
        found = read_deadline(quote, sent)
        if found is not None:
            return f"{change}: {quote!r} sent {sent} read as {found}"
    if min(reached.values()) < 100:
        return f"cases not reached: {reached}"
    return True


def junk_never_raises() -> object:
    from mailroom.deadlines import read_deadline

    pieces = [m for pair in MONTHS for m in pair] + [w for pair in WEEKDAYS for w in pair]
    pieces += ["today", "tomorrow", "next", "noon", "midnight", "am", "pm", "p.m.", "of", "this"]
    pieces += ["0", "1", "12", "13", "20", "29", "30", "31", "32", "99", "2026", "0000", "9999"]
    pieces += [":", "-", ",", ".", "/", " ", "\n", " ", "٢", "о", "İ", "ﬁ", "\x00"]
    for _ in range(20000):
        sent = date(1, 1, 1) + timedelta(days=rng.randrange(date.max.toordinal() - 1))
        quote = "".join(
            rng.choice(pieces) + rng.choice(("", " ")) for _ in range(rng.randrange(12))
        )
        found = read_deadline(quote, sent)
        if found is None:
            continue
        if not (isinstance(found, tuple) and len(found) == 2 and isinstance(found[0], date)):
            return f"{quote!r}: {found!r}"
        if found[1] is not None and not isinstance(found[1], time):
            return f"{quote!r}: {found!r}"
        stated = re.search("[0-9]{4}", quote) is not None
        ahead = found[0].toordinal() - sent.toordinal()
        if not stated and not 0 <= ahead <= 366:
            return f"{quote!r} sent {sent}: {found[0]} without a stated year"
    return True


def the_rule_holds() -> object:
    from mailroom.deadlines import clearly_dated

    reached = 0
    for _ in range(3000):
        sent_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=rng.randrange(365 * 24 * 60))
        sent_day = sent_at.astimezone(ZoneInfo(ZONE)).date()
        quote, when, clock_time = random_deadline(sent_day)
        spaced = "".join(rng.choice((" ", "\n", "\t ", " ")) if c == " " else c for c in quote)
        record = Record(
            provider="gmail",
            message_id="personal/m1",
            thread_id="personal/t1",
            received_at=sent_at,
            link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
            sender="billing@example.test",
            sender_name="Billing",
            subject="Notice",
            sent_at=sent_at,
            body_text=f"Hello.\n{spaced}\nThanks.",
            list_unsubscribe=False,
            authentication_results=(),
        )
        extraction = Extraction(
            summary="A notice.",
            actionable=True,
            urgent=False,
            title="Do it",
            deadline=Deadline(date=when, time=clock_time, explicit=True, quote=quote),
            suspicious=False,
            suspicion_reason="",
            confidence="high",
        )
        now = sent_at + timedelta(minutes=5)
        if not clearly_dated(record, extraction, ZONE, now):
            return f"{quote!r} sent {sent_at}: not clearly dated"
        deadline = extraction.deadline
        broken = rng.choice(
            [
                replace(extraction, suspicious=True),
                replace(extraction, confidence=rng.choice(("medium", "low"))),
                replace(extraction, deadline=replace(deadline, explicit=False)),
                replace(extraction, deadline=replace(deadline, date=when + timedelta(days=1))),
                replace(extraction, deadline=replace(deadline, quote=quote + " x")),
                replace(extraction, title=""),
            ]
        )
        if clearly_dated(record, broken, ZONE, now):
            return f"{quote!r}: a broken case was clearly dated"
        if clearly_dated(record, extraction, ZONE, now + timedelta(days=301)):
            return f"{quote!r}: a past deadline was clearly dated"
        reached += 1
    return True if reached == 3000 else f"reached {reached}"


check("random deadlines read back exactly", quotes_read_back)
check("one change reads as no deadline", one_change_reads_none)
check("junk never raises and stays within a year", junk_never_raises)
check("the rule holds on a valid email and fails on one change", the_rule_holds)
print(f"FAILURES {FAILURES}")
