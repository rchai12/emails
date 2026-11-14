"""Probe for phase 4c. Run from the repository root: .venv/bin/python docs/verification/probe-04c.py

1. The code exchange: each run corrupts one field of FakeGraph's token reply (dropped, retyped,
   or a scope changed), or the status, or the body. `exchange_code` must raise only
   `LoginError`, its message must never hold the code, a token or the reply's text, and it may
   return a refresh token only for a grant of Mail.Read (with offline_access at most).
2. Whole sign-ins against the fake, refused or failing at the exchange at random: the Keychain
   is written only when the exchange succeeded with a read-only grant.
Fakes only (the callback listens on 127.0.0.1). Each check prints `ok` or `FAIL`; the last line is
`FAILURES N`.
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
TMP = Path(tempfile.mkdtemp(prefix="probe04c-"))
os.environ["HOME"] = str(TMP / "home")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from tests.fakes import FakeGraph, FakeKeychain  # noqa: E402

FAILURES = 0
rng = random.Random(43)
MARKER = "reply-text-41ab"
READ = "https://graph.microsoft.com/mail.read"
SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
    "offline_access",
    "openid",
    MARKER,
]


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


def read_only(scope: object) -> bool:
    """The probe's own reading of an acceptable grant, from the spec's rule."""
    if not isinstance(scope, str):
        return False
    granted = {part.lower() for part in scope.split()}
    return READ in granted and granted <= {READ, "offline_access"}


assert read_only("https://graph.microsoft.com/Mail.Read offline_access")
assert not read_only("https://graph.microsoft.com/Mail.Read openid")
assert not read_only("")
print("oracle self-check: ok")


def corrupt(body: dict) -> dict:
    changed = dict(body)
    key = rng.choice(sorted(changed))
    choice = rng.randrange(3)
    if choice == 0:
        del changed[key]
    elif choice == 1:
        changed[key] = rng.choice([None, 7, [], {}, MARKER, ""])
    else:
        changed["scope"] = " ".join(rng.sample(SCOPES, rng.randrange(0, 3)))
    return changed


def the_exchange_fails_only_by_name() -> object:
    from mailroom.gmail_login import LoginError
    from mailroom.outlook_login import exchange_code

    reached = {"accepted": 0, "refused": 0}
    for trial in range(2000):
        sent: dict = {}

        def handler(request: httpx.Request, sent: dict = sent) -> httpx.Response:
            if rng.random() < 0.1:
                return httpx.Response(rng.choice([200, 400, 500]), text=MARKER)
            body = corrupt(
                {
                    "token_type": "Bearer",
                    "scope": "https://graph.microsoft.com/Mail.Read",
                    "expires_in": 3600,
                    "access_token": "access-1",
                    "refresh_token": "refresh-token-from-code",
                }
            )
            sent.update(body)
            return httpx.Response(200, content=json.dumps(body).encode())

        http = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            token = exchange_code(
                http,
                "live",
                client_id="client-id-1",
                code="code-7f",
                verifier="v" * 43,
                redirect_uri="http://127.0.0.1:5000",
            )
        except LoginError as error:
            reached["refused"] += 1
            text = str(error)
            if any(secret in text for secret in (MARKER, "code-7f", "access-1", "refresh-token")):
                return f"trial {trial}: an error carried a secret or reply: {text!r}"
            continue
        reached["accepted"] += 1
        if not read_only(sent.get("scope")):
            return f"trial {trial}: accepted a grant of {sent.get('scope')!r}"
        if not (isinstance(token, str) and token and token == sent.get("refresh_token")):
            return f"trial {trial}: returned {token!r}, the reply had {sent.get('refresh_token')!r}"
    if min(reached.values()) < 50:
        return f"too few cases: {reached}"
    return True


def nothing_is_kept_without_a_read_only_grant() -> object:
    from mailroom.gmail_login import LoginError
    from mailroom.outlook_login import login
    from tests.integration.test_gmail_login import visiting

    clock.now = lambda: datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    reached = {"kept": 0, "refused": 0, "cancelled": 0}
    for trial in range(80):
        keychain = FakeKeychain()
        keyring.core._keyring_backend = keychain
        graph = FakeGraph()
        graph.granted_scope = rng.choice(
            [
                SCOPES[0],
                f"{SCOPES[0]} offline_access",
                SCOPES[1],
                f"{SCOPES[0]} {SCOPES[2]}",
                SCOPES[3],
            ]
        )
        approve = rng.random() < 0.8

        def browser(url: str, graph: FakeGraph = graph, approve: bool = approve) -> bool:
            visiting(graph.consent(url, approve=approve))
            return True

        http = httpx.Client(transport=httpx.MockTransport(graph.handler))
        try:
            login("live", http, ask=lambda label: "client-id-1", open_browser=browser)
        except LoginError:
            if keychain.writes:
                return f"trial {trial}: a refused sign-in wrote {keychain.writes}"
            reached["refused" if approve else "cancelled"] += 1
            continue
        if not (approve and read_only(graph.granted_scope)):
            return f"trial {trial}: a sign-in was kept for {graph.granted_scope!r}"
        reached["kept"] += 1
    if min(reached.values()) < 5:
        return f"too few cases: {reached}"
    return True


check("the code exchange fails only by name", the_exchange_fails_only_by_name)
check("nothing is kept without a read-only grant", nothing_is_kept_without_a_read_only_grant)
print(f"FAILURES {FAILURES}")
