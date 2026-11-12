# Verification guide: Phase 1c (Gmail sync)

Spec: `docs/phases/phase-01c-gmail-sync.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/gmail_sync.py`
- `tests/integration/test_gmail_sync_more.py`
- `grep -c "^## Phase 1c: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01c-gmail-sync.md src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_gmail_sync.py scripts/critical_modules.txt docs/verification/probe-01c.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 25.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 25 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_store_sync.py tests/integration/test_gmail_sync.py --no-cov -q` | `25 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/gmail_sync.py,src/mailroom/store.py,src/mailroom/gmail.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1c: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1c` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_gmail_sync.py scripts/critical_modules.txt docs/verification/probe-01c.py` | no output |
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
| S1 | `gmail_sync.py` | list a first run from `now - CATCH_UP_LIMIT` instead of `now - FIRST_RUN` | `tests/integration/test_gmail_sync.py::test_a_first_sync_stores_the_last_three_days_of_inbox_mail` | `stored=('m4', 'm2')` | `stored=('m4', 'm2', 'm1')` |
| S2 | `gmail_sync.py` | call `profile()` after the listing on a first run | `tests/integration/test_gmail_sync.py::test_a_first_sync_reads_the_bookmark_before_listing` | `/profile` first | `/messages` before `/profile` |
| S3 | `gmail_sync.py` | fetch every ref (drop the `store.get` check) | `tests/integration/test_gmail_sync.py::test_a_stored_message_is_not_fetched_again` | `['m1']` | `['m1', 'm1']` |
| S4 | `gmail_sync.py` | drop the `INBOX` part of the label check | `tests/integration/test_gmail_sync.py::test_mail_that_left_the_inbox_before_fetch_is_skipped[archived]` | `('m2',)` | `('m1', 'm2')` |
| S5 | `gmail_sync.py` | let `MessageGone` propagate | `tests/integration/test_gmail_sync.py::test_a_message_deleted_before_fetch_is_skipped` | `('m2',)` | `MessageGone` raised |
| S6 | `gmail.py` | raise `GmailUnavailable` for a 404 from `fetch`, as in 1b | `tests/integration/test_gmail_sync.py::test_fetching_a_deleted_message_raises_message_gone` | `MessageGone` | `GmailUnavailable` `(404)` |
| S7 | `gmail_sync.py` | let the envelope's `ValueError` propagate | `tests/integration/test_gmail_sync.py::test_a_message_with_an_unusable_id_is_skipped[thread-id]` | `('m2',)` | `ValueError` `invalid record field: thread_id` |
| S8 | `gmail_sync.py` | put the address in the link without `quote` | `tests/integration/test_gmail_sync.py::test_the_stored_record_comes_from_gmail_and_the_parser` | `authuser=owner%2Bmail@example.test` | `authuser=owner+mail@example.test` |
| S9 | `gmail_sync.py` | catch up from `state.synced_at`, without the overlap | `tests/integration/test_gmail_sync.py::test_an_expired_bookmark_catches_up[2-days]` | `after:1794211200` | `after:1794214800` |
| S10 | `gmail_sync.py` | catch up without the 14-day limit | `tests/integration/test_gmail_sync.py::test_an_expired_bookmark_catches_up[20-days]` | `after:1793178000` | `after:1792656000` |
| S11 | `gmail_sync.py` | set `gap` with `>=` instead of `>` | `tests/integration/test_gmail_sync.py::test_an_expired_bookmark_catches_up[14-days]` | `gap=False` | `gap=True` |
| S12 | `gmail_sync.py` | save the sync state before handling the refs | `tests/integration/test_gmail_sync.py::test_a_failed_sync_keeps_the_bookmark_and_what_it_stored` | `None` | a `SyncState` with bookmark `'1002'` |
| S13 | `gmail_sync.py` | on the history path, save the old bookmark instead of the history's `history_id` | `tests/integration/test_gmail_sync.py::test_a_later_sync_stores_new_inbox_mail_from_history` | `bookmark='1003'` | `bookmark='1001'` |
| S14 | `store.py` | keep the existing row on a second save (insert or ignore) | `tests/integration/test_store_sync.py::test_saving_again_replaces_the_state` | `bookmark='1012'` | `bookmark='1007'` |
| S15 | `store.py` | store `synced_at` without converting it to UTC | `tests/integration/test_store_sync.py::test_a_saved_state_is_read_back_in_utc` | `utcoffset()` `0:00:00` | `-1 day, 19:00:00` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01c.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It runs many syncs on random mailboxes, changing the mailbox between them (new mail, archiving, deleting, moving out of spam, clock jumps of up to 16 days, expired bookmarks), and checks three properties against its own oracle:
- every sync stores exactly the new inbox mail its kind should find, never fetches a stored message, reports the right kind, `offline_since` and `gap`, and saves the mailbox's current history id with the sync's start time
- a failure at any Gmail call raises a `GmailError`, leaves the saved state as it was, stores nothing extra, and a retry ends with exactly what one clean sync would have stored
- only token `POST`s and Gmail `GET`s go out

## 5. Searches

Each prints nothing, except the fourth, which prints exactly one line (the token `POST`). A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | no network library but httpx (`urllib.parse` allowed) | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|http\|requests\|aiohttp)([^A-Za-z_]\|$)\|urllib\.request\|(import\|from) urllib([^.A-Za-z_]\|$)' -- src` |
| Q2 | httpx only in `gmail.py` | `git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py'` |
| Q3 | no write method | `git grep --untracked -n -E '\.(put\|patch\|delete\|request\|send\|stream)\(\|"(POST\|PUT\|PATCH\|DELETE)"' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py` |
| Q4 | one `POST`, the token request (exactly one line expected) | `git grep --untracked -n -E '\.post\(' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py` |
| Q5 | no Gmail write path or non-raw format | `git grep --untracked -n -E -i '/(modify\|trash\|untrash\|send\|batchModify\|batchDelete\|insert\|import\|watch\|stop\|labels\|drafts\|settings)([^A-Za-z_]\|$)\|"(full\|metadata\|minimal)"' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py` |
| Q6 | no URL in the sync but the link | `git grep --untracked -n -E 'https?://' -- src/mailroom/gmail_sync.py \| grep -v -F '"https://mail.google.com/mail/?authuser={address}#all/{message_id}"'` |
| Q7 | the sync reaches the database and the client only through their public methods | `git grep --untracked -n -E 'sqlite3\|\.execute\|\._[a-z]' -- src/mailroom/gmail_sync.py` |
| Q8 | email text is never logged or printed | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py'` |
| Q9 | time only through `clock.now()` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py'` |
| Q10 | no coverage or lint exclusions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/gmail_sync.py src/mailroom/store.py src/mailroom/gmail.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- **The sync's shape.** One function, or one function with private helpers for each kind of run.
- **Skipping.** `try`/`except` around `fetch` and around `Envelope(...)`, or a helper returning `None` for a skipped ref.
- **Label check.** Written with sets or with `in` tests.
- **Store queries.** `INSERT ... ON CONFLICT DO UPDATE` or `INSERT OR REPLACE` for `save_sync_state`; reusing `_stamp` and `_read_time`.
- **`MessageGone`.** Built with `__init__(account)` like the other errors, or with the text passed when raising, as long as `str()` matches.
- **`kind`.** Typed with `Literal`, or as `str` with the three values.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01c-gmail-sync.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1c`), then run `.venv/bin/python scripts/check_reports.py --phase 1c`; it must print `Reports OK.`
