"""Probe for phase 4m. Run from the repository root: .venv/bin/python docs/verification/probe-04m.py

1. Neutral module: a fresh interpreter imports `mailroom.token_http` and loads no
   `mailroom.gmail*` or `mailroom.outlook*` module; `token_http.py`'s own imports name no
   provider module; `gmail.TOKEN_MARGIN` and `outlook.TOKEN_MARGIN` are its object.
2. The session: seeded random scripts of clock moves, token replies (good, refused with a
   listed or other code, failing, unusable, unreachable) and API replies (200, 401, other
   statuses, unreachable). The probe predicts every request, token and outcome itself.
3. Where a token may go: seeded random URLs built from good and bad parts (scheme, host,
   port, user info, dot segments, near-miss paths). The probe decides each one itself; a
   refused URL sends nothing at all.
4. Both real clients: each builds one session and sends every request and token post through
   it, and seeded random call scripts against FakeGmail and FakeGraph give the outcomes and
   token posts the probe predicts from one model of the session, for both providers.
Fakes only. Each check prints `ok` or `FAIL`; the last line is `FAILURES N`.
"""

import ast
import importlib
import os
import random
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe04m-"))
os.environ["HOME"] = str(TMP / "home")
for key in [key for key in os.environ if key.startswith("MAILROOM_")]:
    del os.environ[key]
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

import httpx  # noqa: E402
import keyring.core  # noqa: E402

from mailroom import clock, gmail, outlook  # noqa: E402
from tests.fakes import FakeGmail, FakeGraph, FakeKeychain  # noqa: E402

KEYCHAIN = FakeKeychain()
keyring.core.set_keyring(KEYCHAIN)
FAILURES = 0
rng = random.Random(4130)
START = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
MARGIN = timedelta(seconds=60)
NOW = [START]
clock.now = lambda: NOW[0]
API = "https://api.example.test/v2/users/me"
TOKEN = "https://login.example.test/oauth/token"
CODES = frozenset({"invalid_grant", "interaction_required"})


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


def token_http():
    return importlib.import_module("mailroom.token_http")


# 1. Neutral module


def neutral() -> object:
    code = (
        "import sys; import mailroom.token_http; "
        "print(sorted(m for m in sys.modules "
        "if m.startswith(('mailroom.gmail', 'mailroom.outlook'))))"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT)])}
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False
    )
    if done.returncode != 0 or done.stdout.strip() != "[]":
        return f"fresh import: exit {done.returncode}, loaded {done.stdout.strip()!r}"
    tree = ast.parse((ROOT / "src/mailroom/token_http.py").read_text())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
            if node.module == "mailroom":
                names += [f"mailroom.{alias.name}" for alias in node.names]
    bad = [n for n in names if n.startswith("mailroom.") and n not in ("mailroom.clock",)]
    if bad:
        return f"token_http imports {bad}"
    module = token_http()
    if gmail.TOKEN_MARGIN is not module.TOKEN_MARGIN:
        return "gmail.TOKEN_MARGIN is its own object"
    if outlook.TOKEN_MARGIN is not module.TOKEN_MARGIN:
        return "outlook.TOKEN_MARGIN is its own object"
    if module.TOKEN_MARGIN != MARGIN:
        return f"margin {module.TOKEN_MARGIN}"
    return True


# 2. The session against a scripted world


class Failed(Exception):
    def __init__(self, kind: str, detail: object = None) -> None:
        super().__init__(kind, detail)
        self.kind = kind
        self.detail = detail


TOKEN_KINDS = ["good", "good", "good", "listed", "other", "503", "unusable", "network"]
API_KINDS = [200, 200, 200, 200, 401, 401, 403, 500, "network"]


def token_reply(kind: str, number: int, lifetime: int) -> httpx.Response:
    if kind == "good":
        return httpx.Response(200, json={"access_token": f"a{number}", "expires_in": lifetime})
    if kind == "listed":
        status = rng.choice([400, 401])
        return httpx.Response(status, json={"error": rng.choice(sorted(CODES))})
    if kind == "other":
        return httpx.Response(400, json={"error": "invalid_client"})
    if kind == "503":
        return httpx.Response(503)
    if kind == "unusable":
        return httpx.Response(200, json={"access_token": "a", "expires_in": True})
    raise httpx.ConnectError("unreachable")


