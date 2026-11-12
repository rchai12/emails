# Review: Phase 1e

- Verdict: PASS
- Passed: 306
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/sender_auth.py`, `src/mailroom/rules.py`, and `tests/unit/test_sender_auth_more.py` exist, and `grep -c "^## Phase 1e: " docs/progress.md` prints `1`. The baseline files are committed.

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

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `306 passed`, 0 failed, 0 skipped, and there is no warnings summary. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          247 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 226 0 68 0 100%` (`sender_auth.py` 100, `rules.py` 15, `store.py` 111).

G2: `32 passed in 0.08s`.

G4: `1`.

G5: `Reports OK.`

G6: no output.

G7:

```
 M docs/progress.md
 M src/mailroom/store.py
?? src/mailroom/rules.py
?? src/mailroom/sender_auth.py
?? tests/unit/test_sender_auth_more.py
```

G8: `pip list --format=freeze` matches the Phase 1d set. No package is new.

### Searches

Q1 through Q8 printed nothing.

### Spot checks

Each deciding test failed with the Broken value. The edited module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | `True` |
| S2 | `True` |
| S3 | `True` |
| S4 | `True` |
| S5 | `True` |
| S6 | `False` |
| S7 | extra prop `('(dmarc', 'pass')` |
| S8 | `('mx.google.com', ...)` |
| S9 | `'Pass'` |
| S10 | `'mx.google.com 1'` |
| S11 | `None` |
| S12 | `'trusted'` |
| S13 | `trusted=True` |
| S14 | `action='extract'` |
| S15 | `ValueError` `invalid sender address` |

### Probe

`.venv/bin/python docs/verification/probe-01e.py` was run from the repository root and was not edited. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The three tests in `tests/unit/test_sender_auth_more.py` assert behavior. A part with no `=`, an empty side, or no method is skipped. A bare `smtp.mailfrom` domain counts, and when both `header.d` and `header.i` are present, `header.d` decides. SPF or DKIM alone does not verify.
