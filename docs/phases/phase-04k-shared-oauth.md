# Phase 4k: Extract shared OAuth mechanics

## Goal

The pieces both browser sign-ins share move into a new module, `mailroom/oauth.py`, that
names no provider:

- the local callback;
- PKCE;
- the login error;
- the token-reply check.

Gmail and Outlook keep their own consent URL, scope rule, client keys and `login`.
`outlook_login` stops importing from `gmail_login`. Each login command closes the HTTP
client it opens, whether the sign-in succeeds, is cancelled or fails. This closes audit
finding 4.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is **1529**, from the passing Phase 4j review
(`ab949f0`). The coder's clean start is the planning and given-file commit made after
this document.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_oauth.py --ignore=tests/integration/test_login_close.py`
must show `1529 passed`. Nothing needs a missing-module stub. The two new given files
import only names that exist today. They reach `mailroom.oauth` through
`importlib.import_module` when a test runs.

## Facts

- `gmail_login.py` holds the shared parts today:
  - the constants `CALLBACK_TIMEOUT` (5 minutes), `REQUEST_TIMEOUT_SECONDS` (5.0),
    `DONE_PAGE` and `CANCELLED_PAGE`, plus the private `_BAD_PAGE` and `_MISSING_PAGE`;
  - `LoginError`, `new_verifier()` and `code_challenge()`;
  - `Callback(account, *, provider="gmail", request_timeout=...)` and its private
    `_handler`.

  The Gmail-only parts are `AUTH_URL`, `consent_url`, `exchange_code`, `login`,
  `new_http` and `_client_keys`.
- `outlook_login.py` runs
  `from mailroom.gmail_login import Callback, LoginError, code_challenge, new_verifier`,
  so an Outlook sign-in loads `mailroom.gmail_login` and `mailroom.gmail`.
- The two `exchange_code` functions repeat the same reply check, line for line. Each
  error is a `LoginError` raised `from None`, with these texts:

  | Reply | Error text |
  |---|---|
  | A transport error | `"<provider> login failed: <account> (network)"` |
  | Any status other than 200 | `"... (<status>)"` |
  | A body that is not a JSON object | `"... (response)"` |
  | A refresh token that is not text | `"... (response)"` |
  | A scope that is not text | `"... (response)"` |

  The checks differ in one place. Outlook also refuses an empty refresh token, while
  Gmail accepts one today.
- The scope rules differ by provider:
  - Gmail needs the granted set to be exactly `{gmail.SCOPE}`.
  - Outlook lowercases the granted set, which must contain `Mail.Read` and be a subset
    of `{Mail.Read, offline_access}`.

  Both raise `"<provider> login scope refused: <account>"`.
- `cli.gmail_login_command` and `cli.outlook_login_command` pass
  `<module>.new_http()` straight into `login` and never close the client. They catch
  `gmail_login.LoginError`. `cli._registered()` already uses the try/finally close
  pattern for another client.
- `httpx.Client.is_closed` becomes true after `close()` or after leaving a `with`
  block. It also works with a `MockTransport`.
- Existing tests pin the old import paths:
  - `test_gmail_login.py` imports `AUTH_URL`, `CALLBACK_TIMEOUT`, `CANCELLED_PAGE`,
    `DONE_PAGE`, `REQUEST_TIMEOUT_SECONDS`, `Callback`, `LoginError`,
    `code_challenge`, `consent_url`, `exchange_code`, `login` and `new_verifier` from
    `gmail_login`. It also calls `Callback("personal")`.
  - `test_gmail_login_more.py` imports `Callback`, `LoginError` and `new_http` from
    `gmail_login`.
  - `test_outlook_login.py` imports `Callback` and `LoginError` from `gmail_login`,
    and calls `Callback("live", provider="outlook")`.
  - The command tests in all of them monkeypatch `<module>.new_http`.
  - The probes `probe-01d.py` and `probe-04c.py` also import from both modules.
- Validated with a throwaway scratch stand-in only, never copied in:
  - All 80 login and CLI tests pass on it, the given ones included. Those are
    `test_gmail_login*.py`, `test_outlook_login*.py`, `tests/unit/test_cli.py` and the
    two given files.
  - The given tests pass 6 of 6 runs.
  - `probe-01d.py` and `probe-04c.py` end with `FAILURES 0`.
  - On predecessor code, all 25 given cases fail.

## Owner's decisions

- **2026-11-22:** the module is `mailroom/oauth.py`.
- **2026-11-22:** the token-reply check is shared as `oauth.token_reply`, so all
  providers have one error contract, and the scope rules stay per provider. As a
  result, Gmail now refuses an empty refresh token.
- **2026-11-22:** `oauth.Callback` requires the `provider` keyword. `gmail_login` keeps
  a thin `Callback` subclass that defaults to `provider="gmail"`, so old imports and
  tests keep working. Outlook uses `oauth.Callback` directly.
- **2026-11-22:** the CLI command closes the client.
  - Each command opens it with `with <module>.new_http() as http:` inside its `try`.
  - It looks up `new_http` on the module when it runs.
  - `login()` keeps borrowing the client it is given and does not close it.
  - The commands catch `oauth.LoginError`.

## Architect's decisions

- **Moved, not copied.** The shared names exist once, in `oauth.py`.
  - `gmail_login` imports `CALLBACK_TIMEOUT`, `REQUEST_TIMEOUT_SECONDS`, `DONE_PAGE`,
    `CANCELLED_PAGE`, `LoginError`, `new_verifier` and `code_challenge` from it, so
    `gmail_login.X is oauth.X`.
  - `gmail_login` lists those names in `__all__`, so ruff sees them as re-exports.
  - `outlook_login` imports `Callback`, `LoginError`, `code_challenge`, `new_verifier`
    and `token_reply` from `oauth`.
- **`oauth.py` names no provider.** It imports only the standard library, `httpx` and
  `mailroom.clock`. No string in it, docstrings and comments included, names Gmail,
  Outlook, Google, Microsoft or Yahoo. Each caller passes its provider name.
- **The token URL and form stay with the provider.** `token_reply` takes the URL and
  the form data, and only posts them and checks the reply. Each `exchange_code` keeps
  its own form fields and calls `token_reply`, then applies its own scope rule.
- **The CLI change is the two `with` blocks and the caught error type.** The prompts,
  messages and exit codes stay the same.
- **`oauth.py` is a critical module.** This spec adds it to `docs/testing.md` beside
  `gmail_login.py`, which keeps its entry.

## Requirements

1. **`mailroom/oauth.py`.** Create it with exactly these public names:
   - The constants `CALLBACK_TIMEOUT = timedelta(minutes=5)`,
     `REQUEST_TIMEOUT_SECONDS = 5.0`,
     `DONE_PAGE = "Signed in to mailroom. You can close this tab."` and
     `CANCELLED_PAGE = "Sign-in cancelled. You can close this tab."`.
   - `class LoginError(Exception)`.
   - `new_verifier() -> str` and `code_challenge(verifier: str) -> str`, with the
     same behavior as today.
   - `class Callback` with
     `__init__(self, account: str, *, provider: str, request_timeout: float = REQUEST_TIMEOUT_SECONDS)`.
     `provider` has no default, and calling `Callback("x")` raises `TypeError`.
     Everything else behaves as today:
     - it binds `127.0.0.1` on a free port and sets `redirect_uri`;
     - it works as a context manager;
     - `wait(state)` checks the path, the state, and the code or error;
     - it reads the time through `clock.now()`;
     - its timeout and cancel errors read `f"{provider} login timed out: {account}"` and
       `f"{provider} login cancelled: {account}"`, raised `from None`.
   - `token_reply(http: httpx.Client, url: str, data: dict[str, str], *, provider: str, account: str) -> tuple[str, str]`.
     It sends `http.post(url, data=data)` once and returns
     `(refresh_token, scope)`. It raises `LoginError` `from None` with these texts:

     | Reply | Error text |
     |---|---|
     | An `httpx.TransportError` | `f"{provider} login failed: {account} (network)"` |
     | Any status other than 200 | `f"{provider} login failed: {account} ({status})"` |
     | A body that is not JSON | `f"{provider} login failed: {account} (response)"` |
     | A JSON body that is not an object | `f"{provider} login failed: {account} (response)"` |
     | A refresh token that is missing, not text or empty | `f"{provider} login failed: {account} (response)"` |
     | A scope that is missing or not text | `f"{provider} login failed: {account} (response)"` |

     No error text contains the reply, the code, a token or library exception text.
2. **`gmail_login.py`.**
   - Remove the moved definitions, including `_handler`, `_BAD_PAGE` and `_MISSING_PAGE`.
   - Import the shared names from `oauth`, as the Architect's decisions say.
   - Define `class Callback(oauth.Callback)`. Its `__init__` has the same signature as
     today (`provider: str = "gmail"`), and it passes everything to the parent.
   - `exchange_code` keeps its signature and form data. It calls
     `oauth.token_reply(..., provider="gmail", account=account)` and then applies the
     unchanged Gmail scope rule. So an empty refresh token is now refused with
     `"gmail login failed: <account> (response)"`.
   - `AUTH_URL`, `consent_url`, `login`, `new_http` and `_client_keys` stay as they are.
     `login` still uses `Callback(account)`.
3. **`outlook_login.py`.**
   - It imports nothing from `gmail_login` or `gmail`.
   - `exchange_code` keeps its signature and form data. It calls `token_reply(...,
     provider="outlook", account=account)` and then applies the unchanged Outlook scope
     rule.
   - `login` still uses `Callback(account, provider="outlook")`.
   - Everything else is unchanged.
   - In a fresh interpreter, `import mailroom.oauth, mailroom.outlook_login` loads no
     `mailroom.gmail*` module.
4. **CLI closes its client.**
   - In `gmail_login_command` and `outlook_login_command`, open the client with
     `with <module>.new_http() as http:` inside the existing `try`.
   - Pass `http` to `<module>.login(...)`.
   - Catch `oauth.LoginError` in place of `gmail_login.LoginError`.
   - The client is closed after a success, after every reported error, and after an
     unexpected exception that propagates.
   - Output and exit codes are unchanged.
5. **Compatibility.** Existing tests keep passing unchanged. Other things stay the same:
   - the consent URLs and form fields;
   - the scope rules and the Keychain writes after a good exchange;
   - nothing stored on a failed sign-in;
   - the `REQUEST_TIMEOUT_SECONDS` read timeout per callback connection;
   - the `new_http` clients' settings.
6. **Critical module.** Add `oauth.py` to the critical modules list in
   `docs/testing.md`. This is done in the planning commit; the coder does not edit it.
7. **Progress entry** for `## Phase 4k: Extract shared OAuth mechanics (YYYY-MM-DD)` at
   the end of `docs/progress.md`, with actual counts.

