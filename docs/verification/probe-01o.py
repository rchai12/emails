"""Probe for phase 1o. Run from the repository root: .venv/bin/python docs/verification/probe-01o.py

1. Statements: with SQLite's trace on, `open_problem`, `queue_alert` and `close_problem` each run
   one write and never read their table before it.
2. Races: two stores on one file take random turns opening, alerting and closing problems and
   queueing alerts. On a clock read inside one store's call, the other store sometimes writes
   first. A model built from the turns alone says what each call returns and what the file holds
   at the end. Nothing may raise.
3. Sending: `send_messages` runs rounds over random items while Discord fails at random, until
   every item is sent. Each item is marked once, in order, with the id Discord gave it, and each
   report adds up.
Fakes only; everything lives in a temporary folder. Each check prints `ok` or `FAIL`; the last
line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01o-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
os.environ["MAILROOM_DISCORD_CHANNEL_ID"] = "111111111111111111"

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from mailroom.config import get_settings  # noqa: E402
from mailroom.store import open_store  # noqa: E402
from tests.fakes import FakeDiscord, FakeKeychain  # noqa: E402

FAILURES = 0
rng = random.Random(15)
START = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
KEYS = ("model", "gmail-auth:personal", "gateway")
ALERT_KEYS = ("a1", "a2", "a3")


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


# The model: problems map key -> [since, alerted]; alerts map key -> (text, ping).
def apply(model: dict, op: tuple, moment: datetime) -> object:
    problems, alerts = model["problems"], model["alerts"]
    kind, key = op[0], op[1]
    if kind == "open":
        problems.setdefault(key, [moment, False])
        return (key, problems[key][0], problems[key][1])
    if kind == "mark":
        if key in problems:
            problems[key][1] = True
        return None
    if kind == "close":
        found = problems.pop(key, None)
        return None if found is None else (key, found[0], found[1])
    if key in alerts:
        return False
    alerts[key] = (op[2], op[3])
    return True


def run(store, op: tuple) -> object:
    kind, key = op[0], op[1]
    if kind == "open":
        found = store.open_problem(key)
        return (found.key, found.since, found.alerted)
    if kind == "mark":
        store.mark_alerted(key)
        return None
    if kind == "close":
        found = store.close_problem(key)
        return None if found is None else (found.key, found.since, found.alerted)
    return store.queue_alert(key, op[2], op[3])


def random_op() -> tuple:
    kind = rng.choice(("open", "open", "mark", "close", "queue"))
    if kind == "queue":
        return ("queue", rng.choice(ALERT_KEYS), f"text {rng.randrange(1000)}", rng.random() < 0.5)
    return (kind, rng.choice(KEYS))


model_check: dict = {"problems": {}, "alerts": {}}
assert apply(model_check, ("open", "k"), START) == ("k", START, False)
assert apply(model_check, ("open", "k"), START + timedelta(1)) == ("k", START, False)
assert apply(model_check, ("mark", "k"), START) is None
assert apply(model_check, ("close", "k"), START) == ("k", START, True)
assert apply(model_check, ("close", "k"), START) is None
assert apply(model_check, ("queue", "a", "t", True), START) is True
assert apply(model_check, ("queue", "a", "u", False), START) is False
assert model_check == {"problems": {}, "alerts": {"a": ("t", True)}}
print("oracle self-check: ok")


def fresh_folder(name: str) -> None:
    """A data folder of its own, so a check that stops early leaves nothing for the next."""
    os.environ["MAILROOM_DATA_DIR"] = str(TMP / name)


def one_write_and_no_read_first() -> object:
    fresh_folder("statements")
    with open_store(get_settings()) as store:
        seen: list[str] = []
        store._connection.set_trace_callback(seen.append)
        clock.now = lambda: START
        for op in [("open", "model"), ("open", "model"), ("close", "model"), ("close", "model")]:
            op_seen = len(seen)
            run(store, op)
            statements = [s.split()[0].upper() for s in seen[op_seen:] if s.strip()]
            writes = [s for s in statements if s in ("INSERT", "DELETE", "UPDATE")]
            before = statements[: statements.index(writes[0])] if writes else statements
            if len(writes) != 1 or "SELECT" in before:
                return f"{op}: {statements}"
        for op in [("queue", "a1", "t", False), ("queue", "a1", "u", True)]:
            op_seen = len(seen)
            run(store, op)
            statements = [s.split()[0].upper() for s in seen[op_seen:] if s.strip()]
            writes = [s for s in statements if s in ("INSERT", "DELETE", "UPDATE")]
            if len(writes) != 1 or "SELECT" in statements[: statements.index(writes[0])]:
                return f"{op}: {statements}"
        store._connection.set_trace_callback(None)
    return True


def races_match_the_model() -> object:
    raced_ops = 0
    for trial in range(120):
        model: dict = {"problems": {}, "alerts": {}}
        fresh_folder(f"race{trial}")
        with open_store(get_settings()) as first, open_store(get_settings()) as second:
            stores = (first, second)
            for turn in range(40):
                moment = START + timedelta(minutes=turn)
                mine = rng.randrange(2)
                op = random_op()
                other = random_op() if rng.random() < 0.5 else None
                state = {"fired": False}

                def now(moment=moment, other=other, theirs=stores[1 - mine], state=state):
                    if other is not None and not state["fired"]:
                        state["fired"] = True
                        run(theirs, other)
                        return moment
                    return moment + timedelta(seconds=1) if state["fired"] else moment

                clock.now = now
                got = run(stores[mine], op)
                if state["fired"]:
                    raced_ops += 1
                    apply(model, other, moment + timedelta(seconds=1))
                want = apply(model, op, moment)
                if got != want:
                    return f"trial {trial} turn {turn}: {op} after {other} gave {got}, want {want}"
            for store in stores:
                for key in KEYS:
                    found = store.problem(key)
                    have = None if found is None else [found.since, found.alerted]
                    if have != model["problems"].get(key):
                        return f"trial {trial}: problem {key} is {have}"
                pending = {a.key: (a.text, a.ping) for a in store.pending_alerts()}
                if pending != model["alerts"]:
                    return f"trial {trial}: alerts {pending}, want {model['alerts']}"
    if raced_ops < 500:
        return f"only {raced_ops} raced calls"
    return True


def sending_matches_discord() -> object:
    from mailroom.discord_post import send_messages

    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    settings = get_settings()
    choices = [
        None,
        None,
        None,
        httpx.Response(429, json={"message": "Slow down.", "retry_after": 1.0}),
        httpx.Response(500, text="oops"),
        httpx.ConnectError("refused"),
        "lost-reply",
        httpx.Response(200, json={"channel_id": "111111111111111111"}),
    ]
    stops = {"", "network", "response", "429", "500"}
    for trial in range(200):
        discord = FakeDiscord()
        keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
        items = [f"item{trial}-{n}" for n in range(rng.randrange(0, 6))]
        marked: list[tuple[str, str]] = []
        for _ in range(60):
            remaining = items[len(marked) :]
            discord.failures.extend(rng.choice(choices) for _ in range(rng.randrange(3)))
            built: list[str] = []

            def body(item: str, built=built) -> dict[str, object]:
                built.append(item)
                return {
                    "content": item,
                    "allowed_mentions": {"parse": []},
                    "nonce": item,
                    "enforce_nonce": True,
                }

            http = httpx.Client(transport=httpx.MockTransport(discord.handler))
            report = send_messages(
                settings, http, remaining, body, lambda i, m, marked=marked: marked.append((i, m))
            )
            if report.posted + report.waiting != len(remaining) or report.stopped not in stops:
                return f"trial {trial}: report {report} for {len(remaining)} items"
            if (report.stopped == "") != (report.waiting == 0):
                return f"trial {trial}: report {report}"
            expected_built = remaining if not report.stopped else remaining[: report.posted + 1]
            if built != expected_built:
                return f"trial {trial}: built {built}, want {expected_built}"
            if not remaining:
                break
            discord.failures.clear()
        by_nonce = {message["nonce"]: message["id"] for message in discord.messages}
        if marked != [(item, by_nonce.get(item)) for item in items]:
            return f"trial {trial}: marked {marked}"
        if len(discord.messages) != len(items):
            return f"trial {trial}: {len(discord.messages)} messages for {len(items)} items"
    return True


check("each write is one statement with no read before it", one_write_and_no_read_first)
check("two racing stores match the model and never raise", races_match_the_model)
check("sending marks each item once with Discord's id", sending_matches_discord)
print(f"FAILURES {FAILURES}")
