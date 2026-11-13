# Phase 2a: Store package

## Goal

Open stage 2 by splitting `src/mailroom/store.py` into a package, as the [Phase 1 audit](../phase-01-audit.md) asked. The file is 646 lines: eight tables and 30 methods on one class. Stages 2 to 5 would add deadlines, tasks, Outlook and Yahoo to it.

Each area moves to its own module under `src/mailroom/store/`. `Store` is assembled from those modules, and every import and every call stays exactly as it is today. The phase also does the one behaviour change the owner deferred to this split: every write commits or rolls back as a whole. A write that fails partway (a refused value, an error between two statements) leaves nothing behind and releases the file. Today it keeps its transaction open, so the other connection's next write waits 5 seconds and then fails.

Nothing else changes. Checkpoint 2, combined approval and the tasks app come in later sub-phases of stage 2.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 685, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_store_package.py --ignore=tests/integration/test_store_rollback.py` must show `685 passed`. `test_store_package.py` imports the area modules you create. `test_store_rollback.py` imports fine, but two of its three tests fail until writes roll back.

## Facts

Each was checked on this machine.

- **Who uses the store.** Code and tests import `Store` (33 files), `open_store` (28), `Verdict` (14), `SyncState` (4), `Post` (3), `StoredTriage`, `Problem`, `Answer` (2 each), and `StoredMessage`, `StoreError`, `Alert` (1 each), all from `mailroom.store`. No test imports a private name or patches anything inside the store. The only reference to the path `store.py` outside `docs/` was `scripts/critical_modules.txt`, which is a given edit.
- **Imports.** `store.py` imports `clock`, `ids`, `config` (`Settings`, `prepare_data_dir`), `record` (`Record`), `extractor` (`Extraction`, `Deadline`) and `schema` (`MIGRATIONS`). `rules.py`, `triage.py` and the Discord modules import the store. Moving the code into a package changes none of these directions.
- **Writes today.** `store.py` calls `self._connection.commit()` 13 times, once at the end of each write method. Python's `sqlite3`, in its default mode, opens a transaction (`BEGIN`) before the first insert, update or delete, and nothing ends it but `commit()`, `rollback()` or `close()`. So an exception between the first write and the `commit()` leaves the transaction open. The connection then holds the file's write lock until it is closed.
- **Failures you can reach.** `queue_notified` calls `ids.new_id()` once per row it inserts, so an id function that fails on its second call stops it after one insert. `save_triage` with an outcome the schema refuses raises `sqlite3.IntegrityError` from the `CHECK`. With today's code, both leave the transaction open. The first also leaves its own uncommitted post visible to that store, and the second shows as a held lock. `clear_expired_text` runs two statements, so a failure in the second would keep the first.
- **Rolling back.** `sqlite3.Connection` used as a context manager (`with connection:`) commits when the block ends normally and rolls back when it raises. It does not close the connection. A `contextlib.contextmanager` that commits, or rolls back and re-raises, does the same.
- **Seeing a held lock.** A second connection opened with `timeout=0, isolation_level=None` that runs `BEGIN IMMEDIATE` fails at once with `sqlite3.OperationalError` while another connection holds the write lock. The given rollback tests use this, so a regression fails fast, not after 5 seconds.
- **Migrations.** `_migrate` runs each migration with `executescript` and its own `BEGIN` and `COMMIT`. That stays as it is.

## Owner's decisions

- The store becomes a package with one module per area, and `Store`'s API is unchanged. Every import and call such as `store.queue_alert(...)` stays as it is.
- Rollback on a failed write is done in this split (deferred from Phase 1o).
- Unanswered-item follow-ups move to stage 6, with digests.

## Architect's decisions

- **Seven modules.** The areas are `base`, `messages`, `sync`, `senders`, `triage`, `posts` (posts and answers) and `alerts` (problems and alerts). `__init__.py` holds `Store` and `open_store` and re-exports every public name. The given test pins which module defines each method, class and constant.
- **`Store` from mixins.** `base.py` defines `StoreBase`, which holds the connection, the migration, `close`, `__enter__`, `__exit__`, `_write()`, and the shared helpers `_stamp` and `_read_time`. Each area module defines one class that subclasses `StoreBase`: `MessageStore`, `SyncStore`, `SenderStore`, `TriageStore`, `PostStore` and `AlertStore`. Then `class Store(MessageStore, SyncStore, SenderStore, TriageStore, PostStore, AlertStore)` lives in `__init__.py`. Later stages add an area module and one base class.
- **One place commits.** `_write()` is the only code that calls `commit()` or `rollback()`. Every write method runs all its statements inside one `with self._write():` block. Reads open no transaction and stay as they are.
- **Code moves as it is.** SQL text, row readers and validation move unchanged into the module of the area that uses them. `clear_expired_text` stays one method in `messages.py`, even though it also clears the triage text.
- **A size check.** No module in the package is over 200 lines, so the split can't put everything in one module again.

## Requirements

1. **The package.** `src/mailroom/store.py` is gone. `src/mailroom/store/` has `__init__.py`, `base.py`, `messages.py`, `sync.py`, `senders.py`, `triage.py`, `posts.py` and `alerts.py`. Each public method, class and constant is defined in the module the given test names. `mailroom.store` still exports every name it exports today, and `Store` has exactly today's public methods.
2. **`StoreBase`** in `base.py` holds `__init__(path)` (connect, `secure_delete`, `chmod 0o600`, migrate), `_migrate`, `close`, `__enter__`, `__exit__`, `_write()`, `_stamp`, `_read_time`, `StoreError`, `DB_FILENAME` and `SCHEMA_MESSAGE`.
3. **The area classes** `MessageStore`, `SyncStore`, `SenderStore`, `TriageStore`, `PostStore` and `AlertStore` each subclass `StoreBase`. `Store` in `__init__.py` subclasses all six in that order and adds nothing. `open_store(settings)` stays in `__init__.py`, unchanged.
4. **`_write()`** is a context manager. When the block ends normally it commits. When the block raises anything, it rolls back and re-raises the same exception. `commit()` and `rollback()` appear nowhere else in the package.
5. **Every write method** (`add`, `clear_expired_text`, `save_sync_state`, `set_sender_status`, `save_triage`, `queue_notified`, `mark_posted`, `record_answer`, `open_problem`, `mark_alerted`, `close_problem`, `queue_alert`, `mark_alert_posted`) runs all its statements in one `with self._write():` block. A call that raises leaves every table as it was and holds no lock. Return values and every other behaviour are unchanged.
6. **The critical list** names the package's eight files (given edit to `scripts/critical_modules.txt`), and each is fully covered.
7. **Progress entry** for `## Phase 2a: Store package (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/unit/test_store_package.py` | The area modules exist; `Store` keeps exactly its public methods; each method (26 rows), class and constant (14 rows) is defined in its area and still exported by `mailroom.store` |
| `tests/integration/test_store_rollback.py` | A write that fails halfway (`queue_notified` with ids running out) keeps none of its rows; a write the schema refuses releases the file; a good write is committed at once |
| `scripts/critical_modules.txt` | Edited: `store.py` replaced by the package's eight files |
| `docs/verification/probe-02a.py` | The verifier's probe |

