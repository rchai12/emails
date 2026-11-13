# Review: Phase 1o

- Verdict: PASS
- Passed: 685
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `send_messages` imports, and `grep -c "^## Phase 1o: " docs/progress.md` prints `1`. The baseline given files are committed. `git status --short` lists only the five Scope paths.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `685 passed` in 3.15s, 0 failed, 0 skipped, no warnings. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          626 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (495 statements, 88 branches). G2: `11 passed`. G4: `src/mailroom/service.py:1`. G5: `1`. G6: `Reports OK.` G7 is empty. G8 is empty. G9 lists only the Scope paths. G10 freeze matches the Phase 1n list, 35 packages, including `websockets==17.3`. Q1 through Q9 print nothing. Probe: `oracle self-check: ok`, `each write is one statement with no read before it: ok`, `two racing stores match the model and never raise: ok`, `sending marks each item once with Discord's id: ok`, `FAILURES 0`.

Spot checks S1 through S10 each failed as designed, then the files were restored (`git diff HEAD` and `git status --short` matched the snapshots). S1 and S2 raised `IntegrityError`. S3 returned `True`. S4 hit `read_first`. S5 built `['first', 'second', 'third']`. S6 read `[('mailroom', 'discord.bot-token')]`. S7 reported `waiting=1`. S8 sent the ping body for the catch-up. S9 left both alerts pending. S10 raised `SecretMissing`.

| Requirement | Where it is checked |
| --- | --- |
| 1 `open_problem` is one insert | `test_opening_a_problem_another_store_just_opened_returns_theirs`; probe trace |
| 2 `queue_alert` is one insert | `test_queueing_an_alert_another_store_just_queued_keeps_theirs`; probe trace |
| 3 `close_problem` deletes once, without a read first | `test_closing_a_problem_is_one_statement_and_happens_once` |
| 4 `send_messages` | `test_send_messages.py`; probe send rounds |
| 5 `post_pending` uses the helper | `test_discord_post.py` (behaviour unchanged) |
| 6 `post_alerts` uses the helper | `test_alert_post.py`; Q1 prints nothing |
| 7 one status helper | G4; `test_a_missing_bot_token_is_reported_and_posting_waits` |
| 8 Progress entry | G5, G6 |
