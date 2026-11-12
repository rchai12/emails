"""Probe for phase 1g. Run from the repository root: .venv/bin/python docs/verification/probe-01g.py

It builds random verdicts (one base, a few fields changed) and compares `should_notify` and
`rank` with an oracle that compares two emails step by step from the documented order. It stores
random verdicts with awkward text (quotes, backslashes, non-ASCII, JSON-looking text) and reads
them back, and clears text at random times and checks which extractions are gone. The database is
in a temporary folder. Each check prints `ok` or `FAIL`; the last line is `FAILURES N`.
"""

import functools
import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01g-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

from mailroom import clock  # noqa: E402
from mailroom.extractor import Deadline, Extraction, Rejected  # noqa: E402
from mailroom.record import Record  # noqa: E402
from mailroom.rules import Screening  # noqa: E402

FAILURES = 0
rng = random.Random(15)
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


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


# The oracle works on plain facts, never on the code under test.
def notify_oracle(facts: dict) -> bool:
    if facts["dropped"]:
        return False
    if facts["rejected"] or facts["trusted"]:
        return True
    if facts["actionable"] or facts["urgent"] or facts["deadline"] is not None:
        return True
    if facts["confidence"] == "high":
        return False
    return not (facts["confidence"] == "medium" and facts["bulk"])


def compare(a: dict, b: dict) -> int:
    """Negative when a ranks before b. Unknown facts count as not urgent, no deadline, low."""
    steps = [
        (not a["trusted"], not b["trusted"]),
        (a["suspicious"], b["suspicious"]),
        (not a["urgent"], not b["urgent"]),
        (a["deadline"] is None, b["deadline"] is None),
    ]
    if a["deadline"] is not None and b["deadline"] is not None:
        steps.append((end_of(a["deadline"]), end_of(b["deadline"])))
    steps += [
        (CONFIDENCE_ORDER[a["confidence"]], CONFIDENCE_ORDER[b["confidence"]]),
        (b["received"], a["received"]),
        (a["provider"], b["provider"]),
        (a["message_id"], b["message_id"]),
    ]
    for left, right in steps:
        if left != right:
            return -1 if left < right else 1
    return 0


def end_of(deadline: tuple[date, time | None]) -> datetime:
    day, when = deadline
    return datetime.combine(day, time(23, 59, 59, 999999) if when is None else when)


def fact(**changes: object) -> dict:
    base = {
        "dropped": False,
        "rejected": False,
        "trusted": False,
        "bulk": False,
        "actionable": False,
        "urgent": False,
        "suspicious": False,
        "deadline": None,
        "confidence": "high",
        "received": datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
        "provider": "gmail",
        "message_id": "m",
    }
    return {**base, **changes}


assert notify_oracle(fact()) is False
assert notify_oracle(fact(bulk=True, confidence="medium")) is False
assert notify_oracle(fact(confidence="medium")) is True
assert notify_oracle(fact(rejected=True, bulk=True)) is True
assert notify_oracle(fact(dropped=True, trusted=True)) is False
assert compare(fact(trusted=True), fact(urgent=True)) < 0
assert compare(fact(urgent=True, suspicious=True), fact()) > 0
assert (
    compare(
        fact(deadline=(date(2026, 11, 13), time(23, 0))), fact(deadline=(date(2026, 11, 13), None))
    )
    < 0
)
assert compare(fact(deadline=(date(2026, 11, 20), None)), fact(confidence="high")) < 0
assert compare(fact(message_id="b"), fact(message_id="a", provider="yahoo")) < 0
print("oracle self-check: ok")

try:
    from mailroom.config import get_settings
    from mailroom.store import StoredTriage, Verdict, open_store
    from mailroom.triage import rank, should_notify
