"""Probe for phase 1n. Run from the repository root: .venv/bin/python docs/verification/probe-01n.py

1. Ids: random account names (valid, or a valid one with one change) and random provider ids.
   A valid account round-trips through `stored_id` and `account_of`; an invalid one is refused by
   `stored_id` and read back as None by `account_of`.
2. Accounts: 2 to 4 Gmail mailboxes draw message ids from one small shared pool, then sync two or
   three times with labels re-added in between. Every (account, id) in an inbox is stored once
   under `<account>/<id>` with its thread id prefixed the same way, its link holds the bare id and
   that account's address, each message is fetched once per mailbox, and its card's footer names
   the account.
3. Data folder: folders with random names, created fresh or by `prepare_data_dir`, carry the
   attribute macOS's `tmutil addexclusion` writes, read back with `/usr/bin/xattr`.
Fakes only; everything lives in a temporary folder. Each check prints `ok` or `FAIL`; the last
line is `FAILURES N`.
"""

import os
import plistlib
import random
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01n-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from tests.fakes import FakeGmail, FakeKeychain  # noqa: E402

FAILURES = 0
rng = random.Random(14)
NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
ACCOUNT = re.compile(r"[a-z][a-z0-9-]{0,31}")
FIRST = "abcdefghijklmnopqrstuvwxyz"
REST = FIRST + "0123456789-"
ATTRIBUTE = "com.apple.metadata:com_apple_backup_excludeItem"
EXCLUDED = plistlib.dumps("com.apple.backupd", fmt=plistlib.FMT_BINARY)


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


# The oracle's own tables.
def valid_account() -> str:
    return rng.choice(FIRST) + "".join(rng.choice(REST) for _ in range(rng.randrange(32)))


def broken(account: str) -> str:
    """A valid account with one change that settings would refuse."""
    change = rng.randrange(7)
    if change == 0:
        return account[:-1] + account[-1].upper() if account[-1].isalpha() else account + "X"
    if change == 1:
        return rng.choice("0123456789-") + account[1:]
    if change == 2:
        return (account + "a" * 33)[:33]
    if change == 3:
        return account + rng.choice("/ \n.")
    if change == 4:
        return account[:1] + "é" + account[1:]
    if change == 5:
        return ""
    return account + "_"


def provider_id() -> str:
    alphabet = "0123456789abcdef/=-_AZ"
    return "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 40)))


def expected_account(message_id: str) -> str | None:
    account, slash, _ = message_id.partition("/")
    return account if slash and ACCOUNT.fullmatch(account) else None


def attribute(path: Path) -> bytes | None:
    found = subprocess.run(
        ["/usr/bin/xattr", "-px", ATTRIBUTE, str(path)], capture_output=True, text=True
    )
    return bytes.fromhex(found.stdout) if found.returncode == 0 else None


for _ in range(2000):
    assert ACCOUNT.fullmatch(valid_account())
    assert ACCOUNT.fullmatch(broken(valid_account())) is None
assert expected_account("personal/a/b") == "personal"
assert expected_account("m1") is None
assert expected_account("Personal/m1") is None
assert expected_account("/m1") is None
plain = TMP / "plain"
plain.mkdir()
assert attribute(plain) is None
print("oracle self-check: ok")


def ids_round_trip() -> object:
    from mailroom.record import account_of, stored_id

    for _ in range(3000):
        account, provider = valid_account(), provider_id()
        made = stored_id(account, provider)
        if made != f"{account}/{provider}" or account_of(made) != account:
            return f"{account!r} {provider!r}: {made!r}"
        bad = broken(account)
        try:
            stored_id(bad, provider)
        except ValueError as error:
            if str(error) != "invalid record field: account":
                return f"{bad!r}: message {error}"
        else:
            return f"{bad!r} was accepted"
        if account_of(f"{bad}/{provider}") != expected_account(f"{bad}/{provider}"):
            return f"{bad!r} read back as {account_of(f'{bad}/{provider}')!r}"
        if account_of(provider) != expected_account(provider):
            return f"{provider!r} read back as {account_of(provider)!r}"
    return True


def raw(number: int) -> bytes:
    return (
        f"From: Sender {number} <sender{number}@example.test>\r\n"
        f"Subject: Note {number}\r\n"
        "Date: Fri, 13 Nov 2026 07:00:00 +0000\r\n"
        f"\r\nBody {number}.\r\n"
    ).encode()


