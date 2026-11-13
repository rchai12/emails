# Review: Phase 1l

- Verdict: FAIL
- Passed: 607
- Findings: 2
- Approved deviations: None
- For the architect: Corrections change the given test, but that file, the spec, and the two skill files are still uncommitted, so G6 and G7 fail; the service itself passed.

## Findings

G6 | tests/integration/test_service.py:156 | expected no diff from HEAD for the given service tests | found the missing-secret test now expects gmail sign-in needed: personal
G7 | docs/phases/phase-01l-service-loop.md:179 | expected git status --short to list only the five Scope paths | found the spec, the given service tests, two architect skill files, and the previous review as well as the Scope paths

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Requirement 7 is met: `grep -c "^## Phase 1l: " docs/progress.md` prints `1`, and the entry is dated 2026-11-12 with tests 580 to 607. `run_round` reports `str(error)`, so a missing Gmail refresh token is `gmail personal: gmail sign-in needed: personal`, which is what the corrected test expects.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `607 passed` in 2.76s, 0 failed, 0 skipped, no warnings. Last lines:

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

G3, run immediately after that, exit 0, `TOTAL` 100% (252 statements, 34 branches). G2: `22 passed`. G4: `1`. G5, before this report replaced the previous one: `Reports OK.` Q1 through Q9 print nothing. The freeze matches the Phase 1k list, including `websockets==17.3` and no new package. Probe: `oracle self-check: ok`, `every email is posted once despite failures, and the status lines are clean: ok`, `FAILURES 0`.

G6 prints `tests/integration/test_service.py | 6 ++----`. G7 lists ten paths. The Scope paths are `src/mailroom/cli.py`, `src/mailroom/config.py`, `src/mailroom/service.py`, `tests/integration/test_service_more.py`, and `docs/progress.md`. The other five are `docs/phases/phase-01l-service-loop.md`, `tests/integration/test_service.py`, `.claude/skills/phase-architect/SKILL.md`, `.claude/skills/phase-architect/history.md`, and `docs/reviews/phase-01l-service-loop.md`.

Spot checks S1 through S8 each failed as designed, then `service.py` was restored (`git diff HEAD` and `git status --short` matched the snapshots). S1 showed the three repeated lines. S2 omitted `gmail personal: ok`. S3 raised `IndexError`. S4 said `discord posting: ok`. S5 left `text_cleared_at` as `None`. S6 said `discord gateway: failed (ProgrammingError)`. S7 called the listener four times. S8 included `$42.00`.
