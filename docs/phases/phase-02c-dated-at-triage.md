# Phase 2c: Dated at triage

## Goal

Make 2b's rule part of every verdict. When triage stores a verdict, it also stores two things:
- whether the email is clearly dated, decided with `deadlines.clearly_dated` at triage time, while the email text is still there;
- the model's proposed deadline, as a date and an optional time.

The deadline is not email text, so it outlives the 24-hour clearing that removes the extraction and its quote. Checkpoint 2 and the final task can then still propose it when the owner answers late.

Nothing the owner sees changes yet. The checkpoint 2 card (2d), the combined card (2e) and the tasks app (2f) use what this phase stores.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 810, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_store_due.py --ignore=tests/integration/test_triage_dated.py --ignore=tests/integration/test_triage.py` must show `801 passed`. All three ignored files import `Due` from `mailroom.store`, which you create. `test_triage.py` is an earlier file with given edits; it holds the other 9 of the 810.

## Facts

Each was checked on this machine (SQLite 3.54.1).

- **Migration 8 is given.** `src/mailroom/schema.py` now ends with migration 8, which adds three columns to `triage`:
  - `deadline_date TEXT`: an ISO date, only for an `extracted` verdict;
  - `deadline_time TEXT`: `HH:MM`, only with a date;
  - `dated INTEGER NOT NULL DEFAULT 0`: 1 only for an `extracted` verdict with a date.
  The `CHECK`s refuse anything else with `sqlite3.IntegrityError`, including `'17:00:00'`, `'2026-11-31'` and `'20261120'`. Existing rows get `dated = 0` and no deadline. In an added column, a `CHECK` may name only columns that already exist, so the columns are added in that order.
- **What clearing leaves.** `clear_expired_text` sets `triage.extraction` to `NULL` and touches no other triage column, so the three new columns survive it with no change to its SQL. `secure_delete` overwrites the cleared quote, and the given test checks the file's bytes.
- **The extractor's times.** The extractor accepts `deadline_time` only as two digits, a colon and two digits, so `Deadline.time` never has seconds. `time.strftime("%H:%M")` writes it, and `time.fromisoformat` reads it back.
- **Clock reads in earlier tests.** `test_triage.py`'s store fixture hands out one time per `clock.now()` call: the store's `add`, then `save_triage`. Triage needs one more read, for `now`, so the fixture gets a third time between them (a given edit), and `decided_at` is still the last one. A test whose triage returns early (cleared text, no message, an existing verdict) reads no extra time.
- **`GOOD` is clearly dated.** The model reply most triage tests use, sent at 07:59 UTC on November 10 (02:59 in New York) with "due on November 20 at 5 pm" in the body, meets every 2b condition at 08:04 UTC. So one earlier expected verdict gains `dated=True, due=Due(date(2026, 11, 20), time(17, 0))` (a given edit). The other earlier triage tests compare fields or the stored copy, so they pass unchanged.
- **Positional verdicts.** Earlier tests and probes build `Verdict(...)` with up to six positional fields and `reason=` by name. Adding `dated` and `due` after `reason`, with defaults, keeps every one of them valid.
- **Schema version.** Three earlier assertions pinned version 7. They now say 8 (given edits to `test_store.py` and `test_store_sync.py`).

## Owner's decisions

- The proposed deadline's date and time are kept after the email text is cleared, with no email text. The evidence quote is cleared with the extraction.
- Stage 2's remaining order: 2c stores the decision, 2d is checkpoint 2, 2e is the combined card, and 2f sends approved tasks to a stub tasks app.

## Architect's decisions

- **Decided once, at triage.** `dated` uses the triage moment as `now` and is never recomputed. Whether a card still fits when it is posted later is a question for 2e.
- **The proposal is the model's.** `due` holds the model's date and time even when code disagrees (and `dated` is then false). Checkpoint 2 proposes it, and the owner confirms or edits it.
- **One new data class.** `Due(date, time)` sits in `store/triage.py` next to `Verdict`, and `mailroom.store` exports it. It is not `extractor.Deadline`, which carries the quote.
- **The schema refuses.** `save_triage` adds no Python check. A verdict whose deadline doesn't fit raises `IntegrityError` from migration 8's `CHECK`, and 2a's rollback leaves nothing stored.
- **No backfill.** Verdicts stored before migration 8 keep `dated = 0` and no deadline. Any of them still within 24 hours just falls back to two checkpoints.

## Requirements

1. **`Due`** is a frozen dataclass in `src/mailroom/store/triage.py` with `date: date` and `time: time | None`, exported from `mailroom.store`.
2. **`Verdict`** gains `dated: bool = False` and `due: Due | None = None`, after `reason`.
3. **`save_triage`** also writes `deadline_date` (`due.date.isoformat()`), `deadline_time` (`due.time.strftime("%H:%M")`, or `NULL`) and `dated`, in the same single insert. `triage` reads them back into `verdict.due` and `verdict.dated`, before and after the text is cleared. Neither method reads the clock any more often than today.
4. **`triage_message`** reads `clock.now()` exactly once for each verdict it stores, after screening and the model call and before `save_triage`, whatever the outcome. It reads nothing when it returns early or raises. For an `extracted` verdict:
   - `due` is `Due(deadline.date, deadline.time)` when the extraction has a deadline, and `None` otherwise;
   - `dated` is `clearly_dated(record, extraction, settings.time_zone, now)`.
   For `dropped` and `rejected` verdicts, `dated` is false and `due` is `None`. Everything else about the verdict, and the notify decision, is unchanged.
5. **Progress entry** for `## Phase 2c: Dated at triage (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Edited: migration 8 appended |
| `tests/integration/test_store_due.py` | `Due` and the defaults; six verdicts read back with their deadline; three that don't fit refused; clearing keeps `dated` and `due`; the quote leaves the file while the date stays; a version 7 database migrates with nothing proposed |
| `tests/integration/test_triage_dated.py` | Eight model replies and moments, each stored with its decision and deadline; a dropped message reads the clock once and proposes nothing |
| `tests/integration/test_triage.py` | Edited: a third fixture time; the clearly dated verdict's expected `dated` and `due` |
| `tests/integration/test_store.py`, `tests/integration/test_store_sync.py` | Edited: schema version 8 |
| `docs/verification/probe-02c.py` | The verifier's probe |

