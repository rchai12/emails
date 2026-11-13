"""Probe for phase 2e. Run from the repository root: .venv/bin/python docs/verification/probe-02e.py

1. Posting: each trial triages a few emails, clearly dated or not, with deadlines a few hours to
   days ahead, then posts them in rounds an hour apart while Discord fails at random (503, a
   network error, a lost reply). Each post's card must be the one the probe's oracle chose at
   that post's first send attempt: combined when clearly dated, with text, and not yet due;
   checkpoint 1 otherwise. It must never change on a retry, and each email must make exactly one
   Discord message, whose content is that card.
2. Presses: combined cards take random presses and task forms. A two-state model (open, closed)
   says each outcome, and the stored answer and approval must match it after every step.
Fakes only; everything lives in a temporary folder. Each check prints `ok` or `FAIL`; the last
line is `FAILURES N`.
"""

import json
import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe02e-"))
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
rng = random.Random(25)
ZONE = ZoneInfo("America/New_York")
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


def passed(due: tuple[date, time | None], now: datetime) -> bool:
    """The probe's own reading of 'passed', from Requirement 1 of Phase 2b's rule."""
    local = now.astimezone(ZONE)
    if due[1] is None:
        return due[0] < local.date()
    return datetime.combine(due[0], due[1], ZONE) <= local


assert passed((date(2026, 11, 20), time(17, 0)), datetime(2026, 11, 20, 22, 0, tzinfo=UTC))
assert not passed((date(2026, 11, 20), None), datetime(2026, 11, 21, 4, 59, tzinfo=UTC))
print("oracle self-check: ok")


def posting_keeps_the_first_choice() -> object:
    from mailroom.checkpoint import checkpoint_message, combined_message
    from mailroom.discord_post import post_pending
    from mailroom.store import Due, Verdict, open_store
    from tests.integration.test_triage import EXTRACTION, RECORD

    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    clock.now = lambda: MOMENT[0]
    reached = {"combined": 0, "first": 0, "changed-mind": 0}
    for trial in range(80):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"post{trial}")
        MOMENT[0] = START
        discord = FakeDiscord()
        keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
        settings = get_settings()
        chosen: dict[str, str] = {}
        verdicts = {}
        with open_store(settings) as store:
            for number in range(rng.randrange(2, 6)):
                ahead = timedelta(minutes=rng.choice((50, 50, 90, 180, 600)))
                local = (START + ahead).astimezone(ZONE).replace(second=0, microsecond=0)
                due = (local.date(), local.time() if rng.random() < 0.6 else None)
                verdict = Verdict(
                    outcome="extracted",
                    trusted=False,
                    verified=True,
                    bulk=False,
                    notify=True,
                    extraction=EXTRACTION,
                    dated=rng.random() < 0.7,
                    due=Due(*due),
                )
                message_id = f"personal/m{number}"
                store.add(replace(RECORD, message_id=message_id))
                store.save_triage("gmail", message_id, verdict)
                verdicts[message_id] = (verdict, due)
            for round_number in range(10):
                choices = (None, None, httpx.Response(503), "lost-reply", httpx.ConnectError("x"))
                if round_number == 0:
                    # The first post fails, so the others first send an hour later.
                    discord.failures.append(httpx.Response(503))
                else:
                    discord.failures.extend(rng.choice(choices) for _ in range(rng.randrange(3)))
                store.queue_notified()
                for post in store.pending_posts():
                    if post.item_id not in chosen and post.card is None:
                        verdict, due = verdicts[post.message_id]
                        want = (
                            "combined" if verdict.dated and not passed(due, MOMENT[0]) else "first"
                        )
                        chosen[post.item_id] = want
                http = httpx.Client(transport=httpx.MockTransport(discord.handler))
                post_pending(store, settings, http)
                for post in store.pending_posts():
                    if post.card is None and post.item_id in chosen:
                        del chosen[post.item_id]
                discord.failures.clear()
                MOMENT[0] += timedelta(hours=1)
            for post in [store.post("gmail", m) for m in verdicts]:
                if post is None or post.posted_at is None:
                    continue
                verdict, due = verdicts[post.message_id]
                if post.card != chosen.get(post.item_id):
                    return f"trial {trial}: card {post.card}, chosen {chosen.get(post.item_id)}"
                if verdict.dated and post.card == "first":
                    reached["changed-mind"] += 1
                reached[post.card] += 1
                record = replace(RECORD, message_id=post.message_id)
                build = combined_message if post.card == "combined" else checkpoint_message
                want_body = build(record, verdict, post.item_id)
                bodies = [
                    json.loads(r.content)
                    for r in discord.requests
                    if json.loads(r.content).get("nonce") == post.item_id[:25]
                ]
                if not bodies or any(body != want_body for body in bodies):
                    return f"trial {trial}: {post.message_id} sent a different card"
            nonces = [message["nonce"] for message in discord.messages]
            if len(nonces) != len(set(nonces)):
                return f"trial {trial}: an email made two messages"
    if min(reached.values()) < 5:
        return f"too few cases: {reached}"
    return True


