# Phase 1g: Triage result

## Goal

Turn one stored email into a stored verdict. Screen it (1e), ask the model unless the sender is muted (1f), decide in code whether you get a notification, and store the result once in a new `triage` table. The extraction's text (summary, title, quote, reason) is cleared 24 hours after the email was fetched, with the email's own text. Add the ranking that busy-hour digests will use, and the list of messages still waiting for triage. Nothing is sent yet: 1h posts the Discord message and 1i runs the loop.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 352, the tests Phase 1f left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_triage_decide.py --ignore=tests/integration/test_store_triage.py --ignore=tests/integration/test_triage.py` must show `352 passed`. The ignored files import names you create. `test_store.py` and `test_store_sync.py` already pass: they expect schema version 4, which the given migration provides.

## Facts

From SQLite 3.54.1 and Python 3.12 on this machine.

- **Insert only when the message is there.** `INSERT INTO triage (...) SELECT ... FROM messages WHERE provider = ? AND message_id = ? AND text_cleared_at IS NULL ON CONFLICT DO NOTHING` inserts one row when the message is stored with its text, and none when it is missing, cleared, or already has a verdict. `cursor.rowcount` is `1` or `0`.
- **CHECK comes first.** A verdict that breaks one of the table's `CHECK`s raises `sqlite3.IntegrityError`, even when a row already exists. Its text names the constraint, never a value.
- **Times are text in UTC with microseconds** (`_stamp` in `store.py`), so text order is time order. `received_at` is stored that way.
- **No import cycle.** `rules.py` imports `Store` from `store.py`, so `store.py` must not import `rules.py`. `extractor.py` imports nothing from the store, so `store.py` may import `Deadline` and `Extraction` from it.
- **Sorting.** `sorted` is stable and does not change its input. `datetime.time.max` is `23:59:59.999999`. A `datetime` can't be negated: use `-moment.timestamp()`, or sort twice.
- **`secure_delete` is on** (`Store.__init__`), so text set to `NULL` is overwritten in the file.

## Owner's decisions

- **Only sure non-tasks are skipped.** An email is not notified only when the model says it is not actionable, not urgent and has no deadline, with `high` confidence, or `medium` confidence on bulk mail (`List-Unsubscribe`). A trusted sender's email and an email the model couldn't read are always notified. A skipped email is still stored.
- **An unreadable email ranks as if nothing is known**: not urgent, no deadline, `low` confidence, not suspected. It goes after everything the model read with higher confidence, and above suspected spam. Trust still puts it first.

## Architect's decisions

- **A table of its own.** The verdict goes in a new `triage` table (given migration 4), not in `messages`. The `messages` table's `CHECK` ties its text columns together and SQLite can't change a `CHECK`. The extraction is one JSON column, cleared to `NULL` like the body.
- **Cleared by the email's fetch time.** The extraction is cleared when its message's `fetched_at` is 24 hours old, in the same `clear_expired_text` call, so the model's text never outlives the email's.
- **Stored once, refused after clearing.** A verdict is saved only for a stored message whose text is still there, and only once. A later verdict for the same message is ignored, so a retry never changes what was decided.
- **The verdict is data in `store.py`**, as `Verdict`, holding the screening's flags as plain booleans, because `store.py` can't import `Screening`. Dropped mail gets a row too (`outcome` `"dropped"`), so it is not screened again.
- **The rejection reason is the log.** `Rejected.reason` (a field name or a fixed word) is stored in `reason`. The audit log comes in a later phase.
- **The notify rule ignores the spam flag.** A suspected email is notified or not by the same rule; the flag ranks it last and, in stage 2, keeps it from combined approval.
- **Ranking ties.** A deadline without a time counts as the end of that day. After "newest first", ties go by provider, then message id, so the order never depends on the input order. `rank` orders whatever it is given and filters nothing.
- **`triage_message` takes a key, not a record.** It reads the message from the store, so it can never triage text that is already cleared, and it returns a stored verdict without asking the model again.
- **Critical modules**: `triage.py` (what reaches you). `store.py` already is one.

## Requirements

1. **Migration 4** (given) creates `triage`: `provider`, `message_id`, `outcome` (`dropped`, `extracted` or `rejected`), `reason`, `trusted`, `verified`, `bulk`, `notify`, `extraction`, `decided_at` and `text_cleared_at`, keyed by `(provider, message_id)`. Its `CHECK`s: `reason` is non-empty exactly for `rejected`; `dropped` has `notify` 0; only `extracted` may have an `extraction` or a `text_cleared_at`; and an `extracted` row has exactly one of the two.

2. **`store.py`: `Verdict`**, a `@dataclass(frozen=True)`, fields in this order:
   - `outcome: Literal["dropped", "extracted", "rejected"]`
   - `trusted: bool`, `verified: bool`, `bulk: bool`, `notify: bool`
   - `extraction: Extraction | None = None`
   - `reason: str = ""`

   **`StoredTriage`**, a `@dataclass(frozen=True)`: `verdict: Verdict`, `decided_at: datetime`, `text_cleared_at: datetime | None`.

3. **`Store.save_triage(provider: str, message_id: str, verdict: Verdict) -> bool`.**
   - Reads `clock.now()` exactly once and stores it as `decided_at`.
   - Inserts the row only if `messages` holds that key with `text_cleared_at IS NULL` and `triage` does not yet hold it. Returns `True` when it inserted.
   - `extraction` is `NULL` when `verdict.extraction` is `None`. Otherwise it is JSON text (`json.dumps`) holding all eight `Extraction` fields, with the deadline as `null` or its date, time (or `null`), `explicit` and quote, so that reading it back gives an equal `Extraction`.
   - Commits.

4. **`Store.triage(provider: str, message_id: str) -> StoredTriage | None`** reads the row back. A cleared row's verdict has `extraction=None`, and its `text_cleared_at` is set.

5. **`Store.untriaged() -> tuple[tuple[str, str], ...]`** gives `(provider, message_id)` for every message with `text_cleared_at IS NULL` and no `triage` row. They are ordered by `received_at`, oldest first, then provider, then message id.

6. **`Store.clear_expired_text()` also clears extractions.** With the same `now` it already reads (no second clock read), it sets `extraction = NULL, text_cleared_at = <now>` on every `triage` row that still has an `extraction` and whose message's `fetched_at` is at or before `now - TEXT_RETENTION`. This happens in the same commit, and the return value is still the number of messages cleared. Dropped and rejected rows are never changed.

7. **`src/mailroom/triage.py`: `should_notify(screening: Screening, result: Extraction | Rejected | None) -> bool`.** `None` means the rules dropped the email. In order:
   1. `None` gives `False`.
   2. A `Rejected` gives `True`.
   3. `screening.trusted` gives `True`.
   4. `actionable`, `urgent`, or a `deadline` that is not `None`, gives `True`.
   5. `confidence == "high"` gives `False`.
   6. `confidence == "medium"` with `screening.bulk` gives `False`.
   7. Otherwise `True`.

8. **`rank(entries: Iterable[tuple[Record, Verdict]]) -> list[tuple[Record, Verdict]]`** returns a new list, ordered by these steps, each deciding only when the ones before it tie. "Unknown" means `verdict.extraction is None` (dropped, rejected or cleared), and counts as not suspected, not urgent, no deadline, `low` confidence.
   1. `verdict.trusted` first.
   2. `extraction.suspicious` last.
   3. `extraction.urgent` first.
   4. With a deadline before without; then the earlier `(date, time or time.max)` first.
   5. Confidence `high`, then `medium`, then `low`.
   6. `record.received_at` newest first.
   7. `record.provider`, then `record.message_id`, ascending.

9. **`triage_message(store: Store, provider: str, message_id: str, settings: Settings, http: httpx.Client) -> Verdict | None`.**
   1. `store.get(provider, message_id)` is `None`: return `None`.
   2. `store.triage(provider, message_id)` exists: return its `verdict`, with no model call and no clock read.
   3. The message's `text_cleared_at` is set: return `None`.
   4. `screen(record, store)`. For `action == "drop"` the result is `None`, with no model call. Otherwise the result is `extract(record, settings, http)`. A `ModelUnavailable` propagates and nothing is stored, so the message stays in `untriaged()`.
   5. Build the `Verdict`:
      - `outcome`: `"dropped"`, `"extracted"` or `"rejected"`
      - `trusted`, `verified` and `bulk` from the screening
      - `notify=should_notify(screening, result)`
      - `extraction`: the `Extraction`, or `None`
      - `reason`: the `Rejected.reason`, or `""`
   6. `store.save_triage(...)` the verdict, then return it.

10. **Critical modules.** `scripts/critical_modules.txt` (given) lists `triage.py`.

11. **Progress entry** for `## Phase 1g: Triage result (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Adds migration 4, the `triage` table |
| `tests/integration/test_store.py` | Schema version asserts now expect 4 |
| `tests/integration/test_store_sync.py` | Schema version assert now expects 4 |
| `tests/unit/test_triage_decide.py` | 31 tests (requirements 7 and 8) |
| `tests/integration/test_store_triage.py` | 11 tests (requirements 2 to 6) |
| `tests/integration/test_triage.py` | 9 tests (requirement 9) |
| `scripts/critical_modules.txt` | Adds `triage.py` |
| `docs/verification/probe-01g.py` | The verifier's probe |

