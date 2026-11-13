"""Probe for phase 2c. Run from the repository root: .venv/bin/python docs/verification/probe-02c.py

1. Decision: emails with a deadline at a random distance ahead get a model reply that is
   clearly dated, or that one change from a table spoils. Each is triaged at a random moment.
   The stored verdict's `dated` must equal `clearly_dated` (Phase 2b, already verified) for
   that email, extraction and moment, and `due` must be the model's proposed date and time (or
   None without a deadline, or for a reply that was refused). The stored verdict reads back equal
   to the returned one.
2. Retention: 24 hours later every row keeps `dated` and `due` while its extraction is gone, and
   no quote marker is left anywhere in the database file.
Fakes only; everything lives in a temporary folder. Each check prints `ok` or `FAIL`; the last
line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe02c-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
os.environ["MAILROOM_EXTRACTOR_MODEL"] = "qwen-test:27b"
os.environ["MAILROOM_TIME_ZONE"] = "America/New_York"

import httpx  # noqa: E402

from mailroom import clock  # noqa: E402
from mailroom.config import get_settings  # noqa: E402
from mailroom.deadlines import clearly_dated  # noqa: E402
from mailroom.extractor import Deadline, Extraction  # noqa: E402
from mailroom.record import Record  # noqa: E402
from mailroom.store import open_store  # noqa: E402
from mailroom.triage import triage_message  # noqa: E402
from tests.fakes import FakeOllama  # noqa: E402

FAILURES = 0
rng = random.Random(23)
ZONE = "America/New_York"
MONTHS = "January February March April May June July August September October November December"
MOMENT = [datetime(2026, 1, 1, tzinfo=UTC)]


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


def reply_for(when: date, at: time, marker: str) -> dict[str, object]:
    month = MONTHS.split()[when.month - 1]
    hour = at.hour % 12 or 12
    suffix = "am" if at.hour < 12 else "pm"
    spoken = f"{hour}:{at.minute:02d} {suffix}" if at.minute else f"{hour} {suffix}"
    return {
        "summary": "A bill is due.",
        "actionable": True,
        "urgent": False,
        "title": "Pay the bill",
        "has_deadline": True,
        "deadline_date": when.isoformat(),
        "deadline_time": at.strftime("%H:%M"),
        "deadline_explicit": True,
        "deadline_quote": f"due on {month} {when.day}, {when.year} at {spoken} {marker}",
        "suspicious": False,
        "suspicion_reason": "",
        "confidence": "high",
    }


CHANGES = {
    "none": lambda r: r,
    "medium": lambda r: {**r, "confidence": "medium"},
    "vague": lambda r: {**r, "deadline_explicit": False},
    "suspicious": lambda r: {**r, "suspicious": True, "suspicion_reason": "Odd sender."},
    "other-date": lambda r: {
        **r,
        "deadline_date": (date.fromisoformat(r["deadline_date"]) + timedelta(days=1)).isoformat(),
    },
    "no-time": lambda r: {**r, "deadline_time": ""},
    "other-quote": lambda r: {**r, "deadline_quote": r["deadline_quote"] + " please"},
    "no-deadline": lambda r: {
        **r,
        "has_deadline": False,
        "deadline_date": "",
        "deadline_time": "",
        "deadline_explicit": False,
        "deadline_quote": "",
    },
    "refused": lambda r: {**r, "title": "Pay\nnow"},
}


def to_extraction(reply: dict[str, object]) -> Extraction:
    deadline = None
    if reply["has_deadline"]:
        raw_time = reply["deadline_time"]
        deadline = Deadline(
            date=date.fromisoformat(reply["deadline_date"]),
            time=None if raw_time == "" else time.fromisoformat(raw_time),
            explicit=reply["deadline_explicit"],
            quote=reply["deadline_quote"],
        )
    return Extraction(
        summary=reply["summary"],
        actionable=reply["actionable"],
        urgent=reply["urgent"],
        title=reply["title"],
        deadline=deadline,
        suspicious=reply["suspicious"],
        suspicion_reason=reply["suspicion_reason"],
        confidence=reply["confidence"],
    )


assert to_extraction(reply_for(date(2026, 11, 20), time(17, 0), "M")).deadline.quote == (
    "due on November 20, 2026 at 5 pm M"
)
assert reply_for(date(2026, 11, 20), time(0, 30), "M")["deadline_quote"] == (
    "due on November 20, 2026 at 12:30 am M"
)
assert CHANGES["other-date"](reply_for(date(2026, 11, 20), time(9, 0), "M"))["deadline_date"] == (
    "2026-11-21"
)
print("oracle self-check: ok")


def decisions_and_retention() -> object:
    clock.now = lambda: MOMENT[0]
    settings = get_settings()
    seen = {name: 0 for name in CHANGES}
    latest = MOMENT[0]
    dated_count = 0
    with open_store(settings) as store:
        for number in range(400):
            sent = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=rng.randrange(300 * 1440))
            ahead = timedelta(hours=rng.randrange(-48, 24 * 400))
            due_at = (sent + ahead).astimezone(ZoneInfo(ZONE)).replace(second=0, microsecond=0)
            due_at = due_at.replace(minute=rng.choice((0, 30)))
            marker = f"ZQXQ{number:04d}"
            base = reply_for(due_at.date(), due_at.time(), marker)
            change = rng.choice(sorted(CHANGES))
            reply = CHANGES[change](base)
            seen[change] += 1
            record = Record(
                provider="gmail",
                message_id=f"personal/m{number}",
                thread_id=f"personal/t{number}",
                received_at=sent,
                link=f"https://mail.google.com/mail/?authuser=owner@example.test#all/m{number}",
                sender="billing@example.test",
                sender_name="Billing",
                subject="Your bill",
                sent_at=sent,
                body_text=f"Hello.\nYour bill is {base['deadline_quote']}.\nThanks.",
                list_unsubscribe=False,
                authentication_results=(),
            )
            MOMENT[0] = sent + timedelta(minutes=rng.randrange(1, 3 * 1440))
            latest = max(latest, MOMENT[0])
            store.add(record)
            fake = FakeOllama()
            fake.replies.append(reply)
            http = httpx.Client(transport=httpx.MockTransport(fake.handler))
            verdict = triage_message(store, "gmail", record.message_id, settings, http)
            if change == "refused":
                want_dated, want_due = False, None
            else:
                extraction = to_extraction(reply)
                want_dated = clearly_dated(record, extraction, ZONE, MOMENT[0])
                deadline = extraction.deadline
                want_due = None if deadline is None else (deadline.date, deadline.time)
            got_due = None if verdict.due is None else (verdict.due.date, verdict.due.time)
            if (verdict.dated, got_due) != (want_dated, want_due):
                return (
                    f"{number} {change}: {(verdict.dated, got_due)}, want {(want_dated, want_due)}"
                )
            if store.triage("gmail", record.message_id).verdict != verdict:
                return f"{number} {change}: the stored verdict differs"
            dated_count += verdict.dated
        kept = {
            message_id: (found.verdict.dated, found.verdict.due)
            for number in range(400)
            if (found := store.triage("gmail", (message_id := f"personal/m{number}"))) is not None
        }
        MOMENT[0] = latest + timedelta(days=4)
        store.clear_expired_text()
        for message_id, (dated, due) in kept.items():
            found = store.triage("gmail", message_id).verdict
            if found.extraction is not None or (found.dated, found.due) != (dated, due):
                return f"{message_id}: changed by clearing"
    content = (TMP / "data" / "mailroom.sqlite3").read_bytes()
    if b"ZQXQ" in content:
        return "a quote marker is still in the file"
    if min(seen.values()) < 20 or dated_count < 20:
        return f"too few cases: {seen}, dated {dated_count}"
    return True


check(
    "the stored decision and deadline match the rule, and survive clearing", decisions_and_retention
)
print(f"FAILURES {FAILURES}")