def presses_follow_the_model() -> object:
    from mailroom.interactions import handle_interaction
    from mailroom.store import Due, open_store
    from tests.integration.test_interactions import RECORD, VERDICT

    clock.now = lambda: START
    item = "e" * 32
    texts = {"": None, "Friday": (date(2026, 11, 13), None), "11/20": "bad"}
    reached: dict[str, int] = {}
    for trial in range(200):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"press{trial}")
        ids.new_id = lambda: item
        due = Due(date(2026, 11, 20), time(17, 0))
        verdict = replace(VERDICT, dated=True, due=due)
        settings = get_settings()
        state: dict = {"closed": False, "answer": None, "approval": None}
        with open_store(settings) as store:
            store.add(RECORD)
            store.save_triage("gmail", "m1", verdict)
            store.queue_notified()
            store.choose_card(item, "combined")
            store.mark_posted(item, "1300000000000000001")
            for step in range(8):
                discord = FakeDiscord()
                if rng.random() < 0.75:
                    name = rng.choice(
                        ["full", "trust", "yes", "edit", "drop", "approve", "change", "nodeadline"]
                        + ["notask", "mute"]
                    )
                    sent = discord.press(f"mr:{name}:{item}")
                    want, after = press_model(state, name, verdict.extraction.title, due)
                else:
                    form = rng.choice(("task", "title"))
                    text = rng.choice(sorted(texts))
                    sent = discord.submit(
                        f"mr:{form}:{item}", "Pay online", fields={"deadline": text}
                    )
                    want, after = form_model(state, form, texts[text])
                http = httpx.Client(transport=httpx.MockTransport(discord.handler))
                got = handle_interaction(sent, store, settings, http)
                if got != want or len(discord.callbacks) != 1:
                    return f"trial {trial} step {step}: {got}, want {want}"
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
    for outcome in ("approved", "answered", "form", "ignored", "already", "bad-deadline"):
        if reached.get(outcome, 0) < 10:
            return f"too few {outcome}: {reached}"
    return True


def press_model(state: dict, name: str, title: str, due) -> tuple[str, dict]:
    if name == "full":
        return "full", state
    if name == "trust":
        return "trusted", state
    if state["closed"]:
        return "already", state
    if name in ("yes", "edit", "drop"):
        return "ignored", state
    if name == "change":
        return "form", state
    if name in ("notask", "mute"):
        return "answered", {"closed": True, "answer": (name, ""), "approval": None}
    kept = due if name == "approve" else None
    return "approved", {
        "closed": True,
        "answer": ("yes", title),
        "approval": (name, title, kept),
    }


def form_model(state: dict, form: str, reading) -> tuple[str, dict]:
    if state["closed"]:
        return "already", state
    if form == "title":
        return "ignored", state
    if reading == "bad":
        return "bad-deadline", state
    from mailroom.store import Due

    due = None if reading is None else Due(*reading)
    return "approved", {
        "closed": True,
        "answer": ("edit", "Pay online"),
        "approval": ("change", "Pay online", due),
    }


check("each post keeps the card chosen at its first send, once", posting_keeps_the_first_choice)
check("presses on the combined card follow the model", presses_follow_the_model)
print(f"FAILURES {FAILURES}")
