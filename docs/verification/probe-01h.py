"""Probe for phase 1h. Run from the repository root: .venv/bin/python docs/verification/probe-01h.py

It builds checkpoint messages from random records and verdicts with hostile text (markdown,
backticks, mentions, links, every field at its limit) and checks that Discord would accept each
one, that email text appears only inside code blocks it can't close, and that every button id
leads back to its item. Then it posts random batches through random failures (lost replies, 429s,
server errors, network errors) over several rounds and checks that every email reaches Discord
exactly once and nothing is lost. The database is in a temporary folder. Each check prints `ok` or
`FAIL`; the last line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01h-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
os.environ["MAILROOM_DISCORD_CHANNEL_ID"] = "111111111111111111"

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock, ids  # noqa: E402
from mailroom.extractor import Deadline, Extraction  # noqa: E402
from mailroom.record import Record  # noqa: E402
from tests.fakes import FakeDiscord, FakeKeychain  # noqa: E402

FAILURES = 0
rng = random.Random(16)
HOSTILE = [
    "**bold** __u__ ~~s~~ ||spoiler||",
    "`tick` ``two`` ```three```",
    "@everyone @here <@123456789012345678> <#1> <@&2>",
    "[click](https://evil.test) https://evil.test/x",
    "# Heading\n- list",
    "> quote",
    "naïve ✓ 漢字",
    "",
]


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


# The oracle: email text may appear only as the whole inside of a code block.
def blocked(value: str) -> str | None:
    """The text inside a field value that is one code block, or None if it is not one."""
    if not (value.startswith("```\n") and value.endswith("\n```")):
        return None
    inside = value[4:-4]
    return None if "`" in inside else inside


def shown(text: str, empty: str) -> str:
    return text.replace("`", "ˋ") or empty


assert blocked("```\nhi\n```") == "hi"
assert blocked("```\nh`i\n```") is None
assert blocked("hi") is None
assert shown("a`b", "(none)") == "aˋb"
assert shown("", "(none)") == "(none)"
print("oracle self-check: ok")

try:
    from mailroom.checkpoint import checkpoint_message
    from mailroom.config import get_settings
    from mailroom.discord_post import post_pending
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


def text(limit: int) -> str:
    choice = rng.random()
    if choice < 0.2:
        return (rng.choice(HOSTILE[:-1]).replace("\n", " ") * limit)[:limit]
    return rng.choice(HOSTILE).replace("\n", " ")[:limit]


def random_case() -> tuple[Record, Verdict, str]:
    record = replace(
        BASE,
        provider=rng.choice(["gmail", "outlook", "yahoo"]),
        sender=rng.choice(["billing@example.test", "", "a" * 64 + "@" + "b" * 184 + ".test"]),
        sender_name=text(100),
        subject=text(200),
        link=rng.choice(
            [BASE.link, "https://mail.google.com/mail/#all/" + "a" * rng.randrange(470, 490)]
        ),
    )
    kind = rng.choice(["extracted", "extracted", "rejected", "cleared"])
    extraction = Extraction(
        summary=text(300) or "A summary.",
        actionable=rng.random() < 0.6,
        urgent=rng.random() < 0.3,
        title=text(100),
        deadline=rng.choice([None, Deadline(date(2026, 11, 20), None, True, "by Friday")]),
        suspicious=rng.random() < 0.3,
        suspicion_reason="",
        confidence="high",
    )
    if extraction.suspicious:
        extraction = replace(extraction, suspicion_reason=text(120) or "Odd sender")
    verdict = Verdict(
        outcome="extracted" if kind == "cleared" else kind,
        trusted=rng.random() < 0.2,
        verified=rng.random() < 0.6,
        bulk=rng.random() < 0.4,
        notify=True,
        extraction=extraction if kind == "extracted" else None,
        reason="timeout" if kind == "rejected" else "",
    )
    return record, verdict, ids.new_id()


def messages_are_safe_and_accepted() -> object:
    for _ in range(3000):
        record, verdict, item = random_case()
        body = checkpoint_message(record, verdict, item)
        problem = FakeDiscord._problem(body)
        if problem:
            return f"Discord would refuse it: {problem}"
        if body.get("allowed_mentions") != {"parse": []} or "content" in body:
            return "mentions allowed or text outside the embed"
        (embed,) = body["embeds"]
        fields = {field["name"]: field["value"] for field in embed["fields"]}
        address = record.sender or "(no address)"
        sender = f"{record.sender_name} <{address}>" if record.sender_name else address
        expected = {"From": shown(sender, ""), "Subject": shown(record.subject, "(no subject)")}
        extraction = verdict.extraction
        if extraction is not None:
            expected["Summary"] = shown(extraction.summary, "")
            if extraction.title:
                expected["Proposed task"] = shown(extraction.title, "")
            if extraction.suspicious:
                expected["Suspected spam or phishing"] = shown(extraction.suspicion_reason, "")
        for name, inside in expected.items():
            if blocked(fields.get(name, "")) != inside:
                return f"{name}: {fields.get(name)!r} does not hold {inside!r} in a code block"
        extra = set(fields) - set(expected) - {"Summary"}
        if extra:
            return f"unexpected fields {extra}"
        if extraction is None and blocked(fields.get("Summary", "")) is not None:
            return "a summary without an extraction was shown as email text"
        for key in ("title", "footer"):
            value = embed[key] if key == "title" else embed[key]["text"]
            if any(mark in value for mark in ("`", "@", "[", "http")):
                return f"{key} holds formatting: {value!r}"
        ids_seen = []
        for row in body["components"]:
            for button in row["components"]:
                if button["style"] == 5:
                    if button["url"] != record.link:
                        return "the link button is not the record's link"
                else:
                    prefix, _, item_id = button["custom_id"].split(":")
                    if (prefix, item_id) != ("mr", item):
                        return f"button id {button['custom_id']!r} does not lead to {item}"
                    ids_seen.append(button["custom_id"])
        if len(ids_seen) != 6:
            return f"{len(ids_seen)} answer buttons, want 6"
        has_link = any(b["style"] == 5 for row in body["components"] for b in row["components"])
        if has_link != (len(record.link) <= 512):
            return f"link of {len(record.link)} characters: button shown {has_link}"
        if body["nonce"] != item[:25] or body["enforce_nonce"] is not True:
            return "nonce is not the item id's first 25 characters"
    return True


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.moment += timedelta(seconds=1)
        return self.moment


def every_email_reaches_discord_exactly_once() -> object:
    clock.now = Clock()
    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    settings = get_settings()
    for trial in range(40):
        discord = FakeDiscord()
        keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
        http = httpx.Client(transport=httpx.MockTransport(discord.handler))
        with open_store(settings) as store:
            notified = set()
            for round_number in range(12):
                for index in range(rng.randrange(0, 4)):
                    record, verdict, _ = random_case()
                    message_id = f"t{trial}-r{round_number}-{index}"
                    store.add(replace(record, provider="gmail", message_id=message_id))
                    verdict = replace(verdict, notify=rng.random() < 0.8)
                    if verdict.outcome == "extracted" and verdict.extraction is None:
                        verdict = replace(verdict, outcome="rejected", reason="timeout")
                    store.save_triage("gmail", message_id, verdict)
                    if verdict.notify:
                        notified.add(message_id)
                discord.failures = [
                    rng.choice(
                        [
                            None,
                            None,
                            "lost-reply",
                            httpx.Response(429, json={"retry_after": 1.0, "global": False}),
                            httpx.Response(502, text="bad gateway"),
                            httpx.ConnectError("refused"),
                        ]
                    )
                    for _ in range(rng.randrange(0, 4))
                ]
                post_pending(store, settings, http)
            discord.failures = []
            for _ in range(5):
                post_pending(store, settings, http)
            if store.pending_posts():
                return f"trial {trial}: {len(store.pending_posts())} never posted"
            by_nonce = {}
            for message in discord.messages:
                if message["nonce"] in by_nonce:
                    return f"trial {trial}: two Discord messages for one email"
                by_nonce[message["nonce"]] = message["id"]
            if len(discord.messages) != len(notified):
                return f"trial {trial}: {len(discord.messages)} messages for {len(notified)} emails"
            for message_id in notified:
                post = store.post("gmail", message_id)
                if post is None or by_nonce.get(post.item_id[:25]) != post.discord_message_id:
                    return f"trial {trial}: {message_id} recorded against the wrong message"
        (TMP / "data" / "mailroom.sqlite3").unlink()
    return True


check(
    "every message is accepted and keeps email text in code blocks", messages_are_safe_and_accepted
)
check("every notified email reaches Discord exactly once", every_email_reaches_discord_exactly_once)
print(f"FAILURES {FAILURES}")
