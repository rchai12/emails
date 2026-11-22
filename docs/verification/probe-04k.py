"""Probe for phase 4k. Run from the repository root: .venv/bin/python docs/verification/probe-04k.py

1. Neutral module: a fresh interpreter imports `mailroom.oauth` and `mailroom.outlook_login`
   and loads no `mailroom.gmail*` module; `oauth.py`'s own imports name no provider module;
   every shared name `gmail_login` and `outlook_login` expose is oauth's object.
2. The token reply: seeded random replies (network errors, statuses, bodies, retyped, empty or
   missing fields) go to `oauth.token_reply` under random provider and account names and to both
   providers' `exchange_code`. The probe predicts each outcome from its own reading of the
   contract; an error must be a `LoginError` with exactly the predicted text, its context
   suppressed, and must never hold the code, a token or the reply's text.
3. The callback names whichever provider it was given when the wait times out.
4. Each login command closes its client: `login` is replaced by one that records the client it
   was lent (it must still be open), then returns, raises each error the command reports, or
   raises an unexpected error. The client must be closed afterwards on every path.
Fakes only. Each check prints `ok` or `FAIL`; the last line is `FAILURES N`.
"""

import ast
import json
import os
import random
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe04k-"))
os.environ["HOME"] = str(TMP / "home")
for key in [key for key in os.environ if key.startswith("MAILROOM_")]:
    del os.environ[key]
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock  # noqa: E402
from tests.fakes import FakeKeychain  # noqa: E402

keyring.core.set_keyring(FakeKeychain())
FAILURES = 0
rng = random.Random(4011)
NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
MARKER = "reply-text-9c2e"
SECRETS = (MARKER, "code-5d", "access-77", "refresh-77")
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
OUTLOOK_READ = "https://graph.microsoft.com/mail.read"


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


def no_gmail_module_in_a_fresh_interpreter() -> object:
    script = (
        "import sys, mailroom.oauth, mailroom.outlook_login;"
        "print(','.join(sorted(n for n in sys.modules if n.startswith('mailroom.'))))"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT)])}
    found = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=False
    )
    if found.returncode != 0:
        return f"the import failed with exit {found.returncode}"
    loaded = found.stdout.strip().split(",")
    named = [name for name in loaded if name.startswith(("mailroom.gmail", "mailroom.cli"))]
    return True if not named else f"loaded {named}"


def oauth_imports_no_provider() -> object:
    tree = ast.parse((ROOT / "src/mailroom/oauth.py").read_text())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names += [f"{node.module}.{alias.name}" for alias in node.names]
    providers = ("gmail", "outlook", "yahoo", "gmail_login", "outlook_login")
    bad = [name for name in names if any(part in providers for part in name.split("."))]
    return True if not bad else f"oauth.py imports {bad}"


def shared_names_are_oauths() -> object:
    from mailroom import gmail_login, oauth, outlook_login

    wrong = []
    for name in ("LoginError", "new_verifier", "code_challenge"):
        for module in (gmail_login, outlook_login):
            if getattr(module, name) is not getattr(oauth, name):
                wrong.append(f"{module.__name__}.{name}")
    if outlook_login.Callback is not oauth.Callback:
        wrong.append("outlook_login.Callback")
    if not issubclass(gmail_login.Callback, oauth.Callback):
        wrong.append("gmail_login.Callback is not an oauth.Callback")
    return True if not wrong else f"not oauth's: {wrong}"


def expect(status: int | None, body: object) -> str:
    """The probe's own reading of the reply contract: '' for accepted, else the detail."""
    if status is None:
        return "network"
    if status != 200:
        return str(status)
    if not isinstance(body, dict):
        return "response"
    token, scope = body.get("refresh_token"), body.get("scope")
    if not isinstance(token, str) or token == "" or not isinstance(scope, str):
        return "response"
    return ""


