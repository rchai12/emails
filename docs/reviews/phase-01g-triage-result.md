# Review: Phase 1g

- Verdict: PASS
- Passed: 407
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/triage.py`, `tests/integration/test_store_triage_more.py`, and `tests/integration/test_triage_more.py` exist, and `grep -c "^## Phase 1g: " docs/progress.md` prints `1`. The baseline files are committed.

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

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `407 passed`, 0 failed, 0 skipped, and there is no warnings summary. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          348 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 229 0 50 0 100%` (`store.py` 159, `triage.py` 70).

G2: `51 passed in 0.14s`.

G4: `1`.

G5: `Reports OK.`

G6: no output.

G7:

```
 M docs/progress.md
 M src/mailroom/store.py
?? src/mailroom/triage.py
?? tests/integration/test_store_triage_more.py
?? tests/integration/test_triage_more.py
```

G8: `pip list --format=freeze` matches the Phase 1f set. No package is new.

### Searches

Q1 through Q9 printed nothing.

### Spot checks

Each deciding test failed with the Broken value. The edited module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | `True` |
| S2 | `False` |
| S3 | first `'b'` |
| S4 | first `'a'` |
| S5 | first `'a'` |
| S6 | extraction still stored, `text_cleared_at` unset |
| S7 | `True` |
| S8 | `IndexError` |
| S9 | `DID NOT RAISE ModelUnavailable` |

S9 stops at pytest's "did not raise" message.

### Probe

`.venv/bin/python docs/verification/probe-01g.py` was run from the repository root and was not edited. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The extra tests assert behavior. A `dropped` verdict with `notify` true raises `sqlite3.IntegrityError` and leaves the message untriaged. `untriaged()` is empty when nothing is stored. A verdict saved for `gmail` is not found under `yahoo` with the same message id. `rank([])` is `[]`.
