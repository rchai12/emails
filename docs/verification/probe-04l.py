"""Probe for phase 4l. Run from the repository root: .venv/bin/python docs/verification/probe-04l.py

1. Neutral module: a fresh interpreter imports `mailroom.mail_sync` and `mailroom.outlook_sync`
   and loads no `mailroom.gmail*` module; `mail_sync.py`'s own imports name no provider module;
   the windows and `SyncResult` that `gmail_sync`, `outlook_sync` and `service` expose are
   mail_sync's objects.
2. The shared round: seeded random rounds of a scripted adapter for an invented provider
   (first run, resume, expired bookmarks after random absences, messages already stored,
   missing, unusable, or failing mid-round). The probe predicts every adapter call, result and
   bookmark from its own reading of the rules.
3. Both real adapters go through `mail_sync.run_round`, and seeded random timelines against
   FakeGmail and FakeGraph give the rounds the probe predicts, the same for both providers.
Fakes and temporary databases only. Each check prints `ok` or `FAIL`; the last line is
`FAILURES N`.
"""

import ast
import os
import random
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe04l-"))
os.environ["HOME"] = str(TMP / "home")
for key in [key for key in os.environ if key.startswith("MAILROOM_")]:
    del os.environ[key]
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from tests.fakes import FakeGmail, FakeGraph, FakeKeychain  # noqa: E402

KEYCHAIN = FakeKeychain()
keyring.core.set_keyring(KEYCHAIN)
FAILURES = 0
rng = random.Random(4120)
START = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
FIRST = timedelta(days=3)
LIMIT = timedelta(days=14)
OVERLAP = timedelta(hours=1)
NOW = [START]
clock.now = lambda: NOW[0]
STORES = iter(range(10_000))


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


def new_store():
    from mailroom.config import get_settings
    from mailroom.store import open_store

    os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"data-{next(STORES)}")
    return open_store(get_settings())


def no_gmail_module_in_a_fresh_interpreter() -> object:
    script = (
        "import sys, mailroom.mail_sync, mailroom.outlook_sync;"
        "print(','.join(sorted(n for n in sys.modules if n.startswith('mailroom.'))))"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT)])}
    found = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=False
    )
    if found.returncode != 0:
        return f"the import failed with exit {found.returncode}"
    named = [name for name in found.stdout.strip().split(",") if name.startswith("mailroom.gmail")]
    return True if not named else f"loaded {named}"


def mail_sync_imports_no_provider() -> object:
    tree = ast.parse((ROOT / "src/mailroom/mail_sync.py").read_text())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names += [f"{node.module}.{alias.name}" for alias in node.names]
    bad = [
        name
        for name in names
        if any(part.startswith(("gmail", "outlook", "yahoo")) for part in name.split("."))
    ]
    return True if not bad else f"mail_sync.py imports {bad}"


def shared_names_are_mail_syncs() -> object:
    from mailroom import gmail_sync, mail_sync, outlook_sync, service

    if (mail_sync.FIRST_RUN, mail_sync.CATCH_UP_LIMIT, mail_sync.CATCH_UP_OVERLAP) != (
        FIRST,
        LIMIT,
        OVERLAP,
    ):
        return "the windows changed"
    wrong = [
        f"gmail_sync.{name}"
        for name in ("FIRST_RUN", "CATCH_UP_LIMIT", "CATCH_UP_OVERLAP", "SyncResult")
        if getattr(gmail_sync, name) is not getattr(mail_sync, name)
    ]
    for module in (outlook_sync, service):
        if module.SyncResult is not mail_sync.SyncResult:
            wrong.append(f"{module.__name__}.SyncResult")
    return True if not wrong else f"not mail_sync's: {wrong}"


class Scripted:
    """An invented provider. `plan` sets what the next round's calls return."""

    provider = "yahoo"

    def __init__(self, account: str, resumed: str) -> None:
        self.account = account
        self.resumed = resumed
        self.calls: list[tuple] = []
        self.plan: dict = {}

    def begin(self) -> None:
        self.calls.append(("begin",))

    def start(self, after: datetime):
        from mailroom.mail_sync import Page

        self.calls.append(("start", after))
        return Page(tuple(self.plan["ids"]), self.plan["bookmark"])

    def resume(self, bookmark: str):
        from mailroom.mail_sync import Page

        self.calls.append(("resume", bookmark))
        if self.plan["expired"]:
            return None
        return Page(tuple(self.plan["ids"]), self.plan["bookmark"])

    def fetch(self, message_id: str):
        from mailroom.mail_sync import Fetched

        self.calls.append(("fetch", message_id))
        fate = self.plan["fates"][message_id]
        if fate == "fails":
            raise ConnectionError("down")
        if fate == "missing":
            return None
        fields = {
            "raw": f"From: a@example.test\r\nSubject: {message_id}\r\n\r\nBody.\r\n".encode(),
            "thread_id": f"t-{message_id}",
            "received_at": NOW[0] - timedelta(minutes=1),
            "link": f"https://mail.example.test/{message_id}",
        }
        if fate == "bad-thread":
            fields["thread_id"] = "t" * 1001
        elif fate == "bad-time":
            fields["received_at"] = datetime(2026, 11, 1, 8, 0)
        elif fate == "bad-link":
            fields["link"] = "javascript:alert(1)"
        return Fetched(**fields)


