"""Probe for phase 4a. Run from the repository root: .venv/bin/python docs/verification/probe-04a.py

The Graph client runs a first round, a later round and a fetch against FakeGraph, while one
reply in each run is corrupted at random: a field removed or given another type, a page link
pointed elsewhere, a status changed, or the body replaced with bytes that aren't JSON. Whatever
happens, the client must raise only `OutlookError` or `ValueError`, send requests only to
login.microsoftonline.com and graph.microsoft.com, send its access token only to Graph, and never
put a token, a secret or a reply's text into an error message. The check prints `ok` or `FAIL`;
the last line is `FAILURES N`. Fakes only.
"""

import json
import os
import random
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe04a-"))
os.environ["HOME"] = str(TMP / "home")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from tests.fakes import FakeGraph, FakeKeychain  # noqa: E402

FAILURES = 0
rng = random.Random(41)
NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
SINCE = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
HOSTS = {"login.microsoftonline.com", "graph.microsoft.com"}
MARKER = "reply-text-7c1d"


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


def corrupt(body: object) -> object:
    """One change to a JSON body: drop a key, retype a value, or point a link elsewhere."""
    if not isinstance(body, dict) or not body:
        return MARKER
    key = rng.choice(sorted(body))
    changed = dict(body)
    choice = rng.randrange(4)
    if choice == 0:
        del changed[key]
    elif choice == 1:
        changed[key] = rng.choice([None, 7, [], {}, MARKER, True])
    elif choice == 2 and isinstance(changed[key], str) and changed[key].startswith("https://"):
        changed[key] = changed[key].replace("graph.microsoft.com", "graph.example.test", 1)
    elif choice == 3 and isinstance(changed[key], list) and changed[key]:
        changed[key] = [corrupt(changed[key][0]), *changed[key][1:]]
    else:
        changed[key] = MARKER
    return changed


assert corrupt({}) == MARKER
assert set(corrupt({"a": 1, "b": 2})) <= {"a", "b"}
print("oracle self-check: ok")


class Corrupting:
    """FakeGraph behind a transport that corrupts the reply to one chosen request."""

    def __init__(self, graph: FakeGraph, target: int) -> None:
        self.graph = graph
        self.target = target
        self.count = 0
        self.sent: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        if request.url.host not in HOSTS:
            return httpx.Response(200, json={"value": [], "@odata.deltaLink": "x"})
        response = self.graph.handler(request)
        self.count += 1
        if self.count != self.target:
            return response
        kind = rng.randrange(4)
        if kind == 0:
            return httpx.Response(rng.choice([200, 400, 401, 404, 410, 429, 500]), text=MARKER)
        if kind == 1:
            return httpx.Response(200, content=MARKER.encode() + b"\xff{")
        try:
            body = json.loads(response.content)
        except ValueError:
            return httpx.Response(200, content=b"\x00" + MARKER.encode())
        return httpx.Response(response.status_code, json=corrupt(body))


def the_client_fails_only_by_name() -> object:
    from mailroom.outlook import OutlookClient, OutlookError

    clock.now = lambda: NOW
    reached = {"error": 0, "fine": 0}
    for trial in range(1500):
        keychain = FakeKeychain()
        keyring.core._keyring_backend = keychain
        graph = FakeGraph()
        keychain.secrets[("mailroom", "outlook.live.client-id")] = graph.client_id
        keychain.secrets[("mailroom", "outlook.live.refresh-token")] = graph.refresh_token
        for number in range(rng.randrange(1, 4)):
            graph.add_message(
                f"AAMk{number}=", b"Subject: x\r\n\r\nbody", received="2026-11-11T08:00:00Z"
            )
        corrupting = Corrupting(graph, rng.randrange(1, 9))
        outlook = OutlookClient(
            "live", httpx.Client(transport=httpx.MockTransport(corrupting.handler))
        )
        try:
            outlook.profile()
            link = outlook.first_delta(SINCE).delta_link
            graph.add_message("AAMk9=", b"Subject: y\r\n\r\nmore", received="2026-11-12T08:00:00Z")
            outlook.next_delta(link)
            outlook.fetch("AAMk9=")
            reached["fine"] += 1
        except (OutlookError, ValueError) as error:
            reached["error"] += 1
            text = str(error)
            secrets = [MARKER, *graph.issued, graph.refresh_token, "refresh-token-1", "client-id-1"]
            if any(secret in text for secret in secrets):
                return f"trial {trial}: an error carried a token or a reply: {text!r}"
        for request in corrupting.sent:
            if request.url.host not in HOSTS:
                return f"trial {trial}: a request went to {request.url.host}"
            if "authorization" in request.headers and request.url.host != "graph.microsoft.com":
                return f"trial {trial}: the token went to {request.url.host}"
    if min(reached.values()) < 100:
        return f"too few cases: {reached}"
    return True


check("the client fails only by name and talks only to Microsoft", the_client_fails_only_by_name)
print(f"FAILURES {FAILURES}")