def random_reply(scope: str) -> tuple[int | None, object, httpx.Response | Exception]:
    roll = rng.random()
    if roll < 0.08:
        error = rng.choice([httpx.ConnectError(MARKER), httpx.ReadTimeout(MARKER)])
        return None, None, error
    if roll < 0.18:
        status = rng.choice([400, 401, 403, 500, 503])
        return status, None, httpx.Response(status, text=MARKER)
    if roll < 0.24:
        return 200, None, httpx.Response(200, content=MARKER.encode())
    if roll < 0.28:
        body = rng.choice([[MARKER], MARKER, 7, None])
        return 200, body, httpx.Response(200, content=json.dumps(body).encode())
    body: dict = {"access_token": "access-77", "refresh_token": "refresh-77", "scope": scope}
    for key in rng.sample(["refresh_token", "scope", "access_token"], rng.randrange(0, 2)):
        if rng.random() < 0.4:
            del body[key]
        else:
            body[key] = rng.choice([None, 7, [], {}, "", MARKER, ["x"]])
    return 200, body, httpx.Response(200, content=json.dumps(body).encode())


def client_for(answer: httpx.Response | Exception) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.Client(transport=httpx.MockTransport(handler))


def bad_error(error: Exception, wanted: str) -> str:
    from mailroom import oauth

    text = str(error)
    if type(error) is not oauth.LoginError:
        return f"raised {type(error).__name__}"
    if text != wanted:
        return f"said {text!r}, wanted {wanted!r}"
    if error.__cause__ is not None or not error.__suppress_context__:
        return f"kept its context: {text!r}"
    if any(secret in text for secret in SECRETS):
        return f"carried a secret: {text!r}"
    return ""


def token_reply_follows_the_contract() -> object:
    from mailroom import oauth

    reached = {"accepted": 0, "refused": 0}
    for trial in range(1500):
        provider = rng.choice(["yahoo", "fastmail", "gmail", "outlook", "proton"])
        account = rng.choice(["family", "work", "a1", "x-y"])
        status, body, answer = random_reply(rng.choice(["read", "", "a b", MARKER]))
        detail = expect(status, body)
        try:
            found = oauth.token_reply(
                client_for(answer),
                "https://login.example.test/token",
                {"code": "code-5d"},
                provider=provider,
                account=account,
            )
        except Exception as error:
            reached["refused"] += 1
            if not detail:
                return f"trial {trial}: refused a good reply: {type(error).__name__}"
            problem = bad_error(error, f"{provider} login failed: {account} ({detail})")
            if problem:
                return f"trial {trial}: {problem}"
            continue
        reached["accepted"] += 1
        if detail:
            return f"trial {trial}: accepted a reply the contract refuses ({detail})"
        if found != (body["refresh_token"], body["scope"]):
            return f"trial {trial}: returned {found!r}"
    if min(reached.values()) < 100:
        return f"too few cases: {reached}"
    return True


def gmail_granted(scope: str) -> bool:
    return set(scope.split()) == {GMAIL_SCOPE}


def outlook_granted(scope: str) -> bool:
    granted = {part.lower() for part in scope.split()}
    return OUTLOOK_READ in granted and granted <= {OUTLOOK_READ, "offline_access"}


def both_exchanges_follow_the_contract() -> object:
    from mailroom import gmail_login, outlook_login

    scopes = [
        GMAIL_SCOPE,
        f"{GMAIL_SCOPE} https://www.googleapis.com/auth/gmail.modify",
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/Mail.Read offline_access",
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send",
        "",
    ]
    reached = {"accepted": 0, "refused": 0, "scope": 0}
    for trial in range(1500):
        provider = rng.choice(["gmail", "outlook"])
        status, body, answer = random_reply(rng.choice(scopes))
        detail = expect(status, body)
        http = client_for(answer)
        common = {"code": "code-5d", "verifier": "v" * 43, "redirect_uri": "http://127.0.0.1:5"}
        try:
            if provider == "gmail":
                found = gmail_login.exchange_code(
                    http, "personal", client_id="id-1", client_secret="secret-1", **common
                )
            else:
                found = outlook_login.exchange_code(http, "live", client_id="id-1", **common)
        except Exception as error:
            account = "personal" if provider == "gmail" else "live"
            if detail:
                wanted = f"{provider} login failed: {account} ({detail})"
                reached["refused"] += 1
            else:
                wanted = f"{provider} login scope refused: {account}"
                reached["scope"] += 1
            problem = bad_error(error, wanted)
            if problem:
                return f"trial {trial} ({provider}): {problem}"
            continue
        reached["accepted"] += 1
        granted = gmail_granted if provider == "gmail" else outlook_granted
        if detail or not granted(body["scope"]):
            return f"trial {trial} ({provider}): accepted {body!r}"
        if found != body["refresh_token"]:
            return f"trial {trial} ({provider}): returned {found!r}"
    if min(reached.values()) < 50:
        return f"too few cases: {reached}"
    return True


