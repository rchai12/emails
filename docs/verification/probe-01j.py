"""Probe for phase 1j. Run from the repository root: .venv/bin/python docs/verification/probe-01j.py

It runs `run_gateway` against the fake Gateway through random chains of trouble: refused
connections, drops, missing ACKs, Reconnect, Invalid Session, closes that end the session, and
fatal closes, each acting right after READY or RESUMED. It compares what the client did with
a model: which address each connection used, whether it resumed or identified, how long it
waited, when it stopped, and that every press reached the handler exactly once. It also checks
that heartbeats never lapsed, that the send limit was never hit, and that the token was never in
an address. The database is in a temporary folder. Each check prints `ok` or `FAIL`; the last
line is `FAILURES N`.
"""

import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01j-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
os.environ["MAILROOM_DISCORD_CHANNEL_ID"] = "111111111111111111"
os.environ["MAILROOM_DISCORD_OWNER_ID"] = "444444444444444444"

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from mailroom.record import Record  # noqa: E402
from tests.fakes import FakeDiscord, FakeGateway, FakeKeychain  # noqa: E402

FAILURES = 0
rng = random.Random(18)
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
RESUME_AT = "wss://gateway-us-east1-b.discord.gg/?v=10&encoding=json"
BACKOFF = (1, 2, 4, 8, 16, 32, 60)
FATAL = (4004, 4010, 4011, 4012, 4013, 4014)


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


# The oracle, from the plans alone: per connection, the address and first op; the sleeps; the end.
def model(plans: list[dict]) -> tuple[list[tuple[str, int | None]], list[int], int | None]:
    session, waits, attempts, connections = False, 0, [], []
    for plan in plans + [{}]:
        if connections or attempts:
            attempts.append(BACKOFF[min(waits, 6)])
            waits += 1
        if plan.get("refuse"):
            connections.append((RESUME_AT if session else GATEWAY, None))
            continue
        connections.append((RESUME_AT if session else GATEWAY, 6 if session else 2))
        session, waits = True, 0
        then = plan.get("then")
        if (then is None and not plan.get("no_ack")) or then == ("heartbeat",):
            return connections, attempts, None
        if then and then[0] == "close" and then[1] in FATAL:
            return connections, attempts, then[1]
        if then and (
            then in (("invalid", False),) or (then[0] == "close" and then[1] in (1000, 1001))
        ):
            session = False
    return connections, attempts, None


assert model([]) == ([(GATEWAY, 2)], [], None)
assert model([{"refuse": True}]) == ([(GATEWAY, None), (GATEWAY, 2)], [1], None)
assert model([{"then": ("close", 1006)}]) == ([(GATEWAY, 2), (RESUME_AT, 6)], [1], None)
assert model([{"then": ("invalid", False)}]) == ([(GATEWAY, 2), (GATEWAY, 2)], [1], None)
assert model([{"then": ("close", 4004)}]) == ([(GATEWAY, 2)], [], 4004)
assert model([{"refuse": True}, {"refuse": True}, {"no_ack": True}])[1] == [1, 2, 1]
assert model([{"then": ("heartbeat",)}, {"then": ("close", 4004)}])[2] is None
print("oracle self-check: ok")

try:
    from mailroom.config import get_settings
    from mailroom.extractor import Extraction
    from mailroom.gateway import GatewayStopped, run_gateway
    from mailroom.store import Verdict, open_store
except Exception as error:
    print(f"import: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)

RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your bill",
    sent_at=None,
    body_text="Your bill is due.",
    list_unsubscribe=False,
    authentication_results=(),
)
EXTRACTION = Extraction("A bill.", True, False, "Pay", None, False, "", "high")


def random_plan() -> dict:
    kind = rng.choice(["refuse", "no_ack", "close", "close", "reconnect", "invalid", "heartbeat"])
    after = 0
    if kind == "refuse":
        return {"refuse": True}
    if kind == "no_ack":
        return {"no_ack": True}
    if kind == "close":
        return {"then": ("close", rng.choice([1000, 1001, 1006, 4000, 4008, 4009])), "after": after}
    if kind == "invalid":
        return {"then": ("invalid", rng.random() < 0.5), "after": after}
    if kind == "reconnect":
        return {"then": ("reconnect",), "after": after}
    return {"then": ("heartbeat",), "after": after}


def the_client_follows_the_model() -> object:
    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    for trial in range(150):
        gateway = FakeGateway(until=50_000)
        clock.now = gateway.now
        keychain.secrets[("mailroom", "discord.bot-token")] = gateway.token
        discord = FakeDiscord()
        settings = get_settings()
        plans = [random_plan() for _ in range(rng.randrange(0, 7))]
        if rng.random() < 0.15:
            plans.append({"then": ("close", rng.choice(FATAL))})
        gateway.plans = plans
        with open_store(settings) as store:
            store.add(replace(RECORD, message_id=f"m{trial}"))
            store.save_triage(
                "gmail", f"m{trial}", Verdict("extracted", False, True, False, True, EXTRACTION)
            )
            store.queue_notified()
            (post,) = store.pending_posts()
            store.mark_posted(post.item_id, "1300000000000000001")
            presses = rng.randrange(0, 12)
            for _ in range(presses):
                gateway.events.append(
                    ("INTERACTION_CREATE", discord.press(f"mr:full:{post.item_id}"))
                )
                if rng.random() < 0.3:
                    gateway.events.append(("TYPING_START", {"channel_id": "1"}))
            want_connections, want_sleeps, want_stop = model(plans)
            if want_stop is None:
                gateway.until = gateway.seconds() + 2_000 + sum(want_sleeps)
            stopped = None
            http = httpx.Client(transport=httpx.MockTransport(discord.handler))
            try:
                run_gateway(
                    store,
                    settings,
                    http,
                    connect=gateway.connect,
                    sleep=gateway.sleep,
                    rng=random.Random(trial),
                    stop=lambda gateway=gateway: gateway.done,
                )
            except GatewayStopped as error:
                stopped = int(str(error).split("(")[1].rstrip(")"))
        got_connections = [
            (c.url, c.sent[0][1]["op"] if c.sent else None) for c in gateway.connections
        ]
        if (got_connections, gateway.sleeps, stopped) != (want_connections, want_sleeps, want_stop):
            return (
                f"trial {trial} plans {plans}: got {got_connections} {gateway.sleeps} {stopped}, "
                f"want {want_connections} {want_sleeps} {want_stop}"
            )
        delivered = presses - sum(1 for name, _ in gateway.events if name == "INTERACTION_CREATE")
        if len(discord.callbacks) != delivered:
            return f"trial {trial}: {len(discord.callbacks)} replies for {delivered} presses"
        for connection in gateway.connections:
            if connection.close_code in (4002, 4007, 4008):
                return f"trial {trial}: the fake closed {connection.close_code}"
            if gateway.token in connection.url:
                return f"trial {trial}: the token is in an address"
            beats = [at for at, payload in connection.sent if payload["op"] == 1]
            for earlier, later in zip(beats, beats[1:], strict=False):
                if later - earlier > gateway.heartbeat_interval / 1000 + 1:
                    return f"trial {trial}: heartbeats lapsed between {earlier} and {later}"
        (TMP / "data" / "mailroom.sqlite3").unlink()
    return True


check(
    "the client resumes, identifies, waits and stops as the model says",
    the_client_follows_the_model,
)
print(f"FAILURES {FAILURES}")
