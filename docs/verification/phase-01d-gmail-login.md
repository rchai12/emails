# Verification guide: Phase 1d (Gmail login)

Spec: `docs/phases/phase-01d-gmail-login.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/gmail_login.py`
- `tests/integration/test_gmail_login_more.py`
- `grep -c "^## Phase 1d: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01d-gmail-login.md tests/fakes.py tests/unit/test_keychain_write.py tests/integration/test_gmail_login.py scripts/critical_modules.txt docs/verification/probe-01d.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 29.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 29 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_keychain_write.py tests/integration/test_gmail_login.py --no-cov -q` | `29 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/gmail_login.py,src/mailroom/keychain.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1d: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1d` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- tests/fakes.py tests/unit/test_keychain_write.py tests/integration/test_gmail_login.py scripts/critical_modules.txt docs/verification/probe-01d.py` | no output |
| G7 | `git status --short` | only the Scope paths |
| G8 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `keychain.py` | drop the empty-value check | `tests/unit/test_keychain_write.py::test_a_bad_name_or_an_empty_value_is_refused_before_the_keychain[empty]` | `ValueError` `empty secret value` | no exception; one write |
| S2 | `keychain.py` | raise `KeychainUnavailable` without `from None` | `tests/unit/test_keychain_write.py::test_a_keychain_failure_names_only_the_secret` | `__suppress_context__` `True` | `False` |
| S3 | `gmail_login.py` | keep the `=` padding on the challenge | `tests/integration/test_gmail_login.py::test_the_challenge_is_the_unpadded_base64url_sha256` | `...dnLI8` | `...dnLI8=` |
| S4 | `gmail_login.py` | leave `code_challenge_method` out of the consent address | `tests/integration/test_gmail_login.py::test_the_consent_address_asks_for_read_only_access_with_pkce` | 7 parameters | no `('code_challenge_method', 'S256')` |
| S5 | `gmail_login.py` | bind `"0.0.0.0"` instead of `"127.0.0.1"` | `tests/integration/test_gmail_login.py::test_the_callback_listens_on_loopback_only_until_closed` | `http://127.0.0.1:<port>` | `http://0.0.0.0:<port>` |
| S6 | `gmail_login.py` | remove the `log_message` override | `tests/integration/test_gmail_login.py::test_the_callback_returns_the_code_quietly` | `('', '')` | stderr holds `127.0.0.1 - -` |
| S7 | `gmail_login.py` | accept any `state` | `tests/integration/test_gmail_login.py::test_requests_that_are_not_the_callback_are_refused_and_ignored` | `'code-1'` | `'code-9'` |
| S8 | `gmail_login.py` | take the first `code` when there are several | `tests/integration/test_gmail_login.py::test_requests_that_are_not_the_callback_are_refused_and_ignored` | `'code-1'` | `'code-9'` |
| S9 | `gmail_login.py` | time out only after the deadline (`>` instead of `>=`) | `tests/integration/test_gmail_login.py::test_the_wait_ends_five_minutes_after_it_starts` | `LoginError` `timed out` | `StopIteration` (a third clock read) |
| S10 | `gmail_login.py` | ignore `request_timeout` (no per-connection timeout) | `tests/integration/test_gmail_login.py::test_an_idle_connection_does_not_hold_up_the_callback` | under 2 s | about 3 s |
| S11 | `gmail_login.py` | accept a scope that only contains `gmail.SCOPE` | `tests/integration/test_gmail_login.py::test_a_token_for_any_scope_but_read_only_is_refused[extra]` | `LoginError` `scope refused` | `'refresh-token-from-code-1'` returned |
| S12 | `gmail_login.py` | let `httpx.TransportError` propagate | `tests/integration/test_gmail_login.py::test_a_failed_exchange_says_only_why[network]` | `LoginError` `(network)` | `ConnectError` |
| S13 | `gmail_login.py` | store the client ID and secret as soon as they are asked for | `tests/integration/test_gmail_login.py::test_a_cancelled_login_stores_nothing` | `[]` | client ID and secret written |
| S14 | `gmail_login.py` | ignore `new_client` | `tests/integration/test_gmail_login.py::test_a_new_client_replaces_the_stored_one` | three writes | only the refresh token written |
| S15 | `cli.py` | let the error propagate (no `except`) | `tests/integration/test_gmail_login.py::test_the_command_reports_a_failure_and_exits_1` | `gmail login cancelled: personal` | the consent address line |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01d.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks four properties on random inputs:
- whatever stray requests arrive first (other paths, other states, missing or repeated codes, junk), the callback returns the real code, refuses the rest, never echoes them, and writes nothing to the terminal
- the consent address carries any client ID and state, including `+`, `&`, `#`, `%`, spaces and accents, exactly
- a token is accepted only when its scope, however spaced or repeated, is exactly the read-only scope
- a login that is cancelled, rejected, cut off, given a broader scope, or stopped by the Keychain stores nothing and never puts a secret in its error, while a clean login stores three secrets

