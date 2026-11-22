# Phase 4j: Stabilize store readers and lifecycle

## Goal

Each stored record type has one named column list, and every reader for it uses that
list and reads columns by name. A reordered list gives the same records, and a list
that repeats a column is refused by name. One due reader and writer replaces the two
copies. Defining `__init__` in a store area is refused when the class is defined, so
the Store keeps one connection and one migration run. Callers see no new store API.
This closes audit finding 6.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is **1488**, from the passing Phase 4i review
(`e2040b8`). The finalized planning/given-file commit made after this document is the
coder's clean start.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_store_projections.py --ignore=tests/unit/test_store_lifecycle.py`
must show `1488 passed`. Nothing needs a missing-module stub. The two new given files
import only names that exist today. They read the new names when a test runs.

## Facts

- `Store` in `store/__init__.py` combines eight area mixins (`MessageStore`,
  `SyncStore`, `SenderStore`, `TriageStore`, `PostStore`, `AlertStore`,
  `ApprovalStore`, `TaskStore`), all subclasses of `base.StoreBase`. Only
  `StoreBase.__init__` connects: it opens one `sqlite3` connection, sets
  `secure_delete`, sets the file mode to 0600 and runs `_migrate`. Nothing stops a
  mixin from defining its own `__init__`, which would open a second connection or run
  migrations twice.
- These readers unpack each row by position:
  - `posts._read_post`, for `pending_posts`, `post` and `post_by_item`. The same
    8-column SELECT is written out three times.
  - `tasks._read_task`, for `pending_tasks` and `task`.
  - `tasks._read_link`, for `pending_links` (JOIN tasks) and `link` (LEFT JOIN tasks).
  - `approvals._approval`, for `approval` and `approved_in_thread`. The second one
    qualifies every column with `approvals.` because it joins posts and messages.
  - `MessageStore.get` (the 14-column `_SELECT`), and `TriageStore.triage`
    (12 columns).
  A list reordered on one side only would swap fields without any error.
- `triage._read_due` and `approvals._read_due` are two copies of the same rule, and
  `approvals._due_columns` writes a due. `save_triage` formats its due inline with the
  same rule: date as ISO, time as `%H:%M`, time `None` allowed, no due as two NULLs.
- A planning spike on SQLite (Python 3.12) found:
  - `cursor.description` names a qualified column by its bare name (`links.item_id`
    gives `item_id`, `tasks.task_id` gives `task_id`);
  - a SELECT may return the same name twice (`['item_id', 'item_id']`);
  - `sqlite3.Row` still allows positional access and returns the first of two equal
    names.
- `tests/unit/test_store_package.py` pins the module each public method and name lives
  in. `tests/integration/test_store_due.py` pins `Due.__module__ ==
  "mailroom.store.triage"`.
- Answers, alerts, problems, sync state and senders are read with short positional
  SELECTs. They are outside the owner's list.
- Validated with a throwaway scratch stand-in only (never copied in):
  - The 232 store tests (`tests/integration/test_store*.py`,
    `tests/unit/test_store*.py`), the given ones included, pass on it.
  - The given tests pass 6 of 6 runs.
  - On predecessor code, all 29 given cases fail.

## Owner's decisions

- **2026-11-22:** named projections. Each record type's column list is written once as
  a named constant, every SELECT for that record uses it, and rows are read by column
  name.
- **2026-11-22:** a constructor in any store area or in `Store` is refused when the
  class is defined, with a `TypeError`.
- **2026-11-22:** the readers in scope are posts, tasks, links, approvals, messages and
  triage. Alerts, problems and sync stay as they are.
- **2026-11-22:** a column name that appears twice in a projection's result raises
  `StoreError` with a constant message naming the column.

## Architect's decisions

- **Projection constants live with their readers**, as module-level tuples of strings
  in the order the SELECT lists them. They are public in their modules and are not
  re-exported from `mailroom.store`; `__all__` is unchanged.
