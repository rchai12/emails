# Verification guide: Phase 2b (Clearly dated)

Spec: `docs/phases/phase-02b-clearly-dated.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/deadlines.py`
- `grep -c "^## Phase 2b: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-02b-clearly-dated.md tests/unit/test_read_deadline.py tests/unit/test_clearly_dated.py scripts/critical_modules.txt docs/verification/probe-02b.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 80.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 80 = 810 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_read_deadline.py tests/unit/test_clearly_dated.py --no-cov -q` | `80 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/deadlines.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 2b: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 2b` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- tests/unit/test_read_deadline.py tests/unit/test_clearly_dated.py scripts/critical_modules.txt docs/verification/probe-02b.py` | no output |
| G7 | `git diff HEAD --stat -- src tests` | no output: no earlier module or test changed |
| G8 | `git status --short` | only the Scope paths |
| G9 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `deadlines.py` | digits matched with `\d` instead of `[0-9]` | `tests/unit/test_read_deadline.py::test_a_quote_that_names_no_single_readable_deadline_gives_none[arabic-indic-digits]` | `None` | `(date(2026, 11, 20), None)` |
| S2 | `deadlines.py` | a weekday equal to the sent day's resolves to a week later | `tests/unit/test_read_deadline.py::test_a_quote_that_names_no_single_readable_deadline_gives_none[sent-weekday]` | `None` | `(date(2026, 11, 17), None)` |
| S3 | `deadlines.py` | a date without a year always takes the sent year | `tests/unit/test_read_deadline.py::test_a_quote_naming_one_deadline_is_read[january-rolls-to-next-year]` | `date(2027, 1, 5)` | `date(2026, 1, 5)` |
| S4 | `deadlines.py` | `next` before a weekday is ignored | `tests/unit/test_read_deadline.py::test_a_quote_that_names_no_single_readable_deadline_gives_none[next-weekday]` | `None` | `(date(2026, 11, 13), None)` |
| S5 | `deadlines.py` | `H:MM` with `H` 1 to 12 and no suffix is read as 24-hour | `tests/unit/test_read_deadline.py::test_a_quote_that_names_no_single_readable_deadline_gives_none[ambiguous-24-hour]` | `None` | `(date(2026, 11, 20), time(5, 0))` |
| S6 | `deadlines.py` | weekdays are not checked against an explicit date | `tests/unit/test_read_deadline.py::test_a_quote_that_names_no_single_readable_deadline_gives_none[weekday-mismatch]` | `None` | `(date(2026, 11, 20), None)` |
| S7 | `deadlines.py` | `sent_day` taken in UTC (`.astimezone(UTC)`) instead of the time zone | `tests/unit/test_clearly_dated.py::test_only_an_email_meeting_every_condition_is_clearly_dated[local-sent-day]` | `True` | `False` |
| S8 | `deadlines.py` | the quote is searched without joining whitespace | `tests/unit/test_clearly_dated.py::test_only_an_email_meeting_every_condition_is_clearly_dated[clearly-dated]` | `True` | `False` |
| S9 | `deadlines.py` | confidence `medium` also accepted | `tests/unit/test_clearly_dated.py::test_only_an_email_meeting_every_condition_is_clearly_dated[medium-confidence]` | `False` | `True` |
| S10 | `deadlines.py` | the window's upper bound is exclusive (`<`) | `tests/unit/test_clearly_dated.py::test_only_an_email_meeting_every_condition_is_clearly_dated[last-day-of-window]` | `True` | `False` |
| S11 | `deadlines.py` | "past" compares days only, even when a time is given | `tests/unit/test_clearly_dated.py::test_only_an_email_meeting_every_condition_is_clearly_dated[already-past]` | `False` | `True` |
| S12 | `deadlines.py` | the reading is compared on the date only, not the time | `tests/unit/test_clearly_dated.py::test_only_an_email_meeting_every_condition_is_clearly_dated[model-missed-the-time]` | `False` | `True` |
| S13 | `deadlines.py` | the actionable-with-a-title condition is dropped | `tests/unit/test_clearly_dated.py::test_only_an_email_meeting_every_condition_is_clearly_dated[no-title]` | `False` | `True` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-02b.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

Beyond the given tests, it runs thousands of random deadlines, each written in a random accepted form among filler words, and each must read back exactly. One-change negatives (a second date, `next`, a wrong weekday, an ambiguous `H:MM`) must read as `None`. Junk strings, run from every sent day the calendar allows, must never raise, and any date without a stated year must land within a year. Random emails built around a read-back quote, with randomly varied spacing, must be clearly dated, and one broken condition, or a later `now`, must undo it. Its renderer writes only forms in Requirement 2's grammar: a `FAIL` from `random deadlines read back exactly` names the quote, which the verifier checks against the grammar before reporting it.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Digits are `[0-9]`, never `\d` | `git grep --untracked -n -E '\\d' -- src/mailroom/deadlines.py` |
| Q2 | No clock read: `now` is passed in | `git grep --untracked -n -E 'clock\.\|datetime\.now\|date\.today\|time\.time\(' -- src/mailroom/deadlines.py` |
| Q3 | No date library or model call | `git grep --untracked -n -E '(import\|from) (dateutil\|dateparser\|arrow\|pendulum\|httpx\|socket\|subprocess)([^A-Za-z_]\|$)\|extractor\.extract\|ollama' -- src/mailroom/deadlines.py` |
| Q4 | Nothing calls the new module yet | `git grep --untracked -n -E 'mailroom\.deadlines\|from mailroom import [^#]*deadlines' -- src ':!src/mailroom/deadlines.py'` |
| Q5 | No logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src/mailroom/deadlines.py` |
| Q6 | No blanket `except` | `git grep --untracked -n -E 'except:\|except Exception\|except BaseException' -- src/mailroom/deadlines.py` |
| Q7 | No coverage or lint exemptions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/deadlines.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- One regex per form, or one combined pattern with named groups, as long as every match counts (overlapping forms included).
- `read_deadline` gathering dates, weekdays and times first and deciding at the end, or stopping early at the first unreadable part.
- Lowercasing a matched ASCII token to look up its month or weekday number.
- A private exception for "unreadable", caught by name inside `read_deadline`.
- `clearly_dated` checking its conditions in another order, or using a `ZoneInfo` cache.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-02b-clearly-dated.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 2b`), then run `.venv/bin/python scripts/check_reports.py --phase 2b`; it must print `Reports OK.`
