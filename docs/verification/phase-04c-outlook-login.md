# Verification guide: Phase 4c (Outlook login)

Spec: `docs/phases/phase-04c-outlook-login.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/outlook_login.py`
- `grep -c "^## Phase 4c: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-04c-outlook-login.md tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook_login.py docs/verification/probe-04c.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 23.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 23 = 1183 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_outlook_login.py --no-cov -q` | `23 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/outlook_login.py,src/mailroom/gmail_login.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `.venv/bin/python docs/verification/probe-04c.py` | last line `FAILURES 0` |
| G5 | `grep -c "^## Phase 4c: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4c` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook_login.py docs/verification/probe-04c.py` | no output |
| G8 | `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| G9 | `git status --short` | only the Scope paths |
| G10 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `outlook_login.py` | Accept any grant that includes Mail.Read | `tests/integration/test_outlook_login.py::test_any_other_grant_is_refused[send-too]` | `LoginError` (`scope refused`) | `'refresh-token-from-code-1'` returned |
| S2 | `outlook_login.py` | Compare scopes without lower-casing | `tests/integration/test_outlook_login.py::test_a_read_only_grant_is_accepted[lower-case]` | `'refresh-token-from-code-1'` | `LoginError` (`scope refused`) |
| S3 | `outlook_login.py` | Store the asked client ID before opening the browser | `tests/integration/test_outlook_login.py::test_a_cancelled_login_stores_nothing` | `[]` | `[('mailroom', 'outlook.live.client-id')]` |
| S4 | `outlook_login.py` | Leave out `prompt=select_account` | `tests/integration/test_outlook_login.py::test_the_sign_in_address_asks_personal_accounts_for_read_only_mail_with_pkce` | the nine parameters | no `prompt` key |
| S5 | `gmail_login.py` | Keep `gmail` in `Callback`'s errors whatever the provider | `tests/integration/test_outlook_login.py::test_the_callback_names_its_provider` | `'outlook login cancelled: live'` | `'gmail login cancelled: live'` |
| S6 | `outlook_login.py` | Leave out `code_verifier`. The fake then refuses the code | `tests/integration/test_outlook_login.py::test_the_code_is_exchanged_as_a_public_client_for_a_refresh_token` | `'refresh-token-from-code-1'` | `LoginError` (`outlook login failed: live (400)`) |
| S7 | `cli.py` | Print `Opening Google sign-in` for Outlook | `tests/integration/test_outlook_login.py::test_the_command_signs_in_and_names_the_account` | the Microsoft line in the output | absent |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-04c.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks what the given tests don't reach, in two ways.
- **The exchange:** over 2,000 replies with one field corrupted, it raises only `LoginError`, never with a code, token or reply text, and returns a token only for a read-only grant, and only the one the reply carried.
- **Whole sign-ins:** over random grants and refusals, the Keychain is written only after a read-only exchange.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | A client secret, a wider tenant, or a write scope | `git grep --untracked -n -E 'client_secret\|client-secret\|/common/\|/organizations/\|Mail\.(ReadWrite\|Send)' -- src/mailroom/outlook_login.py` |
| Q2 | A second copy of the listener or of PKCE | `git grep --untracked -n -E 'HTTPServer\|BaseHTTPRequestHandler\|def new_verifier\|def code_challenge' -- src/mailroom/outlook_login.py` |
| Q3 | A reply's text or `error_description` echoed | `git grep --untracked -n -E 'response\.text\|str\((error\|exc\|e)\)\|\{(error\|exc\|e)(!r)?\}\|error_description' -- src/mailroom/outlook_login.py` |
| Q4 | A token printed by the command | `git grep --untracked -n -E 'echo\([^)]*(token\|refresh)' -- src/mailroom/cli.py` |
| Q5 | Time or ids read around the seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q6 | Logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q7 | Coverage or lint switched off | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/outlook_login.py src/mailroom/gmail_login.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Building `consent_url` with `httpx.URL(params=...)` or `urlencode`, if the parameters are exactly the nine in Requirement 3.
- A private helper in `cli.py` shared by both login commands, if both print what their tests pin.
- `Callback`'s `provider` stored as an attribute, if Gmail's messages and tests are unchanged.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-04c-outlook-login.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 4c`), then run `.venv/bin/python scripts/check_reports.py --phase 4c`; it must print `Reports OK.`
