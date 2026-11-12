"""Probe for phase 1i. Run from the repository root: .venv/bin/python docs/verification/probe-01i.py

It sends random sequences of button presses and form submissions (from the owner and from
others, in the channel and elsewhere, with real and made-up button ids, good and bad titles) to
`handle_interaction`, and compares the store with a model of what should have happened. Only the
owner's first answer counts, and others change nothing. Every interaction gets exactly one reply
Discord accepts. Email text in a reply appears only inside a code block it can't close. The
database is in a temporary folder. Each check prints `ok` or `FAIL`; the last line is
`FAILURES N`.
"""

import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01i-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
os.environ["MAILROOM_DISCORD_CHANNEL_ID"] = "111111111111111111"
os.environ["MAILROOM_DISCORD_OWNER_ID"] = "444444444444444444"

import httpx  # noqa: E402

from mailroom import clock, ids  # noqa: E402
from mailroom.extractor import Extraction  # noqa: E402
from mailroom.record import Record  # noqa: E402
from tests.fakes import FakeDiscord  # noqa: E402

FAILURES = 0
rng = random.Random(17)
ANSWERS = ("yes", "edit", "notask", "mute")
BAD_CHARS = set("\n\r\t​  \x00")


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


# The oracle: what a title submission should become, and what each press should do.
def good_title(value: str) -> str | None:
    title = value.strip()
    if not 0 < len(title) <= 100 or any(c in BAD_CHARS for c in title):
        return None
    return title


def expected(action: str, owner: bool, answered: bool, has_sender: bool, has_title: bool) -> str:
    if not owner:
        return "ignored"
    if action == "full":
        return "full"
    if action == "trust":
        return "trusted" if has_sender else "no-sender"
    if answered:
        return "already"
    if action == "mute" and not has_sender:
        return "no-sender"
    if action == "edit" or (action == "yes" and not has_title):
        return "form"
    return "answered"


assert good_title("  Pay  ") == "Pay"
assert good_title("Pay\nnow") is None
assert good_title(" ") is None
assert good_title("P" * 100) == "P" * 100
assert expected("mute", False, False, True, True) == "ignored"
assert expected("trust", True, True, True, True) == "trusted"
assert expected("yes", True, False, True, False) == "form"
assert expected("mute", True, True, False, True) == "already"
print("oracle self-check: ok")

try:
    from mailroom.config import get_settings
    from mailroom.interactions import handle_interaction
    from mailroom.store import Verdict, open_store
except Exception as error:
    print(f"import: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)

BASE = Record(
    provider="gmail",
    message_id="m",
    thread_id="t",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m",
    sender="billing@example.test",
    sender_name="Billing",
    subject="Your bill",
    sent_at=None,
    body_text="Your bill is due.",
    list_unsubscribe=False,
    authentication_results=(),
)
TEXTS = ["Pay at `portal` **now** @everyone", "[x](https://evil.test)", "a" * 2500, "", "naïve ✓"]


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.moment += timedelta(seconds=1)
        return self.moment


def reply_is_safe(body: dict, email_text: str) -> str:
    if body["type"] != 4:
        return ""
    data = body["data"]
    if data.get("flags") != 64 or data.get("allowed_mentions") != {"parse": []}:
        return "a reply that is not private, or allows mentions"
    content = data["content"]
    if email_text and email_text[:50].replace("`", "ˋ") in content:
        start = content.index("```\n")
        end = content.index("\n```", start + 4)
        if "`" in content[start + 4 : end]:
            return "a backtick inside the full-text block"
    return ""


def presses_follow_the_model() -> object:
    clock.now = Clock()
    settings = get_settings()
    for trial in range(60):
        discord = FakeDiscord()
        http = httpx.Client(transport=httpx.MockTransport(discord.handler))
        with open_store(settings) as store:
            items = []
            for index in range(rng.randrange(1, 4)):
                sender = rng.choice(
                    [f"s{trial}-{index}@example.test", f"s{trial}-{index}@example.test", ""]
                )
                record = replace(
                    BASE,
                    message_id=f"m{index}",
                    sender=sender,
                    subject=rng.choice(TEXTS)[:200].replace("\n", " "),
                    body_text=rng.choice(TEXTS),
                )
                title = rng.choice(["Pay the bill", "", "Use `code`"])
                extraction = Extraction(
                    summary="A summary.",
                    actionable=bool(title),
                    urgent=False,
                    title=title,
                    deadline=None,
                    suspicious=False,
                    suspicion_reason="",
                    confidence="high",
                )
                verdict = Verdict("extracted", False, True, False, True, extraction)
                store.add(record)
                store.save_triage("gmail", record.message_id, verdict)
                store.queue_notified()
                (post,) = [p for p in store.pending_posts() if p.message_id == record.message_id]
                store.mark_posted(post.item_id, str(1300000000000000001 + index))
                items.append((post.item_id, record, title))
            answered: dict[str, tuple[str, str]] = {}
            status: dict[str, str] = {}
            for _ in range(rng.randrange(1, 25)):
                item_id, record, title = rng.choice(items)
                owner = rng.random() < 0.8
                user = discord.owner_id if owner else "555555555555555555"
                where = rng.choice([None, None, None, "999999999999999999"])
                owner = owner and where is None
                if rng.random() < 0.25:
                    value = rng.choice(["  New title ", "", "x" * 101, "Two\nlines", "Fine`title"])
                    event = discord.submit(f"mr:title:{item_id}", value, user_id=user)
                    if where:
                        event = {**event, "channel_id": where}
                    if not owner:
                        want = "ignored"
                    elif item_id in answered:
                        want = "already"
                    else:
                        want = "answered" if good_title(value) else "bad-title"
                    action, new_title = "edit", good_title(value) or ""
                else:
                    action = rng.choice(["full", "trust", *ANSWERS, "bogus"])
                    custom = (
                        f"mr:{action}:{item_id}"
                        if rng.random() < 0.9
                        else f"mr:{action}:{ids.new_id()}"
                    )
                    event = discord.press(custom, user_id=user, channel_id=where)
                    known = action != "bogus" and custom.endswith(item_id)
                    want = expected(
                        action,
                        owner and known,
                        item_id in answered,
                        bool(record.sender),
                        bool(title),
                    )
                    new_title = title if action == "yes" else ""
                got = handle_interaction(event, store, settings, http)
                if got != want:
                    return f"trial {trial}: {action} by owner={owner}: got {got!r}, want {want!r}"
                if want == "answered":
                    answered[item_id] = (action, new_title)
                    if action == "mute":
                        status[record.sender] = "muted"
                if want == "trusted":
                    status[record.sender] = "trusted"
                body = discord.callbacks[-1][1]
                problem = reply_is_safe(body, record.body_text if action == "full" else "")
                if problem:
                    return f"trial {trial}: {problem}"
            if len(discord.callbacks) != len(discord.requests):
                return f"trial {trial}: a reply Discord refused"
            for item_id, _, _ in items:
                stored = store.answer(item_id)
                want_answer = answered.get(item_id)
                got_answer = None if stored is None else (stored.answer, stored.title)
                if got_answer != want_answer:
                    return f"trial {trial}: {item_id} answer {got_answer}, want {want_answer}"
            for _, record, _ in items:
                if record.sender and store.sender_status(record.sender) != status.get(
                    record.sender
                ):
                    return f"trial {trial}: {record.sender} is {store.sender_status(record.sender)}"
        (TMP / "data" / "mailroom.sqlite3").unlink()
    return True


check("presses and forms follow the model, and every reply is safe", presses_follow_the_model)
print(f"FAILURES {FAILURES}")