except Exception as error:
    print(f"import: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)

AWKWARD = ['say "hi"', "back\\slash", "naïve café ✓", '{"title": "x"}', "tab\tin", "", "'; DROP"]
RECORD = Record(
    provider="gmail",
    message_id="m",
    thread_id="t",
    received_at=datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m",
    sender="sam@example.test",
    sender_name="Sam",
    subject="A question",
    sent_at=None,
    body_text="Can you reply?",
    list_unsubscribe=False,
    authentication_results=(),
)


def random_facts(index: int) -> dict:
    facts = fact(
        trusted=rng.random() < 0.2,
        bulk=rng.random() < 0.4,
        actionable=rng.random() < 0.4,
        urgent=rng.random() < 0.3,
        suspicious=rng.random() < 0.15,
        confidence=rng.choice(["high", "medium", "low"]),
        received=datetime(2026, 11, 12, rng.randrange(0, 4), tzinfo=UTC),
        provider=rng.choice(["gmail", "gmail", "outlook", "yahoo"]),
        message_id=f"m{index % 7}",
    )
    if rng.random() < 0.5:
        day = date(2026, 11, rng.randrange(13, 16))
        when = rng.choice([None, time(9, 0), time(17, 0), time(23, 59, 59, 999999)])
        facts["deadline"] = (day, when)
    kind = rng.choice(["extracted"] * 6 + ["rejected", "dropped", "cleared"])
    facts["rejected"] = kind == "rejected"
    facts["dropped"] = kind == "dropped"
    facts["kind"] = kind
    if kind != "extracted":
        facts.update(actionable=False, urgent=False, suspicious=False, deadline=None)
        facts["confidence"] = "low"
    return facts


def build(facts: dict) -> tuple[Screening, Extraction | Rejected | None, Record, Verdict]:
    screening = Screening(
        action="drop" if facts["dropped"] else "extract",
        trusted=facts["trusted"] and not facts["dropped"],
        verified=facts["trusted"] or rng.random() < 0.5,
        bulk=facts["bulk"],
    )
    facts["trusted"] = screening.trusted
    deadline = None
    if facts["deadline"] is not None:
        day, when = facts["deadline"]
        deadline = Deadline(date=day, time=when, explicit=rng.random() < 0.5, quote="due then")
    extraction = Extraction(
        summary=rng.choice(AWKWARD) or "A summary.",
        actionable=facts["actionable"],
        urgent=facts["urgent"],
        title=rng.choice(AWKWARD) if facts["actionable"] else "",
        deadline=deadline,
        suspicious=facts["suspicious"],
        suspicion_reason="Looks like phishing" if facts["suspicious"] else "",
        confidence=facts["confidence"],
    )
    kind = facts["kind"]
    result: Extraction | Rejected | None = {
        "extracted": extraction,
        "rejected": Rejected("timeout"),
        "dropped": None,
        "cleared": extraction,
    }[kind]
    verdict = Verdict(
        outcome="extracted" if kind == "cleared" else kind,
        trusted=screening.trusted,
        verified=screening.verified,
        bulk=screening.bulk,
        notify=notify_oracle(facts),
        extraction=extraction if kind == "extracted" else None,
        reason="timeout" if kind == "rejected" else "",
    )
    record = replace(
        RECORD,
        provider=facts["provider"],
        message_id=facts["message_id"],
        received_at=facts["received"],
    )
    return screening, result, record, verdict


def notify_follows_the_oracle() -> object:
    for index in range(4000):
        facts = random_facts(index)
        if facts["kind"] == "cleared":
            continue
        screening, result, _, _ = build(facts)
        want = notify_oracle(facts)
        got = should_notify(screening, result)
        if got is not want:
            return f"{facts}: notify {got}, want {want}"
    return True


def rank_follows_the_oracle() -> object:
    for _ in range(600):
        size = rng.randrange(0, 9)
        built = []
        seen = set()
        for _ in range(size):
            facts = random_facts(rng.randrange(100))
            key = (facts["provider"], facts["message_id"])
            if key in seen:
                continue
            seen.add(key)
            _, _, record, verdict = build(facts)
            built.append((facts, (record, verdict)))
        want = [
            entry
            for _, entry in sorted(
                built, key=functools.cmp_to_key(lambda a, b: compare(a[0], b[0]))
            )
        ]
        entries = [entry for _, entry in built]
        got = rank(entries)
        if got != want:
            names = lambda items: [r.message_id + "@" + r.provider for r, _ in items]  # noqa: E731
            return f"got {names(got)}, want {names(want)}"
    return True


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.moment


def stored_verdicts_read_back_and_clear_on_time() -> object:
    fake = Clock()
    clock.now = fake
    with open_store(get_settings()) as store:
        expected: dict[tuple[str, str], tuple[Verdict, datetime, datetime]] = {}
        for index in range(300):
            facts = random_facts(index)
            if facts["kind"] == "cleared":
                facts["kind"] = "extracted"
            _, _, record, verdict = build(facts)
            record = replace(record, message_id=f"p{index}")
            fake.moment = datetime(2026, 11, 10, 8, 0, tzinfo=UTC) + timedelta(minutes=index)
            fetched = fake.moment
            store.add(record)
            fake.moment += timedelta(seconds=30)
            if not store.save_triage(record.provider, record.message_id, verdict):
                return f"p{index}: a new verdict was refused"
            got = store.triage(record.provider, record.message_id)
            if got != StoredTriage(verdict=verdict, decided_at=fake.moment, text_cleared_at=None):
                return f"p{index}: read back {got}, want {verdict}"
            expected[(record.provider, record.message_id)] = (verdict, fake.moment, fetched)
        for step in range(5):
            fake.moment = datetime(2026, 11, 11, 8, 0, tzinfo=UTC) + timedelta(minutes=70 * step)
            store.clear_expired_text()
            cutoff = fake.moment - timedelta(hours=24)
            for (provider, message_id), (verdict, decided, fetched) in expected.items():
                got = store.triage(provider, message_id)
                if got is None:
                    return f"{message_id}: verdict lost"
                gone = fetched <= cutoff and verdict.outcome == "extracted"
                if gone != (got.verdict.extraction is None and verdict.extraction is not None):
                    cleared = got.text_cleared_at
                    return f"{message_id} fetched {fetched}: cleared {cleared} at {fake.moment}"
                if replace(got.verdict, extraction=verdict.extraction) != verdict:
                    return f"{message_id}: other fields changed on clearing"
                if got.decided_at != decided:
                    return f"{message_id}: decided_at changed"
    return True


check("the notify decision follows the owner's rule", notify_follows_the_oracle)
check("ranking follows the documented order", rank_follows_the_oracle)
check(
    "verdicts read back exactly and their text clears on time",
    stored_verdicts_read_back_and_clear_on_time,
)
print(f"FAILURES {FAILURES}")
