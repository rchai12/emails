# Phase 1d: Gmail login

## Goal

Add the one-time Gmail sign-in: `mailroom gmail-login <account>` opens Google's consent page, receives Google's answer on a one-request listener on 127.0.0.1, exchanges the code (with PKCE) for a refresh token that is accepted only for the read-only scope, stores it in the Keychain, and confirms by reading the account's address. On a first login it asks for the OAuth client ID and secret and stores them too. Nothing here polls or syncs: 1h runs the sync with what this phase stores.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 239, the tests Phase 1c left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_keychain_write.py --ignore=tests/integration/test_gmail_login.py` must show `239 passed`. The ignored files import names you create.

## Facts

From Google's "OAuth 2.0 for Mobile & Desktop Apps" page, Python 3.12's standard library on this machine, and `tests/fakes.py`.

- **Desktop sign-in.** The redirect is a loopback address, `http://127.0.0.1:<port>`, with the app listening on a free port; copy-and-paste codes are no longer supported. The consent page is `https://accounts.google.com/o/oauth2/v2/auth` with `client_id`, `redirect_uri`, `response_type=code`, `scope` (space-separated), `code_challenge`, `code_challenge_method=S256` and `state`. Google sends the browser back with `state` and `code` (and `scope`) in the query, or with `error` (`access_denied` when you decline).
- **The exchange.** `POST https://oauth2.googleapis.com/token`, form-encoded `code`, `client_id`, `client_secret`, `redirect_uri`, `grant_type=authorization_code` and `code_verifier`. The answer has `access_token`, `expires_in`, `refresh_token` (always returned for installed apps), `scope` and `token_type`. With granular consent you can untick a scope, so the app must check `scope`.
- **PKCE.** The verifier is 43 to 128 characters from `A-Z a-z 0-9 - . _ ~`; the S256 challenge is the base64url SHA-256 of the verifier without `=` padding. `secrets.token_urlsafe(64)` gives 86 such characters.
- **`http.server`.**
  - `HTTPServer(("127.0.0.1", 0), Handler)` binds and listens at once; `server.server_address` gives the bound host and port.
  - `server.handle_request()` serves one connection, waiting at most `server.timeout` seconds.
  - A handler class's `timeout` sets a timeout on each connection. Without it, an idle connection (browsers open spare ones) blocks the single-threaded server until it closes. Spiked: with `timeout = 2`, an idle socket held the server 2 seconds and the real request was then served.
  - `BaseHTTPRequestHandler.log_message` writes every request line, the code included, and every timeout to stderr unless overridden.
  - A method with no `do_<METHOD>` gets a 501 answer.
- **Tests reach 127.0.0.1.** `tests/conftest.py` allows connections to 127.0.0.1, so tests visit the listener from a thread with `httpx.get`.
- **The fakes.**
  - `FakeGmail.consent(url, approve=True)` checks the consent address and returns Google's redirect: with `state`, a one-time `code` and `scope` (`granted_scope`), or `error=access_denied`.
  - The fake token endpoint now also takes the `authorization_code` grant: it checks the form, the code's redirect address and the PKCE verifier, and returns `refresh_token` `refresh-token-from-<code>`, which the refresh grant then accepts.
  - `FakeKeychain.set_password` stores the value and records the name in `writes`.
- **Typer.** `typer.prompt(label, hide_input=True)` does not echo what is typed. In `CliRunner`, `result.output` holds stdout and stderr together.

## Owner's decisions

- **A local listener** on 127.0.0.1 receives Google's answer, and the browser shows a short "you can close this tab" page.
- **The login asks for the OAuth client ID and secret** (hidden input) when either is missing from the Keychain, and stores them; a later login reuses them unless `--new-client` is given.

## Architect's decisions

- **Only the read-only scope is stored.** A token whose granted `scope` is not exactly `gmail.readonly` (missing, or with anything more) is refused and nothing is stored.
- **Nothing is stored until the exchange succeeds.** The client ID, the client secret and the refresh token are written together at the end, in that order; a cancelled or failed login leaves the Keychain as it was.
- **The listener** binds 127.0.0.1 on a free port, serves one connection at a time with a 5-second limit per connection, ignores every request that is not `GET /` with the expected `state`, waits at most 5 minutes, writes nothing to the terminal, and never echoes a request in its pages.
- **Randomness.** The PKCE verifier and `state` come from `secrets.token_urlsafe` (they are secrets, not ids, so not `ids.new_id`). Tests never need to fix them: the fake checks the verifier against the challenge, and tests read `state` from the address.
- **The confirmation** is a `profile()` call through a `GmailClient` built on the new secrets; its address is the result.
- **`keychain.set_secret`** is the only Keychain write, used only by the login.
- **Critical module**: `gmail_login.py` (it handles every Gmail secret); `keychain.py` already is one.

## Requirements

