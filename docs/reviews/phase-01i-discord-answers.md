# Review: Phase 1i

- Verdict: PASS
- Passed: 490
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/interactions.py` and `tests/integration/test_interactions_more.py` exist, and `grep -c "^## Phase 1i: " docs/progress.md` prints `1`. The baseline files are committed. `tests/integration/test_store_answers_more.py` was not added; coverage of the store was already complete.

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

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `490 passed`, 0 failed, 0 skipped, and there is no warnings summary. That is the previous 441, the 40 given tests, and 9 extra tests. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          431 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 463 0 118 0 100%` (`interactions.py` 122, `checkpoint.py` 50, `store.py` 212, `config.py` 79).

G2: `40 passed in 0.20s`.

G4: `1`.

G5: `Reports OK.`

G6: no output.

G7:

```
 M docs/progress.md
 M src/mailroom/checkpoint.py
 M src/mailroom/config.py
 M src/mailroom/store.py
?? src/mailroom/interactions.py
?? tests/integration/test_interactions_more.py
```

G8: `pip list --format=freeze` matches the Phase 1h set. No package is new.

### Searches

Q1 through Q11 printed nothing.

### Spot checks

Each deciding test failed with the Broken value. The edited module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | `'answered'` |
| S2 | `'answered'` |
| S3 | `StopIteration` |
| S4 | `` `portal` `` |
| S5 | 1,901 `a`s, no note |
| S6 | `'  Pay the bill online  '` |
| S7 | `'answered'` |
| S8 | `None` |
| S9 | `True` |

### Probe

`.venv/bin/python docs/verification/probe-01i.py` was run from the repository root and was not edited. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The extra tests assert behavior. A direct message uses `user.id` and records `notask`. A submission with no title field, and one with no fields, is `bad-title` and stores nothing. A lost connection raises `discord unavailable (network)` and keeps the `notask` answer. Show full text of an empty body is `(no text)`. A form with no title and an empty subject omits `value`. An empty channel sends nothing. A later submission leaves the first answer. A submission whose action is not `title` is ignored.