def scripted_round(seed: int) -> object:
    local = random.Random(seed)
    NOW[0] = START
    log: list[str] = []
    token_plan: list[tuple[str, int]] = []
    api_plan: list[object] = []
    issued = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            kind, lifetime = token_plan.pop(0) if token_plan else ("good", 3600)
            if kind == "good":
                issued[0] += 1
            log.append(f"POST {kind}")
            return token_reply(kind, issued[0], lifetime)
        reply = api_plan.pop(0) if api_plan else 200
        log.append(f"GET {request.headers['authorization']} {reply}")
        if reply == "network":
            raise httpx.ConnectError("unreachable")
        return httpx.Response(int(reply))

    module = token_http()
    holder: list[object] = []
    session = module.TokenSession(
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_url=API,
        token_url=TOKEN,
        auth_codes=CODES,
        refresh=lambda: holder[0].grant({"grant_type": "refresh_token"}),
        auth_error=lambda: Failed("auth"),
        unavailable=lambda detail: Failed("unavailable", detail),
    )
    holder.append(session)

    # The oracle: one cached token and its expiry.
    cached: str | None = None
    expiry = START
    count = 0
    expected_log: list[str] = []
    for _step in range(12):
        NOW[0] += timedelta(seconds=local.choice([0, 30, 600, 3539, 3540, 3600, 7200]))
        tokens = [(local.choice(TOKEN_KINDS), local.choice([60, 120, 3600])) for _ in range(2)]
        replies = [local.choice(API_KINDS) for _ in range(2)]
        token_plan[:] = list(tokens)
        api_plan[:] = list(replies)
        expected: object = None
        for _attempt in range(2):
            if cached is None or NOW[0] >= expiry:
                cached = None
                kind, lifetime = tokens.pop(0) if tokens else ("good", 3600)
                expected_log.append(f"POST {kind}")
                if kind != "good":
                    expected = {
                        "listed": ("auth", None),
                        "other": ("unavailable", 400),
                        "503": ("unavailable", 503),
                        "unusable": ("unavailable", "response"),
                        "network": ("unavailable", "network"),
                    }[kind]
                    break
                count += 1
                cached = f"a{count}"
                expiry = NOW[0] + timedelta(seconds=lifetime) - MARGIN
            reply = replies.pop(0) if replies else 200
            expected_log.append(f"GET Bearer {cached} {reply}")
            if reply == "network":
                expected = ("unavailable", "network")
                break
            if reply != 401:
                expected = ("status", reply)
                break
            cached = None
        if expected is None:
            expected = ("auth", None)
        try:
            got: object = ("status", session.get(f"{API}/item").status_code)
        except Failed as error:
            if error.__suppress_context__ is not True:
                return f"seed {seed}: error keeps its context"
            got = (error.kind, error.detail)
        if got != expected:
            return f"seed {seed}: got {got}, expected {expected}"
    if log != expected_log:
        return f"seed {seed}: requests {log[-4:]}, expected {expected_log[-4:]}"
    return True


def session_scripts() -> object:
    for seed in range(200):
        result = scripted_round(seed)
        if result is not True:
            return result
    return True


# 3. Where a token may go


def random_url(local: random.Random) -> tuple[str, bool]:
    good = True
    scheme = "https"
    if local.random() < 0.15:
        scheme, good = local.choice(["http", "ftp"]), False
    host = "api.example.test"
    roll = local.random()
    if roll < 0.1:
        host, good = "api.example.test.evil.test", False
    elif roll < 0.2:
        host, good = "other.example.test", False
    elif roll < 0.25:
        host = "API.EXAMPLE.TEST"
    port = ""
    if local.random() < 0.1:
        port, good = local.choice([":443", ":8443"]), False
    user = ""
    if local.random() < 0.1:
        user, good = local.choice(["owner@", "owner:pw@", ":@"]), False
    base = "/v2/users/me"
    roll = local.random()
    if roll < 0.08:
        base, good = "/v2/users/meX", False
    elif roll < 0.14:
        base, good = "/v2/users", False
    elif roll < 0.18:
        base, good = "/v3/users/me", False
    segments = [local.choice(["messages", "m1", "a b", "x%2Fy", "history"]) for _ in range(2)]
    if local.random() < 0.15:
        segments.insert(local.randrange(3), local.choice([".", "..", "%2e%2e", "%2E", ".%2e"]))
        good = False
    if good and local.random() < 0.15:
        segments = []
    path = base + "".join("/" + segment for segment in segments)
    query = "?format=raw" if local.random() < 0.3 else ""
    return f"{scheme}://{user}{host}{port}{quote(path, safe='/%')}{query}", good


