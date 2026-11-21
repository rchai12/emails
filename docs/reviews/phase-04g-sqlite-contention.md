# Review: Phase 4g

- Verdict: PASS
- Passed: 1413
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Baseline and scope (fresh)

- Planning baseline fdcba96 (spec, guide, three given test files, package test edit, layout edit, probe). Implementation is commit 0e12e4f; working tree clean at review start.
- 0e12e4f changed only store/base.py, store/__init__.py, interactions.py, service.py, tests/integration/test_lock_waits.py and docs/progress.md. All given files, the spec and the guide are byte-identical to fdcba96 (G7 empty). No change to pyproject.toml, tests/sections.toml or any earlier test.

## Gates (fresh)

- G1 `check.py --first core`: All checks passed; 1413 passed; Sections tooling 77/0 failed, core 1336/0 failed; no skips or warnings.
- G2 coverage service.py 252 stmts / 52 branches, interactions.py 356 / 166, store/base.py 56 / 6, store/__init__.py 23 / 0: TOTAL 100%, exit 0.
- G3 given files: 102 passed, and 102 passed in each of 5 further runs (6 in all).
- G4 probe: oracle self-check ok; real SQLite error classification ok; 40 of 40 trials reached; contention invariants ok; FAILURES 0.
- G5: 1. G7: no output. G8: clean tree.
- Q1 to Q4: no matches (exit 1 each).

## Spot checks (scratch copy, mailroom imported from the copy, original bytes unchanged)

- S1 to S14: the deciding test fails under each mutation, as required. S3 and S2 fail only the targeted cases of their parametrized test (others pass), as expected.

## Source review

- `is_busy` reads only the SQLite error code (masked with 0xFF, 5 or 6) and never the message. `set_lock_wait` issues `PRAGMA busy_timeout` and nothing else changes; no retry loop or SQL replay in the store; commit failure rolls back before propagating.
- `handle_interaction` catches only a busy `OperationalError` from the handling step, after owner, channel and shape checks, and sends the private BUSY_TEXT reply once; other errors propagate with no callback.
- Poll loop: the guarded part covers listener tracking, `run_round` and end-of-episode work. A busy error reports `store: busy` and the loop waits as usual; non-busy errors end the service. The episode ping uses one nonce per episode, is marked posted only on confirmation, tolerates KeychainError, and the free-again notice uses the alert queue. Waits are read from the module constants at use. Time and ids go through `clock.now()` and `ids.new_id()`.