1. **`keychain.py`: `set_secret(name: str, value: str) -> None`.**
   - It raises `ValueError(NAME_MESSAGE)` for a name `get_secret` would refuse, and `ValueError(VALUE_MESSAGE)` with `VALUE_MESSAGE = "empty secret value"` for `""`, before any Keychain call.
   - It stores the value with `keyring.set_password(SERVICE, name, value)`.
   - A `KeyringError` raises `KeychainUnavailable(f"keychain unavailable: {name}")` from `None`.

2. **`src/mailroom/gmail_login.py`, names.**
   - `AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"`
   - `CALLBACK_TIMEOUT = timedelta(minutes=5)`, `REQUEST_TIMEOUT_SECONDS = 5.0`
   - `DONE_PAGE = "Signed in to mailroom. You can close this tab."`, `CANCELLED_PAGE = "Sign-in cancelled. You can close this tab."`
   - `class LoginError(Exception)`, always raised `from None`, with one of these texts: `gmail login cancelled: <account>`, `gmail login timed out: <account>`, `gmail login scope refused: <account>`, `gmail login failed: <account> (<detail>)`, where the detail is the HTTP status number, `network` or `response`.

3. **PKCE.** `new_verifier() -> str` returns `secrets.token_urlsafe(64)`. `code_challenge(verifier: str) -> str` returns the base64url SHA-256 of the verifier's ASCII bytes, without `=` padding.

4. **`consent_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str`** returns `AUTH_URL` with exactly these query parameters, each once and correctly encoded: `client_id`, `redirect_uri`, `response_type=code`, `scope=gmail.SCOPE`, `code_challenge`, `code_challenge_method=S256`, `state`.

5. **`Callback(account: str, *, request_timeout: float = REQUEST_TIMEOUT_SECONDS)`**, a context manager.
   - **Opening.** Creating it binds an `http.server.HTTPServer` to `("127.0.0.1", 0)`. Its handler's per-connection timeout is `request_timeout`.
   - **`redirect_uri`** (attribute) is `f"http://{host}:{port}"` from the server's `server_address`, with no path.
   - **Closing.** Leaving the `with` block closes the server, so the port refuses connections.
   - **No output.** Nothing is written to stdout or stderr: the handler overrides `log_message` to do nothing.

6. **`Callback.wait(state: str) -> str`.**
   - **Time.** It reads `clock.now()` once to set the deadline (`+ CALLBACK_TIMEOUT`), then before each `handle_request()`. At or after the deadline it raises `LoginError` `timed out`; otherwise it sets the server's timeout to the seconds remaining.
   - **Each request.** Only `GET` is handled. A path other than `/` gets 404. A request to `/` whose query does not hold exactly one `state` equal to `state` gets 400, as does one with that state but without exactly one non-empty `code` or `error`. These are ignored, and the wait goes on.
   - **The answer.** With the right state, exactly one non-empty `code` gets 200 with `DONE_PAGE`, and `wait` returns the code. An `error` gets 200 with `CANCELLED_PAGE`, and `wait` raises `LoginError` `cancelled`.
   - **Pages** are `text/plain; charset=utf-8` with constant text (the two pages above, or a constant for 400 and 404); none includes anything from the request.

7. **`exchange_code(http: httpx.Client, account: str, *, client_id: str, client_secret: str, code: str, verifier: str, redirect_uri: str) -> str`.**
   - **The request.** `http.post(gmail.TOKEN_URL, data=...)` with exactly `code`, `client_id`, `client_secret`, `redirect_uri`, `grant_type="authorization_code"` and `code_verifier`, and no `Authorization` header.
   - **The answer.** A 200 whose JSON has a string `refresh_token` and a string `scope`. If the set of `scope.split()` is exactly `{gmail.SCOPE}`, it returns the refresh token. Otherwise it raises `LoginError` `scope refused`.
   - **Failures.**
     - Another status raises `failed (<status>)`.
     - An `httpx.TransportError` raises `failed (network)`.
     - Bad JSON, or a missing or non-string field, raises `failed (response)`.

8. **`login(account: str, http: httpx.Client, *, ask: Callable[[str], str], open_browser: Callable[[str], object], new_client: bool = False) -> str`.**
   1. Build `gmail.GmailClient(account, http)` first, so an invalid account raises its `ValueError` before anything else.
   2. **The client.** Unless `new_client`, read `gmail.<account>.client-id` and `.client-secret` with `keychain.get_secret`. If `new_client`, or either raises `SecretMissing`, call `ask("Gmail OAuth client ID")` then `ask("Gmail OAuth client secret")` and use the answers. Other keychain errors propagate.
   3. **Consent.** Make a verifier and `state = secrets.token_urlsafe(32)`, open a `Callback`, call `open_browser(consent_url(...))` with its `redirect_uri`, and `wait(state)`.
   4. **Exchange.** Call `exchange_code` with the same `redirect_uri`, then close the callback.
   5. **Store.** Write with `keychain.set_secret`: the client ID and client secret (only if they were asked for), then `gmail.<account>.refresh-token`.
   6. **Confirm.** Return the client's `profile().email_address`.
   - Every error propagates unchanged; a `LoginError` before step 5 leaves the Keychain unwritten.

