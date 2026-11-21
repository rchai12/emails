# Verification guide: Phase 4f (Supervise listener recovery)

Spec: `docs/phases/phase-04f-listener-recovery.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh
session. Everything is synthetic: fake gateways, MockTransport and the fake
Keychain. Never access real Discord, mail, model, tasks app, Keychain or data folder.

## 1. Coder ran

Before gates, inspect status, the tracked diff and untracked files. Require one
`## Phase 4f: ` progress entry and implementation changes in `src/mailroom/service.py`.
A stopped entry is not a completed implementation; report a missing coder or a stop
without treating every missing behavior as a new defect.

Require the spec, this guide, `tests/integration/test_service_listener.py`, the
`src/mailroom/discord_layout.py` given edit and the probe to be committed. Record
the full planning-baseline commit and verify their bytes match it (G7). A dirty
planning tree must not be called a coder diff. Do not waive this gate or commit.

The only permitted implementation paths are the spec's Scope. Your report adds only
`docs/reviews/phase-04f-listener-recovery.md`.

## 2. Gates

Run sequentially from the repository root. G2 reads G1's coverage data before any
other test run. All 20 given cases are new; the minimum suite is 1337 + 20.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | All checks passed.; tests (core) passed; at least 1357 passed, 0 failed/skipped/xfailed, no warnings; all Sections rows have 0 failed |
| G2 | `.venv/bin/python -m coverage report --include=src/mailroom/service.py --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_service_listener.py --no-cov -q` | 20 passed |
| G4 | `.venv/bin/python docs/verification/probe-04f.py` | check lines end ok; final FAILURES 0 |
| G5 | `grep -c '^## Phase 4f: ' docs/progress.md` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4f` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04f-listener-recovery.md docs/verification/phase-04f-listener-recovery.md tests/integration/test_service_listener.py src/mailroom/discord_layout.py docs/verification/probe-04f.py` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope, plus this review if already written |

Because the given tests are threaded, also run G3 five more times; every run must
show 20 passed. A single intermittent failure is a finding (requirement 4 or 8),
not noise. Inspect the full diff for unlisted earlier-test changes, dependencies,
coverage exclusions, new logging and weak assertions in the coder's tests.

## Requirement checks

| Requirement | Deciding evidence |
|---|---|
| 1: seam and constants | test_shutdown_interrupts_the_default_restart_wait (replaces RESTART_SECONDS, uses the default wait); every test passing restart_wait |
| 2: classification | test_a_recoverable_failure_restarts_with_fresh_resources[*]; test_a_terminal_outcome_is_alerted_and_never_restarted[*] |
| 3: terminal outcome | terminal tests' exact lines and posted alert; existing test_service_alerts.py and test_service.py gateway tests |
| 4: attempts and resources | earlier_closed and is_closed assertions; test_a_listener_that_cannot_open_its_client_is_retried_and_its_store_closed; test_only_one_listener_runs_at_a_time_on_one_thread; probe |
| 5: recoverable status | exact gateway_lines in the recoverable tests; no PRIVATE text |
| 6: backoff | test_restart_waits_back_off_to_a_cap; test_a_stop_during_the_restart_wait_starts_no_new_listener; probe |
| 7: health and listener alert | the 15-minute, recovers-within-a-round, still-failing and fails-between-every-round tests; test_a_listener_that_survives_a_round_resets_the_backoff |
| 8: shutdown and independence | shutdown tests; test_a_later_press_works_after_a_handler_failure (card posted while restarting); existing round-error test |
| 9: privacy and compatibility | PRIVATE assertions; probe privacy checks; full suite; searches |
| 10: progress | G5/G6 and the entry's factual contents |

## 3. Spot checks

Run only in disposable scratch copies of the current implementation and tests, with
the existing venv and `PYTHONPATH=src:.`. Confirm `mailroom.__file__` is inside the
copy. Never mutate the implementation under review. Start each row from original
bytes, run the deciding test with `--no-cov`, then discard only your mutation and
compare bytes. Locate the equivalent code if private helpers differ; do not
prescribe helper names.

Every test below has prefix `tests/integration/test_service_listener.py::`.