## Given files

Committed with the finalized spec before coding. The coder never changes them.

| File | What it is |
|---|---|
| `tests/integration/test_oauth.py` | 17 cases. It checks that the shared names are oauth's objects, re-exported by `gmail_login` and used by `outlook_login`, and that the neutral callback requires its provider and names it in a timeout. It checks that `gmail_login.Callback` still defaults to gmail, and that a fresh interpreter loading oauth and Outlook sign-in loads no gmail module. It runs a good reply and 11 bad replies through `token_reply` under a made-up provider, each with one exact, context-free error. It checks that Gmail now refuses an empty refresh token |
| `tests/integration/test_login_close.py` | 8 cases. Each provider's command is run signed in, cancelled, with a failing Keychain and with an invalid account name. Each case checks the exit code and last line, and that the one client it opened is closed |
| `docs/verification/probe-04k.py` | It loads `mailroom.oauth` and `mailroom.outlook_login` in a fresh interpreter, and inspects oauth's imports (no provider) and the shared names (oauth's objects). It sends 1500 seeded random replies to `token_reply` under random providers, and 1500 to both `exchange_code` functions, checking each against its own oracle for the reply and scope contracts. It checks that the callback names any provider, and sends every login command outcome (success, every reported error, an unexpected error) through a recording `login` that must be lent an open client that is closed afterwards |

