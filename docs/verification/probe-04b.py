"""Probe for phase 4b. Run from the repository root: .venv/bin/python docs/verification/probe-04b.py

Each trial runs Outlook sync for many rounds against FakeGraph while, between rounds, mail
arrives in the inbox or in junk, moves between them, or is deleted, the delta links expire, and
some rounds fail at a random request. The probe's own model of the mailbox says:
- nothing that was never in the inbox is ever stored;
- no message is downloaded successfully twice;
- a failed round leaves the bookmark as it was;
- after a final clean round, every message still in the inbox (and not deleted) is stored, except
  one moved into the inbox and then caught by an expired link before it was stored: a catch-up
  lists mail by when it was received, so an old message moved in can fall outside its window, as
  the design says for Gmail too.
Fakes only; everything lives in a temporary folder. The check prints `ok` or `FAIL`; the last
line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe04b-"))
os.environ["HOME"] = str(TMP / "home")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from mailroom.config import get_settings  # noqa: E402
from tests.fakes import FakeGraph, FakeKeychain  # noqa: E402

FAILURES = 0
rng = random.Random(42)
START = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
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


def stamp(moment: datetime) -> str:
    """Graph's receivedDateTime, zero-padded so the fake's text comparison orders it."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


assert stamp(datetime(2026, 11, 9, 8, 5, tzinfo=UTC)) == "2026-11-09T08:05:00Z"
assert stamp(datetime(2026, 11, 9, 8, 5, tzinfo=UTC)) < stamp(datetime(2026, 11, 10, tzinfo=UTC))
print("oracle self-check: ok")


class Watched:
    """FakeGraph that fails the round's chosen request and counts each successful download."""

    def __init__(self, graph: FakeGraph) -> None:
        self.graph = graph
        self.fail_at = 0
        self.count = 0
        self.downloads: Counter[str] = Counter()

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "graph.microsoft.com":
            self.count += 1
            if self.count == self.fail_at:
                return httpx.Response(503)
        response = self.graph.handler(request)
        if request.url.path.endswith("/$value") and response.status_code == 200:
            self.downloads[request.url.path.split("/")[-2]] += 1
        return response


def raw(number: int) -> bytes:
    return f"From: S{number} <s{number}@example.test>\r\nSubject: N{number}\r\n\r\nB.\r\n".encode()


def sync_follows_the_mailbox() -> object:
    from mailroom.outlook import OutlookClient, OutlookError
    from mailroom.outlook_sync import sync_outlook
    from mailroom.store import open_store

    clock.now = lambda: MOMENT[0]
    reached = {"expired": 0, "failed": 0, "moved-in": 0, "deleted": 0, "moved-out": 0}
    for trial in range(120):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"trial{trial}")
        MOMENT[0] = START
        keychain = FakeKeychain()
        keyring.core._keyring_backend = keychain
        graph = FakeGraph()
        keychain.secrets[("mailroom", "outlook.live.client-id")] = graph.client_id
        keychain.secrets[("mailroom", "outlook.live.refresh-token")] = graph.refresh_token
        watched = Watched(graph)
        ever_in_inbox: set[str] = set()
        where: dict[str, str] = {}
        deleted: set[str] = set()
        moved_in: set[str] = set()
        excused: set[str] = set()
        with open_store(get_settings()) as store:
            for round_number in range(16):
                for _ in range(rng.randrange(4)):
                    action = rng.choice(("inbox", "inbox", "junk", "move", "delete"))
                    if action in ("inbox", "junk") or not where:
                        number = len(where)
                        folder = "junkemail" if action == "junk" else "inbox"
                        message_id = f"AAMk{number}="
                        graph.add_message(
                            message_id, raw(number), folder=folder, received=stamp(MOMENT[0])
                        )
                        where[message_id] = folder
                        if folder == "inbox":
                            ever_in_inbox.add(message_id)
                        continue
                    message_id = rng.choice(sorted(where))
                    if message_id in deleted:
                        continue
                    if action == "delete":
                        graph.delete(message_id)
                        deleted.add(message_id)
                        reached["deleted"] += 1
                        continue
                    target = "inbox" if where[message_id] == "junkemail" else "junkemail"
                    graph.move(message_id, target)
                    where[message_id] = target
                    if target == "inbox":
                        ever_in_inbox.add(message_id)
                        moved_in.add(message_id)
                        reached["moved-in"] += 1
                    else:
                        reached["moved-out"] += 1
                if round_number and rng.random() < 0.15:
                    graph.expire_deltas()
                    reached["expired"] += 1
                    excused |= {
                        message_id
                        for message_id in moved_in
                        if store.get("outlook", f"live/{message_id}") is None
                    }
                last = round_number == 15
                watched.count = 0
                watched.fail_at = 0 if last or rng.random() < 0.7 else rng.randrange(1, 8)
                before = store.sync_state("outlook", "live")
                http = httpx.Client(transport=httpx.MockTransport(watched.handler))
                try:
                    sync_outlook(OutlookClient("live", http), store)
                except OutlookError:
                    reached["failed"] += 1
                    if store.sync_state("outlook", "live") != before:
                        return f"trial {trial}: a failed round moved the bookmark"
                    if last:
                        return f"trial {trial}: the final clean round failed"
                MOMENT[0] += timedelta(minutes=rng.choice((1, 1, 5, 60, 60 * 24 * 2)))
            for message_id in where:
                stored = store.get("outlook", f"live/{message_id}") is not None
                if stored and message_id not in ever_in_inbox:
                    return f"trial {trial}: {message_id} was stored but never in the inbox"
                wanted = where[message_id] == "inbox" and message_id not in deleted
                if wanted and not stored and message_id not in excused:
                    return f"trial {trial}: {message_id} is in the inbox but not stored"
            twice = [message_id for message_id, count in watched.downloads.items() if count > 1]
            if twice:
                return f"trial {trial}: downloaded twice: {twice[0]}"
    if min(reached.values()) < 10:
        return f"too few cases: {reached}"
    return True


check("sync stores what reaches the inbox, once, and never loses it", sync_follows_the_mailbox)
print(f"FAILURES {FAILURES}")
