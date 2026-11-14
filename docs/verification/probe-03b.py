"""Probe for phase 3b. Run from the repository root: .venv/bin/python docs/verification/probe-03b.py

Each trial runs rounds three hours apart. New emails arrive in two threads, and each round's
open emails are answered at random, as the cards would allow:
- an email in a thread with an approved item is a follow-up: Add to task, New task (then No
  deadline) or Not a task;
- any other email: approved (No deadline), dropped at checkpoint 2, or Not a task.
The stub tasks app fails at random (503, a network error, a lost reply, an id that can't name a
path), and every trial's first link request loses its reply. Closing rounds have no failures.
At the end the app must hold exactly one task per approved email and one link per follow-up
added to a task, on the id of the task it follows. Every request for a key must carry one body,
and the app must never answer 404 for a link (a link sent before its task had an id). Fakes
only; everything lives in a temporary folder. The check prints `ok` or `FAIL`; the last line is
`FAILURES N`.
"""

import json
import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe03b-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_TIME_ZONE"] = "America/New_York"
os.environ["MAILROOM_TASKS_URL"] = "http://127.0.0.1:8765"

import httpx  # noqa: E402

from mailroom import clock  # noqa: E402
from mailroom.config import get_settings  # noqa: E402
from tests.fakes import FakeTasksApp  # noqa: E402

FAILURES = 0
rng = random.Random(32)
START = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
MOMENT = [START]


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


def link_body(message_id: str, link: str) -> dict:
    """The probe's own reading of a link's body, from the spec's table."""
    return {"source": "email", "provider": "gmail", "message_id": message_id, "link": link}


assert link_body("personal/m2", "https://x") == {
    "source": "email",
    "provider": "gmail",
    "message_id": "personal/m2",
    "link": "https://x",
}
print("oracle self-check: ok")


class Watched:
    """The fake behind a transport that records each answer and loses the first link's reply."""

    def __init__(self) -> None:
        self.fake = FakeTasksApp()
        self.statuses: list[tuple[str, int]] = []
        self.lost_one = False
        self.noisy = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        is_link = request.url.path.endswith("/links")
        if is_link and not self.lost_one and not self.fake.failures:
            self.lost_one = True
            self.fake.failures.append("lost-reply")
        if self.noisy and not is_link and rng.random() < 0.1:
            # An id that can't name a path, only ever for a task.
            return httpx.Response(201, json={"id": "a.b"})
        response = self.fake.handler(request)
        self.statuses.append((request.url.path, response.status_code))
        return response


def each_follow_up_makes_one_link() -> object:
    from mailroom.store import open_store
    from mailroom.tasks_app import send_tasks
    from tests.integration.test_store_posts import NOTIFY, RECORD

    clock.now = lambda: MOMENT[0]
    reached = {"links": 0, "retried": 0, "waited": 0, "new-task": 0, "after-clear": 0}
    choices = (None, None, httpx.Response(503), "lost-reply", httpx.ConnectError("x"))
    for trial in range(60):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"trial{trial}")
        MOMENT[0] = START
        settings = get_settings()
        watched = Watched()
        http = httpx.Client(transport=httpx.MockTransport(watched.handler))
        tasks: set[str] = set()
        links: dict[str, str] = {}
        records: dict[str, object] = {}
        with open_store(settings) as store:
            for round_number in range(14):
                if round_number < 10:
                    for _ in range(rng.randrange(1, 3)):
                        number = len(records)
                        thread = "t1" if number < 2 else rng.choice(("t1", "t2"))
                        record = replace(
                            RECORD,
                            message_id=f"personal/m{number}",
                            thread_id=f"personal/{thread}",
                            link=f"https://mail.google.com/mail/#all/m{number}",
                        )
                        records[record.message_id] = record
                        store.add(record)
                        store.save_triage("gmail", record.message_id, NOTIFY)
                    store.queue_notified()
                for message_id, record in records.items():
                    post = store.post("gmail", message_id)
                    if post is None or store.answer(post.item_id) is not None:
                        continue
                    if post.card is None:
                        target = store.approved_in_thread("gmail", record.thread_id)
                        if target is None:
                            store.choose_card(post.item_id, "first")
                        else:
                            store.choose_card(post.item_id, "followup", follows=target.item_id)
                        post = store.post("gmail", message_id)
                    # Round 0's first email is approved and its task fails to send, so the
                    # second, a follow-up linked in round 1, has to wait for it.
                    forced = round_number == 0 and message_id == "personal/m0"
                    forced_link = round_number == 1 and message_id == "personal/m1"
                    if message_id == "personal/m1" and round_number == 0:
                        continue
                    if not (forced or forced_link) and (round_number >= 10 or rng.random() < 0.5):
                        continue
                    key = f"gmail:{message_id}"
                    if post.card == "followup":
                        kind = rng.choice(("link", "link", "new", "notask"))
                        kind = "link" if forced_link else kind
                    else:
                        kind = "approve" if forced else rng.choice(("approve", "drop", "notask"))
                    if kind == "notask":
                        store.record_answer(post.item_id, "notask", "")
                    elif kind == "link":
                        store.record_answer(post.item_id, "link", "")
                        links[key] = f"gmail:{store.post_by_item(post.follows).message_id}"
                        target_task = store.task(post.follows)
                        reached["waited"] += target_task is None or target_task.task_id is None
                    else:
                        title = f"Task {message_id}"
                        store.record_answer(post.item_id, "yes", title)
                        outcome = "drop" if kind == "drop" else "nodeadline"
                        store.record_approval(
                            post.item_id, outcome, "" if outcome == "drop" else title, None
                        )
                        if outcome == "nodeadline":
                            tasks.add(key)
                            reached["new-task"] += kind == "new"
                watched.noisy = 0 < round_number < 11
                if round_number == 0:
                    watched.fake.failures.append(httpx.Response(503))
                elif round_number < 11:
                    picks = [rng.choice(choices) for _ in range(rng.randrange(3))]
                    watched.fake.failures.extend(picks)
                store.clear_expired_text()
                send_tasks(store, settings, http)
                watched.fake.failures.clear()
                MOMENT[0] += timedelta(hours=3)
            fake = watched.fake
            if set(fake.tasks) != tasks:
                return f"trial {trial}: tasks {sorted(fake.tasks)}, wanted {sorted(tasks)}"
            if set(fake.links) != set(links):
                return f"trial {trial}: links {sorted(fake.links)}, wanted {sorted(links)}"
            for key, target_key in links.items():
                message_id = key.removeprefix("gmail:")
                _, task_id, body = fake.links[key]
                if task_id != fake.tasks[target_key][0]:
                    return f"trial {trial}: {key} went to {task_id}"
                want = link_body(message_id, records[message_id].link)
                sent = [
                    json.loads(r.content)
                    for r in fake.requests
                    if r.url.path.endswith("/links") and r.headers.get("idempotency-key") == key
                ]
                if body != want or any(found != want for found in sent):
                    return f"trial {trial}: {key} sent another body"
                reached["links"] += 1
                reached["retried"] += len(sent) > 1
                link = store.link(store.post("gmail", message_id).item_id)
                reached["after-clear"] += link.sent_at - START >= timedelta(hours=24)
            refused = [path for path, status in watched.statuses if status == 404]
            if refused:
                return f"trial {trial}: the app refused {refused[0]}"
    if min(reached.values()) < 10:
        return f"too few cases: {reached}"
    return True


check("each follow-up added to a task makes one link on it", each_follow_up_makes_one_link)
print(f"FAILURES {FAILURES}")