- **Read by bare name.** A reader takes each column's name from
  `cursor.description`, which drops a table prefix. Two projections need a prefix
  because their queries join: links (`tasks.task_id` comes from the joined table) and
  approvals (`approved_in_thread` joins posts and messages). The same qualified list
  also works for `approval`, which reads one table.
- **The duplicate check runs on every read**, before any record is built, including a
  read that finds no row. It is one shared helper in `base.py`; its name is the
  coder's choice.
- **One due reader and writer, in `triage.py`**, where `Due` lives:
  `due_columns(due)` and `read_due(deadline_date, deadline_time)`. `approvals.py`
  imports them. They stay module-level names, not store methods.
- **The guard checks the class body only** (`"__init__" in cls.__dict__`), through
  `StoreBase.__init_subclass__`. A subclass that inherits `StoreBase.__init__` is
  accepted. `StoreBase.__init__` itself is unchanged.
- **SQL tails stay byte-for-byte**: the FROM, JOIN, WHERE, ORDER BY and LIMIT text of
  each reader, and every write statement, are unchanged.

## Requirements

1. **Projections.** Define exactly these constants:

   | Module | Constant | Columns, in order |
   |---|---|---|
   | `store/posts.py` | `POST_COLUMNS` | `item_id`, `provider`, `message_id`, `queued_at`, `discord_message_id`, `posted_at`, `card`, `follows` |
   | `store/tasks.py` | `TASK_COLUMNS` | `item_id`, `provider`, `message_id`, `queued_at`, `task_id`, `sent_at` |
   | `store/tasks.py` | `LINK_COLUMNS` | `links.item_id`, `links.provider`, `links.message_id`, `links.task_item_id`, `tasks.task_id`, `links.queued_at`, `links.sent_at` |
   | `store/approvals.py` | `APPROVAL_COLUMNS` | `approvals.item_id`, `approvals.outcome`, `approvals.title`, `approvals.deadline_date`, `approvals.deadline_time`, `approvals.decided_at` |
   | `store/messages.py` | `MESSAGE_COLUMNS` | `provider`, `message_id`, `thread_id`, `received_at`, `link`, `sender`, `sender_name`, `subject`, `sent_at`, `list_unsubscribe`, `body_text`, `authentication_results`, `fetched_at`, `text_cleared_at` |
   | `store/triage.py` | `TRIAGE_COLUMNS` | `outcome`, `trusted`, `verified`, `bulk`, `notify`, `extraction`, `reason`, `decided_at`, `text_cleared_at`, `deadline_date`, `deadline_time`, `dated` |

   Each is a `tuple[str, ...]`. Remove `messages._SELECT`.
2. **Every reader uses its constant at call time.** These eleven methods build their
   column list from the module's constant when they run: `pending_posts`, `post`,
   `post_by_item`, `pending_tasks`, `task`, `pending_links`, `link`, `approval`,
   `approved_in_thread`, `get`, `triage`. A test that replaces the constant on the
   module must change what the next call selects. So never copy it into import-time
   SQL, a default argument or a class attribute.
3. **Read by name.** Each of those readers maps every field from the column's bare
   name, never from its position. Reversing or shuffling any constant returns equal
   records, including null and non-null dates, times, sent and cleared stamps.
4. **Duplicate columns.** Add `PROJECTION_MESSAGE = "duplicate stored column"` to
   `store/base.py`. When a reader's result names a column twice, raise
   `StoreError(f"{PROJECTION_MESSAGE}: {name}")` with the bare name. The message
   carries no row value.
5. **One due reader and writer.** In `store/triage.py`:
   - `due_columns(due: Due | None) -> tuple[str | None, str | None]` returns
     `(None, None)` for no due, and otherwise the ISO date and the time as `%H:%M`, or
     `None`;
   - `read_due(deadline_date: str | None, deadline_time: str | None) -> Due | None` is
     its inverse.
   `save_triage`, `triage`, `record_approval`, `record_combined` and the approval
   reader use them. Remove `triage._read_due`, `approvals._read_due` and
   `approvals._due_columns`; `approvals.read_due` and `approvals.due_columns` are the
   imported triage functions.
