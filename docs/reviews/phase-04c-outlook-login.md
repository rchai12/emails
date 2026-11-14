# Review: Phase 4c

- Verdict: PASS
- Passed: 1184
- Findings: 0
- Approved deviations: None
- For the architect: S2's lower-case grant is already lowercase, so dropping .lower() leaves that test passing; the capital Mail.Read case is the one that raises scope refused.

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

`git status --short` lists the five Scope paths: `docs/progress.md`, `src/mailroom/cli.py`, `src/mailroom/gmail_login.py`, `src/mailroom/outlook_login.py`, and `tests/integration/test_outlook_login_more.py`. `outlook_login.py` exists, and `grep -c "^## Phase 4c: " docs/progress.md` prints `1`. The baseline given files are committed. `git diff HEAD -- src/mailroom/gmail_login.py` adds `Callback`'s `provider` argument and uses it in the two login errors.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `1184 passed` in 6.55s, 0 failed, 0 skipped. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core         1125 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G2 is `23 passed`. The extra test asserts `new_http` uses a 30 second timeout, ignores proxy settings, and does not follow redirects. G3, taken from the check.py coverage data before any later pytest, exit 0 with `TOTAL 100%` (outlook_login.py 52 statements and 10 branches, gmail_login.py 127 statements and 24 branches). G4 and the probe: `oracle self-check: ok`; `the code exchange fails only by name: ok`; `nothing is kept without a read-only grant: ok`; `FAILURES 0`. G5 prints `1`. G6 prints `Reports OK.` G7 and G8 print nothing. G9 lists the five Scope paths. G10 `.venv/bin/python -m pip list --format=freeze` is the same 35 packages as before this phase. Q1 through Q7 print nothing.

S1 failed with `DID NOT RAISE LoginError`. The grant was accepted. The Broken column names the returned token, which this assertion does not print. S3, S4, S5, S6, and S7 failed with the Broken values. S2's deciding test passed after the parts were left unlowered, because that grant and the expected mail scope are already lowercase. The same change makes `[mail-read]` raise `outlook login scope refused: live`. The files were copied back. `cmp` matched, `git diff HEAD` matched the snapshot, and `git status --short` matched the snapshot.
