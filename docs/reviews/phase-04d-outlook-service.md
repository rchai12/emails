# Review: Phase 4d

- Verdict: FAIL
- Passed: 1150
- Findings: 1
- Approved deviations: None
- For the architect: The dmarc-other-domain and dkim-other-domain cases expect False, but Gmail's rule returns True for the same results: other.example.test aligns as a subdomain, and a DMARC pass for another domain does not cancel SPF and DKIM.

## Findings

6 | docs/progress.md:247 | expected a heading ## Phase 4d: Outlook in the service | found the file ends at Phase 4c

Parts that needed a repair: none

Built beyond the spec: none

## Detail

`git status --short` lists the four code Scope paths: `src/mailroom/alerts.py`, `src/mailroom/config.py`, `src/mailroom/sender_auth.py`, and `src/mailroom/service.py`. `grep -c "^## Phase 4d: " docs/progress.md` prints `0`. The baseline given files are committed.

G1 `.venv/bin/python scripts/check.py --first core` stopped at the core tests: `2 failed, 1150 passed` in 4.90s, 0 skipped. The full tests step and the critical coverage step did not run. Last lines:

```
Sections:
  core         1150 passed    2 failed    0 skipped  rerun: .venv/bin/python scripts/check.py --section core

Summary:
  lint: passed
  format: passed
  tests (core): FAILED
  tests: not run
  critical coverage: not run
Check failed at: tests (core)
```

The two failures are `test_microsofts_first_header_decides[dmarc-other-domain]` and `[dkim-other-domain]`. Both got `True` where the test expects `False`. The same headers, written with Gmail's server name, also verify as `True` through the unchanged Gmail rule. The probe then agrees: `oracle self-check: ok`; `Gmail and Outlook verify the same results alike: ok`; `no forged or misplaced header verifies an Outlook email: ok`; `FAILURES 0`.

G2 is `2 failed, 37 passed`. G3, run on the coverage data left after the stopped check, exit 2 with `TOTAL 70%`. That data does not include this run's core tests. G5 prints `0`. G7 and G8 print nothing. G9 lists the four code Scope paths. G10 `.venv/bin/python -m pip list --format=freeze` is the same 35 packages as before this phase. Q1 through Q6 print nothing.

S1 through S8 each failed with the Broken value, then the modules were copied back. `cmp` matched, `git diff HEAD` matched the snapshot, and `git status --short` matched the snapshot.

Requirement 6 is missing. Append the Phase 4d progress entry at the end of `docs/progress.md`, with the heading `## Phase 4d: Outlook in the service (YYYY-MM-DD)` and the fields `docs/phase-conventions.md` requires.
