"""Probe for phase 2d. Run from the repository root: .venv/bin/python docs/verification/probe-02d.py

Each trial posts one card (with or without a proposed deadline) and sends 12 random events: any
button press, a title form, or a task form whose deadline comes from this probe's own table of
texts it knows the reading of (or knows to be unreadable). A model of the card's three states
(unanswered, waiting at checkpoint 2, closed) says what each event must return and what must be
stored. Every reply must be one Discord accepts (the fake checks it), and nothing is recorded for
checkpoint 2 without a Yes first, nor twice. Fakes only; everything lives in a temporary folder.
Each check prints `ok` or `FAIL`; the last line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe02d-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DISCORD_CHANNEL_ID"] = "111111111111111111"
os.environ["MAILROOM_DISCORD_OWNER_ID"] = "444444444444444444"
os.environ["MAILROOM_TIME_ZONE"] = "America/New_York"

import httpx  # noqa: E402

from mailroom import clock, ids  # noqa: E402
from mailroom.config import get_settings  # noqa: E402
from tests.fakes import FakeDiscord  # noqa: E402

FAILURES = 0
rng = random.Random(24)
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)  # Tuesday November 10, 04:00 in New York
ITEM = "c" * 32
# Deadline texts and their reading on Tuesday 2026-11-10 (None: unreadable).
TEXTS = {
    "": (None, None),
    "Friday": (date(2026, 11, 13), None),
    "Nov 21 at 9 am": (date(2026, 11, 21), time(9, 0)),
    "2026-11-20 5:00 pm": (date(2026, 11, 20), time(17, 0)),
    "tomorrow": (date(2026, 11, 11), None),
    "11/20": "unreadable",
    "next Friday": "unreadable",
    "soon": "unreadable",
}
TITLES = {"Pay online": "Pay online", "  Pay it  ": "Pay it", "Pay\nnow": None, "": None}
PRESSES = ["full", "yes", "edit", "notask", "mute", "trust", "approve", "change", "nodeadline"]
PRESSES += ["drop"]


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


def expected(state: dict, event: tuple, has_due: bool) -> tuple[str, dict]:
    """The outcome an event must return, and the state after it."""
    kind, name, title, text = event
    phase = state["phase"]
    if kind == "press" and name == "full":
        return "full", state
    if kind == "press" and name == "trust":
        return "trusted", state
    if phase == "closed":
        return (
            "ignored" if (kind, name) == ("form", "task") and state["answer"] is None else "already"
        ), state
    if kind == "form" and name == "title":
        if phase != "open":
            return "already", state
        if TITLES[title] is None:
            return "bad-title", state
        return "answered", {**state, "phase": "second", "answer": "edit", "title": TITLES[title]}
    if kind == "form":
        if phase == "open":
            return "ignored", state
        if TITLES[title] is None:
            return "bad-title", state
        if TEXTS[text] == "unreadable":
            return "bad-deadline", state
        due = None if TEXTS[text][0] is None else TEXTS[text]
        return "approved", {**state, "phase": "closed", "approval": ("change", TITLES[title], due)}
    if phase == "open":
        if name == "yes":
            return "answered", {
                **state,
                "phase": "second",
                "answer": "yes",
                "title": state["proposed"],
            }
        if name == "edit":
            return "form", state
        if name in ("notask", "mute"):
            return "answered", {**state, "phase": "closed", "answer": name}
        return "ignored", state
    if name in ("yes", "edit"):
        return "again", state
    if name in ("notask", "mute"):
        return "already", state
    if name == "change":
        return "form", state
    if name == "approve" and not has_due:
        return "ignored", state
    if name == "drop":
        return "dropped", {**state, "phase": "closed", "approval": ("drop", "", None)}
    due = state["due"] if name == "approve" else None
    return "approved", {**state, "phase": "closed", "approval": (name, state["title"], due)}


def random_event() -> tuple:
    if rng.random() < 0.7:
        return ("press", rng.choice(PRESSES), None, None)
    return (
        "form",
        rng.choice(("title", "task")),
        rng.choice(sorted(TITLES)),
        rng.choice(sorted(TEXTS)),
    )


start = {
    "phase": "open",
    "answer": None,
    "approval": None,
    "title": "",
    "proposed": "P",
    "due": None,
}
assert expected(start, ("press", "approve", None, None), True)[0] == "ignored"
second = expected(start, ("press", "yes", None, None), True)[1]
assert expected(second, ("press", "approve", None, None), False)[0] == "ignored"
assert expected(second, ("form", "task", "Pay online", "11/20"), True)[0] == "bad-deadline"
print("oracle self-check: ok")


def cards_follow_the_model() -> object:
    from mailroom.interactions import handle_interaction
    from mailroom.store import Due, open_store
    from tests.integration.test_interactions import RECORD, VERDICT

    clock.now = lambda: NOW
    reached: dict[str, int] = {}
    for trial in range(300):
        os.environ["MAILROOM_DATA_DIR"] = str(TMP / f"trial{trial}")
        ids.new_id = lambda: ITEM
        has_due = rng.random() < 0.6
        due = (date(2026, 11, 20), time(17, 0)) if has_due else None
        verdict = replace(VERDICT, due=Due(*due) if due else None)
        settings = get_settings()
        state = {**start, "proposed": VERDICT.extraction.title, "due": due}
        with open_store(settings) as store:
            store.add(RECORD)
            store.save_triage("gmail", "m1", verdict)
            store.queue_notified()
            store.mark_posted(ITEM, "1300000000000000001")
            for step in range(12):
                event = random_event()
                want, after = expected(state, event, has_due)
                discord = FakeDiscord()
                kind, name, title, text = event
                if kind == "press":
                    sent = discord.press(f"mr:{name}:{ITEM}")
                else:
                    action = "title" if name == "title" else "task"
                    fields = {"deadline": text} if name == "task" else {}
                    sent = discord.submit(f"mr:{action}:{ITEM}", title, fields=fields)
                http = httpx.Client(transport=httpx.MockTransport(discord.handler))
                got = handle_interaction(sent, store, settings, http)
                if got != want:
                    where = f"trial {trial} step {step} {event} from {state['phase']}"
                    return f"{where}: {got}, want {want}"
                if len(discord.callbacks) != 1:
                    return f"trial {trial} step {step} {event}: {len(discord.callbacks)} replies"
                state = after
                reached[got] = reached.get(got, 0) + 1
                stored = store.approval(ITEM)
                have = (
                    None
                    if stored is None
                    else (
                        stored.outcome,
                        stored.title,
                        None if stored.due is None else (stored.due.date, stored.due.time),
                    )
                )
                if have != state["approval"]:
                    return (
                        f"trial {trial} step {step} {event}: approval {have}, {state['approval']}"
                    )
                answered = store.answer(ITEM)
                if (None if answered is None else answered.answer) != state["answer"]:
                    return f"trial {trial} step {step} {event}: answer differs"
    for outcome in ("answered", "again", "approved", "dropped", "form", "bad-deadline", "already"):
        if reached.get(outcome, 0) < 10:
            return f"too few {outcome}: {reached}"
    return True


check(
    "every press and form follows the model and Discord accepts each reply", cards_follow_the_model
)
print(f"FAILURES {FAILURES}")