| # | Function/boundary | One-line mutation | Deciding test suffix | Correct | Broken |
|---|---|---|---|---|---|
| S1 | classification | Treat every KeychainError, not only SecretMissing, as terminal | test_a_recoverable_failure_restarts_with_fresh_resources[keychain-locked] | 2 calls, delays [1] | 1 call; a stopped alert |
| S2 | terminal outcome | After queuing the gateway alert, fall through to a restart instead of ending | test_a_terminal_outcome_is_alerted_and_never_restarted[fatal-close] | 1 call, delays [] | 2 calls, delays [1] |
| S3 | resource closing | Drop the Discord client close for a failed attempt | test_a_recoverable_failure_restarts_with_fresh_resources[bug] | earlier_closed [True, True] | [True, False] |
| S4 | resource closing | Drop the store close for a failed attempt | test_a_recoverable_failure_restarts_with_fresh_resources[bug] | every opened store closed | is_closed False |
| S5 | open order | Open the Discord client before the store | test_a_listener_that_cannot_open_its_client_is_retried_and_its_store_closed | 3 stores opened | 2 stores opened |
| S6 | backoff index | Use RESTART_SECONDS[min(k, 6)] instead of min(k - 1, 6) | test_restart_waits_back_off_to_a_cap | [1, 2, 4, 8, 16, 32, 60, 60, 60] | [2, 4, 8, 16, 32, 60, 60, 60, 60] |
| S7 | backoff reset | Never reset the consecutive count on a healthy round | test_a_listener_that_survives_a_round_resets_the_backoff | [1, 2, 1] | [1, 2, 4] |
| S8 | health rule | Call the listener healthy whenever an attempt is running, ignoring the failure count | test_a_listener_that_fails_between_every_round_still_alerts | [KEEPS_FAILING, ANSWERING] | [] |
| S9 | alert wait | Use timedelta(0) instead of LISTENER_WAIT | test_a_listener_that_recovers_within_a_round_sends_no_alert | [] posted | a listener ping posted |
| S10 | default wait | Make the default restart wait time.sleep(seconds) | test_shutdown_interrupts_the_default_restart_wait | thread ended | thread still alive after the 10 s join |

These mutations were run against a throwaway scratch supervisor at planning time,
not against the coder's code. A different failure needs diagnosis; a passing
mutation may mean a weak test rather than a product defect. Report the difference.

## 4. Probe

`.venv/bin/python docs/verification/probe-04f.py --oracle-only` checks the script
corpus alone: 48 seeded scripts that reach every recoverable kind at least 5 times,
each terminal outcome at least 4 times, and a 9-failure run that reaches the cap.
The normal probe runs each script through `run_service` with an immediate restart
wait and isolated HOME/MAILROOM settings. Its independent oracle checks only:
attempt count, one attempt at a time, the literal backoff table, every store and
client closed, no private marker in lines or alerts, and exactly one stopped alert
for a terminal script and none otherwise. It reports failure names and counts,
never payloads, and always reaches `FAILURES N`. Health rounds and the 15-minute
alert are decided by the given tests, not the probe. Never edit the probe; an
oracle self-check failure belongs to the architect.

## 5. Searches

Each prints nothing; grep exit 1 is no match, exit above 1 is an error.

| # | Rule | Command |
|---|---|---|
| Q1 | Time/id seams, no sleeping | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|time\.sleep\|from mailroom\.(clock\|ids) import' -- src/mailroom/service.py` |
| Q2 | No output, broad catch, bypass or exception text | `git grep --untracked -n -E 'print\(\|logger\.\|logging\.\|warnings\.warn\|except BaseException\|pragma: no cover\|noqa\|str\(error\)\}\|\{error\}' -- src/mailroom/service.py` |

Escaped pipes in the table stand for ordinary alternation pipes. Q2 allows
`except Exception` (the supervisor needs it) and `str(error)` used as a whole
reason; source review checks that `str(error)` is used only for the terminal
types and `KeychainUnavailable`, whose texts are constant plus a secret name.

## 6. Reasonable variations

- A private supervisor function or small class in service.py, with its own lock or
  immutable snapshots for cross-thread state.
- Checking the stop event before or after an attempt in addition to the wait's
  result, provided no attempt starts once the service is stopping.
- Reporting `running` from the supervisor before the first attempt too (Health
  drops the repeat).

Not variations: alerting on each failure, restarting terminal outcomes, a restart
limit, waits other than the table, or listener alerts written from the listener's
thread.

## 7. Verdict

Write `docs/reviews/phase-04f-listener-recovery.md`, starting `# Review: Phase 4f`,
with the exact conventions-format head and findings. Include gate and Sections
output, coverage, the repeated G3 runs, searches, probe and spot-check results.
Classify defects as requirement, observed result and required result; do not
repair code or tests. Run G6 after writing it.

## Handoff prompts

Only after the final planning documents and given files are committed and the
coder's checkout is clean:

> Use $phase-coder to implement only Phase 4f from
> docs/phases/phase-04f-listener-recovery.md in this checkout. Read the required
> project docs and every given test. Run Start and all Acceptance commands;
> append progress. Do not read the verification guide or write a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4f against
> docs/phases/phase-04f-listener-recovery.md and
> docs/verification/phase-04f-listener-recovery.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probe, searches and
> scratch-only spot checks; write only docs/reviews/phase-04f-listener-recovery.md.