def guarded(url: str) -> tuple[bool, list[str], int, object]:
    sent: list[str] = []
    prepared: list[int] = []
    holder: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "a", "expires_in": 3600})
        return httpx.Response(200)

    session = token_http().TokenSession(
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_url=API,
        token_url=TOKEN,
        auth_codes=CODES,
        refresh=lambda: holder[0].grant({}),
        auth_error=lambda: Failed("auth"),
        unavailable=lambda detail: Failed("unavailable", detail),
        prepare=lambda: prepared.append(1),
    )
    holder.append(session)
    try:
        session.get(url)
    except Failed as error:
        return False, sent, len(prepared), (error.kind, error.detail)
    return True, sent, len(prepared), None


def url_guard() -> object:
    local = random.Random(4131)
    for number in range(400):
        url, good = random_url(local)
        allowed, sent, prepared, error = guarded(url)
        if not allowed and error != ("unavailable", "response"):
            return f"url {number}: {error}"
        if allowed != good:
            return f"url {number}: {'sent' if allowed else 'refused'}, expected the opposite"
        if not allowed and (sent or prepared):
            return f"url {number}: refused after {sent} requests and {prepared} prepares"
    return True


# 4. Both real clients


class Spy:
    def __init__(self) -> None:
        self.built = 0
        self.gets = 0
        self.grants = 0


def with_spy(run):
    module = token_http()
    session = module.TokenSession
    spy = Spy()
    real = (session.__init__, session.get, session.grant)

    def init(self, http, **options):
        spy.built += 1
        real[0](self, http, **options)

    def get(self, url, **options):
        spy.gets += 1
        return real[1](self, url, **options)

    def grant(self, form):
        spy.grants += 1
        return real[2](self, form)

    session.__init__, session.get, session.grant = init, get, grant
    try:
        return run(), spy
    finally:
        session.__init__, session.get, session.grant = real


def gmail_world():
    fake = FakeGmail()
    KEYCHAIN.secrets.clear()
    KEYCHAIN.secrets.update(
        {
            ("mailroom", "gmail.personal.client-id"): fake.client_id,
            ("mailroom", "gmail.personal.client-secret"): fake.client_secret,
            ("mailroom", "gmail.personal.refresh-token"): fake.refresh_token,
        }
    )
    return fake, lambda http: gmail.GmailClient("personal", http), 1, gmail


def outlook_world():
    fake = FakeGraph()
    KEYCHAIN.secrets.clear()
    KEYCHAIN.secrets[("mailroom", "outlook.live.client-id")] = fake.client_id
    KEYCHAIN.secrets[("mailroom", "outlook.live.refresh-token")] = fake.refresh_token
    return fake, lambda http: outlook.OutlookClient("live", http), 2, outlook


def routed() -> object:
    for world in (gmail_world, outlook_world):
        fake, build, per_call, module = world()
        NOW[0] = START

        def run(fake=fake, build=build):
            client = build(httpx.Client(transport=httpx.MockTransport(fake.handler)))
            client.profile()
            client.profile()
            return client

        _client, spy = with_spy(run)
        gets = sum(1 for r in fake.requests if r.method == "GET")
        posts = sum(1 for r in fake.requests if r.method == "POST")
        if (spy.built, spy.gets, spy.grants) != (1, gets, posts) or gets != 2 * per_call:
            counts = f"built {spy.built}, gets {spy.gets}/{gets}, grants {spy.grants}/{posts}"
            return f"{module.__name__}: {counts}"
    return True


CLIENT_TOKEN = ["good", "good", "good", "listed", "503", "unusable", "network"]
CLIENT_API = [None, None, None, None, 401, 503, "network"]