6. **Constructor guard.** Add
   `CONSTRUCTOR_MESSAGE = "a store area must not define __init__"` to `store/base.py`.
   A class that subclasses `StoreBase`, at any depth (an area, `Store`, or a subclass
   of either), and defines `__init__` in its own body raises
   `TypeError(f"{CONSTRUCTOR_MESSAGE}: {cls.__name__}")` at class definition.
7. **Lifecycle and compatibility.**
   - `open_store` still opens exactly one connection, runs each pending migration once,
     and runs none when reopened.
   - Every write still commits or rolls back as a whole through `_write`.
   - Public store names, method placement (`test_store_package.py`), `Due`'s module,
     schema and every write's SQL are unchanged. Existing tests keep passing
     unchanged.
8. **Progress entry** for `## Phase 4j: Stabilize store readers and lifecycle (YYYY-MM-DD)`
   at the end of docs/progress.md, with actual counts.

## Given files

Committed with the finalized spec before coding; never change them as the coder.

| File | What it is |
|---|---|
| `tests/integration/test_store_projections.py` | 24 cases: each projection read as written and reversed against literal posts, tasks, links, approvals, messages and triage (null and set dates, times, sent and task ids); cleared text through reversed projections; a duplicate column refused by name in each of the 11 readers |
| `tests/unit/test_store_lifecycle.py` | 5 cases: a constructor refused at definition in `StoreBase`, `PostStore` and `Store` subclasses while a plain subclass is accepted; the due columns round trip; approvals share the triage due reader and writer |
| `docs/verification/probe-04j.py` | 40 seeded store chains read through 3 shuffles of every projection against an independent oracle; a seeded duplicate per projection and reader; constructor refusal for every area; one connection and one migration run per open |

Given test count: **29** new cases, so the minimum final suite is **1517**.

## Tests to write

Add behavior tests in `tests/integration/test_store_readers.py` (not a `_more` file).
The whole `store/` package is critical: every line and branch stays covered. The given
tests and the existing store tests already reach 100% on a stand-in. Add tests for
behavior they leave unpinned, for example:

- `open_store` on a new file connects once and runs every migration once, and a reopen
  connects once and runs none (count calls with a wrapping `sqlite3.connect` factory);
- a duplicate column is refused by a read that finds no row;
- a reader still works when a constant is shuffled in some other order than reversed;
- a failed `record_combined` still writes neither the answer nor the approval.