def the_shared_round_follows_the_rules() -> object:
    from mailroom import mail_sync

    reached = {"first": 0, "resumed": 0, "catch_up": 0, "gap": 0, "interrupted": 0, "skip": 0}
    for trial in range(60):
        account = rng.choice(["family", "work", "x1"])
        source = Scripted(account, rng.choice(["history", "delta"]))
        state: tuple[str, datetime] | None = None
        stored: set[str] = set()
        NOW[0] = START
        counter = 0
        with new_store() as store:
            for step in range(rng.randrange(3, 8)):
                NOW[0] += rng.choice(
                    [
                        timedelta(minutes=1),
                        timedelta(hours=5),
                        timedelta(days=2),
                        timedelta(days=20),
                    ]
                )
                old = sorted(stored)
                fresh = [f"y{counter + n}" for n in range(rng.randrange(0, 4))]
                counter += len(fresh)
                ids = rng.sample(old, min(len(old), rng.randrange(0, 3))) + fresh
                rng.shuffle(ids)
                fates = {
                    one: rng.choice(
                        ["ok"] * 6 + ["missing", "bad-thread", "bad-time", "bad-link", "fails"]
                    )
                    for one in ids
                }
                bookmark = f"b{trial}-{step}"
                source.plan = {
                    "ids": ids,
                    "bookmark": bookmark,
                    "expired": rng.random() < 0.35,
                    "fates": fates,
                }
                source.calls = []
                want_calls: list[tuple] = [("begin",)]
                if state is None:
                    kind, offline, gap = "first", None, False
                    want_calls.append(("start", NOW[0] - FIRST))
                else:
                    want_calls.append(("resume", state[0]))
                    if source.plan["expired"]:
                        synced = state[1]
                        kind, offline, gap = "catch_up", synced, NOW[0] - synced > LIMIT
                        want_calls.append(("start", max(synced - OVERLAP, NOW[0] - LIMIT)))
                    else:
                        kind, offline, gap = source.resumed, None, False
                want_stored: list[str] = []
                failed = False
                for one in ids:
                    if one in stored:
                        continue
                    want_calls.append(("fetch", one))
                    if fates[one] == "fails":
                        failed = True
                        break
                    if fates[one] == "ok":
                        want_stored.append(f"{account}/{one}")
                        stored.add(one)
                    else:
                        reached["skip"] += 1
                label = f"trial {trial} step {step}"
                try:
                    result = mail_sync.run_round(source, store)
                except ConnectionError:
                    if not failed:
                        return f"{label}: raised without a failing fetch"
                    reached["interrupted"] += 1
                    if source.calls != want_calls:
                        return f"{label}: calls {source.calls!r}, wanted {want_calls!r}"
                    saved = store.sync_state("yahoo", account)
                    if (saved and (saved.bookmark, saved.synced_at)) != (state or None):
                        return f"{label}: an interrupted round moved the bookmark"
                    continue
                if failed:
                    return f"{label}: a failing fetch did not stop the round"
                if source.calls != want_calls:
                    return f"{label}: calls {source.calls!r}, wanted {want_calls!r}"
                want = mail_sync.SyncResult(account, kind, tuple(want_stored), offline, gap)
                if result != want:
                    return f"{label}: {result!r}, wanted {want!r}"
                saved = store.sync_state("yahoo", account)
                if saved is None or (saved.bookmark, saved.synced_at) != (bookmark, NOW[0]):
                    return f"{label}: the bookmark was not saved after a completed round"
                state = (bookmark, NOW[0])
                reached["resumed" if kind == source.resumed else kind] += 1
                reached["gap"] += gap
                for one in stored:
                    if store.get("yahoo", f"{account}/{one}") is None:
                        return f"{label}: {one} is missing from the store"
    if min(reached.values()) < 10:
        return f"too few cases: {reached}"
    return True


