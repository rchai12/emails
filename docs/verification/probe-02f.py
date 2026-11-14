"""Probe for phase 2f. Run from the repository root: .venv/bin/python docs/verification/probe-02f.py

Each trial posts a few emails, then runs rounds three hours apart. In each round some emails
are decided at random (Approve, Edit, No deadline, Not a task at checkpoint 2, Not a task at
checkpoint 1, or one of the combined decisions), and the stub tasks app fails at random (503,
500, a network error, a lost reply, an id that is not text). Closing rounds have no failures.
At the end the tasks app must hold exactly one task per approved email, under the key
`gmail:<message id>`, with the body the probe's own decision table gives. Every request for a key
must carry that same body, the store must hold the app's id, and no request may contain the
email's subject or body. Fakes only; everything lives in a temporary folder. The check prints `ok`
or `FAIL`; the last line is `FAILURES N`.
"""

import json
import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe02f-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_TIME_ZONE"] = "America/New_York"
os.environ["MAILROOM_TASKS_URL"] = "http://127.0.0.1:8765"

import httpx  # noqa: E402

from mailroom import clock  # noqa: E402
from mailroom.config import get_settings  # noqa: E402
from tests.fakes import FakeTasksApp  # noqa: E402

FAILURES = 0
rng = random.Random(26)
ZONE = "America/New_York"
START = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
MOMENT = [START]
TITLES = ("Pay the bill", "Send the signed form", "Renew the parking permit")
TASKS = ("approve", "change", "nodeadline", "c-approve", "c-change", "c-nd")
DECISIONS = (*TASKS, "drop", "notask")
SUBJECT = "Probe subject 7f3a"
BODY = "Probe body 9c2e: please pay."


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


def deadline(due: tuple[date, time | None] | None) -> dict | None:
    """The probe's own reading of the payload's deadline, from the spec's table."""
    if due is None:
        return None
    at = None if due[1] is None else due[1].strftime("%H:%M")
    return {"date": due[0].isoformat(), "time": at, "time_zone": ZONE}


assert deadline(None) is None
assert deadline((date(2026, 11, 20), time(9, 5))) == {
    "date": "2026-11-20",
    "time": "09:05",
    "time_zone": ZONE,
}
print("oracle self-check: ok")


def random_due() -> tuple[date, time | None]:
    day = date(2026, 11, 10) + timedelta(days=rng.randrange(1, 40))
    return day, time(rng.randrange(24), rng.choice((0, 15, 30))) if rng.random() < 0.5 else None


def decide(store, item: str, kind: str) -> tuple[str, tuple | None] | None:
    """Record one decision the way the listener would; return the task it should make."""
    from mailroom.store import Due

    title = rng.choice(TITLES)
    due = random_due()
    if kind == "notask":
        store.record_answer(item, "notask", "")
        return None
    if kind.startswith("c-"):
        outcome = {"c-approve": "approve", "c-change": "change", "c-nd": "nodeadline"}[kind]
    else:
        outcome = kind
    if outcome == "drop":
        store.record_answer(item, "yes", title)
        store.record_approval(item, "drop", "", None)
        return None
    # Approve needs a deadline (the schema says so); Edit may leave it empty.
    kept = None if outcome == "nodeadline" or (outcome == "change" and rng.random() < 0.3) else due
    found = None if kept is None else Due(*kept)
    if kind.startswith("c-"):
        store.record_combined(item, outcome, title, found)
    else:
        store.record_answer(item, "yes", title)
        store.record_approval(item, outcome, title, found)
    return title, kept


def each_approved_email_makes_one_task() -> object:
    from mailroom.store import open_store
    from mailroom.tasks_app import send_tasks
    from tests.integration.test_store_posts import NOTIFY, RECORD

    clock.now = lambda: MOMENT[0]
    reached = {"retried": 0, "dropped": 0, "combined": 0, "no-deadline": 0, "after-clear": 0}
    choices = (None, None, httpx.Response(503), httpx.Response(500), "lost-reply")
    choices += (httpx.ConnectError("x"), httpx.Response(201, json={"id": 5}))
    for trial in range(60):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"trial{trial}")
        MOMENT[0] = START
        settings = get_settings()
        fake = FakeTasksApp()
        http = httpx.Client(transport=httpx.MockTransport(fake.handler))
        wanted: dict[str, tuple[str, tuple | None]] = {}
        with open_store(settings) as store:
            emails = [f"personal/m{number}" for number in range(rng.randrange(2, 6))]
            for message_id in emails:
                email = replace(RECORD, message_id=message_id, subject=SUBJECT, body_text=BODY)
                store.add(email)
                store.save_triage("gmail", message_id, NOTIFY)
            store.queue_notified()
            open_items = {store.post("gmail", m).item_id: m for m in emails}
            for round_number in range(14):
                for item, message_id in list(open_items.items()):
                    # The first email is approved at once, so round 0's lost reply hits it; the
                    # last waits until its text is cleared (round 9 is 27 hours in), then approves.
                    first = round_number == 0 and message_id == emails[0]
                    late = round_number == 9 and message_id == emails[-1]
                    early = message_id != emails[-1] and round_number < 10
                    if first or late or (early and rng.random() < 0.3):
                        kind = rng.choice(DECISIONS)
                        kind = "approve" if first else rng.choice(TASKS) if late else kind
                        task = decide(store, item, kind)
                        del open_items[item]
                        reached["combined"] += kind.startswith("c-")
                        reached["dropped"] += task is None
                        if task is not None:
                            wanted[f"gmail:{message_id}"] = task
                            reached["no-deadline"] += task[1] is None
                if round_number == 0:
                    fake.failures.append("lost-reply")
                elif round_number < 11:
                    fake.failures.extend(rng.choice(choices) for _ in range(rng.randrange(3)))
                store.clear_expired_text()
                send_tasks(store, settings, http)
                fake.failures.clear()
                MOMENT[0] += timedelta(hours=3)
            if set(fake.tasks) != set(wanted):
                return f"trial {trial}: tasks {sorted(fake.tasks)}, wanted {sorted(wanted)}"
            for key, (title, due) in wanted.items():
                message_id = key.removeprefix("gmail:")
                body = {
                    "source": "email",
                    "title": title,
                    "deadline": deadline(due),
                    "provider": "gmail",
                    "message_id": message_id,
                    "link": RECORD.link,
                }
                sent = [
                    json.loads(request.content)
                    for request in fake.requests
                    if request.headers.get("idempotency-key") == key
                ]
                if any(found != body for found in sent):
                    return f"trial {trial}: {key} sent another body"
                reached["retried"] += len(sent) > 1
                item = store.post("gmail", message_id).item_id
                if store.task(item).task_id != fake.tasks[key][0]:
                    return f"trial {trial}: {key} stored {store.task(item).task_id}"
                if store.task(item).sent_at - START >= timedelta(hours=24):
                    reached["after-clear"] += 1
            for request in fake.requests:
                text = request.content.decode()
                if SUBJECT in text or BODY in text:
                    return f"trial {trial}: a request carried email text"
    if min(reached.values()) < 10:
        return f"too few cases: {reached}"
    return True


check("each approved email makes one task, with one body", each_approved_email_makes_one_task)
print(f"FAILURES {FAILURES}")
