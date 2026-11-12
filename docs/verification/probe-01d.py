"""Probe for phase 1d. Run from the repository root: .venv/bin/python docs/verification/probe-01d.py

It drives the Gmail login against `tests.fakes.FakeGmail` with a fake keychain and a fake clock.
The callback listens on 127.0.0.1 and the probe visits it from a thread, as a browser would;
nothing else leaves the process and the real Keychain is never read. Each check prints `ok` or
`FAIL`; the last line is `FAILURES N`.
"""

import contextlib
import io
import os
import random
import sys
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01d-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

import httpx  # noqa: E402
import keyring.core  # noqa: E402
from keyring.errors import KeyringLocked  # noqa: E402

from tests.fakes import FakeGmail, FakeKeychain  # noqa: E402

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
OTHER_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.readonly.extra",
    "openid",
]
FAILURES = 0


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


# The oracle's rule for a granted scope: exactly the read-only scope, however it is spaced.
def scope_ok(scope: str) -> bool:
    return set(scope.split()) == {SCOPE}


assert scope_ok(SCOPE) and scope_ok(f" {SCOPE}  {SCOPE} ")
assert not scope_ok("") and not scope_ok(f"{SCOPE} openid") and not scope_ok(SCOPE + "x")
print("oracle self-check: ok")

from mailroom import clock  # noqa: E402

try:
    from mailroom.gmail_login import Callback, LoginError, consent_url, exchange_code, login
except Exception as error:
    print(f"import mailroom.gmail_login: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)

clock.now = lambda: datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
rng = random.Random(13)
KEYCHAIN = FakeKeychain()
keyring.core._keyring_backend = KEYCHAIN
TEXT = "abcXYZ019-._~+/=&?# %é"


def word(low: int = 1, high: int = 12) -> str:
    return "".join(rng.choice(TEXT) for _ in range(rng.randrange(low, high)))


def visit(urls: list[str]) -> tuple[threading.Thread, list[httpx.Response]]:
    responses: list[httpx.Response] = []

    def run() -> None:
        for url in urls:
            responses.append(httpx.get(url, trust_env=False, timeout=5))

    thread = threading.Thread(target=run)
    thread.start()
    return thread, responses


def stray(base: str, state: str) -> str:
    """A request that is not the callback: another path, another state, or a broken query."""
    kind = rng.choice(["path", "state", "nostate", "nocode", "twice", "junk"])
    code = quote("ZQX" + word())
    if kind == "path":
        return f"{base}/favicon-{quote(word())}?state={quote(state)}&code={code}"
    if kind == "state":
        return f"{base}/?state={quote(state + 'x')}&code={code}"
    if kind == "nostate":
        return f"{base}/?code={code}"
    if kind == "nocode":
        return f"{base}/?state={quote(state)}&scope={quote(word())}"
    if kind == "twice":
        return f"{base}/?state={quote(state)}&code={code}&code={code}"
    return f"{base}/?{quote(word())}={code}&state={quote(state + word())}"


def the_callback_finds_the_one_real_answer() -> object:
    for trial in range(25):
        state, code = "ST-" + word(8, 40), "c" + word(1, 60)
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured), contextlib.redirect_stdout(captured):
            with Callback("personal") as callback:
                base = callback.redirect_uri
                urls = [stray(base, state) for _ in range(rng.randrange(0, 6))]
                urls.append(f"{base}/?state={quote(state)}&code={quote(code)}&scope=x")
                thread, responses = visit(urls)
                got = callback.wait(state)
            thread.join()
        if got != code:
            return f"trial {trial}: returned a different code"
        if [response.status_code == 200 for response in responses] != [False] * (len(urls) - 1) + [
            True
        ]:
            return f"trial {trial}: statuses {[response.status_code for response in responses]}"
        if any("ZQX" in response.text or state in response.text for response in responses):
            return f"trial {trial}: a page echoes the request"
        if captured.getvalue():
            return f"trial {trial}: the callback wrote to the terminal"
    return True


