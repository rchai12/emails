# Phase 4c: Outlook login

## Goal

Sign in to one live.com account from the terminal, as Phase 1d does for Gmail: `mailroom outlook-login <account>`.

The command:
1. asks for the Microsoft app's client ID the first time, hidden;
2. opens Microsoft's sign-in page for personal accounts, with PKCE;
3. receives the answer on Gmail login's one-request listener on 127.0.0.1;
4. exchanges the code as a public client;
5. keeps the refresh token only if the grant is read-only mail;
6. names the signed-in address.

Nothing is stored unless the exchange succeeds with that grant. The service doesn't use Outlook yet (4d).

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 1160, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_outlook_login.py` must show `1160 passed`. The ignored file imports `mailroom.outlook_login`, which you create.

## Facts

Checked in Microsoft's documentation (auth code flow, redirect URIs) and against today's code. Nothing here was checked with a real account.

- **The sign-in page** is `https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize`.
  - `response_mode=query` puts the answer in the redirect's query, which the listener reads.
  - `prompt=select_account` lets the owner pick the live.com account when the browser knows several.
  - PKCE with `S256` is supported, and the code lives about a minute.
- **The exchange** POSTs `client_id`, `scope`, `code`, `redirect_uri`, `grant_type=authorization_code` and `code_verifier` to 4a's `TOKEN_URL`. A public client sends no secret. The reply's `scope` lists what was granted; Microsoft's case varies (`Mail.Read`, `mail.read`).
- **The redirect.** Microsoft ignores the port of a loopback redirect when matching it. The listener's `http://127.0.0.1:<port>` matches the registered `http://127.0.0.1` (a manifest step for the owner, from 4a). Microsoft adds `session_state` to a success and `error_description` to a refusal. Today's `gmail_login.Callback` ignores unknown keys, which was checked with the fake: a code is read, and a refusal cancels.
- **The listener's errors name Gmail.** `Callback` raises `"gmail login timed out: …"` and `"gmail login cancelled: …"`. It gains a `provider` keyword (default `"gmail"`) so Outlook's errors name Outlook. Gmail's tests don't change.
- **The address comes from 4a's `profile()`.** It refreshes with the stored token, which rotates it once more: a first login writes the refresh token twice.
- **The fake is extended (given).** `FakeGraph.consent(url, approve=True)` checks the sign-in request and answers as Microsoft does. The token endpoint accepts the code once, with its PKCE verifier and redirect. `granted_scope` sets the reply's `scope`.

## Owner's decisions

- From 4a: personal accounts only, and browser sign-in like Gmail (PKCE, a listener on 127.0.0.1).
- From 1d, for every login: ask for missing client keys hidden, with `--new-client` to replace them; store nothing unless the sign-in succeeds; end by showing the address.

## Architect's decisions

- **Reuse, don't copy.** `LoginError`, `Callback`, `new_verifier` and `code_challenge` come from `gmail_login`.
- **The grant must be read-only mail.** Lower-cased, the granted scopes must include `https://graph.microsoft.com/mail.read`, and may add only `offline_access`. Anything wider, or no mail scope, is refused.
- **The client ID** is asked as `Microsoft app (client) ID` and stored as `outlook.<account>.client-id` only after the exchange succeeds, as Gmail does.

## Requirements

1. **`gmail_login.Callback(account, *, provider: str = "gmail", request_timeout=...)`** uses `provider` in place of `gmail` in its two errors. Nothing else in `gmail_login.py` changes.
2. **`src/mailroom/outlook_login.py`, names:** `AUTH_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"` and `CLIENT_ID_LABEL = "Microsoft app (client) ID"`.
3. **`consent_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str`** is `AUTH_URL` with exactly these query parameters:
   - `client_id`, `response_type=code`, `redirect_uri`, `response_mode=query`;
   - `scope=outlook.SCOPE`, `state`;
   - `code_challenge`, `code_challenge_method=S256`, `prompt=select_account`.
