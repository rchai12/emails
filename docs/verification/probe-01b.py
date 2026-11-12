"""Probe for phase 1b. Run from the repository root: .venv/bin/python docs/verification/probe-01b.py

It drives `GmailClient` against `tests.fakes.FakeGmail` with a fake keychain and a fake clock,
so nothing leaves the machine and the real Keychain is never read. Each check prints `ok` or
`FAIL`; the last line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01b-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from tests.fakes import FakeGmail, FakeKeychain  # noqa: E402

KEYCHAIN = FakeKeychain()
keyring.core._keyring_backend = KEYCHAIN
SECRETS = {"client-id": "cid-ZQX1", "client-secret": "csec-ZQX2", "refresh-token": "rtok-ZQX3"}
for key, value in SECRETS.items():
    KEYCHAIN.secrets[("mailroom", f"gmail.personal.{key}")] = value

FAILURES = 0


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


# Self-check of the probe's own oracle helpers. A stop here is the probe's fault.
def inbox_history(fake: FakeGmail, start: int) -> list[str]:
    """The ids history(start) must return, from the fake's records: first appearance wins."""
    found: list[str] = []
    for record in fake.history:
        if int(record["id"]) <= start or "INBOX" not in record["_labels"]:
            continue
        for entry in record.get("messagesAdded", []):
            found.append(entry["message"]["id"])
        for entry in record.get("labelsAdded", []):
            if "INBOX" in entry["labelIds"]:
                found.append(entry["message"]["id"])
    return list(dict.fromkeys(found))


def inbox_since(fake: FakeGmail, after: datetime) -> list[str]:
    cutoff = int(after.timestamp()) * 1000
    rows = [
        (int(message["internalDate"]), message_id)
        for message_id, message in fake.messages.items()
        if "INBOX" in message["labelIds"]
        and not {"SPAM", "TRASH"} & set(message["labelIds"])
        and int(message["internalDate"]) > cutoff
    ]
    return [message_id for _, message_id in sorted(rows, reverse=True)]


_sample = FakeGmail()
_sample.add_message("a", b"x")
_sample.add_message("b", b"x", labels=("SENT",))
_sample.add_labels("b", "INBOX")
_sample.add_labels("a", "STARRED")
assert inbox_history(_sample, 1000) == ["a", "b"]
assert inbox_history(_sample, 1001) == ["b"]
assert inbox_since(_sample, datetime(2026, 1, 1, tzinfo=UTC)) == ["b", "a"]
print("oracle self-check: ok")

from mailroom import clock  # noqa: E402

try:
    from mailroom import gmail
