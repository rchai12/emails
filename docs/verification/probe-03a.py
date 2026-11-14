"""Probe for phase 3a. Run from the repository root: .venv/bin/python docs/verification/probe-03a.py

1. Posting: each trial spreads a few emails over two threads and posts them in rounds an hour
   apart, while earlier emails are approved, dropped or left alone between rounds and Discord
   fails at random. Each post's card must be the one the probe's oracle chose at that post's
   first send attempt: the follow-up card, naming the latest approved item in its thread, when
   there is one; checkpoint 1 otherwise. It must never change on a retry, and every request for a
   post must carry that card.
2. Presses: follow-up cards take random presses and forms. A three-state model (open, waiting
   for checkpoint 2, closed) says each outcome, and the stored answer and approval must match it.
Fakes only; everything lives in a temporary folder. Each check prints `ok` or `FAIL`; the last
line is `FAILURES N`.
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
TMP = Path(tempfile.mkdtemp(prefix="probe03a-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DISCORD_CHANNEL_ID"] = "111111111111111111"
os.environ["MAILROOM_DISCORD_OWNER_ID"] = "444444444444444444"
os.environ["MAILROOM_TIME_ZONE"] = "America/New_York"

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock, ids  # noqa: E402
from mailroom.config import get_settings  # noqa: E402
from tests.fakes import FakeDiscord, FakeKeychain  # noqa: E402

FAILURES = 0
rng = random.Random(31)
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


def latest(approved: list[tuple[datetime, str, str]]) -> tuple[str, str] | None:
    """The probe's own reading of the target: the latest decision, then the larger item id."""
    if not approved:
        return None
    _, item, title = max(approved)
    return item, title


assert latest([]) is None
assert latest([(START, "a", "x"), (START, "c", "y"), (START - timedelta(1), "z", "w")]) == (
    "c",
    "y",
)
print("oracle self-check: ok")


def posting_follows_the_latest_approval() -> object:
    from mailroom.checkpoint import checkpoint_message, followup_message
    from mailroom.discord_post import post_pending
    from mailroom.store import open_store
    from tests.integration.test_post_followup import UNDATED
    from tests.integration.test_triage import RECORD

    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    clock.now = lambda: MOMENT[0]
    reached = {"followup": 0, "first": 0, "retargeted": 0}
    choices = (None, None, httpx.Response(503), "lost-reply", httpx.ConnectError("x"))
    for trial in range(80):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"post{trial}")
        MOMENT[0] = START
        discord = FakeDiscord()
        keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
        settings = get_settings()
        approved: dict[str, list[tuple[datetime, str, str]]] = {"t1": [], "t2": []}
        chosen: dict[str, tuple[str, str] | None] = {}
        records = {}
        with open_store(settings) as store:
            for _ in range(8):
                for _new in range(rng.randrange(3)):
                    number = len(records)
                    # Round 0's first two share a thread, so a follow-up is always possible.
                    thread = "t1" if number < 2 else rng.choice(("t1", "t2"))
                    record = replace(
                        RECORD, message_id=f"personal/m{number}", thread_id=f"personal/{thread}"
                    )
                    records[record.message_id] = (record, thread)
                    store.add(record)
                    store.save_triage("gmail", record.message_id, UNDATED)
                for post in [store.post("gmail", m) for m in records]:
                    if post is None or post.posted_at is None or store.answer(post.item_id):
                        continue
                    if rng.random() < 0.5:
                        continue
                    title = f"Task {post.item_id[:6]}"
                    store.record_answer(post.item_id, "yes", title)
                    outcome = rng.choice(("nodeadline", "nodeadline", "drop"))
                    store.record_approval(
                        post.item_id, outcome, "" if outcome == "drop" else title, None
                    )
                    if outcome != "drop":
                        thread = records[post.message_id][1]
                        approved[thread].append((MOMENT[0], post.item_id, title))
                discord.failures.extend(rng.choice(choices) for _ in range(rng.randrange(3)))
                store.queue_notified()
                for post in store.pending_posts():
                    if post.item_id not in chosen and post.card is None:
                        chosen[post.item_id] = latest(approved[records[post.message_id][1]])
                http = httpx.Client(transport=httpx.MockTransport(discord.handler))
                post_pending(store, settings, http)
                for post in store.pending_posts():
                    if post.card is None:
                        chosen.pop(post.item_id, None)
                discord.failures.clear()
                MOMENT[0] += timedelta(hours=1)
            for message_id, (record, _thread) in records.items():
                post = store.post("gmail", message_id)
                if post is None or post.card is None:
                    continue
                want = chosen[post.item_id]
                card = "first" if want is None else "followup"
                if (post.card, post.follows) != (card, None if want is None else want[0]):
                    got = f"{post.card}/{post.follows}"
                    return f"trial {trial}: {message_id} got {got}, want {want}"
                reached[card] += 1
                if want is not None and want[0] != store.post("gmail", "personal/m0").item_id:
                    reached["retargeted"] += 1
                if want is None:
                    body = checkpoint_message(record, UNDATED, post.item_id)
                else:
                    body = followup_message(record, UNDATED, post.item_id, want[1])
                sent = [
                    json.loads(r.content)
                    for r in discord.requests
                    if json.loads(r.content).get("nonce") == post.item_id[:25]
                ]
                if not sent or any(found != body for found in sent):
                    return f"trial {trial}: {message_id} sent another card"
    if min(reached.values()) < 10:
        return f"too few cases: {reached}"
    return True