9. **`new_http() -> httpx.Client`** returns `httpx.Client(timeout=gmail.TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)`.

10. **`cli.py`: `mailroom gmail-login ACCOUNT [--new-client]`.**
    - It calls `gmail_login.login(account, gmail_login.new_http(), ask=..., open_browser=..., new_client=...)`, looking up `new_http` on the module when it runs.
    - **`ask`** is `typer.prompt(label, hide_input=True)`.
    - **`open_browser`** prints `Opening Google sign-in. If no browser opens, visit:` and then the address on its own line, then calls `webbrowser.open(address)`, looked up on the `webbrowser` module when it runs.
    - **Success** prints `Signed in: <account> (<address>)` and exits 0.
    - **A failure** (a `LoginError`, `GmailError`, `KeychainError` or `ValueError`) prints the error's text to stderr as the last line and exits 1, with no traceback.

11. **Critical modules.** `scripts/critical_modules.txt` (given) lists `gmail_login.py`.

12. **Progress entry** for `## Phase 1d: Gmail login (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/fakes.py` | `FakeKeychain` stores writes; `FakeGmail` adds `consent` and the authorization-code grant |
| `tests/unit/test_keychain_write.py` | 4 tests (requirement 1) |
| `tests/integration/test_gmail_login.py` | 25 tests (requirements 2 to 10) |
| `scripts/critical_modules.txt` | Adds `gmail_login.py` |
| `docs/verification/probe-01d.py` | The verifier's probe |

Given test count: **29**.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_gmail_login_more.py`, never by changing a given test, for at least:
- a `POST` to the callback gets 501 and the wait goes on (requirement 6)
- a token answer whose `scope` is not a string (`failed (response)`, requirement 7)
- `new_http()`'s timeout, `trust_env` and `follow_redirects` (requirement 9)

## Scope

| Path | Change |
|---|---|
| `src/mailroom/gmail_login.py` | create |
| `src/mailroom/keychain.py` | add `VALUE_MESSAGE` and `set_secret` |
| `src/mailroom/cli.py` | add the `gmail-login` command |
| `tests/integration/test_gmail_login_more.py` | create |
| `docs/progress.md` | append your entry |

## Out of scope

- **Running anything.** The poll loop, sync scheduling, a launchd file (1h). Discord alerts for a revoked token (1g).
- **More sign-in.** Revoking or deleting tokens, a `logout` command, listing accounts, settings for accounts, a second provider's login, refresh-token rotation, DPoP.
- **More listener.** Threads, HTTPS, an HTML page, retries, a configurable port or host.
- **Other changes.** Logging. Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Secrets** (`AGENTS.md` rule 6): the client secret, the code, the verifier and the tokens never appear in an error, a page, a log or the terminal. Only the consent address (client ID, redirect, challenge and state) is printed, for you to open.
- **Least access**: only `gmail.readonly` is asked for, and only a token for exactly that scope is stored.
- **Network**: `oauth2.googleapis.com` (through `http`) and the listener on 127.0.0.1, nothing else. Tests reach Google's endpoints only through `FakeGmail`. Never run the login against real Google, not even to try it, and never read or write the real Keychain.
- **Time through the module**: `clock.now()`, never `datetime.now()` or `time.time()`, and never `from mailroom.clock import now`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 29 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_keychain_write.py tests/integration/test_gmail_login.py --no-cov -q` | `29 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/gmail_login.py,src/mailroom/keychain.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1d: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1d` | `Reports OK.` |
| `git diff HEAD --stat -- tests/fakes.py tests/unit/test_keychain_write.py tests/integration/test_gmail_login.py scripts/critical_modules.txt docs/verification/probe-01d.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing, except the fourth, which prints exactly two lines (the token `POST` in `gmail.py` and in `gmail_login.py`), and the seventh, which prints exactly one line (`set_password` in `keychain.py`).

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request|(import|from) urllib([^.A-Za-z_]|$)' -- src
git grep --untracked -n -E 'httpx|http\.server' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py'
git grep --untracked -n -E '\.(put|patch|delete|request|send|stream)\(|"(POST|PUT|PATCH|DELETE)"' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py src/mailroom/gmail_login.py
git grep --untracked -n -E '\.post\(' -- src
git grep --untracked -n -E 'https?://' -- src/mailroom/gmail_login.py | grep -v -F -e '"https://accounts.google.com/o/oauth2/v2/auth"' -e 'f"http://{'
git grep --untracked -n -E '0\.0\.0\.0|"localhost"|"::"|"::1"' -- src
git grep --untracked -n -E 'set_password|delete_password' -- src
git grep --untracked -n -E 'set_secret|webbrowser' -- src ':!src/mailroom/keychain.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/cli.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn|sys\.std(out|err)' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.(time|monotonic)\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/gmail_login.py src/mailroom/keychain.py src/mailroom/cli.py
```
