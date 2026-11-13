# Review: Phase 2c

- Verdict: PASS
- Passed: 832
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `from mailroom.store import Due` exits 0, and `grep -c "^## Phase 2c: " docs/progress.md` prints `1`. The baseline given files are committed. `git status --short` lists `docs/progress.md`, `src/mailroom/store/__init__.py`, `src/mailroom/store/triage.py`, and `src/mailroom/triage.py`.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `832 passed` in 4.30s, 0 failed, 0 skipped. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          773 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (163 statements, 42 branches). G2: `46 passed`. G4: `src/mailroom/triage.py:1`. G5: `1`. G6: `Reports OK.` G7 is empty. G8 is empty. G9 lists only the four Scope paths. G10 freeze matches the Phase 2b list, 35 packages, including `websockets==17.3`. Q1 through Q6 print nothing.

The probe prints `oracle self-check: ok`, `the stored decision and deadline match the rule, and survive clearing: ok`, and `FAILURES 0`.

S1 through S7 each failed with the Broken value. After every edit the module was restored from the copy outside the repository, `src/mailroom/__pycache__` and `src/mailroom/store/__pycache__` were removed, and `git diff HEAD` and `git status --short` matched the snapshot.

`Due` is a frozen dataclass with `date` and `time`, exported from `mailroom.store`. `Verdict` gains `dated` and `due` after `reason`, both defaulting to nothing. `save_triage` writes the date, `HH:MM`, and the flag in the same insert, and `triage` reads them back. `triage_message` calls `clock.now()` once for every stored verdict and passes that moment to `clearly_dated`. A dropped or rejected verdict stores `dated` false and `due` none. The model's proposal is stored when the extraction has a deadline, including when `dated` is false.