4. **`exchange_code(http, account, *, client_id, code, verifier, redirect_uri) -> str`**:
   - It POSTs the exchange form above to `outlook.TOKEN_URL` and returns the reply's refresh token.
   - **Failures**, each `LoginError` raised `from None`: `"outlook login failed: <account> (network)"` for a transport error; `(<status>)` for a non-200; `(response)` for a body that isn't JSON, a `refresh_token` that isn't a non-empty string, or a `scope` that isn't a string.
   - **The scope rule** (Architect's decisions): a grant that breaks it raises `"outlook login scope refused: <account>"`.
5. **`login(account, http, *, ask, open_browser, new_client=False) -> str`**, in this order:
   1. It builds `OutlookClient(account, http)` first, so an invalid name raises `ValueError` before anything else.
   2. It reads `outlook.<account>.client-id`, or, when that's missing or `new_client` is set, asks `ask(CLIENT_ID_LABEL)`.
   3. It makes a verifier and a state, then, within `Callback(account, provider="outlook")`, opens the browser at `consent_url`, waits for the code and exchanges it.
   4. Only then it stores the client ID (if it was asked) and the refresh token.
   5. It returns `client.profile().email_address`.
6. **`new_http() -> httpx.Client`** is `httpx.Client(timeout=outlook.TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)`.
7. **`mailroom outlook-login <account> [--new-client]`** in `cli.py`, as `gmail-login`:
   - it prints `Opening Microsoft sign-in. If no browser opens, visit:` and the address, then opens it;
   - it asks with hidden input;
   - it prints `Signed in: <account> (<address>)`;
   - on `LoginError`, `OutlookError`, `KeychainError` or `ValueError`, it prints the error alone to stderr and exits 1.
8. **Progress entry** for `## Phase 4c: Outlook login (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Verify before building

For the owner, on the real account, after building:
- Run `mailroom outlook-login live` once. Confirm that the page offers your live.com account, that the consent lists only reading mail and staying signed in, and that the command ends `Signed in: live (<your address>)`.
- If Microsoft's reply grants a scope this phase refuses, for example `openid` added without being asked, the command says `scope refused`. Then the rule is revisited, not loosened in code.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/fakes.py` | Edited: `FakeGraph.consent`, the code exchange, `granted_scope` |
| `scripts/critical_modules.txt` | Edited: `outlook_login.py` added |
| `tests/integration/test_outlook_login.py` | The sign-in address; the exchange as a public client; three read-only grants accepted; four other grants refused; five failed exchanges; the callback naming Outlook; a first login; a later one; a new client; a cancelled login; a refused grant; an invalid account; the command signing in and failing |
| `docs/verification/probe-04c.py` | The verifier's probe |

Given test count: **23**, all new.

## Tests to write

The given tests cover every requirement's main cases. `outlook_login.py` and `gmail_login.py` are critical. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/outlook_login.py` | create |
| `src/mailroom/gmail_login.py` | `Callback`'s `provider` |
| `src/mailroom/cli.py` | the `outlook-login` command |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Outlook in the service, settings or alerts (4d).
- Device code flow, work accounts or a `common` tenant.
- Signing out, revoking tokens, or listing accounts.
- Any change to `outlook.py` or `outlook_sync.py`.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Read-only access.** Only `Mail.Read` (and `offline_access`) is asked for or kept.
- **Secrets come only from the Keychain,** never printed. The client ID is typed with hidden input, and no token appears in output or an error.
- **Nothing stored on a failed sign-in.**
- **Network.** Only `login.microsoftonline.com` and, for the address, `graph.microsoft.com`. The listener binds 127.0.0.1 only.
- **Time through the module:** the listener's deadline, as today.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 23 = 1183 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_outlook_login.py --no-cov -q` | `23 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/outlook_login.py,src/mailroom/gmail_login.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python docs/verification/probe-04c.py` | last line `FAILURES 0` |
| `grep -c "^## Phase 4c: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 4c` | `Reports OK.` |
| `git diff HEAD --stat -- tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook_login.py docs/verification/probe-04c.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'client_secret|client-secret|/common/|/organizations/|Mail\.(ReadWrite|Send)' -- src/mailroom/outlook_login.py
git grep --untracked -n -E 'HTTPServer|BaseHTTPRequestHandler|def new_verifier|def code_challenge' -- src/mailroom/outlook_login.py
git grep --untracked -n -E 'response\.text|str\((error|exc|e)\)|\{(error|exc|e)(!r)?\}|error_description' -- src/mailroom/outlook_login.py
git grep --untracked -n -E 'echo\([^)]*(token|refresh)' -- src/mailroom/cli.py
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/outlook_login.py src/mailroom/gmail_login.py
```
