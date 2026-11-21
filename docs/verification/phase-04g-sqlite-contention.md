# Verification guide: Phase 4g (Bound SQLite contention)

Spec: `docs/phases/phase-04g-sqlite-contention.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh
session. Everything is synthetic: temporary database files, fake Discord, fake Gmail,
fake model, MockTransport and the fake Keychain. Never access real Discord, mail,
model, tasks app, Keychain or data folder.

## 1. Coder ran

Before gates, inspect status, the tracked diff and untracked files. Require one
`## Phase 4g: ` progress entry and implementation changes in `src/mailroom/store/base.py`,
`src/mailroom/interactions.py` and `src/mailroom/service.py`. A stopped entry is not a
completed implementation. Report a missing coder or a stop, without treating every
missing behavior as a new defect.

Require these to be committed: the spec, this guide, the three new given test files,
the `tests/unit/test_store_package.py` and `src/mailroom/discord_layout.py` given
edits, and the probe. Record the full planning-baseline commit and verify their
bytes match it (G7). A dirty planning tree must not be called a coder diff. Do not
waive this gate or commit.

The only permitted implementation paths are the spec's Scope. Your report adds only
`docs/reviews/phase-04g-sqlite-contention.md`.

## 2. Gates

Run them in order from the repository root. G2 reads G1's coverage data before any
other test run. 44 given cases are new, so the minimum suite is 1364 + 44.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | All checks passed.; tests (core) passed; at least 1408 passed, 0 failed/skipped/xfailed, no warnings; all Sections rows have 0 failed |
| G2 | `.venv/bin/python -m coverage report --include=src/mailroom/service.py,src/mailroom/interactions.py,src/mailroom/store/base.py,src/mailroom/store/__init__.py --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_store_busy.py tests/integration/test_interactions_busy.py tests/integration/test_service_busy.py tests/unit/test_store_package.py --no-cov -q` | 102 passed |
| G4 | `.venv/bin/python docs/verification/probe-04g.py` | check lines end ok; final FAILURES 0 |
| G5 | `grep -c '^## Phase 4g: ' docs/progress.md` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4g` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04g-sqlite-contention.md docs/verification/phase-04g-sqlite-contention.md tests/integration/test_store_busy.py tests/integration/test_interactions_busy.py tests/integration/test_service_busy.py tests/unit/test_store_package.py src/mailroom/discord_layout.py docs/verification/probe-04g.py` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope, plus this review if already written |

The given tests use real lock timing and threads, so run G3 five more times. Every
run must show 102 passed. A single intermittent failure is a finding (requirement 1,
6 or 8), not noise.

Inspect the full diff for:

- unlisted changes to earlier tests;
- dependencies;
- coverage exclusions;
- new logging;
- retry loops or SQL replay in the store;
- a `PRAGMA` other than `busy_timeout`;
- weak assertions in the coder's tests.

## Requirement checks

| Requirement | Deciding evidence |
|---|---|
| 1: store wait | test_a_store_waits_its_lock_wait_then_raises_a_busy_error; test_a_lower_lock_wait_replaces_a_higher_one; test_the_file_keeps_its_rollback_journal; Q3 |
| 2: busy predicate | test_only_busy_and_locked_codes_count_as_lock_waits[*]; test_sqlite_errors_are_told_apart_by_their_code[*]; probe error classification; Q4 |
| 3: atomic writes | test_a_commit_that_cannot_finish_is_rolled_back_and_frees_the_file; test_a_many_row_write_that_runs_out_of_time_keeps_none_of_its_rows; probe leaked-lock and state checks |
| 4: waits used | test_the_poll_store_waits_ten_seconds_and_each_listener_store_one_and_a_half |
| 5: busy press | the busy press, command and form tests; test_a_press_from_someone_else_is_still_ignored_while_the_file_is_locked; test_a_database_error_that_is_not_a_lock_wait_is_not_hidden[*]; probe press checks |
| 6: busy round | test_a_round_that_meets_a_locked_file_is_skipped_and_the_next_one_catches_up; test_the_listener_is_not_restarted_while_rounds_are_skipped; test_a_database_error_that_is_not_a_lock_wait_still_stops_the_service; existing test_service_more.py round-error test |
| 7: episode and alerts | the 15-minute, under-15-minutes, lost-reply, second-episode and untroubled tests; coder tests for the open branches |
| 8: no leaks, no duplicates | test_pressing_again_after_the_lock_clears_answers_once; the Mute split test; probe |
| 9: privacy and compatibility | full suite including 4f given tests; searches; source review of replies and lines |
| 10: progress | G5/G6 and the entry's factual contents |

