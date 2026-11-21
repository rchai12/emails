"""Independent listener-supervision probe: seeded failure scripts, synthetic fakes only."""

import argparse
import os
import random
import sqlite3
import sys
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

PRIVATE = "probe-private-subject"
WAITS = (1, 2, 4, 8, 16, 32, 60)
KINDS = ("bug", "key", "database", "keychain", "return")
TERMINALS = ("fatal", "unconfigured", "missing")
TRIALS = 48


def scripts() -> list[tuple[list[str], str]]:
    rng = random.Random(406)
    result = []
    for trial in range(TRIALS):
        count = 9 if trial % 12 == 5 else rng.randrange(0, 7)
        kinds = [KINDS[(trial + n) % len(KINDS)] for n in range(count)]
        rng.shuffle(kinds)
        end = TERMINALS[trial % 3] if trial % 4 == 0 else "hold"
        result.append((kinds, end))
    return result


def expected_delays(count: int) -> list[int]:
    return [WAITS[min(n, len(WAITS) - 1)] for n in range(count)]


def oracle_self_check(corpus: list[tuple[list[str], str]]) -> None:
    assert len(corpus) == TRIALS
    assert expected_delays(0) == []
    assert expected_delays(9) == [1, 2, 4, 8, 16, 32, 60, 60, 60]
    seen = [kind for kinds, _ in corpus for kind in kinds]
    assert all(seen.count(kind) >= 5 for kind in KINDS)
    ends = [end for _, end in corpus]
    assert all(ends.count(end) >= 4 for end in TERMINALS)
    assert ends.count("hold") >= 30
    assert any(len(kinds) == 9 for kinds, _ in corpus)


def run_trial(kinds: list[str], end: str, folder: Path, index: int) -> list[str]:
    """Runs one script through the service; returns the names of the invariants it broke."""
    import httpx
    import keyring.core

    from mailroom import clock, service
    from mailroom.config import get_settings
    from mailroom.discord_post import DiscordUnavailable
    from mailroom.gateway import GatewayStopped
    from mailroom.keychain import KeychainUnavailable, SecretMissing
    from mailroom.store import open_store
    from tests.fakes import FakeKeychain, FakeTasksApp
    from tests.integration.test_service import World

    failures = {
        "bug": lambda: RuntimeError(PRIVATE),
        "key": lambda: KeyError(PRIVATE),
        "database": lambda: sqlite3.OperationalError(PRIVATE),
        "keychain": lambda: KeychainUnavailable("keychain unavailable: discord.bot-token"),
        "fatal": lambda: GatewayStopped(4004),
        "unconfigured": lambda: DiscordUnavailable("not configured"),
        "missing": lambda: SecretMissing("secret not found: discord.bot-token"),
    }
    steps = [*kinds, end]
    os.environ["MAILROOM_DATA_DIR"] = str(folder / f"data-{index}")
    keychain = FakeKeychain()
    keyring.core._keyring_backend = keychain
    clock.now = lambda: datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
    settings = get_settings()
    world = World(keychain, ("personal",))
    lock = threading.Lock()
    state = {"calls": 0, "active": 0, "most": 0}
    reached = threading.Event()
    https: list[httpx.Client] = []
    delays: list[float] = []

    def gateway(store, found, http, *, stop) -> None:
        with lock:
            number = state["calls"]
            state["calls"] += 1
            state["active"] += 1
            state["most"] = max(state["most"], state["active"])
            https.append(http)
        try:
            step = steps[number] if number < len(steps) else "hold"
            if number >= len(steps) - 1:
                reached.set()
            if step == "return":
                return
            if step != "hold":
                raise failures[step]()
            while not stop():
                threading.Event().wait(0.001)
        finally:
            with lock:
                state["active"] -= 1

    class Stop(threading.Event):
        def wait(self, timeout: float | None = None) -> bool:
            if threading.current_thread().name == "mailroom-gateway":
                return super().wait(timeout)
            reached.wait(5)
            for thread in threading.enumerate():
                if thread.name == "mailroom-gateway" and end != "hold":
                    thread.join(5)
            self.set()
            return True

    stop = Stop()
    closed: set[int] = set()
    opened: list[object] = []

    def tracking(found):
        store = open_store(found)
        close = store.close

        def closing() -> None:
            closed.add(id(store))
            close()

        store.close = closing
        opened.append(store)
        return store

    service.open_store = tracking

    def restart_wait(seconds: float) -> bool:
        delays.append(seconds)
        return stop.is_set()

    try:
        service.run_service(
            settings,
            say=world.lines.append,
            stop=stop,
            open_gmail=world.client,
            open_model_http=world.model_http,
            open_discord_http=world.discord_http,
            open_tasks_http=lambda: httpx.Client(
                transport=httpx.MockTransport(FakeTasksApp().handler)
            ),
            gateway=gateway,
            restart_wait=restart_wait,
        )
    finally:
        service.open_store = open_store
    broken = []
    if state["calls"] != len(steps):
        broken.append("attempts")
    if state["most"] != 1:
        broken.append("one-at-a-time")
    if delays != expected_delays(len(kinds)):
        broken.append("backoff")
    if not all(client.is_closed for client in https):
        broken.append("http-closed")
    if len(opened) != len(steps) + 1 or not all(id(store) in closed for store in opened):
        broken.append("store-closed")
    if any(PRIVATE in line for line in world.lines):
        broken.append("private-line")
    with open_store(settings) as store:
        texts = [alert.text for alert in store.pending_alerts()]
    texts += [m["content"] for m in world.discord.messages if m["content"]]
    if any(PRIVATE in text for text in texts):
        broken.append("private-alert")
    stopped = [text for text in texts if "The Discord listener stopped" in text]
    if len(stopped) != (0 if end == "hold" else 1) or len(texts) != len(stopped):
        broken.append("alerts")
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
    counts: dict[str, int] = {}
    reached = 0
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04f-trials-") as scratch:
        for index, (kinds, end) in enumerate(corpus):
            try:
                broken = run_trial(kinds, end, Path(scratch), index)
                reached += 1
            except Exception as error:
                broken = [f"raised {type(error).__name__}"]
            for name in broken:
                counts[name] = counts.get(name, 0) + 1
    print(f"trials reached: {reached} of {TRIALS}")
    if counts:
        detail = ", ".join(f"{name} x{count}" for name, count in sorted(counts.items()))
        print(f"supervision invariants: FAIL ({detail})")
    else:
        print("supervision invariants across 48 seeded scripts: ok")
    print(f"FAILURES {int(bool(counts))}")
    return int(bool(counts))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04f-") as folder:
        env = {key: value for key, value in os.environ.items() if not key.startswith("MAILROOM_")}
        env.update(
            HOME=folder,
            MAILROOM_DATA_DIR=str(Path(folder) / "data"),
            MAILROOM_GMAIL_ACCOUNTS="personal",
            MAILROOM_EXTRACTOR_MODEL="qwen-test:27b",
            MAILROOM_TIME_ZONE="America/New_York",
            MAILROOM_DISCORD_CHANNEL_ID="111111111111111111",
            MAILROOM_DISCORD_OWNER_ID="444444444444444444",
            MAILROOM_TASKS_URL="http://127.0.0.1:8765",
        )
        with patch.dict(os.environ, env, clear=True):
            sys.exit(main())
