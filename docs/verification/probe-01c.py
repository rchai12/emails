"""Probe for phase 1c. Run from the repository root: .venv/bin/python docs/verification/probe-01c.py

It runs `sync_gmail` many times against `tests.fakes.FakeGmail` while changing the fake mailbox
between runs (new mail, archiving, deleting, moving out of spam, outages, expired bookmarks), and
compares what was stored with an oracle built from the probe's own rules. A fake keychain, a fake
clock and a temporary data folder are used, so nothing leaves the machine. Each check prints `ok`
or `FAIL`; the last line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01c-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from tests.fakes import FakeGmail, FakeKeychain  # noqa: E402

KEYCHAIN = FakeKeychain()
keyring.core._keyring_backend = KEYCHAIN
for key, value in {
    "client-id": "client-id-1",
    "client-secret": "client-secret-1",
    "refresh-token": "refresh-token-1",
}.items():
    KEYCHAIN.secrets[("mailroom", f"gmail.personal.{key}")] = value

FAILURES = 0
DAY = timedelta(days=1)


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


# The oracle: which messages a sync must store, from the fake's tables and the probe's rules.
def in_inbox(fake: FakeGmail, message_id: str) -> bool:
    message = fake.messages.get(message_id)
    if message is None:
        return False
    labels = set(message["labelIds"])
    return "INBOX" in labels and not {"SPAM", "TRASH"} & labels


def added_since(fake: FakeGmail, start: int) -> set[str]:
    found: set[str] = set()
    for record in fake.history:
        if int(record["id"]) <= start or "INBOX" not in record["_labels"]:
            continue
        for entry in record.get("messagesAdded", []):
            found.add(entry["message"]["id"])
        for entry in record.get("labelsAdded", []):
            if "INBOX" in entry["labelIds"]:
                found.add(entry["message"]["id"])
    return found


def received_after(fake: FakeGmail, moment: datetime) -> set[str]:
    cutoff = int(moment.timestamp()) * 1000
    return {key for key, value in fake.messages.items() if int(value["internalDate"]) > cutoff}


def expected(fake: FakeGmail, state, expired: bool, now: datetime, stored: set[str]):
    """(kind, ids to store, offline_since, gap) for one sync."""
    if state is None:
        kind, candidates, since, gap = "first", received_after(fake, now - 3 * DAY), None, False
    elif not expired:
        kind, candidates, since, gap = (
            "history",
            added_since(fake, int(state.bookmark)),
            None,
            False,
        )
    else:
        after = max(state.synced_at - timedelta(hours=1), now - 14 * DAY)
        since, gap = state.synced_at, now - state.synced_at > 14 * DAY
        kind, candidates = "catch_up", received_after(fake, after)
    return kind, {key for key in candidates if in_inbox(fake, key)} - stored, since, gap


_sample = FakeGmail()
_sample.add_message("a", b"x", internal_ms=1_794_000_000_000)
_sample.add_message("b", b"x", labels=("SPAM",), internal_ms=1_794_000_000_000)
_sample.messages["b"]["labelIds"] = []
_sample.add_labels("b", "INBOX")
_sample.add_message("c", b"x", labels=("INBOX", "TRASH"))
_sample.add_labels("a", "STARRED")
assert added_since(_sample, 1000) == {"a", "b", "c"}
assert added_since(_sample, 1001) == {"b", "c"}
assert received_after(_sample, datetime.fromtimestamp(1_793_999_999, UTC)) == {"a", "b"}
assert received_after(_sample, datetime.fromtimestamp(1_794_000_000, UTC)) == set()
assert not in_inbox(_sample, "c") and in_inbox(_sample, "b") and not in_inbox(_sample, "z")
print("oracle self-check: ok")

from mailroom import clock  # noqa: E402

try:
    from mailroom.gmail import GmailClient, GmailError
    from mailroom.gmail_sync import sync_gmail
    from mailroom.store import Store
except Exception as error:
    print(f"import: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)

NOW = [datetime(2026, 11, 11, 9, 0, tzinfo=UTC)]
clock.now = lambda: NOW[0]
rng = random.Random(12)
STORES = iter(range(10_000))


def new_store() -> Store:
    return Store(TMP / f"store-{next(STORES)}.sqlite3")


def client_for(handler) -> GmailClient:
    return GmailClient("personal", httpx.Client(transport=httpx.MockTransport(handler)))


def stored_ids(store: Store, known: set[str]) -> set[str]:
    return {key for key in known if store.get("gmail", key) is not None}


def change_mailbox(fake: FakeGmail, serial: list[int]) -> None:
    """One to four random changes to the mailbox, as a person or Gmail would make them."""
    for _ in range(rng.randrange(1, 5)):
        action = rng.choice(["mail", "mail", "mail", "archive", "delete", "unspam", "relabel"])
        ids = list(fake.messages)
        if action == "mail" or not ids:
            serial[0] += 1
            age = rng.choice([timedelta(minutes=rng.randrange(120)), DAY * rng.uniform(0, 20)])
            labels = rng.choice([("INBOX", "UNREAD"), ("INBOX",), ("SENT",), ("SPAM",)])
            fake.add_message(
                f"m{serial[0]}",
                f"Subject: n{serial[0]}\r\n\r\nbody\r\n".encode(),
                thread_id=f"t{serial[0] % 5}",
                labels=labels,
                internal_ms=int((NOW[0] - age).timestamp() * 1000),
            )
        elif action == "archive":
            message = fake.messages[rng.choice(ids)]
            message["labelIds"] = [label for label in message["labelIds"] if label != "INBOX"]
        elif action == "delete":
            del fake.messages[rng.choice(ids)]
        elif action == "unspam":
            key = rng.choice(ids)
            fake.messages[key]["labelIds"] = []
            fake.add_labels(key, "INBOX")
        else:
            fake.add_labels(rng.choice(ids), rng.choice(["INBOX", "STARRED"]))


def every_sync_stores_what_the_oracle_says() -> object:
    for trial in range(40):
        fake, store, serial = FakeGmail(), new_store(), [0]
        NOW[0] = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
        known: set[str] = set()
        for step in range(12):
            change_mailbox(fake, serial)
            known |= set(fake.messages)
            NOW[0] += rng.choice([timedelta(minutes=1), timedelta(hours=5), DAY * 3, DAY * 16])
            state = store.sync_state("gmail", "personal")
            expired = state is not None and rng.random() < 0.25
            fake.oldest_history_id = fake.history_id + 1 if expired else 0
            before = stored_ids(store, known)
            kind, want, since, gap = expected(fake, state, expired, NOW[0], before)
            start = len(fake.requests)
            result = sync_gmail(client_for(fake.handler), store)
            where = f"trial {trial} step {step} ({kind})"
            if (result.kind, result.offline_since, result.gap) != (kind, since, gap):
                return f"{where}: got {result.kind}, {result.offline_since}, {result.gap}"
            if len(result.stored) != len(set(result.stored)) or set(result.stored) != want:
                return f"{where}: stored {sorted(result.stored)}, want {sorted(want)}"
            if stored_ids(store, known) != before | want:
                return f"{where}: the database does not hold what the result says"
            saved = store.sync_state("gmail", "personal")
            if (saved.bookmark, saved.synced_at) != (str(fake.history_id), NOW[0]):
                return f"{where}: saved {saved}, want bookmark {fake.history_id} at {NOW[0]}"
            for request in fake.requests[start:]:
                key = request.url.path.removeprefix("/gmail/v1/users/me/messages/")
                if key != request.url.path and key in before:
                    return f"{where}: fetched {key}, which was already stored"
    return True


FAULTS = [
    lambda: httpx.Response(500),
    lambda: httpx.Response(503),
    lambda: httpx.Response(429),
    lambda: httpx.Response(200, text="not json"),
    lambda: httpx.ConnectError("refused"),
    lambda: httpx.ReadTimeout("slow"),
]


def a_failure_keeps_the_bookmark_and_a_retry_catches_up() -> object:
    for trial in range(80):
        fake, store, serial = FakeGmail(), new_store(), [0]
        NOW[0] = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
        for _ in range(rng.randrange(0, 2)):
            change_mailbox(fake, serial)
            NOW[0] += timedelta(minutes=2)
            sync_gmail(client_for(fake.handler), store)
        change_mailbox(fake, serial)
        known = set(fake.messages)
        state = store.sync_state("gmail", "personal")
        before = stored_ids(store, known)
        _, want, _, _ = expected(fake, state, False, NOW[0], before)
        api_calls = [0]
        fail_at = rng.randrange(1, 3 + len(want))

        def failing(request: httpx.Request, fail_at=fail_at, api_calls=api_calls, fake=fake):
            if request.url.host == "gmail.googleapis.com":
                api_calls[0] += 1
                if api_calls[0] == fail_at:
                    fault = rng.choice(FAULTS)()
                    if isinstance(fault, Exception):
                        raise fault
                    return fault
            return fake.handler(request)

        try:
            sync_gmail(client_for(failing), store)
            failed = False
        except GmailError:
            failed = True
        if failed and store.sync_state("gmail", "personal") != state:
            return f"trial {trial}: a failed sync changed the saved state"
        if not stored_ids(store, known) <= before | want:
            return f"trial {trial}: a failed sync stored a message it should not"
        sync_gmail(client_for(fake.handler), store)
        if stored_ids(store, known) != before | want:
            return f"trial {trial}: after a retry the database differs from the oracle"
    return True


def only_read_calls_go_out() -> object:
    fake, store, serial = FakeGmail(), new_store(), [0]
    for _ in range(30):
        change_mailbox(fake, serial)
        NOW[0] += timedelta(minutes=2)
        fake.oldest_history_id = fake.history_id + 1 if rng.random() < 0.2 else 0
        sync_gmail(client_for(fake.handler), store)
    for request in fake.requests:
        key = (request.method, request.url.host)
        if key not in {("POST", "oauth2.googleapis.com"), ("GET", "gmail.googleapis.com")}:
            return f"request outside the allowed set: {key} {request.url.path}"
    return True


check("every sync stores exactly the new inbox mail, once", every_sync_stores_what_the_oracle_says)
check(
    "a failed sync keeps the bookmark, and a retry stores the rest",
    a_failure_keeps_the_bookmark_and_a_retry_catches_up,
)
check("only token posts and read calls reach Google", only_read_calls_go_out)
print(f"FAILURES {FAILURES}")
