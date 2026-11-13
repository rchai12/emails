# Verification guide: Phase 2a (Store package)

Spec: `docs/phases/phase-02a-store-package.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/store/base.py` and the other seven package files exist
- `grep -c "^## Phase 2a: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-02a-store-package.md tests/unit/test_store_package.py tests/integration/test_store_rollback.py scripts/critical_modules.txt docs/verification/probe-02a.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 45.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 45 = 730 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_store_package.py tests/integration/test_store_rollback.py --no-cov -q` | `45 passed` |
| G3 | `.venv/bin/python -m coverage report --include='src/mailroom/store/*' --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `test ! -e src/mailroom/store.py && echo gone` | `gone` |
| G5 | `for f in src/mailroom/store/*.py; do [ $(wc -l < $f) -gt 200 ] && echo $f; done` | no output |
| G6 | `grep -c "^## Phase 2a: " docs/progress.md` | `1` |
| G7 | `.venv/bin/python scripts/check_reports.py --phase 2a` | `Reports OK.` |
| G8 | `git diff HEAD --stat -- tests/unit/test_store_package.py tests/integration/test_store_rollback.py scripts/critical_modules.txt docs/verification/probe-02a.py` | no output |
| G9 | `git diff HEAD --stat -- tests src ':!src/mailroom/store.py'` | no output: no earlier test or other module changed |
| G10 | `git status --short` | only the Scope paths |
| G11 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `store/base.py` | `_write()` commits whether or not the block raised (no rollback) | `tests/integration/test_store_rollback.py::test_a_write_that_fails_halfway_keeps_none_of_its_rows` | `pending_posts()` `()` | one `Post` |
| S2 | `store/posts.py` | `queue_notified` opens a separate `with self._write():` for each insert | `tests/integration/test_store_rollback.py::test_a_write_that_fails_halfway_keeps_none_of_its_rows` | `pending_posts()` `()` | one `Post` |
| S3 | `store/triage.py` | `save_triage` runs its insert outside `_write()` and calls `self._connection.commit()` after it | `tests/integration/test_store_rollback.py::test_a_write_the_database_refuses_releases_the_file` | `unlocked()` `True` | `False` |
| S4 | `store/base.py` | `_write()` rolls back but does not re-raise | `tests/integration/test_store_rollback.py::test_a_write_that_fails_halfway_keeps_none_of_its_rows` | `RuntimeError` raised | nothing raised |
| S5 | `store/base.py`, `store/messages.py` | `close` moved from `StoreBase` to `MessageStore` | `tests/unit/test_store_package.py::test_each_method_lives_in_its_area[close]` | `'mailroom.store.base'` | `'mailroom.store.messages'` |
| S6 | `store/__init__.py`, `store/triage.py` | `Verdict` defined in `__init__.py` and imported by `triage.py` | `tests/unit/test_store_package.py::test_each_name_is_defined_in_its_area_and_still_imported_from_the_store[Verdict]` | `'mailroom.store.triage'` | `'mailroom.store'` |
| S7 | `store/base.py` | add a public method `def connection(self): return self._connection` to `StoreBase` | `tests/unit/test_store_package.py::test_the_store_keeps_exactly_its_public_methods` | 26 names | 27, with `'connection'` |
| S8 | `store/messages.py` | `clear_expired_text` drops its second statement (the triage clear) | `tests/integration/test_store_triage.py::test_the_extraction_is_cleared_with_the_email_text` | `extraction=None` | the extraction kept |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-02a.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

Beyond the given tests, two stores take random turns over most write methods, with refused inputs and with `ids.new_id` or `clock.now` failing after a random number of calls. After every call, another connection must be able to take the write lock at once. After every failed call, all tables must read exactly as before, through a separate connection. And only the injected failure or the expected refusal may be raised. It asserts that it reached injected failures, refusals, and a `queue_notified` that failed after handing out an id.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Only `base.py` commits or rolls back | `git grep --untracked -n -E '\.commit\(\)\|\.rollback\(\)' -- src/mailroom/store ':!src/mailroom/store/base.py'` |
| Q2 | Only `base.py` opens or configures the connection | `git grep --untracked -n -E 'sqlite3\.connect\|executescript\|PRAGMA' -- src/mailroom/store ':!src/mailroom/store/base.py'` |
| Q3 | No change to how SQLite is opened or locked | `git grep --untracked -n -E 'isolation_level\|BEGIN IMMEDIATE\|timeout=\|journal_mode\|busy_timeout' -- src/mailroom/store` |
| Q4 | No swallowed exception | `git grep --untracked -n -E 'except[^:]*:[[:space:]]*(pass\|return\|continue)' -- src/mailroom/store` |
| Q5 | No network or concurrency imports | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|httpx\|aiohttp\|asyncio\|subprocess\|multiprocessing\|concurrent)([^A-Za-z_]\|$)' -- src/mailroom/store` |
| Q6 | No logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src/mailroom/store` |
| Q7 | Time and ids through the modules | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid\|from mailroom\.(clock\|ids) import' -- src/mailroom/store` |
| Q8 | No coverage or lint exemptions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/store` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `_write()` written as `@contextmanager` around `try`/`except BaseException`/`raise`, or as `with self._connection:` returned from a method, as long as `commit()` and `rollback()` appear only in `base.py`.
- Area classes that declare `_connection: sqlite3.Connection` (or import `StoreBase` only for typing), and an `__all__` in `__init__.py`.
- Private SQL constants and row readers kept in whichever area module uses them, and shared private helpers in `base.py`.
- A module docstring per area.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-02a-store-package.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 2a`), then run `.venv/bin/python scripts/check_reports.py --phase 2a`; it must print `Reports OK.`