def accounts_never_collide() -> object:
    from mailroom.checkpoint import checkpoint_message
    from mailroom.config import get_settings
    from mailroom.gmail import GmailClient
    from mailroom.gmail_sync import sync_gmail
    from mailroom.store import Verdict, open_store

    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    clock.now = lambda: NOW
    arrived = round((NOW - timedelta(hours=1)).timestamp() * 1000)
    pool = [f"{rng.getrandbits(64):016x}" for _ in range(6)]
    verdict = Verdict("rejected", False, False, False, True, None, reason="probe")
    reached_shared = False
    for trial in range(150):
        accounts = rng.sample(["personal", "work", "a", "school-2", "x" * 32], rng.randrange(2, 5))
        boxes: dict[str, FakeGmail] = {}
        inbox: dict[tuple[str, str], str] = {}
        for account in accounts:
            for name in ("client-id", "client-secret", "refresh-token"):
                keychain.secrets[("mailroom", f"gmail.{account}.{name}")] = f"{name}-1"
            box = FakeGmail()
            box.email_address = f"{account}@example.test"
            for number, message in enumerate(rng.sample(pool, rng.randrange(1, len(pool)))):
                thread = f"t{rng.randrange(3)}"
                labels = ("INBOX",) if rng.random() < 0.8 else ("SPAM",)
                box.add_message(
                    message, raw(number), thread_id=thread, labels=labels, internal_ms=arrived
                )
                if labels == ("INBOX",):
                    inbox[(account, message)] = thread
            boxes[account] = box
        ids = [message for _, message in inbox]
        reached_shared = reached_shared or len(ids) > len(set(ids))
        with open_store(get_settings()) as store:
            for _ in range(rng.randrange(2, 4)):
                for account in accounts:
                    http = httpx.Client(transport=httpx.MockTransport(boxes[account].handler))
                    sync_gmail(GmailClient(account, http), store)
                    stored = sorted(m for a, m in inbox if a == account)
                    for message in rng.sample(stored, min(1, len(stored))):
                        boxes[account].add_labels(message, "INBOX")
            want = {("gmail", f"{a}/{m}") for a, m in inbox}
            have = set(store.untriaged())
            if have != want:
                return f"trial {trial}: stored {sorted(have ^ want)[:3]} differ"
            for (account, message), thread in inbox.items():
                record = store.get("gmail", f"{account}/{message}").record
                if record.thread_id != f"{account}/{thread}":
                    return f"trial {trial}: thread {record.thread_id!r}"
                if not record.link.endswith(f"?authuser={account}@example.test#all/{message}"):
                    return f"trial {trial}: link {record.link!r}"
                card = checkpoint_message(record, verdict, "0" * 32)
                footer = card["embeds"][0]["footer"]["text"]
                if not footer.startswith(f"Gmail {account} · "):
                    return f"trial {trial}: footer {footer!r}"
            for account, box in boxes.items():
                prefix = "/gmail/v1/users/me/messages/"
                paths = [r.url.path for r in box.requests if r.url.path.startswith(prefix)]
                if len(paths) != len(set(paths)):
                    return f"trial {trial}: {account} fetched a message twice"
        (TMP / "data" / "mailroom.sqlite3").unlink()
    if not reached_shared:
        return "no trial had two accounts sharing an id"
    return True


def data_folders_are_excluded() -> object:
    from mailroom.config import ConfigError, exclude_from_backup, get_settings, prepare_data_dir

    letters = "abcXYZ019 -_.éß東"
    for number in range(60):
        name = "".join(rng.choice(letters) for _ in range(rng.randrange(1, 20))).strip(" .")
        folder = TMP / "folders" / f"{number}-{name}"
        folder.mkdir(parents=True)
        exclude_from_backup(folder)
        if attribute(folder) != EXCLUDED:
            return f"{folder.name!r} not excluded"
        if attribute(folder.parent) is not None:
            return "the parent was excluded too"
    os.environ["MAILROOM_DATA_DIR"] = str(TMP / "fresh" / "nested" / "data")
    found = prepare_data_dir(get_settings())
    if attribute(found) != EXCLUDED:
        return "prepare_data_dir left the folder in backups"
    try:
        exclude_from_backup(TMP / "missing")
    except ConfigError as error:
        if str(error) != "could not exclude the data folder from Time Machine":
            return f"message {error}"
        if error.__cause__ is not None or not error.__suppress_context__:
            return "the library's error is chained"
    else:
        return "a missing folder was accepted"
    return True


check("ids round-trip and bad accounts are refused", ids_round_trip)
check("accounts sharing Gmail ids never collide", accounts_never_collide)
check("data folders are excluded from Time Machine", data_folders_are_excluded)
print(f"FAILURES {FAILURES}")
