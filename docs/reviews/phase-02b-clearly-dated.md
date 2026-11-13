# Review: Phase 2b

- Verdict: PASS
- Passed: 810
- Findings: 0
- Approved deviations: None
- For the architect: S1's replacement of [0-9] with \d still returns None for the arabic-indic quote while the patterns keep re.ASCII, which Requirement 2 requires; the broken date appears only when that flag is removed as well

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/deadlines.py` exists, and `grep -c "^## Phase 2b: " docs/progress.md` prints `1`. The baseline given files are committed. `git status --short` lists `docs/progress.md` and the new `src/mailroom/deadlines.py`.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `810 passed` in 3.48s, 0 failed, 0 skipped. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          751 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (132 statements, 54 branches). G2: `80 passed`. G4: `1`. G5: `Reports OK.` G6 is empty. G7 is empty. G8 lists only the two Scope paths. G9 freeze matches the Phase 2a list, 35 packages, including `websockets==17.3`. Q1 through Q7 print nothing.

The probe prints `oracle self-check: ok`, `random deadlines read back exactly: ok`, `one change reads as no deadline: ok`, `junk never raises and stays within a year: ok`, `the rule holds on a valid email and fails on one change: ok`, and `FAILURES 0`.

S2 through S13 each failed with the Broken value. After every edit the module was restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the snapshot.

S1's deciding test still passed. The file's digit classes are `[0-9]`, and every pattern is compiled with `re.ASCII | re.IGNORECASE`. Under that flag `\d` matches the same digits as `[0-9]`, so the arabic-indic quote stays `None`. Replacing `[0-9]` with `\d` and also dropping `re.ASCII` makes that test fail with `(datetime.date(2026, 11, 20), None)`. Requirement 2 asks for the ASCII flag on letters and for `[0-9]` digits, and both are present, so this pass is recorded for the architect.
