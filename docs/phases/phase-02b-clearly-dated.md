# Phase 2b: Clearly dated

## Goal

Decide, in code, which emails are clearly dated: the ones that may later skip checkpoint 1 and get one combined approval ([Approval flow](../approval-flow.md#combined-approval-for-clearly-dated-emails)). The model suggests a deadline. Code reads the model's evidence quote on its own and accepts the deadline only when its reading agrees, along with every other condition.

This phase adds two pure functions in a new module, `src/mailroom/deadlines.py`:
- `read_deadline` reads the one date (and time) a quote names, or gives `None`.
- `clearly_dated` applies every condition.

Nothing calls them yet. Storing the decision at triage, the checkpoint 2 card, the combined card and the tasks app come in later sub-phases of stage 2.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 730, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_read_deadline.py --ignore=tests/unit/test_clearly_dated.py` must show `730 passed`. Both ignored files import `mailroom.deadlines`, which you create.

## Facts

Each was checked on this machine.

- **What the model gives.** `Extraction.deadline` is a `Deadline(date, time, explicit, quote)` or `None`. `date` is the model's own reading of the email, "worked out from the sent date and time zone given above the email" (`extractor_prompt.py`). The model sees the sent time (or the received time when there is no sent time) in `MAILROOM_TIME_ZONE`. `confidence` is one of `"high"`, `"medium"`, `"low"`. Model fields may hold no line breaks, so a quote that crosses a line break in the email has a space there instead.
- **Digits and letters.** `\d` in Python's `re` matches non-ASCII digits (`"٢"` is Arabic-Indic two). `[0-9]` does not. `"İ".lower()` is two characters long. So match letters with `re.ASCII | re.IGNORECASE` on the original text, and never index the original by positions found in a lowered copy. Lookalike letters, such as Cyrillic `о` in `Nоvember`, must never match.
- **Whitespace.** `str.split()` with no argument splits on every character for which `str.isspace()` is true, no-break space (` `) and thin space (` `) included. Zero-width space (`​`) is not whitespace.
- **What raises.** `date(2026, 2, 30)`, `date(0, 1, 1)` and `date(10000, 1, 1)` raise `ValueError`. `date.max + timedelta(days=1)` raises `OverflowError`. The reader turns both into `None`, and the given calendar-end cases pin them.
- **The calendar of the given tests.** 2026-11-10 is a Tuesday, 2026-11-13 and 2026-11-20 are Fridays, and 2027 has no February 29. In November, New York is UTC−5.

## Owner's decisions

- Code reads the quote. An email is clearly dated only if code's reading of the quote equals the model's date (and time). A quote code can't read, numeric dates like `11/20` included, means two checkpoints, where the owner confirms the date.
- Only confidence `high` counts.
- The quote must appear in the subject or body exactly, case included, except that each run of whitespace counts as one space.
- The deadline must fall on or after the day the email was sent, within 366 days of it, and must not have passed when the decision is made. Days are counted in the owner's time zone.

## Architect's decisions

- **A closed grammar.** The reader knows the forms in Requirement 2 and nothing else. Anything outside them adds no date, and anything ambiguous makes the whole quote unreadable. A wrong reading can only cause a fallback, never a combined approval, because the model must have reached the same answer.
- **A weekday checks a date.** When a quote also names an explicit date, every weekday in it must be that date's weekday. Alone, a weekday means the next such day after the sent day. The sent day's own weekday ("by Tuesday" in a Tuesday email) and `next Friday` are ambiguous.
- **A year is resolved forward.** A date without a year falls in the sent year when its month and day are on or after the sent day's, and in the next year otherwise. A stated year is kept as written, and the window check refuses it if it falls outside.
- **Times are read too.** The quote's time must equal the model's time, or both must be absent. `5:00` with no am/pm is ambiguous; `17:00` and `00:30` are not.
- **Actionable with a title.** A combined card proposes a task, so the email must be actionable with a non-empty title. This is the one condition the design's list doesn't spell out.
- **"Past" means at or before now.** With a time, the deadline is past when that local moment is at or before `now`. Without one, it is past when its day is before today's local date. A deadline later today still counts.

## Requirements

1. **`src/mailroom/deadlines.py`** with `CONFIDENCE = "high"`, `WINDOW = timedelta(days=366)`, `read_deadline` and `clearly_dated`.
2. **`read_deadline(quote: str, sent_day: date) -> tuple[date, time | None] | None`** reads the quote with this grammar.
   - **Matching.** Letters match as ASCII with case ignored; digits are `[0-9]` only. A word or number matches only where no ASCII letter or digit touches it on either side. `sp` is one or more whitespace characters.
   - **Months.** `MONTH` is `january`, `jan`, `february`, `feb`, `march`, `mar`, `april`, `apr`, `may`, `june`, `jun`, `july`, `jul`, `august`, `aug`, `september`, `sept`, `sep`, `october`, `oct`, `november`, `nov`, `december` or `dec`, optionally followed by `.`.
   - **Days and years.** `DAY` is one or two digits with value 1 to 31, optionally followed by `st`, `nd`, `rd` or `th`. `YEAR` is four digits.
   - **Dates.** Every match counts:
     - (a) `MONTH sp DAY`, optionally followed by `[,] sp YEAR`;
     - (b) `DAY sp [of sp] MONTH`, optionally followed by `sp YEAR`;
     - (c) `YYYY-MM-DD`;
     - (d) `today` or `tonight`, meaning the sent day, and `tomorrow`, meaning the day after it.
     A date without a year takes the sent year when (month, day) is at or after the sent day's, and the next year otherwise. A date that does not exist makes the quote unreadable.
   - **Weekdays.** `WEEKDAY` is `monday`, `mon`, `tuesday`, `tues`, `tue`, `wednesday`, `wed`, `thursday`, `thurs`, `thur`, `thu`, `friday`, `fri`, `saturday` or `sunday`, optionally followed by `.`. (`sat` and `sun` are not weekdays.) A `WEEKDAY` that only whitespace separates from a preceding `next` makes the quote unreadable.
   - **Times.**
     - `H[:MM] [sp] SUFFIX`, where `SUFFIX` is `am`, `a.m.`, `a.m`, `pm`, `p.m.` or `p.m`. `H` must be 1 to 12 and `MM` 00 to 59, or the quote is unreadable. `12 am` is 00:00 and `12 pm` is 12:00.
     - `H:MM` not followed by a suffix: `H` of 0 or 13 to 23 with `MM` 00 to 59 is that time. Any other value, `1` to `12` included, makes the quote unreadable.
     - `noon` and `midday` are 12:00. `midnight` makes the quote unreadable.
   - **The result.** The explicit dates from (a) to (d) must be at most one distinct date. If there is one, every weekday must be its weekday, and it is the result's date. If there is none, there must be exactly one distinct weekday, not the sent day's, and the result's date is the next day after `sent_day` with that weekday. The distinct times must be at most one, and the result's time is that time or `None`. Anything else, an unreadable part, or a date past the calendar's ends gives `None`. It never raises.
3. **`clearly_dated(record: Record, extraction: Extraction, time_zone: str, now: datetime) -> bool`** is `True` only when all of these hold:
   1. `extraction.actionable` is true and `extraction.title` is not empty;
   2. `extraction.suspicious` is false;
   3. `extraction.confidence == CONFIDENCE`;
   4. `extraction.deadline` is not `None`, and its `explicit` is true;
   5. its `quote` is not empty, and `" ".join(quote.split())` is a substring of `" ".join(record.subject.split())` or of `" ".join(record.body_text.split())`;
   6. `read_deadline(quote, sent_day) == (deadline.date, deadline.time)`, where `sent_day` is `(record.sent_at or record.received_at).astimezone(ZoneInfo(time_zone)).date()`;
   7. `sent_day <= deadline.date <= sent_day + WINDOW`;
   8. the deadline has not passed at `now`, as defined in Architect's decisions.
   It never raises for a valid time zone and aware datetimes.
4. **Progress entry** for `## Phase 2b: Clearly dated (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/unit/test_read_deadline.py` | 31 quotes read to one deadline, 22 that give `None`, and 5 cases at the calendar's ends |
| `tests/unit/test_clearly_dated.py` | The constants; 21 emails varying one condition from a clearly dated base |
| `scripts/critical_modules.txt` | Edited: `deadlines.py` added |
| `docs/verification/probe-02b.py` | The verifier's probe |

Given test count: **80**.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage of `deadlines.py` (a critical module), add behaviour tests in `tests/unit/test_deadlines_more.py`, never by changing a given test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/deadlines.py` | new |
| `tests/unit/test_deadlines_more.py` | new, if coverage needs it |
| `docs/progress.md` | append your entry |

## Out of scope

- Calling either function from triage, storing the decision, or a migration.
- Any card, button or Discord change; the tasks app.
- Date forms beyond the grammar: numeric dates (`11/20`, `20.11.`), `next week`, `end of month`, `EOD`, time zones named in the quote, or a second language.
- A date-parsing library such as `dateutil` or `dateparser`. No new dependency.
- Changing the extractor's prompt, schema or validation.
- Any change to a given or earlier test, `AGENTS.md` or the design docs.

## Rules that bite

- **Code decides, the model suggests.** `clearly_dated` never calls the model, and never repairs a model value to make it agree. A mismatch is simply `False`.
- **Email text is untrusted.** The quote and body are only matched and read, never echoed. `deadlines.py` logs nothing, and anything it raises inside is caught by name (`ValueError`, `OverflowError`, or its own private exception), never by a bare `except` or `except Exception`.
- **Time through the module.** `deadlines.py` never reads the clock. `now` and `sent_day` are passed in.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 80 = 810 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_read_deadline.py tests/unit/test_clearly_dated.py --no-cov -q` | `80 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/deadlines.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 2b: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 2b` | `Reports OK.` |
| `git diff HEAD --stat -- tests/unit/test_read_deadline.py tests/unit/test_clearly_dated.py scripts/critical_modules.txt docs/verification/probe-02b.py` | no output |
| `git diff HEAD --stat -- src tests` | no output: no earlier module or test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '\\d' -- src/mailroom/deadlines.py
git grep --untracked -n -E 'clock\.|datetime\.now|date\.today|time\.time\(' -- src/mailroom/deadlines.py
git grep --untracked -n -E '(import|from) (dateutil|dateparser|arrow|pendulum|httpx|socket|subprocess)([^A-Za-z_]|$)|extractor\.extract|ollama' -- src/mailroom/deadlines.py
git grep --untracked -n -E 'mailroom\.deadlines|from mailroom import [^#]*deadlines' -- src ':!src/mailroom/deadlines.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src/mailroom/deadlines.py
git grep --untracked -n -E 'except:|except Exception|except BaseException' -- src/mailroom/deadlines.py
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/deadlines.py
```