def the_callback_names_its_provider() -> object:
    from mailroom import gmail_login, oauth

    real = clock.now
    try:
        for provider in ("yahoo", "fastmail", "outlook"):
            moments = iter([NOW])
            clock.now = lambda moments=moments: next(moments, NOW + timedelta(minutes=6))
            with oauth.Callback("acct-3", provider=provider) as callback:
                try:
                    callback.wait("state-1")
                except oauth.LoginError as error:
                    problem = bad_error(error, f"{provider} login timed out: acct-3")
                    if problem:
                        return problem
                else:
                    return f"{provider}: the wait returned"
        try:
            oauth.Callback("acct-3")
        except TypeError:
            pass
        else:
            return "oauth.Callback made a callback without a provider"
        moments = iter([NOW])
        clock.now = lambda: next(moments, NOW + timedelta(minutes=6))
        with gmail_login.Callback("acct-3") as callback:
            try:
                callback.wait("state-1")
            except oauth.LoginError as error:
                return bad_error(error, "gmail login timed out: acct-3") or True
            return "gmail: the wait returned"
    finally:
        clock.now = real


def every_login_command_closes_its_client() -> object:
    from typer.testing import CliRunner

    from mailroom import gmail_login, oauth, outlook_login
    from mailroom.cli import app
    from mailroom.gmail import GmailError
    from mailroom.keychain import KeychainUnavailable
    from mailroom.outlook import OutlookError

    runner = CliRunner()
    outcomes = {
        "gmail": [None, oauth.LoginError("gmail login cancelled: a1"), GmailError("gmail x: a1")],
        "outlook": [
            None,
            oauth.LoginError("outlook login cancelled: a1"),
            OutlookError("outlook x: a1"),
        ],
    }
    shared = [KeychainUnavailable("keychain unavailable: a1"), ValueError("empty secret value")]
    unexpected = [RuntimeError("boom"), KeyError("k")]
    modules = {"gmail": gmail_login, "outlook": outlook_login}
    cases = [
        (provider, outcome)
        for provider in modules
        for outcome in outcomes[provider] + shared + unexpected
    ]
    rng.shuffle(cases)
    for provider, outcome in cases:
        module = modules[provider]
        opened: list[httpx.Client] = []
        lent: list[tuple[httpx.Client, bool]] = []

        def new_http(opened: list = opened) -> httpx.Client:
            client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
            opened.append(client)
            return client

        def login(account, http, *, outcome=outcome, lent=lent, **_kw) -> str:
            lent.append((http, http.is_closed))
            if outcome is not None:
                raise outcome
            return "owner@example.test"

        saved = (module.new_http, module.login)
        module.new_http, module.login = new_http, login
        try:
            result = runner.invoke(app, [f"{provider}-login", "a1"])
        finally:
            module.new_http, module.login = saved
        label = f"{provider} / {type(outcome).__name__ if outcome else 'success'}"
        if len(opened) != 1:
            return f"{label}: opened {len(opened)} clients"
        if len(lent) != 1 or lent[0][0] is not opened[0] or lent[0][1]:
            return f"{label}: login was not lent the open client it made"
        if not opened[0].is_closed:
            return f"{label}: the client was left open"
        if outcome is None and result.exit_code != 0:
            return f"{label}: exit {result.exit_code}"
        if isinstance(
            outcome, (oauth.LoginError, GmailError, OutlookError, KeychainUnavailable, ValueError)
        ):
            if result.exit_code != 1 or result.output.splitlines()[-1:] != [str(outcome)]:
                return f"{label}: exit {result.exit_code}, did not report the error"
        if outcome in unexpected and result.exception is not outcome:
            return f"{label}: the unexpected error was not left to propagate"
    return True


check("outlook sign-in loads no gmail module", no_gmail_module_in_a_fresh_interpreter)
check("oauth.py imports no provider module", oauth_imports_no_provider)
check("the shared names are oauth's objects", shared_names_are_oauths)
check("token_reply follows the reply contract", token_reply_follows_the_contract)
check("both exchanges follow the reply and scope contracts", both_exchanges_follow_the_contract)
check("the callback names its provider", the_callback_names_its_provider)
check("every login command closes its client", every_login_command_closes_its_client)
print(f"FAILURES {FAILURES}")
sys.exit(1 if FAILURES else 0)
