# Review: Phase 1a

- Verdict: PASS
- Passed: 175
- Findings: 0
- Approved deviations: If get_content() is not text, or get_payload() raises, the body is empty. If the content type cannot be read, or HTML conversion raises, the decoded text is kept as plain text.
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/mime.py` and `src/mailroom/store.py` exist, and `grep -c "^## Phase 1a: " docs/progress.md` prints `1`. The baseline files are committed.

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

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `175 passed`, 0 failed, 0 skipped, and there is no warnings summary. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          116 passed    0 failed    0 skipped
```

G2, run immediately after G1: exit 0, `TOTAL 332 0 80 0 100%`.

G3: `69 passed in 0.17s`.

G4: `Reports OK.`

G5: no output.

G6:

```
 M docs/progress.md
?? src/mailroom/mime.py
?? src/mailroom/store.py
?? tests/unit/test_mime_more.py
```

G7: `pip list --format=freeze` matches the Phase 0 set. `pyproject.toml` is unchanged.

### Searches

Q1, Q2, Q3, Q4, Q6, and Q7 printed nothing. Q5 printed one line: `src/mailroom/store.py:62` `PRAGMA secure_delete = ON`.

### Spot checks

Each deciding test failed with the Broken value. The module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies. Umask was `022`.

| # | Result |
|---|---|
| S1 | `b"ZQX-BODY-7"` present in the file |
| S2 | `assert 420 == 384` (0o644 left in place) |
| S3 | second clear returned `0` |
| S4 | third clear returned `2` |
| S5 | second `add` returned `True` |
| S6 | `DID NOT RAISE StoreError` |
| S7 | stored sent time `'2026-11-03T19:45:00.000250+05:30'` |
| S8 | `body_text=None` |
| S9 | sender `'Billing@Billing.Example.TEST'` |
| S10 | body `'HTML part'` |
| S11 | `'Pay the bill now\u200b!\u202e'` |
| S12 | output contains `'p {}'` |
| S13 | output contains `'One\n\nTwo'` |
| S14 | `IndexError` |
| S15 | `AttributeError` |
| S16 | 12 authentication-results values |
| S17 | `LookupError` |

### Probe

`/tmp/probe-01a.py` was run from the repository root and then deleted. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The extra tests in `tests/unit/test_mime_more.py` each assert an outcome from the spec (a missing header, an empty body, plain text kept when the content type cannot be read). `store.py` reached 100% from the given tests, so `tests/integration/test_store_more.py` is absent.