Given test count: **45**.

## Tests to write

The given tests cover every requirement's main cases, and the 685 earlier tests cover the moved behaviour unchanged. To reach full coverage of each new file (the rollback branch of `_write()` included), add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store.py` | deleted |
| `src/mailroom/store/*.py` | the eight new modules |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Any change to a method's signature, SQL, return value or validation, or to a data class.
- Per-area objects such as `store.posts.queue(...)`, or any change to a caller in `src`.
- A schema change or a migration.
- A busy timeout, `BEGIN IMMEDIATE`, WAL mode, or any other change to how SQLite is opened.
- Retrying a failed write.
- Checkpoint 2, combined approval, deadlines, the tasks app, or follow-ups.
- Any change to a given or earlier test, `AGENTS.md` or the design docs.

## Rules that bite

- **Email text cleared after 24 hours.** `clear_expired_text` keeps its two statements and their order, now committed together. The given and earlier retention tests must pass unchanged.
- **The data file stays private.** `chmod 0o600` and `PRAGMA secure_delete = ON` move with `__init__`, unchanged.
- **Error messages stay constants.** `SCHEMA_MESSAGE`, `SENDER_MESSAGE` and `STATUS_MESSAGE` move unchanged. A rolled-back error is re-raised as it was, never wrapped or reworded.
- **Time and ids through the modules**: `clock.now()` and `ids.new_id()` called through the module, never `from mailroom.clock import now`. The rollback test replaces `ids.new_id`.
- **Same clock reads.** Earlier tests (`fixed_times`) hand out one time per `clock.now()` call, in order. Each method keeps exactly the clock reads it makes today, in the same order.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 45 = 730 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_store_package.py tests/integration/test_store_rollback.py --no-cov -q` | `45 passed` |
| `.venv/bin/python -m coverage report --include='src/mailroom/store/*' --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `test ! -e src/mailroom/store.py && echo gone` | `gone` |
| `for f in src/mailroom/store/*.py; do [ $(wc -l < $f) -gt 200 ] && echo $f; done` | no output |
| `grep -c "^## Phase 2a: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 2a` | `Reports OK.` |
| `git diff HEAD --stat -- tests/unit/test_store_package.py tests/integration/test_store_rollback.py scripts/critical_modules.txt docs/verification/probe-02a.py` | no output |
| `git diff HEAD --stat -- tests src ':!src/mailroom/store.py'` | no output: no earlier test or other module changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '\.commit\(\)|\.rollback\(\)' -- src/mailroom/store ':!src/mailroom/store/base.py'
git grep --untracked -n -E 'sqlite3\.connect|executescript|PRAGMA' -- src/mailroom/store ':!src/mailroom/store/base.py'
git grep --untracked -n -E 'isolation_level|BEGIN IMMEDIATE|timeout=|journal_mode|busy_timeout' -- src/mailroom/store
git grep --untracked -n -E 'except[^:]*:[[:space:]]*(pass|return|continue)' -- src/mailroom/store
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|httpx|aiohttp|asyncio|subprocess|multiprocessing|concurrent)([^A-Za-z_]|$)' -- src/mailroom/store
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src/mailroom/store
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid|from mailroom\.(clock|ids) import' -- src/mailroom/store
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/store
```