except Exception as error:
    print(f"import mailroom.gmail: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)

NOW = [datetime(2026, 11, 11, 9, 0, tzinfo=UTC)]
clock.now = lambda: NOW[0]
rng = random.Random(11)
ALLOWED = {
    ("POST", "oauth2.googleapis.com", "/token"),
    ("GET", "gmail.googleapis.com", "/gmail/v1/users/me/profile"),
    ("GET", "gmail.googleapis.com", "/gmail/v1/users/me/history"),
    ("GET", "gmail.googleapis.com", "/gmail/v1/users/me/messages"),
}


def new_fake() -> FakeGmail:
    """A fake Gmail that accepts the probe's keychain secrets."""
    fake = FakeGmail()
    fake.client_id, fake.client_secret = SECRETS["client-id"], SECRETS["client-secret"]
    fake.refresh_token = SECRETS["refresh-token"]
    return fake


def client_for(fake: FakeGmail) -> "gmail.GmailClient":
    http = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return gmail.GmailClient("personal", http)


def random_mailbox(fake: FakeGmail, count: int) -> None:
    for number in range(count):
        labels = rng.choice([("INBOX", "UNREAD"), ("INBOX",), ("SENT",), ("SPAM",), ("TRASH",)])
        fake.add_message(
            f"m{number}",
            f"Subject: ZQXBODY{number}\r\n\r\nbody\r\n".encode(),
            thread_id=f"t{number % 4}",
            labels=labels,
            internal_ms=1_794_000_000_000 + rng.randrange(400_000_000),
        )
        if rng.random() < 0.3:
            target = f"m{rng.randrange(number + 1)}"
            fake.add_labels(target, rng.choice(["INBOX", "STARRED", "IMPORTANT"]))


def history_matches() -> object:
    for _ in range(60):
        fake = new_fake()
        random_mailbox(fake, rng.randrange(0, 25))
        fake.page_size = rng.choice([1, 2, 3, 7, None])
        start = 1000 + rng.randrange(0, 10)
        got = client_for(fake).history(str(start))
        want = inbox_history(fake, start)
        if [ref.id for ref in got.added] != want or got.history_id != str(fake.history_id):
            return f"start {start}: got {[ref.id for ref in got.added]}, want {want}"
        threads = {ref.id: ref.thread_id for ref in got.added}
        if any(threads[key] != fake.messages[key]["threadId"] for key in threads):
            return "a thread id does not match the message"
    return True


def list_matches() -> object:
    for _ in range(60):
        fake = new_fake()
        random_mailbox(fake, rng.randrange(0, 25))
        fake.page_size = rng.choice([1, 2, 5, None])
        after = datetime.fromtimestamp(1_794_000_000 + rng.randrange(400_000), UTC)
        after += timedelta(microseconds=rng.randrange(1_000_000))
        got = [ref.id for ref in client_for(fake).list_inbox(after)]
        if got != inbox_since(fake, after):
            return f"after {after}: got {got}, want {inbox_since(fake, after)}"
    return True


def fetch_round_trips() -> object:
    for size in [0, 1, 2, 3, 255, 256, 4097]:
        raw = bytes(rng.randrange(256) for _ in range(size))
        fake = new_fake()
        fake.add_message("m1", raw, internal_ms=1_794_128_400_999)
        message = client_for(fake).fetch("m1")
        if message.raw != raw:
            return f"size {size}: raw differs"
        if message.internal_date != datetime(2026, 11, 8, 9, 0, 0, 999_000, tzinfo=UTC):
            return f"internal_date {message.internal_date!r}"
    return True


def tokens_follow_the_clock() -> object:
    fake = new_fake()
    fake.expires_in = rng.choice([120, 600, 3599])
    client = client_for(fake)
    NOW[0] = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
    expiry = None
    refreshes = 0
    for _ in range(200):
        NOW[0] += timedelta(seconds=rng.choice([0, 1, 30, 59, 60, 61, 300]))
        if expiry is None or NOW[0] >= expiry:
            refreshes += 1
            expiry = NOW[0] + timedelta(seconds=fake.expires_in - 60)
        client.profile()
    if len(fake.issued) != refreshes:
        return f"{len(fake.issued)} token requests, want {refreshes}"
    return True


FAULTS = [
    lambda: httpx.Response(500, text="ZQXBODY leak"),
    lambda: httpx.Response(503),
    lambda: httpx.Response(429),
    lambda: httpx.Response(401, json={"error": {"code": 401}}),
    lambda: httpx.Response(200, text="ZQXBODY not json"),
    lambda: httpx.Response(200, json={"unexpected": "ZQXBODY"}),
    lambda: httpx.ConnectError("ZQXBODY refused"),
    lambda: httpx.ReadTimeout("ZQXBODY slow"),
]


def faults_are_contained() -> object:
    fake = new_fake()
    random_mailbox(fake, 10)
    client = client_for(fake)
    for _ in range(400):
        if rng.random() < 0.4:
            fake.failures.append(rng.choice(FAULTS)())
        call = rng.choice(["profile", "history", "list", "fetch"])
        try:
            if call == "profile":
                client.profile()
            elif call == "history":
                client.history("1000")
            elif call == "list":
                client.list_inbox(datetime(2026, 11, 1, tzinfo=UTC))
            else:
                client.fetch(f"m{rng.randrange(10)}")
        except gmail.GmailError as error:
            text = str(error)
            if "ZQX" in text or "access-" in text:
                return f"{call}: error text leaks: {text!r}"
            if not text.startswith(("gmail unavailable: personal", "gmail sign-in needed")):
                if text != "gmail history expired: personal":
                    return f"{call}: unexpected error text {text!r}"
        fake.failures.clear()
    for request in fake.requests:
        path = request.url.path
        key = (request.method, request.url.host, path)
        if key not in ALLOWED and not (
            request.method == "GET" and path.startswith("/gmail/v1/users/me/messages/")
        ):
            return f"request outside the allowed set: {key}"
        if request.url.host == "gmail.googleapis.com" and any(
            value in str(request.url) for value in SECRETS.values()
        ):
            return "a secret appears in an API URL"
        if request.url.host == "oauth2.googleapis.com" and "authorization" in request.headers:
            return "an access token was sent to the token endpoint"
    return True


check("history returns exactly the inbox additions, once each, in order", history_matches)
check("list_inbox returns inbox mail after the moment, newest first", list_matches)
check("fetch returns the exact bytes and time", fetch_round_trips)
check("a token is refreshed exactly when it is a minute from expiry", tokens_follow_the_clock)
check(
    "faults raise GmailError without leaking text, and only read calls go out", faults_are_contained
)
print(f"FAILURES {FAILURES}")
