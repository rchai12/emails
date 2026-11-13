"""Probe for phase 1l. Run from the repository root: .venv/bin/python docs/verification/probe-01l.py

It runs `run_round` for 40 rounds while mail keeps arriving in two Gmail accounts, and breaks
parts at random: a revoked or missing Gmail token, Gmail answering 500, the model refusing
connections, and Discord answering 429, 503 or losing its reply. Then everything is repaired
for a few rounds. It checks that every delivered email ends triaged and posted exactly once.
Each part's status line changes only when its state does, and says "ok" at the end. No line
holds email text or a token. The database is in a temporary folder. Each check prints `ok` or
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
TMP = Path(tempfile.mkdtemp(prefix="probe01l-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
for name, value in (
    ("MAILROOM_GMAIL_ACCOUNTS", "personal,work"),
    ("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b"),
    ("MAILROOM_TIME_ZONE", "America/New_York"),
    ("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111"),
    ("MAILROOM_DISCORD_OWNER_ID", "444444444444444444"),
):
    os.environ[name] = value

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from tests.fakes import FakeDiscord, FakeGmail, FakeKeychain, FakeOllama  # noqa: E402

FAILURES = 0
rng = random.Random(20)
ACCOUNTS = ("personal", "work")
SECRET_MARK = "ZQX-SECRET"
TEXT_MARK = "ZQX-TEXT"
GOOD = {
    "summary": "Someone asks for a reply.",
    "actionable": True,
    "urgent": False,
    "title": "Reply",
    "has_deadline": False,
    "deadline_date": "",
    "deadline_time": "",
    "deadline_explicit": False,
    "deadline_quote": "",
    "suspicious": False,
    "suspicion_reason": "",
    "confidence": "high",
}


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


# The oracle: status lines, read back per part, never repeat; the last one per part is "ok".
def line_problem(lines: list[str]) -> str:
    last: dict[str, str] = {}
    for line in lines:
        part, _, state = line.partition(": ")
        if last.get(part) == state:
            return f"{part} repeated {state!r}"
        last[part] = state
    bad = {part: state for part, state in last.items() if state != "ok"}
    return f"not ok at the end: {bad}" if bad else ""


assert line_problem(["a: ok", "a: down", "a: ok"]) == ""
assert line_problem(["a: ok", "a: ok"]) == "a repeated 'ok'"
assert line_problem(["a: ok", "b: down"]) == "not ok at the end: {'b': 'down'}"
print("oracle self-check: ok")

try:
    from mailroom.config import get_settings
    from mailroom.gmail import GmailClient
    from mailroom.service import Health, run_round
    from mailroom.store import open_store
except Exception as error:
    print(f"import: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.moment


def mail(number: int, moment: datetime) -> tuple[str, bytes, int]:
    raw = (
        f"From: Sender <s{number}@example.test>\r\nSubject: {TEXT_MARK} subject {number}\r\n"
        f"\r\n{TEXT_MARK} body {number}\r\n"
    ).encode()
    return f"m{number}", raw, round(moment.timestamp() * 1000)


def rounds_converge() -> object:
    now = Clock()
    clock.now = now
    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    settings = get_settings()
    for trial in range(8):
        gmail = {account: FakeGmail() for account in ACCOUNTS}
        model, discord = FakeOllama(), FakeDiscord()
        lines: list[str] = []
        health = Health(lines.append)
        delivered: set[str] = set()
        number = 0
        with open_store(settings) as store:
            for round_number in range(46):
                breaking = round_number < 40
                now.moment += timedelta(seconds=60)
                for account in ACCOUNTS:
                    secrets = {
                        "client-id": "client-id-1",
                        "client-secret": "client-secret-1",
                        "refresh-token": "refresh-token-1",
                    }
                    if breaking and rng.random() < 0.15:
                        secrets["refresh-token"] = rng.choice([f"{SECRET_MARK}-revoked", None])
                    for name, value in secrets.items():
                        key = ("mailroom", f"gmail.{account}.{name}")
                        if value is None:
                            keychain.secrets.pop(key, None)
                        else:
                            keychain.secrets[key] = value
                    for _ in range(rng.randrange(0, 3)):
                        number += 1
                        message_id, raw, ms = mail(number, now.moment - timedelta(seconds=30))
                        gmail[account].add_message(f"{account}-{message_id}", raw, internal_ms=ms)
                        delivered.add(f"{account}-{message_id}")
                keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
                model.replies[:] = [
                    httpx.ConnectError("refused") if breaking and rng.random() < 0.1 else GOOD
                    for _ in range(400)
                ]
                discord.failures[:] = (
                    [
                        rng.choice(
                            [
                                httpx.Response(429, json={"retry_after": 1.0}),
                                httpx.Response(503),
                                "lost-reply",
                            ]
                        )
                    ]
                    if breaking and rng.random() < 0.2
                    else []
                )

                def gmail_handler(fake: FakeGmail, breaking: bool = breaking):
                    def handle(request: httpx.Request) -> httpx.Response:
                        if breaking and rng.random() < 0.05:
                            return httpx.Response(500, json={"error": {"code": 500}})
                        return fake.handler(request)

                    return handle

                clients = [
                    GmailClient(
                        account,
                        httpx.Client(transport=httpx.MockTransport(gmail_handler(gmail[account]))),
                    )
                    for account in ACCOUNTS
                ]
                run_round(
                    store,
                    settings,
                    clients,
                    httpx.Client(transport=httpx.MockTransport(model.handler)),
                    httpx.Client(transport=httpx.MockTransport(discord.handler)),
                    health,
                )
            if store.untriaged():
                return f"trial {trial}: {len(store.untriaged())} never triaged"
            if store.pending_posts():
                return f"trial {trial}: {len(store.pending_posts())} never posted"
            for message_id in delivered:
                if store.post("gmail", message_id) is None:
                    return f"trial {trial}: {message_id} was never queued"
            if len({m["nonce"] for m in discord.messages}) != len(discord.messages):
                return f"trial {trial}: an email was posted twice"
            if len(discord.messages) != len(delivered):
                return f"trial {trial}: {len(discord.messages)} posts for {len(delivered)} emails"
        problem = line_problem(lines)
        if problem:
            return f"trial {trial}: {problem}"
        for line in lines:
            if TEXT_MARK in line or SECRET_MARK in line or discord.token in line:
                return f"trial {trial}: a status line holds email text or a secret: {line!r}"
        (TMP / "data" / "mailroom.sqlite3").unlink()
    return True


check(
    "every email is posted once despite failures, and the status lines are clean", rounds_converge
)
print(f"FAILURES {FAILURES}")
