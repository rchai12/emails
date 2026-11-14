# Verification guide: Phase 4b (Outlook sync)

Spec: `docs/phases/phase-04b-outlook-sync.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/outlook_sync.py`
- `grep -c "^## Phase 4b: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-04b-outlook-sync.md tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook_sync.py docs/verification/probe-04b.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 18.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 18 = 1160 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_outlook_sync.py --no-cov -q` | `18 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/outlook_sync.py,src/mailroom/gmail_sync.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `.venv/bin/python docs/verification/probe-04b.py` | last line `FAILURES 0` |
| G5 | `grep -c "^## Phase 4b: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4b` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook_sync.py docs/verification/probe-04b.py` | no output |
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
| S1 | `outlook_sync.py` | Drop the inbox-folder check | `tests/integration/test_outlook_sync.py::test_mail_moved_out_of_the_inbox_before_its_fetch_is_skipped` | `()` | `('live/AAMk1=',)` |
| S2 | `outlook_sync.py` | Drop the "already stored" check (the store still refuses a second copy, so only the download count shows it) | `tests/integration/test_outlook_sync.py::test_a_message_listed_again_is_not_fetched_again` | one `$value` request | two |
| S3 | `outlook_sync.py` | Catch up from `state.synced_at` with no overlap. Message 1 is then outside the window, but it was already stored, so the result is the same and only the filter differs | `tests/integration/test_outlook_sync.py::test_an_expired_bookmark_catches_up_from_the_last_round_with_an_hour_overlap` | `'receivedDateTime ge 2026-11-13T08:00:00Z'` | `'… 2026-11-13T09:00:00Z'` |
| S4 | `outlook_sync.py` | Check the prefix as `https://outlook.live.com`, without the slash | `tests/integration/test_outlook_sync.py::test_an_odd_web_link_is_replaced_by_the_inbox_link[lookalike-host]` | `INBOX_LINK` | `'https://outlook.live.com.evil.example.test/owa/'` |
| S5 | `outlook_sync.py` | Skip the message when its link fails, instead of using `INBOX_LINK` | `tests/integration/test_outlook_sync.py::test_an_odd_web_link_is_replaced_by_the_inbox_link[too-long]` | `('live/AAMk1=',)` | `()` |
| S6 | `outlook_sync.py` | Don't catch `MessageGone` | `tests/integration/test_outlook_sync.py::test_a_message_deleted_before_its_fetch_is_skipped` | `('live/AAMk2=',)` | `MessageGone` raised |
| S7 | `outlook_sync.py` | Call a bookmark round `"history"` | `tests/integration/test_outlook_sync.py::test_a_later_round_reads_only_new_mail_from_the_bookmark` | `kind='delta'` | `kind='history'` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-04b.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks what the given tests don't reach. Over 120 trials of 16 rounds, mail arrives in the inbox or junk, moves, or is deleted, links expire and rounds fail at random requests, and the model must hold:
- nothing never in the inbox is stored;
- nothing is downloaded twice;
- a failed round leaves the bookmark;
- after a final clean round, every message still in the inbox is stored.

The one exception is the documented catch-up limit for an old message moved in.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | A call that bypasses the client, or a folder other than the inbox | `git grep --untracked -n -E 'http\.\|httpx\.\|junkemail\|mailFolders' -- src/mailroom/outlook_sync.py` |
| Q2 | An auth, network or Keychain error swallowed in sync | `git grep --untracked -n -E 'except (Exception\|OutlookError\|OutlookUnavailable\|OutlookAuthError\|KeychainError)' -- src/mailroom/outlook_sync.py` |
| Q3 | A bookmark saved in a `finally` | `git grep --untracked -n -E 'finally:' -- src/mailroom/outlook_sync.py` |
| Q4 | Time or ids read around the seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q5 | Logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q6 | Coverage or lint switched off | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/outlook_sync.py src/mailroom/gmail_sync.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Sharing a private helper with `gmail_sync.py` for the catch-up window, if Gmail's behaviour and tests are unchanged.
- Checking the link with `record`'s own rules through a small helper, if every case in Requirement 4 holds.
- Building the envelope once and swapping in `INBOX_LINK` on a link failure, if a thread-id failure still skips the message.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-04b-outlook-sync.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 4b`), then run `.venv/bin/python scripts/check_reports.py --phase 4b`; it must print `Reports OK.`