def the_consent_address_carries_the_values_exactly() -> object:
    for _ in range(200):
        values = {
            "client_id": word(),
            "redirect_uri": f"http://127.0.0.1:{rng.randrange(1024, 65536)}",
            "state": word(),
            "code_challenge": word(),
        }
        url = consent_url(
            client_id=values["client_id"],
            redirect_uri=values["redirect_uri"],
            state=values["state"],
            challenge=values["code_challenge"],
        )
        params = httpx.URL(url).params
        for key in values:
            if params.get_list(key) != [values[key]]:
                return f"{key}: sent {params.get_list(key)!r} for {values[key]!r}"
    return True


def only_the_read_only_scope_is_accepted() -> object:
    for _ in range(150):
        parts = [SCOPE] * rng.randrange(0, 3) + rng.sample(OTHER_SCOPES, rng.randrange(0, 2))
        rng.shuffle(parts)
        scope = rng.choice([" ", "  "]).join(parts)
        fake = FakeGmail()
        fake.granted_scope = scope

        def handler(request: httpx.Request, fake=fake) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "a",
                        "refresh_token": "r-ZQX",
                        "scope": fake.granted_scope,
                    },
                )
            return fake.handler(request)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        arguments = {
            "client_id": "client-id-1",
            "client_secret": "client-secret-1",
            "code": "code-1",
            "verifier": "v" * 43,
            "redirect_uri": "http://127.0.0.1:9",
        }
        try:
            accepted = exchange_code(http, "personal", **arguments) == "r-ZQX"
        except LoginError:
            accepted = False
        if accepted != scope_ok(scope):
            return f"scope {scope!r}: accepted {accepted}"
    return True


class Browser:
    def __init__(self, fake: FakeGmail, approve: bool) -> None:
        self.fake, self.approve = fake, approve

    def __call__(self, url: str) -> None:
        visit([self.fake.consent(url, approve=self.approve)])


def a_failed_login_stores_nothing_and_leaks_nothing() -> object:
    secrets = ("client-secret-ZQX", "refresh-token-from-code", "code-1")
    for trial in range(40):
        fake = FakeGmail()
        fake.client_secret = "client-secret-ZQX"
        KEYCHAIN.secrets.clear()
        KEYCHAIN.writes.clear()
        KEYCHAIN.error = None
        fault = rng.choice(["none", "cancel", "token-500", "token-network", "scope", "keychain"])
        if fault == "scope":
            fake.granted_scope = f"{SCOPE} https://mail.google.com/"

        def handler(request: httpx.Request, fake=fake, fault=fault) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com" and "authorization_code" in str(
                request.content
            ):
                if fault == "token-500":
                    return httpx.Response(500, text="code-1 client-secret-ZQX")
                if fault == "token-network":
                    raise httpx.ConnectError("client-secret-ZQX")
            return fake.handler(request)

        if fault == "keychain":
            KEYCHAIN.error = KeyringLocked("client-secret-ZQX")
        answers = iter(["client-id-1", "client-secret-ZQX"])
        try:
            address = login(
                "personal",
                httpx.Client(transport=httpx.MockTransport(handler)),
                ask=lambda _label, answers=answers: next(answers),
                open_browser=Browser(fake, approve=fault != "cancel"),
            )
            error_text = None
        except Exception as error:
            address, error_text = None, str(error)
        if fault == "none":
            if address != "owner@example.test" or len(KEYCHAIN.writes) != 3:
                return f"trial {trial}: a clean login did not finish ({error_text!r})"
            continue
        if error_text is None:
            return f"trial {trial} ({fault}): no error"
        if any(secret in error_text for secret in secrets):
            return f"trial {trial} ({fault}): the error leaks a secret: {error_text!r}"
        if KEYCHAIN.writes:
            return f"trial {trial} ({fault}): stored {KEYCHAIN.writes}"
    return True


check("the callback returns the one real answer, quietly", the_callback_finds_the_one_real_answer)
check(
    "the consent address carries its values exactly", the_consent_address_carries_the_values_exactly
)
check(
    "only a token for exactly the read-only scope is accepted", only_the_read_only_scope_is_accepted
)
check(
    "a failed login stores nothing and leaks nothing",
    a_failed_login_stores_nothing_and_leaks_nothing,
)
print(f"FAILURES {FAILURES}")
