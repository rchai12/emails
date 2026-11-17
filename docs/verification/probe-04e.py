"""Independent malformed-input isolation probe; synthetic data and MockTransport only."""

import argparse
import json
import os
import random
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]


def cases() -> list[dict]:
    rng = random.Random(404)
    result = []
    # Every required shape class is forced; random variation never makes a valid body.
    for field in ("data", "member", "channel_id"):
        for invalid in (None, [], 0, False):
            for _ in range(8):
                event = {
                    "id": "1400000000000000001",
                    "token": "synthetic-token",
                    "type": rng.choice((2, 3, 5)),
                    "data": {},
                    "member": {"user": {"id": "444444444444444444"}},
                    "channel_id": "111111111111111111",
                }
                event[field] = invalid
                result.append(event)
    return result


class ForbiddenStore:
    def __getattr__(self, name: str) -> object:
        raise AssertionError("unexpected store access")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-only", action="store_true")
    args = parser.parse_args()
    corpus = cases()
    assert len(corpus) == 96
    assert {item["type"] for item in corpus} == {2, 3, 5}
    assert all(
        any(not isinstance(item[k], dict) for k in ("data", "member"))
        or not isinstance(item["channel_id"], str)
        for item in corpus
    )
    print("oracle self-check: ok")
    if args.oracle_only:
        print("FAILURES 0")
        return 0

    import httpx

    from mailroom.config import Settings
    from mailroom.interactions import handle_interaction

    settings = Settings(
        discord_owner_id="444444444444444444", discord_channel_id="111111111111111111"
    )
    failures = 0
    replies = []

    def callback(request: httpx.Request) -> httpx.Response:
        replies.append(json.loads(request.content))
        assert str(request.url) == (
            "https://discord.com/api/v10/interactions/1400000000000000001/synthetic-token/callback"
        )
        return httpx.Response(204)

    with httpx.Client(transport=httpx.MockTransport(callback)) as http:
        for event in corpus:
            before = len(replies)
            expected = (
                {"type": 6}
                if event["type"] in (3, 5)
                else {
                    "type": 4,
                    "data": {
                        "content": "This interaction is unavailable.",
                        "flags": 64,
                        "allowed_mentions": {"parse": []},
                    },
                }
            )
            try:
                outcome = handle_interaction(event, ForbiddenStore(), settings, http)
                good = outcome == "ignored" and replies[before:] == [expected]
            except Exception:
                good = False
            failures += not good
    print(
        "malformed shapes cannot access store or echo content: "
        + ("ok" if failures == 0 else f"FAIL ({failures} cases)")
    )
    print(f"FAILURES {int(failures != 0)}")
    return int(failures != 0)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="mailroom-probe-04e-") as folder:
        env = {key: value for key, value in os.environ.items() if not key.startswith("MAILROOM_")}
        env.update(HOME=folder, MAILROOM_DATA_DIR=str(Path(folder) / "data"))
        with patch.dict(os.environ, env, clear=True):
            sys.exit(main())