## 5. Searches

Each prints nothing, except the fourth, which prints exactly two lines (the token `POST` in `gmail.py` and in `gmail_login.py`), and the seventh, which prints exactly one line (`set_password` in `keychain.py`). A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | no network library but httpx and the listener's `http.server` (`urllib.parse` allowed) | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request\|(import\|from) urllib([^.A-Za-z_]\|$)' -- src` |
| Q2 | httpx and `http.server` only in the Gmail modules | `git grep --untracked -n -E 'httpx\|http\.server' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py'` |
| Q3 | no write method | `git grep --untracked -n -E '\.(put\|patch\|delete\|request\|send\|stream)\(\|"(POST\|PUT\|PATCH\|DELETE)"' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py src/mailroom/gmail_login.py` |
| Q4 | two `POST`s, the token requests (exactly two lines expected) | `git grep --untracked -n -E '\.post\(' -- src` |
| Q5 | no URL in the login but the consent page and the loopback redirect | `git grep --untracked -n -E 'https?://' -- src/mailroom/gmail_login.py \| grep -v -F -e '"https://accounts.google.com/o/oauth2/v2/auth"' -e 'f"http://{'` |
| Q6 | the listener binds loopback only | `git grep --untracked -n -E '0\.0\.0\.0\|"localhost"\|"::"\|"::1"' -- src` |
| Q7 | the only Keychain write is `set_password` in `keychain.py` (exactly one line expected) | `git grep --untracked -n -E 'set_password\|delete_password' -- src` |
| Q8 | `set_secret` only in the login, the browser only in the CLI and the login | `git grep --untracked -n -E 'set_secret\|webbrowser' -- src ':!src/mailroom/keychain.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/cli.py'` |
| Q9 | secrets never logged or printed | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn\|sys\.std(out\|err)' -- src ':!src/mailroom/cli.py'` |
| Q10 | time only through `clock.now()` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.(time\|monotonic)\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py'` |
| Q11 | no coverage or lint exclusions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/gmail_login.py src/mailroom/keychain.py src/mailroom/cli.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- **The handler.** A nested class or a module-level one, passing results back through the server object or a closure.
- **Parsing the query.** `urllib.parse.parse_qs` or `httpx.URL(...).params`; with `parse_qs`, an empty `code=` disappears, which is still a 400.
- **Pages.** The 400 and 404 bodies are any constant text.
- **Building the address.** `urllib.parse.urlencode` or `httpx.URL(..., params=...)`: the encodings differ, the decoded values must not.
- **Closing.** `server_close()` in `__exit__`, also when `wait` raised.
- **The CLI's printing.** `typer.echo` for the address and result, with `err=True` for the error.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01d-gmail-login.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1d`), then run `.venv/bin/python scripts/check_reports.py --phase 1d`; it must print `Reports OK.`
