"""Independent rotated-token probe: seeded round/restart/login scripts, synthetic data only."""

import argparse
import os
import random
import re
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

KINDS = ("saved", "refused", "restart", "login", "token-503")
TRIALS = 40
STEPS = 12
OWNER = "444444444444444444"
NAME = ("mailroom", "outlook.live.refresh-token")
UNSAVED = (
    f"<@{OWNER}> Outlook live got a new sign-in that the Keychain would not save. "
    "Mailroom keeps it in memory and tries again each round. "
    "If Mailroom stops before then, run: mailroom outlook-login live"
)
SAVED = "Outlook live works again and its sign-in is saved."
SIGN_IN = f"<@{OWNER}> Outlook sign-in needed for live. Run: mailroom outlook-login live"
FIXED = "Outlook live works again."
LINES = {
    "ok": "outlook live: ok",
    "unsaved": "outlook live: outlook new sign-in not saved: live",
    "signin": "outlook live: outlook sign-in needed: live",
    "unavailable": "outlook live: outlook unavailable: live (503)",
}
SECRET = re.compile(r"refresh-token-\d|access-\d")
START = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
LIFETIME = timedelta(seconds=3600 - 60)


def times(steps: list[str]) -> list[datetime]:
    """When each step happens: rounds alternate 5 minutes and 2 hours after the one before."""
    moment, out = START, []
    for index, kind in enumerate(steps):
        if kind not in ("restart", "login"):
            moment += timedelta(minutes=5) if index % 2 else timedelta(hours=2)
        out.append(moment)
    return out


def scripts() -> list[list[str]]:
    rng = random.Random(408)
    corpus = []
    for trial in range(TRIALS):
        steps = ["refused"] if trial % 2 else [rng.choice(("saved", "refused"))]
        for step in range(1, STEPS):
            steps.append(KINDS[(trial + step) % len(KINDS)] if step % 3 == 0 else rng.choice(KINDS))
        corpus.append(steps)
    return corpus


class Oracle:
    """What Graph, the Keychain and the owner's channel must hold after each step."""

    def __init__(self) -> None:
        self.graph = 1
        self.keychain = 1
        self.held: int | None = None
        self.until: datetime | None = None
        self.open_unsaved = False
        self.open_signin = False
        self.posts: list[str] = []
        self.sent: list[int] = []
        self.status = ""

    def step(self, kind: str, now: datetime) -> None:
        if kind == "restart":
            self.held = self.until = None
            return
        if kind == "login":
            if self.open_signin:
                self.keychain = self.graph
            return
        refuse = kind == "refused"
        self.status = self._round(refuse, kind == "token-503", now)
        if self.status == "unsaved" and not self.open_unsaved:
            self.open_unsaved = True
            self.posts.append(UNSAVED)
        if self.status == "signin" and not self.open_signin:
            self.open_signin = True
            self.posts.append(SIGN_IN)
        if self.status == "ok":
            resolved = []
            if self.open_signin:
                resolved.append(FIXED)
            if self.open_unsaved:
                resolved.append(SAVED)
            self.posts.extend(resolved)
            self.open_signin = self.open_unsaved = False

    def _round(self, refuse: bool, token_503: bool, now: datetime) -> str:
        if self.held is not None:
            if refuse:
                return "unsaved"
            self.keychain, self.held = self.held, None
        if self.until is not None and now < self.until:
            return "ok"
        self.until = None
        self.sent.append(self.keychain)
        if token_503:
            return "unavailable"
        if self.keychain != self.graph:
            return "signin"
        self.graph += 1
        if refuse:
            self.held = self.graph
            return "unsaved"
        self.keychain = self.graph
        self.until = now + LIFETIME
        return "ok"


def oracle_self_check(corpus: list[list[str]]) -> None:
    assert len(corpus) == TRIALS
    flat = [kind for steps in corpus for kind in steps]
    assert all(flat.count(kind) >= 40 for kind in KINDS)
    lost = recovered = signed_in = quiet = 0
    for steps in corpus:
        oracle = Oracle()
        for kind, now in zip(steps, times(steps), strict=True):
            before = oracle.held
            sent = len(oracle.sent)
            oracle.step(kind, now)
            quiet += kind == "refused" and oracle.status == "ok" and len(oracle.sent) == sent
            lost += kind == "restart" and before is not None
            recovered += kind == "saved" and before is not None and oracle.held is None
            signed_in += oracle.status == "ok" and FIXED in oracle.posts[-2:]
    assert lost >= 10 and recovered >= 10 and signed_in >= 5 and quiet >= 5
    check = Oracle()
    for kind in ("refused", "refused", "saved"):
        check.step(kind, START)
    assert (check.status, check.posts, check.keychain) == ("ok", [UNSAVED, SAVED], 3)
    assert check.sent == [1, 2]
    check = Oracle()
    for kind in ("refused", "token-503", "saved"):
        check.step(kind, START)
    assert (check.status, check.posts, check.sent) == ("ok", [UNSAVED, SAVED], [1, 2, 2])
    check = Oracle()
    for kind in ("refused", "restart", "saved"):
        check.step(kind, START)
    assert (check.status, check.posts, check.sent) == ("signin", [UNSAVED, SIGN_IN], [1, 1])