def presses_follow_the_model() -> object:
    from mailroom.interactions import handle_interaction
    from mailroom.store import open_store
    from tests.integration.test_interactions import RECORD, VERDICT

    clock.now = lambda: START
    target, item = "f" * 32, "e" * 32
    title = VERDICT.extraction.title
    reached: dict[str, int] = {}
    names = ["full", "trust", "link", "yes", "edit", "notask", "mute"]
    names += ["approve", "change", "nodeadline", "drop"]
    for trial in range(200):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"press{trial}")
        ids.new_id = iter((target, item)).__next__
        settings = get_settings()
        state: dict = {"state": "open", "answer": None, "approval": None}
        with open_store(settings) as store:
            store.add(replace(RECORD, message_id="m0"))
            store.save_triage("gmail", "m0", VERDICT)
            store.add(RECORD)
            store.save_triage("gmail", "m1", VERDICT)
            store.queue_notified()
            store.record_answer(target, "yes", "Pay the October bill")
            store.record_approval(target, "nodeadline", "Pay the October bill", None)
            store.choose_card(item, "followup", follows=target)
            store.mark_posted(item, "1300000000000000001")
            for step in range(8):
                discord = FakeDiscord()
                if rng.random() < 0.85:
                    name = rng.choice(names)
                    sent = discord.press(f"mr:{name}:{item}")
                    want, after = press_model(state, name, title)
                else:
                    sent = discord.submit(f"mr:title:{item}", "Pay online")
                    want, after = state_after_title_form(state)
                http = httpx.Client(transport=httpx.MockTransport(discord.handler))
                got = handle_interaction(sent, store, settings, http)
                if got != want or len(discord.callbacks) != 1:
                    return f"trial {trial} step {step}: {got}, want {want} ({state['state']})"
                state = after
                reached[got] = reached.get(got, 0) + 1
                answer = store.answer(item)
                approval = store.approval(item)
                have = (
                    None if answer is None else (answer.answer, answer.title),
                    None if approval is None else (approval.outcome, approval.title, approval.due),
                )
                if have != (state["answer"], state["approval"]):
                    return f"trial {trial} step {step}: stored {have}, model {state}"
    for outcome in ("answered", "ignored", "already", "approved", "dropped", "form", "again"):
        if reached.get(outcome, 0) < 10:
            return f"too few {outcome}: {reached}"
    return True


def press_model(state: dict, name: str, title: str) -> tuple[str, dict]:
    """The spec's follow-up card, from its own table: open, waiting (after New task), closed."""
    if name == "full":
        return "full", state
    if name == "trust":
        return "trusted", state
    if state["state"] == "closed":
        return "already", state
    if state["state"] == "open":
        if name in ("edit", "approve", "change", "nodeadline", "drop"):
            return "ignored", state
        if name == "yes":
            return "answered", {"state": "waiting", "answer": ("yes", title), "approval": None}
        return "answered", {"state": "closed", "answer": (name, ""), "approval": None}
    # Waiting: checkpoint 2 as in Phase 2d, with no proposed deadline.
    if name in ("yes", "edit"):
        return "again", state
    if name in ("link", "notask", "mute"):
        return "already", state
    if name == "change":
        return "form", state
    if name == "approve":
        return "ignored", state
    if name == "nodeadline":
        decided = ("nodeadline", state["answer"][1], None)
        return "approved", {**state, "state": "closed", "approval": decided}
    return "dropped", {**state, "state": "closed", "approval": ("drop", "", None)}


def state_after_title_form(state: dict) -> tuple[str, dict]:
    """The title form is shown only by an open card's Yes without a title; here it answers."""
    if state["state"] != "open":
        return "already", state
    return "answered", {
        "state": "waiting",
        "answer": ("edit", "Pay online"),
        "approval": None,
    }


check("each post keeps the card chosen at its first send", posting_follows_the_latest_approval)
check("presses on the follow-up card follow the model", presses_follow_the_model)
print(f"FAILURES {FAILURES}")