Use synthetic data. Do not edit given or earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store/base.py` | The two messages, the constructor guard, the named-row helper with its duplicate check |
| `src/mailroom/store/posts.py` | `POST_COLUMNS` and its three readers |
| `src/mailroom/store/tasks.py` | `TASK_COLUMNS`, `LINK_COLUMNS` and their four readers |
| `src/mailroom/store/approvals.py` | `APPROVAL_COLUMNS`, its two readers, the shared due functions |
| `src/mailroom/store/messages.py` | `MESSAGE_COLUMNS` and `get` |
| `src/mailroom/store/triage.py` | `TRIAGE_COLUMNS`, `triage`, `due_columns`, `read_due`, `save_triage` |
| `tests/integration/test_store_readers.py` | New coder-written behavior tests |
| `docs/progress.md` | Append Phase 4j entry |

New tests fall in `core`; tests/sections.toml stays unchanged.

## Out of scope

- Readers of answers (`PostStore.answer`), alerts, problems, sync state, senders,
  `choose_card`, `untriaged`, and the SELECTs inside `queue_*` writes.
- Schema, migrations, foreign keys (6a), write SQL, new store methods or a repository
  redesign; splitting or renaming the `Store` facade; moving methods between modules.
- Changes outside the store package, to fakes, given files, earlier tests,
  dependencies or design documents.
- `sqlite3.Row` or a `row_factory` on the connection: other areas still read by
  position.

## Rules that bite

All checks are synthetic and offline, on temporary database files. Never touch real
mail, Discord, the tasks app, the Keychain or the data folder. The given tests replace
each projection constant on its module with `monkeypatch.setattr`. So a reader must
look the constant up when it runs. A default argument such as
`columns=POST_COLUMNS` is bound at definition and defeats the test. Do not catch
`KeyError` or a broad exception to hide a missing column, and do not fall back to a
position. Leave `StoreBase.__init__` alone except for the guard that sits beside it.

## Acceptance

Run from the repository root, in order. The coverage row reads the data the check
left; the given-only run has --no-cov and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line All checks passed.; tests (core) passed; at least 1517 passed, 0 failed/skipped/xfailed, no warnings; every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include='src/mailroom/store/*' --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_store_projections.py tests/unit/test_store_lifecycle.py --no-cov -q` | 29 passed |
| `.venv/bin/python docs/verification/probe-04j.py` | each check line ends ok; final FAILURES 0 |
| `grep -c '^## Phase 4j: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4j` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04j-store-readers-lifecycle.md docs/verification/phase-04j-store-readers-lifecycle.md tests/integration/test_store_projections.py tests/unit/test_store_lifecycle.py docs/verification/probe-04j.py` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may additionally write its named review |

### Searches

Each prints nothing (git grep exit 1 means no matches; above 1 is an error).

```zsh
git grep --untracked -n -E '^ +([a-z_]+, ){4,}[a-z_]+ = row$|^ +\) = row$|row\[[1-9]' -- src/mailroom/store/posts.py src/mailroom/store/tasks.py src/mailroom/store/approvals.py src/mailroom/store/messages.py src/mailroom/store/triage.py
git grep --untracked -n -E 'SELECT (item_id, provider, message_id, queued_at|outcome, trusted|provider, message_id, thread_id|links\.item_id, links\.provider|(approvals\.)?item_id, (approvals\.)?outcome)' -- src/mailroom/store
git grep --untracked -n -E 'def _?(read_due|due_columns)\(|strftime\("%H:%M"\)|fromisoformat\(deadline_time\)' -- src/mailroom/store ':!src/mailroom/store/triage.py'
git grep --untracked -n -E 'def __init__\(' -- src/mailroom/store ':!src/mailroom/store/base.py'
git grep --untracked -n -E 'except (KeyError|IndexError|LookupError|Exception)[ :]|except \(|suppress\(|pragma: no cover|noqa|row_factory|sqlite3\.Row|datetime\.now|date\.today|from mailroom\.(clock|ids) import' -- src/mailroom/store
```

## Architect validation and handoff

No feature implementation was built. The given tests collect on predecessor imports,
and all 29 new cases fail there.

A throwaway scratch stand-in (about 190 changed lines, deleted with the scratch clone)
did the following. It is not a reference for the coder.

- It passed the given tests 6 of 6 runs.
- It passed all 232 store tests, the given ones included.
- It left every store module it changed at 100% line and branch coverage.
- 16 of 16 mutations of it were caught by a given test. They covered:
  - refusing no duplicate, and a duplicate message without the column name;
  - a fixed column list in place of the constant, in `pending_posts` and in
    `approved_in_thread`;
  - reading a triage flag and a message stamp by position;
  - swapped and dropped fields in posts, links and triage, and a dropped
    cleared stamp;
  - a due reader that drops the time, a due writer that adds seconds, and a private
    due reader kept in approvals;
  - no constructor guard, a guard for direct subclasses only, and a qualified class
    name in the message.

The probe results:

- Oracle-only mode passes.
- On predecessor code it ends FAILURES 2: every constructor is accepted, and all 40
  trials raise `AttributeError`.
- On the stand-in it ends FAILURES 0.
- It catches 14 of the 16 mutations. It defines its classes at module level and does
  not check the approvals module's names, so the qualified-name and private-reader
  mutations are left to the given tests, which catch them.
- It also catches one mutation no given test can pin before coding: a second
  connection opened on construction (`lifecycle:2x13`). The coder's lifecycle test
  should pin it too.

The searches print nothing on the stand-in, and each catches a planted line. On
predecessor code, searches 1 to 3 print the old positional readers, SELECT lists and
due copies. Start shows 1488 passed. Given files are linted and formatted.

Before coder use, commit the finalized planning docs and given artifacts, including
the roadmap and history updates, and require a clean checkout.
