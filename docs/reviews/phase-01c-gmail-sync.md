# Review: Phase 1c

- Verdict: PASS
- Passed: 239
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/gmail_sync.py` and `tests/integration/test_gmail_sync_more.py` exist, and `grep -c "^## Phase 1c: " docs/progress.md` prints `1`. The baseline files are committed.

### Gates

G1 `.venv/bin/python scripts/check.py --first core` exit 0. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `239 passed`, 0 failed, 0 skipped, and there is no warnings summary. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          180 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 329 0 56 0 100%` (`gmail.py` 194, `gmail_sync.py` 55, `store.py` 80).

G2: `25 passed in 0.13s`.

G4: `1`.

G5: `Reports OK.`

G6: no output.

G7:

```
 M docs/progress.md
 M src/mailroom/gmail.py
 M src/mailroom/store.py
?? src/mailroom/gmail_sync.py
?? tests/integration/test_gmail_sync_more.py
```

G8: `pip list --format=freeze` matches the Phase 1b set. No package is new.

### Searches

Q1, Q2, Q3, Q5, Q6, Q7, Q8, Q9, and Q10 printed nothing. Q4 printed one line: `src/mailroom/gmail.py:218` `self.http.post(`.

### Spot checks

Each deciding test failed with the Broken value. The edited module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | stored `('m4', 'm2', 'm1')` |
| S2 | `/messages` before `/profile` |
| S3 | fetches `['m1', 'm1']` |
| S4 | stored `('m1', 'm2')` |
| S5 | `MessageGone` raised |
| S6 | `GmailUnavailable` `(404)` |
| S7 | `ValueError` `invalid record field: thread_id` |
| S8 | `authuser=owner+mail@example.test` |
| S9 | `after:1794214800` |
| S10 | `after:1792656000` |
| S11 | `gap=True` |
| S12 | `SyncState` bookmark `'1002'` |
| S13 | bookmark `'1001'` |
| S14 | bookmark `'1007'` |
| S15 | `utcoffset()` `timedelta(days=-1, seconds=68400)` |

S15 prints pytest's timedelta form of a five-hour offset, which is the same value as `-1 day, 19:00:00`.

### Probe

`.venv/bin/python docs/verification/probe-01c.py` was run from the repository root and was not edited. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The two tests in `tests/integration/test_gmail_sync_more.py` assert behavior. A profile 404 is `gmail unavailable: personal (404)`, is not `MessageGone`, and leaves sync state unset. When `add` returns false, the id is left out of `stored` and the row stays in the store.
