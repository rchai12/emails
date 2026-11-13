"""Probe for phase 1k. Run from the repository root: .venv/bin/python docs/verification/probe-01k.py

It sends random sequences of /trust, /untrust, /trusted, /unmute and /muted (from the owner and
from others, in the channel and elsewhere, with good, odd and broken addresses, against lists of
up to 60 senders) to `handle_interaction`, and compares the sender lists with a model kept from
the commands alone. Every reply must be one Discord accepts, under 2,000 characters, private,
with mentions off. A list must show its addresses in order, inside one code block, followed by
a count of the rest. The database is in a temporary folder. Each check prints `ok` or `FAIL`;
the last line is `FAILURES N`.
"""

import os
import random
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01k-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
os.environ["MAILROOM_DISCORD_CHANNEL_ID"] = "111111111111111111"
os.environ["MAILROOM_DISCORD_OWNER_ID"] = "444444444444444444"

import httpx  # noqa: E402

from tests.fakes import FakeDiscord  # noqa: E402

FAILURES = 0
rng = random.Random(19)
ADDRESS = re.compile(r"[^@\s]+@[^@\s]+")


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


# The oracle: the address rule, and how a list should be shown.
def normal(address: str | None) -> str | None:
    if address is None:
        return None
    lowered = address.lower()
    return lowered if ADDRESS.fullmatch(lowered) and len(lowered) <= 254 else None


def listed(addresses: list[str]) -> tuple[list[str], int]:
    shown: list[str] = []
    for address in sorted(addresses):
        if len("\n".join([*shown, address])) > 1800:
            break
        shown.append(address)
    return shown, len(addresses) - len(shown)


assert normal("Sam@Example.TEST") == "sam@example.test"
assert normal("two@at@x") is None
assert normal(None) is None
assert listed(["b@x", "a@x"]) == (["a@x", "b@x"], 0)
assert listed(["a" * 900 + "@x"] * 3) == (["a" * 900 + "@x"], 2)
print("oracle self-check: ok")

try:
    from mailroom.config import get_settings
    from mailroom.interactions import handle_interaction
    from mailroom.store import open_store
except Exception as error:
    print(f"import: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)


def random_address(pool: list[str]) -> str | None:
    choice = rng.random()
    if choice < 0.5 and pool:
        address = rng.choice(pool)
        return address.upper() if rng.random() < 0.2 else address
    if choice < 0.8:
        name = rng.choice(["sam", "a`b", "x" * rng.randrange(1, 240), "naïve", "o'neil"])
        return f"{name}@example.test"
    return rng.choice(["not-an-address", "two@at@example.test", "a b@example.test", None, "@"])


def replies_follow_the_model() -> object:
    settings = get_settings()
    for trial in range(80):
        discord = FakeDiscord()
        http = httpx.Client(transport=httpx.MockTransport(discord.handler))
        status: dict[str, str] = {}
        pool: list[str] = []
        with open_store(settings) as store:
            for index in range(rng.choice([0, 3, 60])):
                address = f"{'s' * rng.randrange(1, 120)}{index}@example.test"
                kind = rng.choice(["trusted", "muted"])
                store.set_sender_status(address, kind)
                status[address] = kind
                pool.append(address)
            for _ in range(rng.randrange(1, 30)):
                name = rng.choice(["trust", "untrust", "trusted", "unmute", "muted"])
                owner = rng.random() < 0.85
                elsewhere = rng.random() < 0.1
                address = random_address(pool) if name in ("trust", "untrust", "unmute") else None
                event = discord.command(
                    name,
                    address,
                    user_id=None if owner else "555555555555555555",
                    channel_id="999999999999999999" if elsewhere else None,
                )
                got = handle_interaction(event, store, settings, http)
                body = discord.callbacks[-1][1]["data"]
                content = body["content"]
                if body.get("flags") != 64 or body.get("allowed_mentions") != {"parse": []}:
                    return f"trial {trial}: a reply that is not private or allows mentions"
                if len(content) > 2000:
                    return f"trial {trial}: a reply of {len(content)} characters"
                if not owner or elsewhere:
                    if got != "refused":
                        return f"trial {trial}: {name} from someone else gave {got!r}"
                    continue
                if name in ("trusted", "muted"):
                    kind = name
                    shown, more = listed([a for a, s in status.items() if s == kind])
                    if not shown and more == 0:
                        continue
                    inside = content.split("```\n", 1)[1].split("\n```", 1)[0]
                    if inside != "\n".join(a.replace("`", "ˋ") for a in shown):
                        return f"trial {trial}: /{name} showed the wrong addresses"
                    if (more > 0) != content.endswith(f"...and {more} more."):
                        return f"trial {trial}: /{name} miscounted the rest ({more})"
                    continue
                target = normal(address)
                if target is None:
                    if got != "bad-address":
                        return f"trial {trial}: /{name} {address!r} gave {got!r}"
                    continue
                want = {"trust": "trusted", "untrust": "untrusted", "unmute": "unmuted"}[name]
                if name == "trust":
                    status[target] = "trusted"
                    pool.append(target)
                elif status.get(target) == {"untrust": "trusted", "unmute": "muted"}[name]:
                    del status[target]
                else:
                    want = "unchanged"
                if got != want:
                    return f"trial {trial}: /{name} {address!r} gave {got!r}, want {want!r}"
            for kind in ("trusted", "muted"):
                if store.senders(kind) != tuple(sorted(a for a, s in status.items() if s == kind)):
                    return f"trial {trial}: the {kind} list differs from the model"
        if len(discord.callbacks) != len(discord.requests):
            return f"trial {trial}: a reply Discord refused"
        (TMP / "data" / "mailroom.sqlite3").unlink()
    return True


check("commands follow the model and every reply fits", replies_follow_the_model)
print(f"FAILURES {FAILURES}")