Given test count: **25** new cases, so the minimum final suite is **1554**.

## Tests to write

Add behavior tests in `tests/integration/test_oauth_flow.py`, not a `_more` file.
`oauth.py` and `gmail_login.py` are critical: cover every line and branch.
`outlook_login.py` stays at 100% too. On a stand-in, the given tests and existing tests
already reach that. Add tests for behavior they leave unpinned, for example:

- an unexpected exception raised inside `login` still closes the client and propagates
  from the command;
- `login` is lent the client `new_http` returned, still open;
- a 400 reply carrying an `error_description` gives only the status in the error, for
  both providers' `exchange_code`;
- `token_reply` sends exactly the form it was given and nothing else, such as no extra
  header or field that holds a secret.

Use synthetic data. Do not edit given or earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/oauth.py` | New: the shared constants, `LoginError`, PKCE, `Callback` and `token_reply` |
| `src/mailroom/gmail_login.py` | Re-exports, the `Callback` subclass, `exchange_code` through `token_reply` |
| `src/mailroom/outlook_login.py` | Imports from `oauth`, `exchange_code` through `token_reply` |
| `src/mailroom/cli.py` | The two login commands close their client; catch `oauth.LoginError` |
| `tests/integration/test_oauth_flow.py` | New coder-written behavior tests |
| `docs/progress.md` | Append the Phase 4k entry |

New tests fall in `core`, so `tests/sections.toml` stays unchanged.

## Out of scope

- A Yahoo or any third provider, an IMAP sign-in, or app passwords.
- Changes to the following:
  - the refresh-token use in `gmail.py` and `outlook.py`, or the rotated Outlook token
    (4h);
  - the consent URLs, scopes, form fields, Keychain names or prompts;
  - `new_http` settings.
- A login class hierarchy, a provider registry, or moving `login`, `consent_url` or
  `_client_keys` into `oauth.py`.
- Making `login()` own or close its client, and closing clients in other commands.
- Changes to fakes, given files, earlier tests, dependencies or design documents. The
  `docs/testing.md` line comes with this spec.

## Rules that bite

All checks are synthetic and offline. The callback listens only on 127.0.0.1. Never
open a real consent page, contact Google or Microsoft, read the Keychain or touch the
data folder.

- **Moved names must be oauth's objects.** Redefining `LoginError` in `gmail_login` or
  `outlook_login` splits the error type. The CLI would then miss one provider's errors.
- **The command tests replace `<module>.new_http`**, so the CLI must look it up on the
  module when the command runs. Never bind it at import, as a default argument or with
  `from ... import new_http`.
- **Use `with`.** Closing only after a successful `login`, or in an `except` block,
  leaves the client open on other paths.
- **Keep the error texts.** Do not add the reply's `error` or `error_description` to an
  error. Do not catch a broad `Exception` to make one.

## Acceptance

Run from the repository root, in order. The coverage row reads the data the check left;
the given-only run has `--no-cov` and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | The last line is `All checks passed.`. The tests (core) passed: at least 1554 passed; 0 failed, skipped or xfailed; no warnings. Every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include='src/mailroom/oauth.py,src/mailroom/gmail_login.py,src/mailroom/outlook_login.py' --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_oauth.py tests/integration/test_login_close.py --no-cov -q` | 25 passed |
| `.venv/bin/python docs/verification/probe-04k.py` | each check line ends ok; final FAILURES 0 |
| `.venv/bin/python docs/verification/probe-01d.py` | final FAILURES 0 |
| `.venv/bin/python docs/verification/probe-04c.py` | final FAILURES 0 |
| `grep -c '^## Phase 4k: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4k` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04k-shared-oauth.md docs/verification/phase-04k-shared-oauth.md tests/integration/test_oauth.py tests/integration/test_login_close.py docs/verification/probe-04k.py docs/testing.md` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may also write its named review |

### Searches

Each prints nothing. A git grep exit of 1 means no matches, and an exit above 1 is an
error.

```zsh
git grep --untracked -n -E 'http\.post\(|\.json\(\)|TransportError|HTTPServer|BaseHTTPRequestHandler|hashlib|base64|class LoginError|def (new_verifier|code_challenge|_handler)\(' -- src/mailroom/gmail_login.py src/mailroom/outlook_login.py
git grep --untracked -n -i -E 'gmail|outlook|google|microsoft|yahoo' -- src/mailroom/oauth.py
git grep --untracked -n -E 'gmail' -- src/mailroom/outlook_login.py
git grep --untracked -n -E '[a-z_]+_login\.LoginError|^ +[a-z_]+_login\.new_http\(\),|from mailroom\.[a-z_]+_login import' -- src/mailroom/cli.py
git grep --untracked -n -E 'except (Exception|BaseException)[ :]|pragma: no cover|noqa|datetime\.now|from mailroom\.(clock|ids) import|print\(|logging' -- src/mailroom/oauth.py src/mailroom/gmail_login.py src/mailroom/outlook_login.py
```

## Architect validation and handoff

No feature implementation was built. The given tests collect on predecessor imports,
and all 25 new cases fail there.

A throwaway scratch stand-in (about 360 changed lines, 128 of them the new module, deleted with the scratch clone)
did the following. It is not a reference for the coder.

- It passed the given tests 6 of 6 runs.
- It passed all 80 login and CLI tests, the given ones included.
- It left `oauth.py`, `gmail_login.py` and `outlook_login.py` at 100% line and branch
  coverage.
- `probe-01d.py` and `probe-04c.py` ended FAILURES 0 on it.
- 11 of 11 mutations of it were caught by a given or existing test:
  - a gmail default on the neutral callback, and gmail named in every timeout;
  - an empty token or a non-text scope accepted by `token_reply`;
  - only server errors treated as failed;
  - the network error kept as context;
  - `outlook_login` importing from `gmail_login` again;
  - either provider's scope rule loosened;
  - either command passing its client without closing it.

The probe results:

- On predecessor code it ends FAILURES 7. `mailroom.oauth` does not exist, so every
  check fails.
- On the stand-in it ends FAILURES 0.
- It catches all 11 mutations. It also catches a command that closes the client only
  after success, which needs two edits and so is not a single mutation row.

The searches print nothing on the stand-in, and each catches a planted line. On
predecessor code, searches 1, 3 and 4 print the old reply checks, the import from
`gmail_login` and the CLI's inline `new_http()`. Start shows 1529 passed. The given
files are linted and formatted.

Before coder use, commit the finalized planning docs and given artifacts, including the
roadmap, history and `docs/testing.md` updates, and require a clean checkout.