## 3. Spot checks

Run spot checks only in disposable scratch copies of the current implementation and
tests.

- Use the existing venv and `PYTHONPATH=src:.`, and confirm `mailroom.__file__` is
  inside the copy.
- Never mutate the implementation under review.
- Start each row from the original bytes and run the deciding test with `--no-cov`.
  Then discard only your mutation and compare bytes.
- If private helpers differ, locate the equivalent code; do not prescribe helper
  names.

Test prefixes: SB is `tests/integration/test_store_busy.py::`, IB is
`tests/integration/test_interactions_busy.py::`, VB is
`tests/integration/test_service_busy.py::`.

| # | Function/boundary | One-line mutation | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `_write` | Commit outside the rollback guard, as before | SB test_a_commit_that_cannot_finish_is_rolled_back_and_frees_the_file | passes | status reads muted / file still locked |
| S2 | `is_busy` | Compare the code without `& 0xFF` | SB test_only_busy_and_locked_codes_count_as_lock_waits[busy-snapshot] | True | False |
| S3 | `is_busy` | Accept any `sqlite3.DatabaseError` | SB test_only_busy_and_locked_codes_count_as_lock_waits[integrity] | False | True |
| S4 | `is_busy` | Ignore the code (any OperationalError) | IB test_a_database_error_that_is_not_a_lock_wait_is_not_hidden[set_sender_status] | raises, no callback | busy reply sent |
| S5 | `set_lock_wait` | Make it do nothing | SB test_a_store_waits_its_lock_wait_then_raises_a_busy_error | waits about 0.3 s | waits about 5 s, fails the < 4 s bound |
| S6 | press | Re-raise every OperationalError | IB test_a_press_that_meets_a_locked_file_is_asked_to_press_again[mute] | ("busy", BUSY) | OperationalError raised |
| S7 | listener wait | Drop the listener store's set_lock_wait | VB test_the_poll_store_waits_ten_seconds_and_each_listener_store_one_and_a_half | two waits | only the poll wait |
| S8 | ping wait | Ping at once instead of after STORE_WAIT | VB test_a_lock_shorter_than_fifteen_minutes_sends_no_alert | no ping | one ping |
| S9 | nonce | Draw a new nonce on every try | VB test_a_lost_ping_reply_is_retried_with_the_same_nonce_and_posts_once | one message | two messages |
| S10 | once-only | Drop the "not yet posted" condition | VB test_a_file_locked_for_fifteen_minutes_pings_once_and_says_when_it_clears | [PING, FIXED] | two pings |
| S11 | episode end | Never end the episode on a completed round | VB test_a_new_lock_after_one_clears_starts_a_new_fifteen_minutes | [PING, FIXED, PING, FIXED] | [PING] only |
| S12 | resolved notice | Never queue the free-again notice | VB test_a_file_locked_for_fifteen_minutes_pings_once_and_says_when_it_clears | [PING, FIXED] | [PING] |
| S13 | round catch | Treat every OperationalError as busy | VB test_a_database_error_that_is_not_a_lock_wait_still_stops_the_service | raises | returns normally with store: busy |
| S14 | status | Report `store: ok` after every round | VB test_an_untroubled_service_reports_no_store_line | no store line | store: ok |

These mutations were run against a throwaway scratch stand-in at planning time, not
against the coder's code. A different failure needs diagnosis, and a passing
mutation may mean a weak test rather than a product defect. Report the difference.

## 4. Probe

`.venv/bin/python docs/verification/probe-04g.py --oracle-only` checks the script
corpus alone:

