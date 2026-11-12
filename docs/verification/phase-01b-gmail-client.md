# Verification guide: Phase 1b (Gmail client)

Spec: `docs/phases/phase-01b-gmail-client.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/gmail.py`
- `grep -c "^## Phase 1b: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01b-gmail-client.md pyproject.toml tests/fakes.py tests/integration/test_gmail.py scripts/critical_modules.txt docs/verification/probe-01b.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 30.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 30 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_gmail.py --no-cov -q` | `30 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/gmail.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1b: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1b` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- pyproject.toml tests/fakes.py tests/integration/test_gmail.py scripts/critical_modules.txt docs/verification/probe-01b.py` | no output |
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
| S1 | `gmail.py` | refresh only when `clock.now()` is after the expiry (`>` instead of `>=`) | `tests/integration/test_gmail.py::test_the_token_is_reused_until_a_minute_before_it_expires` | `['access-1', 'access-2']` | `['access-1']` |
| S2 | `gmail.py` | set the expiry without subtracting `TOKEN_MARGIN` | `tests/integration/test_gmail.py::test_the_token_is_reused_until_a_minute_before_it_expires` | `['access-1', 'access-2']` | `['access-1']` |
| S3 | `gmail.py` | on a 401 from the API, raise instead of refreshing and repeating | `tests/integration/test_gmail.py::test_a_rejected_access_token_is_refreshed_once` | `history_id == '1000'` | a `GmailError` raised |
| S4 | `gmail.py` | repeat after every 401, not only once | `tests/integration/test_gmail.py::test_a_second_rejection_needs_sign_in` | `GmailAuthError` | no exception: the third `GET` succeeds |
| S5 | `gmail.py` | ignore `labelsAdded` entries | `tests/integration/test_gmail.py::test_history_follows_pages_and_keeps_messages_added_to_the_inbox` | `m1, m3, m2, m4` | `m1, m3, m4` (no `m2`) |
| S6 | `gmail.py` | keep repeated ids (drop the first-occurrence rule) | `tests/integration/test_gmail.py::test_history_follows_pages_and_keeps_messages_added_to_the_inbox` | 4 refs | 5 refs (`m3` twice) |
| S7 | `gmail.py` | read only the first page (ignore `nextPageToken`) | `tests/integration/test_gmail.py::test_history_follows_pages_and_keeps_messages_added_to_the_inbox` | 4 refs | `m1, m3` only |
| S8 | `gmail.py` | decode `raw` without adding padding | `tests/integration/test_gmail.py::test_fetch_returns_the_raw_message` | a `RawMessage` | `GmailUnavailable` `(response)` |
| S9 | `gmail.py` | remove the message id check | `tests/integration/test_gmail.py::test_an_unsafe_message_id_is_refused_before_any_request[../profile]` | `ValueError`, no request | no `ValueError`; a request is sent |
| S10 | `gmail.py` | raise `GmailUnavailable` for a transport error without `from None` | `tests/integration/test_gmail.py::test_a_failing_service_is_unavailable[connect]` | `__suppress_context__` is `True` | `False` |
| S11 | `gmail.py` | add the response text to the error | `tests/integration/test_gmail.py::test_a_failing_service_is_unavailable[500]` | `'gmail unavailable: personal (500)'` | text containing `secret body` |
| S12 | `gmail.py` | let `SecretMissing` propagate | `tests/integration/test_gmail.py::test_a_refresh_token_that_does_not_work_needs_sign_in[missing]` | `GmailAuthError` | `SecretMissing` |
| S13 | `gmail.py` | treat every non-200 token answer as unavailable (drop the `invalid_grant` case) | `tests/integration/test_gmail.py::test_a_refresh_token_that_does_not_work_needs_sign_in[revoked]` | `GmailAuthError` | `GmailUnavailable` `(400)` |
| S14 | `gmail.py` | list without the `labelIds` param | `tests/integration/test_gmail.py::test_list_inbox_returns_inbox_mail_after_a_moment_newest_first` | `b, a` | `sent` first |
| S15 | `gmail.py` | build the client without `trust_env=False` | `tests/integration/test_gmail.py::test_open_gmail_ignores_proxy_settings_and_times_out` | `False` | `True` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01b.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks five properties on random mailboxes and faults:
- history returns exactly the inbox additions, once each and in order, whatever the page size
- `list_inbox` returns inbox mail after the moment, newest first
- `fetch` returns the exact bytes for any size
- the token is refreshed exactly when it is a minute from expiry
- under random faults, only `GmailError`s are raised, their text never leaks a body or token, and only the allowed read calls go out

## 5. Searches

Each prints nothing, except the fifth, which prints exactly one line (the token `POST`). A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | no network library but httpx | `git grep --untracked -n -E 'import (socket\|ssl\|imaplib\|smtplib\|http\|urllib\|requests\|aiohttp)([^A-Za-z_]\|$)\|from (socket\|ssl\|imaplib\|smtplib\|http\|urllib\|requests\|aiohttp)([^A-Za-z_]\|$)' -- src` |
| Q2 | httpx only in `gmail.py` | `git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py'` |
| Q3 | no URL but Google's three | `git grep --untracked -n -E 'https?://' -- src/mailroom/gmail.py \| grep -v -E '"https://(oauth2\|gmail\|www)\.googleapis\.com/'` |
| Q4 | no write method | `git grep --untracked -n -E '\.(put\|patch\|delete\|request\|send\|stream)\(\|"(POST\|PUT\|PATCH\|DELETE)"' -- src/mailroom/gmail.py` |
| Q5 | one `POST`, the token request (exactly one line expected) | `git grep --untracked -n -E '\.post\(' -- src/mailroom/gmail.py` |
| Q6 | no Gmail write path or non-raw format | `git grep --untracked -n -E -i '/(modify\|trash\|untrash\|send\|batchModify\|batchDelete\|insert\|import\|watch\|stop\|labels\|drafts\|settings)([^A-Za-z_]\|$)\|"(full\|metadata\|minimal)"' -- src/mailroom/gmail.py` |
| Q7 | email text is never logged or printed | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py'` |
| Q8 | time only through `clock.now()` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py'` |
| Q9 | no coverage or lint exclusions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/gmail.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- **Token state.** Kept as attributes or in a small private dataclass.
- **Request helper.** A private helper that adds the token, does the 401 retry and maps failures, used by all four calls.
- **Response checks.** Done by hand, with pydantic models, or with `isinstance` checks, as long as a wrong type gives `GmailUnavailable` `(response)`.
- **Paging.** Written as a loop or a generator.
- **Error classes.** Built with `__init__(account, detail)` or with the text passed when raising, as long as `str()` matches.
- **`after`.** Computed with `math.floor(after.timestamp())`, which equals `int(...)` for times after 1970.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01b-gmail-client.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1b`), then run `.venv/bin/python scripts/check_reports.py --phase 1b`; it must print `Reports OK.`