Given test count: **51** in the three new files.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_store_triage_more.py` and `tests/integration/test_triage_more.py` (and `tests/unit/test_triage_decide_more.py` if needed), never by changing a given test, for at least:
- an inconsistent `Verdict` (for example `dropped` with `notify=True`) raising `sqlite3.IntegrityError` and storing nothing
- `untriaged()` on an empty database
- a verdict stored for one provider not being found under another provider with the same message id
- `rank([])` returning `[]`

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store.py` | add `Verdict`, `StoredTriage`, `save_triage`, `triage` and `untriaged`, and extend `clear_expired_text` |
| `src/mailroom/triage.py` | create |
| `tests/integration/test_store_triage_more.py` | create |
| `tests/integration/test_triage_more.py` | create |
| `tests/unit/test_triage_decide_more.py` | create, only if coverage needs it |
| `docs/progress.md` | append your entry |

## Out of scope

- **Sending.** Discord messages, digests, the 20-an-hour count, follow-ups (1h and later).
- **Running it.** A poll loop, a CLI command, retrying an unavailable model (1i).
- **Stage 2 and later.** The "clearly dated" checks, the evidence quote's presence in the email, sender scores, the `items`, `threads` and `audit_log` tables.
- **Other changes.** Logging, extra settings, a sort over SQL, any change to the extractor, the rules, a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Code decides** (`AGENTS.md`): the notify rule and the ranking are fixed code, never asked of the model.
- **Email text is cleared after 24 hours**: the summary, title, quote and reason live only in `extraction`, which `clear_expired_text` clears with the body. No other column may hold model text.
- **Nothing is sent**: `triage.py` reaches the model only through `extract`, and makes no other call with `http`.
- **No email text in errors or logs.** Nothing in this phase prints, logs or raises with a summary, title or body.
- **Time through the module**: `clock.now()`, never `datetime.now()`, and never `from mailroom.clock import now`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 51 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_triage_decide.py tests/integration/test_store_triage.py tests/integration/test_triage.py --no-cov -q` | `51 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/triage.py,src/mailroom/store.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1g: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1g` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_triage_decide.py tests/integration/test_store_triage.py tests/integration/test_triage.py scripts/critical_modules.txt docs/verification/probe-01g.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|discord)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request|(import|from) urllib([^.A-Za-z_]|$)' -- src
git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py'
git grep --untracked -n -E 'httpx\.[A-Za-z]+\(|http\.(get|post|put|patch|delete|request|send|stream)\(' -- src/mailroom/triage.py
git grep --untracked -n -E '^(import|from) .*(rules|triage)([^A-Za-z_]|$)' -- src/mailroom/store.py
git grep --untracked -n -E 'DELETE FROM triage|DROP TABLE|ALTER TABLE' -- src
git grep --untracked -n -E 'while |range\(' -- src/mailroom/triage.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/triage.py src/mailroom/store.py
```
