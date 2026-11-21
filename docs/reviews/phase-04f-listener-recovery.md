# Review: Phase 4f

- Verdict: PASS
- Passed: 1364
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Baseline and scope (fresh)

- Planning baseline 80fa60b (spec, guide, given tests, discord_layout edit, probe). Implementation is commit 3ad54ea; working tree clean at review start.
- 3ad54ea changed only service.py, test_service_supervision.py and docs/progress.md. The spec, guide, given test file, discord_layout.py and probe are byte-identical to 80fa60b (G7 empty). No change to pyproject.toml, tests/sections.toml or any earlier test.
- The coder's progress deviation (a terminal-kind error raised while opening the store or client is recoverable) matches Requirement 4 (an open failure is a recoverable Exception), so it is not a departure from the spec.

## Gates (fresh)

- G1 `check.py --first core`: All checks passed; 1364 passed; Sections tooling 77/0 failed, core 1287/0 failed; no skips or warnings.
- G2 coverage service.py 211 stmts / 42 branches: TOTAL 100%, exit 0.
- G3 given file: 20 passed, and 20 passed in each of 5 further runs (6 in all).
- G4 probe: oracle self-check ok; 48 of 48 trials reached; supervision invariants ok; FAILURES 0.
- G5: 1. G7: no output. G8: clean tree.
- Q1 and Q2: no matches (exit 1 each).

## Spot checks (scratch copy, mailroom imported from the copy, original bytes unchanged)

- S1 to S10: the deciding test fails under each mutation, as required. S10 (default wait replaced by time.sleep) fails after the 10 s join.

## Source review

- Terminal types (GatewayStopped, DiscordUnavailable, SecretMissing) are alerted on the attempt's store before it closes and end the thread. KeychainUnavailable and every other Exception are recoverable. BaseException is not caught.
- Reasons are `str(error)` only for KeychainUnavailable, otherwise `failed (<type>)` or `ended`. No exception text reaches a status line or alert; the coder's tests assert PRIVATE text is absent.
- Resources are closed in a `finally` before any restart wait. Backoff uses `RESTART_SECONDS[min(streak - 1, 6)]`, read at wait time. Failure counters are guarded by a lock.
- Health is judged once per round on the poll thread (count unchanged and an attempt running), is skipped while the thread is dead, and resets the streak when healthy. The `listener` alert is written on the poll loop's store.