class GmailCase:
    provider, account, resumed = "gmail", "personal", "history"

    def __init__(self) -> None:
        self.fake = FakeGmail()
        KEYCHAIN.secrets.update(
            {
                ("mailroom", "gmail.personal.client-id"): self.fake.client_id,
                ("mailroom", "gmail.personal.client-secret"): self.fake.client_secret,
                ("mailroom", "gmail.personal.refresh-token"): self.fake.refresh_token,
            }
        )
        self.count = 0

    def deliver(self, moment: datetime) -> str:
        self.count += 1
        raw = f"From: a@example.test\r\nSubject: g{self.count}\r\n\r\nBody.\r\n".encode()
        self.fake.add_message(
            f"m{self.count}",
            raw,
            thread_id=f"t{self.count}",
            internal_ms=round(moment.timestamp() * 1000),
        )
        return f"personal/m{self.count}"

    def expire(self) -> None:
        self.fake.history_id += 1
        self.fake.oldest_history_id = self.fake.history_id

    def sync(self, store):
        from mailroom.gmail import GmailClient
        from mailroom.gmail_sync import sync_gmail

        http = httpx.Client(transport=httpx.MockTransport(self.fake.handler))
        return sync_gmail(GmailClient("personal", http), store)


class OutlookCase:
    provider, account, resumed = "outlook", "live", "delta"

    def __init__(self) -> None:
        self.fake = FakeGraph()
        KEYCHAIN.secrets[("mailroom", "outlook.live.client-id")] = self.fake.client_id
        KEYCHAIN.secrets[("mailroom", "outlook.live.refresh-token")] = self.fake.refresh_token
        self.count = 0

    def deliver(self, moment: datetime) -> str:
        self.count += 1
        raw = f"From: a@example.test\r\nSubject: o{self.count}\r\n\r\nBody.\r\n".encode()
        received = moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.fake.add_message(f"AAMk{self.count}=", raw, received=received)
        return f"live/AAMk{self.count}="

    def expire(self) -> None:
        self.fake.expire_deltas()

    def sync(self, store):
        from mailroom.outlook import OutlookClient
        from mailroom.outlook_sync import sync_outlook

        http = httpx.Client(transport=httpx.MockTransport(self.fake.handler))
        return sync_outlook(OutlookClient("live", http), store)


def both_providers_follow_the_shared_round() -> object:
    from mailroom import mail_sync

    real = mail_sync.run_round
    seen: list[tuple[str, str]] = []

    def spy(source, store):
        seen.append((source.provider, source.account))
        return real(source, store)

    mail_sync.run_round = spy
    try:
        for trial in range(12):
            steps = []
            for _ in range(rng.randrange(3, 7)):
                steps.append(
                    (
                        rng.choice(
                            [
                                timedelta(minutes=2),
                                timedelta(hours=3),
                                timedelta(days=2),
                                timedelta(days=16),
                            ]
                        ),
                        rng.randrange(0, 3),
                        rng.random() < 0.4,
                    )
                )
            outcomes = {}
            for case_type in (GmailCase, OutlookCase):
                case = case_type()
                NOW[0] = START
                rounds = []
                synced: datetime | None = None
                seen.clear()
                with new_store() as store:
                    for number, (step, count, expire) in enumerate(steps):
                        NOW[0] += step
                        if expire and synced is not None:
                            case.expire()
                        delivered = [
                            case.deliver(NOW[0] - timedelta(seconds=30 + 10 * n))
                            for n in range(count)
                        ]
                        result = case.sync(store)
                        if synced is None:
                            want = ("first", None, False)
                        elif expire:
                            want = ("catch_up", synced, NOW[0] - synced > LIMIT)
                        else:
                            want = ("resumed", None, False)
                        kind = "resumed" if result.kind == case.resumed else result.kind
                        got = (kind, result.offline_since, result.gap)
                        if got != want or sorted(result.stored) != sorted(delivered):
                            return (
                                f"trial {trial} round {number} ({case.provider}): "
                                f"{got} storing {len(result.stored)}, wanted {want} "
                                f"storing {len(delivered)}"
                            )
                        rounds.append((got, len(result.stored)))
                        synced = NOW[0]
                if seen != [(case.provider, case.account)] * len(steps):
                    return f"trial {trial} ({case.provider}): rounds through run_round {seen}"
                outcomes[case.provider] = rounds
            if outcomes["gmail"] != outcomes["outlook"]:
                return f"trial {trial}: the providers differ"
    finally:
        mail_sync.run_round = real
    return True


check("outlook sync loads no gmail module", no_gmail_module_in_a_fresh_interpreter)
check("mail_sync.py imports no provider module", mail_sync_imports_no_provider)
check("the shared names are mail_sync's objects", shared_names_are_mail_syncs)
check("the shared round follows the rules", the_shared_round_follows_the_rules)
check("both providers follow the shared round", both_providers_follow_the_shared_round)
print(f"FAILURES {FAILURES}")
sys.exit(1 if FAILURES else 0)