- 40 seeded scripts of 14 steps;
- every lock (none, read, write, exclusive) with every operation (mark, read, alert,
  notify, press) at least 3 times;
- every script ends with an unlocked press;
- at least 15 scripts press under a lock before that.

The normal probe first checks `is_busy` on five real SQLite errors. It expects True
exactly for names starting `SQLITE_BUSY` or `SQLITE_LOCKED`. It then runs each script
on a real store with a 0.02 s wait while a raw connection holds the given lock.

Its oracle states the expected outcome of each step:

- writes are busy under any lock;
- reads are busy only under an exclusive lock;
- a press is busy unless it only reads (already answered);
- queueing notified mail writes only while there is mail to queue.

After every step it checks:

- the file can be write-locked at once;
- senders, pending alerts, pending posts and the answer match a model updated only by
  successful steps;
- a busy press got one private BUSY_TEXT reply and did not raise;
- the journal mode is still `delete`.

It reports failure names and counts, never payloads, and always reaches `FAILURES N`.
The 15-minute ping and the service loop are decided by the given tests, not the probe.
Never edit the probe; an oracle self-check failure belongs to the architect.

## 5. Searches

Each prints nothing; grep exit 1 is no match, exit above 1 is an error.

| # | Rule | Command |
|---|---|---|
| Q1 | Time/id seams, no sleeping | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|time\.sleep\|time\.monotonic\|from mailroom\.(clock\|ids) import' -- src/mailroom/service.py src/mailroom/interactions.py src/mailroom/store/base.py` |
| Q2 | No output, broad catch, bypass or exception text | `git grep --untracked -n -E 'print\(\|logger\.\|logging\.\|warnings\.warn\|pragma: no cover\|noqa\|\{error\}\|str\(error\)\}\|except BaseException' -- src/mailroom/interactions.py src/mailroom/store/__init__.py` |
| Q3 | No WAL or connection-mode change | `git grep --untracked -n -i -w -E 'wal\|journal_mode\|locking_mode\|isolation_level\|secure_delete *= *off' -- src/mailroom` |
| Q4 | Waits and error codes only in store/base.py | `git grep --untracked -n -E 'busy_timeout\|sqlite3\.connect\|sqlite_errorcode\|sqlite_errorname\|database is locked' -- src/mailroom ':(exclude)src/mailroom/store/base.py'` |

Escaped pipes in the table stand for ordinary alternation pipes. `store/base.py`
keeps its existing `except BaseException` in `_write`. Source review checks that
`is_busy` reads only the code and that no store method loops on a busy error.

## 6. Reasonable variations

- A wrapper function or a `try` inside `handle_interaction`, if the reply and
  propagation rules hold.
- Episode state as a small private class or local variables in `run_service`.
- Posting the ping with `send_messages` or an equivalent single request with the same
  body.
- Reporting `store: busy` before or after the ping attempt.

Not variations:

- deciding busy from message text;
- a retry loop inside the store;
- queueing the ping in the alert table;
- a ping on every busy round;
- a lock wait other than the constants;
- WAL.

## 7. Verdict

Write `docs/reviews/phase-04g-sqlite-contention.md`, starting `# Review: Phase 4g`,
with the exact conventions-format head and findings. Include:

- gate and Sections output;
- coverage;
- the repeated G3 runs;
- searches;
- probe results;
- spot-check results.

Classify each defect as requirement, observed result and required result. Do not
repair code or tests. Run G6 after writing it.

## Handoff prompts

Only after the final planning documents and given files are committed and the
coder's checkout is clean:

> Use $phase-coder to implement only Phase 4g from
> docs/phases/phase-04g-sqlite-contention.md in this checkout. Read the required
> project docs and every given test. Run Start and all Acceptance commands;
> append progress. Do not read the verification guide or write a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4g against
> docs/phases/phase-04g-sqlite-contention.md and
> docs/verification/phase-04g-sqlite-contention.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probe, searches and
> scratch-only spot checks; write only docs/reviews/phase-04g-sqlite-contention.md.
