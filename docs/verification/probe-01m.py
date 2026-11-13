"""Probe for phase 1m. Run from the repository root: .venv/bin/python docs/verification/probe-01m.py

It runs `run_round` a minute apart for 60 rounds per trial. Mail arrives in two Gmail accounts
while their tokens are revoked and restored at random, the model goes down for random stretches,
and Discord fails at random (429, 503, lost replies). An oracle, built from the schedule alone,
says which alerts should exist and in what order:
  - a sign-in alert, pinging the owner, as soon as an account's token fails, and one "works
    again" when it next syncs
  - a model alert once triage has failed for 15 minutes, and one "back" when triage next works
After a few clean rounds, the alert messages on Discord must be exactly that list, each once,
with pings only on the sign-in alerts and no email text. The database is in a temporary folder.
Each check prints `ok` or `FAIL`; the last line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01m-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
OWNER = "444444444444444444"
for name, value in (
    ("MAILROOM_GMAIL_ACCOUNTS", "personal,work"),
    ("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b"),
    ("MAILROOM_TIME_ZONE", "America/New_York"),
    ("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111"),
    ("MAILROOM_DISCORD_OWNER_ID", OWNER),
):
    os.environ[name] = value

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from tests.fakes import FakeDiscord, FakeGmail, FakeKeychain, FakeOllama  # noqa: E402

FAILURES = 0
rng = random.Random(21)
ACCOUNTS = ("personal", "work")
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
SIGN_IN = "<@" + OWNER + "> Gmail sign-in needed for {account}. Run: mailroom gmail-login {account}"
FIXED = "Gmail {account} works again."
MODEL_DOWN = (
    "The local model has been unreachable for 15 minutes. New mail is waiting; nothing is lost."
)
MODEL_BACK = "The local model is back. Waiting mail is being triaged."


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


# The oracle: from each round's (revoked accounts, arrivals, model down), the alerts in order.
def expected(schedule: list[tuple[set[str], dict[str, int], bool]]) -> list[str]:
    alerts: list[str] = []
    auth_open = {account: False for account in ACCOUNTS}
    unsynced = {account: 0 for account in ACCOUNTS}
    untriaged = 0
    model_since: int | None = None
    model_alerted = False
    for minute, (revoked, arrivals, down) in enumerate(schedule):
        for account in ACCOUNTS:
            unsynced[account] += arrivals.get(account, 0)
            if account in revoked:
                if not auth_open[account]:
                    auth_open[account] = True
                    alerts.append(SIGN_IN.format(account=account))
            else:
                if auth_open[account]:
                    auth_open[account] = False
                    alerts.append(FIXED.format(account=account))
                untriaged += unsynced[account]
                unsynced[account] = 0
        if untriaged == 0:
            continue
        if down:
            if model_since is None:
                model_since = minute
            if not model_alerted and minute - model_since >= 15:
                model_alerted = True
                alerts.append(MODEL_DOWN)
        else:
            untriaged = 0
            if model_since is not None and model_alerted:
                alerts.append(MODEL_BACK)
            model_since, model_alerted = None, False
    return alerts


assert expected([({"work"}, {}, False), (set(), {}, False)]) == [
    SIGN_IN.format(account="work"),
    FIXED.format(account="work"),
]
assert expected([(set(), {"personal": 1}, True)] * 15) == []
assert expected([(set(), {"personal": 1}, True)] * 16 + [(set(), {}, False)]) == [
    MODEL_DOWN,
    MODEL_BACK,
]
assert expected([(set(), {}, True)] * 30) == []
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
        self.moment = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.moment


def schedule_for_trial() -> list[tuple[set[str], dict[str, int], bool]]:
    rounds: list[tuple[set[str], dict[str, int], bool]] = []
    revoked: set[str] = set()
    down = False
    for _ in range(60):
        for account in ACCOUNTS:
            if rng.random() < 0.08:
                revoked ^= {account}
        if rng.random() < (0.05 if not down else 0.08):
            down = not down
        arrivals = {a: 1 for a in ACCOUNTS if rng.random() < 0.4}
        rounds.append((set(revoked), arrivals, down))
    rounds += [(set(), {}, False)] * 4
    return rounds


def alerts_follow_the_schedule() -> object:
    now = Clock()
    clock.now = now
    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    settings = get_settings()
    for trial in range(12):
        gmail = {account: FakeGmail() for account in ACCOUNTS}
        model, discord = FakeOllama(), FakeDiscord()
        keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
        health = Health(lambda line: None)
        schedule = schedule_for_trial()
        number = 0
        with open_store(settings) as store:
            for minute, (revoked, arrivals, down) in enumerate(schedule):
                now.moment = datetime(2026, 11, 12, 9, 0, tzinfo=UTC) + timedelta(minutes=minute)
                for account in ACCOUNTS:
                    token = "revoked" if account in revoked else "refresh-token-1"
                    for name, value in (
                        ("client-id", "client-id-1"),
                        ("client-secret", "client-secret-1"),
                        ("refresh-token", token),
                    ):
                        keychain.secrets[("mailroom", f"gmail.{account}.{name}")] = value
                    for _ in range(arrivals.get(account, 0)):
                        number += 1
                        raw = f"From: s@example.test\r\nSubject: {TEXT_MARK} {number}\r\n\r\nhi\r\n"
                        stamp = round((now.moment - timedelta(seconds=30)).timestamp() * 1000)
                        gmail[account].add_message(
                            f"{account}-m{number}", raw.encode(), internal_ms=stamp
                        )
                reply = httpx.ConnectError("refused") if down else GOOD
                model.replies[:] = [reply] * 500
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
                    if minute < 60 and rng.random() < 0.2
                    else []
                )
                clients = [
                    GmailClient(a, httpx.Client(transport=httpx.MockTransport(gmail[a].handler)))
                    for a in ACCOUNTS
                ]
                run_round(
                    store,
                    settings,
                    clients,
                    httpx.Client(transport=httpx.MockTransport(model.handler)),
                    httpx.Client(transport=httpx.MockTransport(discord.handler)),
                    health,
                )
            if store.pending_alerts():
                return f"trial {trial}: {len(store.pending_alerts())} alerts never posted"
        posted = [m["content"] for m in discord.messages if not m["embeds"]]
        want = expected(schedule)
        if posted != want:
            return f"trial {trial}: posted {posted}, want {want}"
        for message in discord.messages:
            if TEXT_MARK in message["content"]:
                return f"trial {trial}: an alert holds email text"
        (TMP / "data" / "mailroom.sqlite3").unlink()
    return True


check("alerts follow the schedule, once each, in order", alerts_follow_the_schedule)
print(f"FAILURES {FAILURES}")
