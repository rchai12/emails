# Verification guide: Phase 2c (Dated at triage)

Spec: `docs/phases/phase-02c-dated-at-triage.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `.venv/bin/python -c "from mailroom.store import Due"` exits 0
- `grep -c "^## Phase 2c: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-02c-dated-at-triage.md src/mailroom/schema.py tests/integration/test_store_due.py tests/integration/test_triage_dated.py tests/integration/test_triage.py tests/integration/test_store.py tests/integration/test_store_sync.py docs/verification/probe-02c.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 46.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 22 = 832 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_store_due.py tests/integration/test_triage_dated.py tests/integration/test_triage.py tests/integration/test_store.py tests/integration/test_store_sync.py --no-cov -q` | `46 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/store/triage.py,src/mailroom/store/__init__.py,src/mailroom/triage.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `git grep -c 'clock.now()' -- src/mailroom/triage.py` | `src/mailroom/triage.py:1` |
| G5 | `grep -c "^## Phase 2c: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 2c` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- src/mailroom/schema.py tests/integration/test_store_due.py tests/integration/test_triage_dated.py tests/integration/test_triage.py tests/integration/test_store.py tests/integration/test_store_sync.py docs/verification/probe-02c.py` | no output |
| G8 | `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| G9 | `git status --short` | only the Scope paths |
| G10 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `triage.py` | `now` is `record.received_at` instead of `clock.now()` | `tests/integration/test_triage_dated.py::test_triage_stores_the_decision_and_the_proposed_deadline[past-at-triage-time]` | `(False, Due(..., time(17, 0)))` | `(True, ...)` |
| S2 | `triage.py` | `clock.now()` is read only for an `extracted` verdict | `tests/integration/test_triage_dated.py::test_a_dropped_message_reads_the_clock_once_and_proposes_nothing` | `decided_at` 08:05 | 08:04 |
| S3 | `triage.py` | `due` is set only when `dated` is true | `tests/integration/test_triage_dated.py::test_triage_stores_the_decision_and_the_proposed_deadline[medium-confidence]` | `(False, Due(date(2026, 11, 20), time(17, 0)))` | `(False, None)` |
| S4 | `store/triage.py` | `save_triage` writes `dated` as 0 always | `tests/integration/test_store_due.py::test_a_saved_verdict_reads_back_with_its_deadline[dated]` | `dated=True` | `dated=False` |
| S5 | `store/triage.py` | `deadline_time` written with `isoformat()` (`'17:00:00'`) | `tests/integration/test_store_due.py::test_a_saved_verdict_reads_back_with_its_deadline[dated]` | `True` returned | `IntegrityError` |
| S6 | `store/triage.py` | `triage` reads `deadline_time` as `None` always | `tests/integration/test_store_due.py::test_a_saved_verdict_reads_back_with_its_deadline[dated]` | `time(17, 0)` | `None` |
| S7 | `store/messages.py` | clearing also sets `deadline_date`, `deadline_time` to `NULL` and `dated` to 0 | `tests/integration/test_store_due.py::test_clearing_the_text_keeps_the_deadline_and_the_decision` | `due=Due(...)`, `dated=True` | `due=None`, `dated=False` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-02c.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

Beyond the given tests, it triages 400 emails with deadlines from two days back to 400 days ahead, each at a random moment. Each gets a model reply that is clearly dated or spoiled by one change from a table. The stored `dated` must equal 2b's `clearly_dated` for that email and moment, `due` must be the model's proposal, and the stored verdict must read back equal. After clearing, every row must keep `dated` and `due` without its extraction, and no quote marker may be left in the file. It asserts that every change and enough clearly dated emails were reached.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Triage calls `clearly_dated`, never re-implements it | `git grep --untracked -n -E 'read_deadline\|ZoneInfo\|deadlines\.(CONFIDENCE\|WINDOW)\|import [^#]*(CONFIDENCE\|WINDOW)' -- src/mailroom/triage.py src/mailroom/store` |
| Q2 | Nothing outside triage and the store uses `dated` or `due` yet | `git grep --untracked -n -E '\.dated\|\.due([^A-Za-z_]\|$)\|Due\(' -- src ':!src/mailroom/triage.py' ':!src/mailroom/store/triage.py' ':!src/mailroom/store/__init__.py' ':!src/mailroom/deadlines.py' ':!src/mailroom/schema.py'` |
| Q3 | Triage never reads the quote itself | `git grep --untracked -n -E 'deadline_quote\|\.quote' -- src/mailroom/triage.py` |
| Q4 | Time through the module | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src/mailroom/triage.py src/mailroom/store` |
| Q5 | No logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src/mailroom/triage.py src/mailroom/store` |
| Q6 | No coverage or lint exemptions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/triage.py src/mailroom/store/triage.py src/mailroom/store/__init__.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `due` built with a conditional expression or an `if`; `dated` computed only when the extraction has a deadline (the rule would say false anyway), as long as the clock is still read once for every stored verdict.
- The new columns read by name or by position in `triage`'s row reader.
- `Due` declared with `slots=True`.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-02c-dated-at-triage.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 2c`), then run `.venv/bin/python scripts/check_reports.py --phase 2c`; it must print `Reports OK.`