def run_trial(steps: list[str], folder: Path, index: int) -> list[str]:
    """Runs one script through real service rounds; returns the invariants it broke."""
    import httpx
    import keyring.core
    import keyring.errors

    from mailroom import clock
    from mailroom.config import get_settings
    from mailroom.service import Health, run_round
    from mailroom.store import open_store
    from tests.fakes import FakeKeychain
    from tests.integration.test_service_outlook import BothWorld

    class Keychain(FakeKeychain):
        refuse = False

        def set_password(self, service: str, username: str, password: str) -> None:
            if self.refuse:
                raise keyring.errors.KeyringError("probe")
            super().set_password(service, username, password)

    moment = [START]
    clock.now = lambda: moment[0]
    keychain = Keychain()
    keyring.core._keyring_backend = keychain
    os.environ["MAILROOM_DATA_DIR"] = str(folder / f"data-{index}")
    settings = get_settings()
    store = open_store(settings)
    world = BothWorld(keychain, ())
    lines: list[str] = []
    health = Health(lines.append)
    oracle = Oracle()
    client = None
    broken: list[str] = []
    seen_posts: list[str] = []
    shown_posts: list[str] = []
    wanted_posts: list[str] = []
    for kind, now in zip(steps, times(steps), strict=True):
        expected_before = len(oracle.posts)
        oracle.step(kind, now)
        if kind == "restart":
            client = None
            continue
        if kind == "login":
            if oracle.open_signin:
                keychain.secrets[NAME] = world.graph.refresh_token
            continue
        if client is None:
            client = world.outlook()
        keychain.refuse = kind == "refused"
        if kind == "token-503":
            world.graph.token_failures.append(httpx.Response(503))
        moment[0] = now
        api_before = sum(r.url.host == "graph.microsoft.com" for r in world.graph.requests)
        run_round(
            store,
            settings,
            [client],
            world.model_http(),
            world.discord_http(),
            world.tasks_http(),
            health,
        )
        world.graph.token_failures.clear()
        api_after = sum(r.url.host == "graph.microsoft.com" for r in world.graph.requests)
        shown = [line for line in lines if line.startswith("outlook ")]
        if not shown or shown[-1] != LINES[oracle.status]:
            broken.append(f"status-{oracle.status}")
        if oracle.status != "ok" and api_after != api_before:
            broken.append("mail-read-unsaved")
        if keychain.secrets[NAME] != f"refresh-token-{oracle.keychain}":
            broken.append("keychain-token")
        if world.graph.refresh_token != f"refresh-token-{oracle.graph}":
            broken.append("graph-token")
        posts = [m["content"] for m in world.discord.messages if m["content"]]
        shown_posts += sorted(posts[len(seen_posts) :])
        wanted_posts += sorted(oracle.posts[expected_before:])
        seen_posts = posts
        if shown_posts != wanted_posts:
            broken.append("alerts")
        sent = [
            dict(httpx.QueryParams(r.content.decode()))["refresh_token"]
            for r in world.graph.requests
            if r.url.host == "login.microsoftonline.com"
        ]
        if sent != [f"refresh-token-{n}" for n in oracle.sent]:
            broken.append("sent-tokens")
        if any(SECRET.search(text) for text in lines + posts):
            broken.append("token-text")
    store.close()
    return broken


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-only", action="store_true")
    args = parser.parse_args()
    corpus = scripts()
    oracle_self_check(corpus)
    print("oracle self-check: ok")
    if args.oracle_only:
        print("FAILURES 0")
        return 0
    failures = 0
    counts: dict[str, int] = {}
    reached = 0
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04h-trials-") as scratch:
        for index, steps in enumerate(corpus):
            try:
                broken = run_trial(steps, Path(scratch), index)
                reached += 1
            except Exception as error:
                broken = [f"raised {type(error).__name__}"]
            for name in broken:
                counts[name] = counts.get(name, 0) + 1
    print(f"trials reached: {reached} of {TRIALS}")
    if counts:
        detail = ", ".join(f"{name} x{count}" for name, count in sorted(counts.items()))
        print(f"rotation invariants: FAIL ({detail})")
        failures += 1
    else:
        print(f"rotation invariants across {TRIALS} seeded scripts: ok")
    print(f"FAILURES {failures}")
    return int(bool(failures))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04h-") as folder:
        env = {key: value for key, value in os.environ.items() if not key.startswith("MAILROOM_")}
        env.update(
            HOME=folder,
            MAILROOM_DATA_DIR=str(Path(folder) / "data"),
            MAILROOM_OUTLOOK_ACCOUNTS="live",
            MAILROOM_EXTRACTOR_MODEL="qwen-test:27b",
            MAILROOM_TIME_ZONE="America/New_York",
            MAILROOM_DISCORD_CHANNEL_ID="111111111111111111",
            MAILROOM_DISCORD_OWNER_ID=OWNER,
        )
        with patch.dict(os.environ, env, clear=True):
            sys.exit(main())