def client_outcome(error: Exception, module) -> tuple[str, object]:
    auth = module.GmailAuthError if module is gmail else module.OutlookAuthError
    unavailable = module.GmailUnavailable if module is gmail else module.OutlookUnavailable
    if type(error) is auth:
        return ("auth", None)
    if type(error) is unavailable:
        return ("unavailable", str(error).rsplit("(", 1)[1].rstrip(")"))
    return ("other", type(error).__name__)


def client_script(seed: int, world) -> object:
    local = random.Random(seed)
    fake, build, per_call, module = world()
    NOW[0] = START
    token_plan: list[str] = []
    api_plan: list[object] = []
    posts = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts[0] += 1
            kind = token_plan.pop(0) if token_plan else "good"
            if kind == "good":
                return fake.handler(request)
            if kind == "listed":
                return httpx.Response(400, json={"error": "invalid_grant"})
            if kind == "503":
                return httpx.Response(503)
            if kind == "unusable":
                return httpx.Response(200, json={"access_token": 1, "expires_in": 60})
            raise httpx.ConnectError("unreachable")
        reply = api_plan.pop(0) if api_plan else None
        if reply is None:
            return fake.handler(request)
        if reply == "network":
            raise httpx.ConnectError("unreachable")
        return httpx.Response(int(reply))

    client = build(httpx.Client(transport=httpx.MockTransport(handler)))
    cached = False
    valid = False
    expiry = START
    lifetime = fake.expires_in
    outcomes: list[object] = []
    expected: list[object] = []
    for _step in range(8):
        NOW[0] += timedelta(seconds=local.choice([0, 60, 3000, 3600, 7200]))
        if local.random() < 0.2:
            fake.invalidate_tokens()
            valid = False
        tokens = [local.choice(CLIENT_TOKEN) for _ in range(2)]
        replies = [local.choice(CLIENT_API) for _ in range(2)]
        token_plan[:] = list(tokens)
        api_plan[:] = list(replies)
        before = posts[0]
        predicted: object = ("ok", None)
        predicted_posts = 0
        done = False
        for _get in range(per_call):
            outcome = None
            for _attempt in range(2):
                if not cached or NOW[0] >= expiry:
                    cached = False
                    kind = tokens.pop(0) if tokens else "good"
                    predicted_posts += 1
                    if kind != "good":
                        outcome = {
                            "listed": ("auth", None),
                            "503": ("unavailable", "503"),
                            "unusable": ("unavailable", "response"),
                            "network": ("unavailable", "network"),
                        }[kind]
                        break
                    cached = valid = True
                    expiry = NOW[0] + timedelta(seconds=lifetime) - MARGIN
                reply = replies.pop(0) if replies else None
                if reply is None and not valid:
                    reply = 401
                if reply == "network":
                    outcome = ("unavailable", "network")
                    break
                if reply == 401:
                    cached = False
                    continue
                if reply is not None:
                    outcome = ("unavailable", str(reply))
                break
            else:
                outcome = ("auth", None)
            if outcome is not None:
                predicted = outcome
                done = True
                break
        assert done or predicted == ("ok", None)
        expected.append((predicted, predicted_posts))
        try:
            client.profile()
            got: object = ("ok", None)
        except Exception as error:  # noqa: BLE001 - the probe classifies every error
            got = client_outcome(error, module)
        outcomes.append((got, posts[0] - before))
    if outcomes != expected:
        for index, (got, want) in enumerate(zip(outcomes, expected, strict=True)):
            if got != want:
                return f"{module.__name__} seed {seed} call {index}: got {got}, expected {want}"
    return outcomes


def client_parity() -> object:
    for seed in range(60):
        for world in (gmail_world, outlook_world):
            result = client_script(seed, world)
            if not isinstance(result, list):
                return result
    return True


check("1 neutral module", neutral)
check("2 session scripts (200 seeded)", session_scripts)
check("3 url guard (400 seeded urls)", url_guard)
check("4a both clients route through one session", routed)
check("4b client scripts match the oracle for both providers (60 seeded)", client_parity)
print(f"FAILURES {FAILURES}")
sys.exit(1 if FAILURES else 0)
