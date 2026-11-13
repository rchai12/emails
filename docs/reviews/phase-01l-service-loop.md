# Review: Phase 1l

- Verdict: PASS
- Passed: 607
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

The reviewed code is `git diff 6a0b383 HEAD` (through `170b970`). The diff gates were run against HEAD. `git diff HEAD` of the given files, including `tests/integration/test_service.py`, is empty. The test change inside that range is the Corrections change: a missing Gmail refresh token is reported as `gmail personal: gmail sign-in needed: personal`.

`git diff --stat 6a0b383 HEAD` is the five Scope paths, that test change, the Corrections section, this review, and the two skill files as they stood in `170b970`. `git status --short` also lists newer uncommitted edits to those two skill files. They are not in HEAD and were not judged.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `607 passed` in 2.66s, 0 failed, 0 skipped, no warnings. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          548 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (252 statements, 34 branches). G2: `22 passed`. G4: `1`. Q1 through Q9 print nothing. The freeze is the Phase 1k list, 35 packages, including `websockets==17.3`. Probe: `oracle self-check: ok`, `every email is posted once despite failures, and the status lines are clean: ok`, `FAILURES 0`.

Spot checks S1 through S8 each failed as designed, then `service.py` was restored (`git diff HEAD` and `git status --short` matched the snapshots). S1 showed the three repeated lines. S2 omitted `gmail personal: ok`. S3 raised `IndexError`. S4 said `discord posting: ok`. S5 left `text_cleared_at` as `None`. S6 said `discord gateway: failed (ProgrammingError)`. S7 called the listener four times. S8 included `$42.00`.

Requirements: the two settings are `tests/unit/test_config_service.py`; a round is `test_a_round_syncs_triages_and_posts`; a missing Gmail secret is `test_a_missing_gmail_secret_asks_for_sign_in`; one broken account is `test_one_broken_account_does_not_stop_the_others`; triage stops for the round in `test_an_unreachable_model_leaves_mail_for_the_next_round`; posting waits in `test_a_discord_failure_leaves_posts_queued`; the listener's own store is `test_the_service_polls_every_interval_and_listens_on_its_own_thread`; a stopped gateway is `test_a_stopped_gateway_is_reported_once_and_polling_goes_on`; an unexpected listener error is `test_an_unexpected_gateway_error_names_only_its_type`; `mailroom run` is `tests/unit/test_cli_run.py`. The extra file asserts an unexpected round error still stops and closes, a Gmail 500, a listener `DiscordUnavailable`, a listener `KeychainError`, and an empty accounts value.
