# Review: Phase 1m

- Verdict: PASS
- Passed: 637
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/alerts.py` and `tests/integration/test_alerts_more.py` exist, and `grep -c "^## Phase 1m: " docs/progress.md` prints `1`. The baseline given files are committed. `git status --short` lists only the five Scope paths.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `637 passed` in 3.43s, 0 failed, 0 skipped, no warnings. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          578 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (466 statements, 92 branches). G2: `40 passed`. G4: `1`. G6 is empty. G8 freeze matches the Phase 1l list, 35 packages, including `websockets==17.3`. Q1 through Q10 print nothing. Probe: `oracle self-check: ok`, `alerts follow the schedule, once each, in order: ok`, `FAILURES 0`.

Spot checks S1 through S8 each failed as designed, then the files were restored (`git diff HEAD` and `git status --short` matched the snapshots). S1 queued `[('down', False)]` at 14:59. S2 reached 3 alerts. S3 left only `('down', False)`. S4 dropped the owner id from the pinging alert's mentions. S5 said `1 new emails`. S6 posted the model alert before minute 15. S7 posted 3 alerts. S8 posted 2 messages for a Gmail 500.

Requirements: waiting and recovery are `test_a_problem_alerts_once_after_it_has_lasted_long_enough` and `test_a_fixed_problem_says_so_only_if_it_was_announced`; the catch-up wording is `test_the_catch_up_summary_reads_naturally`; posting and pings are `test_alerts_are_posted_in_order_and_only_action_alerts_ping`; the model wait is `test_an_unreachable_model_is_announced_after_15_minutes_and_its_return_too`; a listener that dies at once is `test_a_listener_that_dies_at_once_is_never_called_running_again`; a Gmail 500 stays a status line in `test_a_gmail_500_is_reported_and_the_round_goes_on`. The extra file asserts a 200 without an id, a network error, `mark_alert_posted` returning false, a catch-up with no offline time, a model failure after one email, a queued alert with no token, and posting with no owner.