Given test count: **46** (22 new; 24 in the three edited files).

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage of `store/triage.py` and `triage.py` (both critical), add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store/triage.py` | `Due`, the `Verdict` fields, the insert and the read |
| `src/mailroom/store/__init__.py` | export `Due` |
| `src/mailroom/triage.py` | the clock read, `dated` and `due` |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Any card, button, Discord or posting change, and any use of `dated` or `due` outside triage and the store.
- Recomputing `dated` later, or backfilling verdicts stored before migration 8.
- Keeping the quote, or any other email text, past 24 hours.
- A change to `schema.py`, `deadlines.py`, the extractor, the notify rule or ranking.
- Any change to a given or earlier test, `AGENTS.md` or the design docs.

## Rules that bite

- **Email text cleared after 24 hours.** The quote stays only inside `extraction`, which clearing removes. The new columns hold a date, a time and a flag, never text from the email.
- **Code decides.** `dated` comes from `clearly_dated` alone. Triage never asks the model again and never adjusts the model's proposal.
- **Time through the module.** Exactly one `clock.now()` in `triage.py`, called through the module. `deadlines.py` is passed `now` and never reads the clock.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 22 = 832 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_store_due.py tests/integration/test_triage_dated.py tests/integration/test_triage.py tests/integration/test_store.py tests/integration/test_store_sync.py --no-cov -q` | `46 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/store/triage.py,src/mailroom/store/__init__.py,src/mailroom/triage.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `git grep -c 'clock.now()' -- src/mailroom/triage.py` | `src/mailroom/triage.py:1` |
| `grep -c "^## Phase 2c: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 2c` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py tests/integration/test_store_due.py tests/integration/test_triage_dated.py tests/integration/test_triage.py tests/integration/test_store.py tests/integration/test_store_sync.py docs/verification/probe-02c.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'read_deadline|ZoneInfo|deadlines\.(CONFIDENCE|WINDOW)|import [^#]*(CONFIDENCE|WINDOW)' -- src/mailroom/triage.py src/mailroom/store
git grep --untracked -n -E '\.dated|\.due([^A-Za-z_]|$)|Due\(' -- src ':!src/mailroom/triage.py' ':!src/mailroom/store/triage.py' ':!src/mailroom/store/__init__.py' ':!src/mailroom/deadlines.py' ':!src/mailroom/schema.py'
git grep --untracked -n -E 'deadline_quote|\.quote' -- src/mailroom/triage.py
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src/mailroom/triage.py src/mailroom/store
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src/mailroom/triage.py src/mailroom/store
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/triage.py src/mailroom/store/triage.py src/mailroom/store/__init__.py
```
