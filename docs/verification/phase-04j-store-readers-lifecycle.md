# Verification guide: Phase 4j (Stabilize store readers and lifecycle)

Spec: `docs/phases/phase-04j-store-readers-lifecycle.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh
session. Everything is synthetic and runs on temporary database files. Never access
real mail, Discord, the model, the tasks app, the Keychain or the data folder.

## 1. Coder ran

Before the gates, inspect status, the tracked diff and untracked files. Require one
`## Phase 4j: ` progress entry and implementation changes in `src/mailroom/store/`
(`base.py`, `posts.py`, `tasks.py`, `approvals.py`, `messages.py`, `triage.py`). A
stopped entry is not a completed implementation. If the coder did not run or
stopped, report that, without treating every missing behavior as a new defect.

Require these to be committed: the spec, this guide, the two new given test files and
the probe. Record the full planning-baseline commit and verify their bytes match it
(G7). A dirty planning tree must not be called a coder diff. Do not waive this gate or
commit.

The only permitted implementation paths are the spec's Scope. Your report adds only
`docs/reviews/phase-04j-store-readers-lifecycle.md`.

## 2. Gates

Run them in order from the repository root. G2 reads G1's coverage data before any
other test run. 29 given cases are new, so the minimum suite is 1488 + 29.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | All checks passed.; tests (core) passed; at least 1517 passed, 0 failed/skipped/xfailed, no warnings; all Sections rows have 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='src/mailroom/store/*' --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_store_projections.py tests/unit/test_store_lifecycle.py --no-cov -q` | 29 passed |
| G4 | `.venv/bin/python docs/verification/probe-04j.py` | check lines end ok; final FAILURES 0 |
| G5 | `grep -c '^## Phase 4j: ' docs/progress.md` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4j` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04j-store-readers-lifecycle.md docs/verification/phase-04j-store-readers-lifecycle.md tests/integration/test_store_projections.py tests/unit/test_store_lifecycle.py docs/verification/probe-04j.py` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope, plus this review if already written |

Run G3 two more times; every run must show 29 passed. The tests use no threads or
real timing, so any failure is a finding.

Inspect the full diff for:

- unlisted changes to earlier tests;
- dependencies;
- coverage exclusions;
- new logging or output;
- a changed FROM, JOIN, WHERE, ORDER BY or LIMIT text, or any changed write SQL;
- a method moved between modules, a public name added to `mailroom.store`, or a
  change to `StoreBase.__init__` beyond the guard;
- a positional fallback, or a caught `KeyError` standing in for a missing column;
- a row value in a `StoreError` or `TypeError` message;
- weak assertions in the coder's tests, and whether they pin one connection and one
  migration run per open.

## Requirement checks

Test prefixes: PJ is `tests/integration/test_store_projections.py::`, LC is
`tests/unit/test_store_lifecycle.py::`.

| Requirement | Deciding evidence |
|---|---|
| 1: projections | every PJ test (each reads its constant by name); source review of the six tuples against the spec's table; `messages._SELECT` gone |
| 2: constants used at call time | PJ test_a_duplicate_column_in_a_projection_is_refused_by_name, all 11 readers; probe duplicate-accepted |
| 3: read by name | PJ test_posts_read_back_as_literal_records, test_tasks_..., test_links_..., test_approvals_..., test_messages_..., test_triage_reads_back_as_literal_records, each as written and reversed; PJ test_cleared_text_reads_back_the_same_through_reversed_projections; probe *-shuffled; Q1, Q2 |
| 4: duplicate columns | PJ test_a_duplicate_column_in_a_projection_is_refused_by_name; probe duplicate-message |
| 5: one due reader and writer | LC test_the_due_columns_round_trip_through_one_reader_and_writer; LC test_approvals_share_the_triage_due_reader_and_writer; Q3 |
| 6: constructor guard | LC test_defining_a_store_constructor_is_refused_at_definition (StoreBase, PostStore, Store); probe constructor line; Q4 |
| 7: lifecycle and compatibility | probe lifecycle line; the coder's lifecycle test; `tests/integration/test_store_rollback.py`; `tests/unit/test_store_package.py`; full suite; Q5; source review |
| 8: progress | G5/G6 and the entry's factual contents |

## 3. Spot checks

Run spot checks only in disposable scratch copies of the current implementation and
tests.

- Use the existing venv and `PYTHONPATH=src:.`, and confirm `mailroom.__file__` is
  inside the copy.
- Set `PYTHONDONTWRITEBYTECODE=1` and remove the copy's `__pycache__` folders first.
  Two same-size mutations written within one second can otherwise run stale bytecode.
- Never mutate the implementation under review.
- Start each row from the original bytes and run the deciding test with `--no-cov`.
  Then discard only your mutation and compare bytes.
- If private helpers differ, locate the equivalent code; do not prescribe helper
  names. "Duplicate check" is the shared named-row helper, wherever the coder put it.

| # | Function/boundary | One-line mutation | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | duplicate check | Never refuse a duplicate column | PJ test_a_duplicate_column_in_a_projection_is_refused_by_name | StoreError | a record |
| S2 | duplicate message | Leave the column name out of the message | PJ test_a_duplicate_column_in_a_projection_is_refused_by_name | duplicate stored column: provider | duplicate stored column |
| S3 | pending_posts | Select a fixed column list instead of POST_COLUMNS | PJ test_a_duplicate_column_in_a_projection_is_refused_by_name[posts-pending_posts] | StoreError | records |
| S4 | approved_in_thread | Select a fixed column list instead of APPROVAL_COLUMNS | PJ test_a_duplicate_column_in_a_projection_is_refused_by_name[approvals-approved_in_thread] | StoreError | an approval |
| S5 | triage | Read trusted by position | PJ test_triage_reads_back_as_literal_records[reversed] | same verdicts | trusted from another column |
| S6 | get | Read sent_at by position | PJ test_messages_read_back_as_literal_records[reversed] | same records | error or wrong sent_at |
| S7 | post reader | Read card from follows | PJ test_posts_read_back_as_literal_records[as written] | card followup | card is an item id |
| S8 | link reader | Drop the task id of a link | PJ test_links_read_back_as_literal_records[as written] | task-1 | None |
| S9 | read_due | Drop the due time | LC test_the_due_columns_round_trip_through_one_reader_and_writer | 17:00 | no time |
| S10 | due_columns | Write seconds in the due time | LC test_the_due_columns_round_trip_through_one_reader_and_writer | 17:00 | 17:00:00 |
| S11 | shared due reader | Keep a private due reader in approvals | LC test_approvals_share_the_triage_due_reader_and_writer | no _read_due | _read_due present |
| S12 | constructor guard | Accept a constructor | LC test_defining_a_store_constructor_is_refused_at_definition[StoreBase] | TypeError | class defined |
| S13 | constructor guard | Guard only direct subclasses of StoreBase | LC test_defining_a_store_constructor_is_refused_at_definition[Store] | TypeError | class defined |
| S14 | constructor message | Name the qualified class | LC test_defining_a_store_constructor_is_refused_at_definition[PostStore] | ...: Extra | ...: test_...<locals>.Extra |
| S15 | triage | Read dated from notify | PJ test_triage_reads_back_as_literal_records[as written] | dated False for m2 | dated True |
| S16 | get | Keep cleared text as an empty marker | PJ test_cleared_text_reads_back_the_same_through_reversed_projections | LATER | None |
| S17 | StoreBase.__init__ | Open and close a second connection before the real one | the coder's lifecycle test, and G4's lifecycle line | 1 connect | lifecycle:2x13 |

These mutations were run against a throwaway scratch stand-in at planning time, not
against the coder's code. A different failure needs diagnosis, and a passing
mutation may mean a weak test rather than a product defect. Report the difference.
S17 had no given test at planning time; if the coder's tests do not catch it, report
the missing lifecycle test as a finding against "Tests to write" even when the probe
catches it.

## 4. Probe

`.venv/bin/python docs/verification/probe-04j.py --oracle-only` checks the trial
corpus alone:

- 40 seeded chains of 2 to 5 emails each;
- every due kind (none, date only, date and time) on triage and on approvals;
- every answer (none, approve, change, nodeadline, drop), and some follow-up links;
- trials with and without cleared text;
- every follow-up targets an email with a task.

The normal probe writes each chain through the public store and builds the expected
records from the chain plan itself, not from store code. It then checks:

- that `open_store` connects once and runs every migration on a new file, and connects
  once and runs none on reopen;
- that a constructor is refused, with the exact message, in a subclass of `StoreBase`,
  `Store` and every area, while a plain subclass is accepted;
- every reader in scope, as written and through 3 seeded shuffles of all six
  projections at once, against the oracle: pending and single posts, tasks, links,
  approvals, `approved_in_thread`, messages and triage;
- a seeded repeated column in each projection, refused with the exact message by every
  reader of it.

It does not check module layout or class names other than its own; the given tests
do. It reports failure names and counts, never payloads, and always reaches
`FAILURES N`. Never edit the probe; an oracle self-check failure belongs to the
architect.

## 5. Searches

Each prints nothing; grep exit 1 is no match, exit above 1 is an error.

| # | Rule | Command |
|---|---|---|
| Q1 | No positional row unpacking in the readers in scope | `git grep --untracked -n -E '^ +([a-z_]+, ){4,}[a-z_]+ = row$\|^ +\) = row$\|row\[[1-9]' -- src/mailroom/store/posts.py src/mailroom/store/tasks.py src/mailroom/store/approvals.py src/mailroom/store/messages.py src/mailroom/store/triage.py` |
| Q2 | No column list written out instead of its constant | `git grep --untracked -n -E 'SELECT (item_id, provider, message_id, queued_at\|outcome, trusted\|provider, message_id, thread_id\|links\.item_id, links\.provider\|(approvals\.)?item_id, (approvals\.)?outcome)' -- src/mailroom/store` |
| Q3 | One due reader and writer, in triage.py | `git grep --untracked -n -E 'def _?(read_due\|due_columns)\(\|strftime\("%H:%M"\)\|fromisoformat\(deadline_time\)' -- src/mailroom/store ':!src/mailroom/store/triage.py'` |
| Q4 | Only StoreBase defines a constructor | `git grep --untracked -n -E 'def __init__\(' -- src/mailroom/store ':!src/mailroom/store/base.py'` |
| Q5 | No hidden fallbacks, row factories or time and id shortcuts | `git grep --untracked -n -E 'except (KeyError\|IndexError\|LookupError\|Exception)[ :]\|except \(\|suppress\(\|pragma: no cover\|noqa\|row_factory\|sqlite3\.Row\|datetime\.now\|date\.today\|from mailroom\.(clock\|ids) import' -- src/mailroom/store` |

Escaped pipes in the table stand for ordinary alternation pipes. Q1 and Q2 are
text-based. Source review also checks that no reader maps a field by position under
another spelling, such as `zip` with a fixed name list or `tuple(row)`.

## 6. Reasonable variations

- A shared helper returning one dict per row, or a small mapping object, as long as
  fields are looked up by name and the duplicate check runs first.
- Reading `cursor.description` once per call, and a separate one-row helper.
- Building the SELECT text with `", ".join(...)` inside the reader or inside the
  helper.
- Keeping the SQL tails as triple-quoted strings or one-line strings with the same
  clauses.
- Private helpers inside the Scope modules, and extra behavior tests in the coder's
  test file.

Not variations:

- a projection copied into import-time SQL, a default argument or a class attribute;
- reading any field of an in-scope reader by position, or falling back to a position;
- `sqlite3.Row` or a `row_factory`;
- a due copy left in approvals, or an inline due format in `save_triage`;
- a guard that also refuses subclasses which inherit `StoreBase.__init__`, or a
  changed `StoreBase.__init__`;
- a new public store method, a moved method, or a changed schema or write statement.

## 7. Verdict

Write `docs/reviews/phase-04j-store-readers-lifecycle.md`, starting
`# Review: Phase 4j`, with the exact conventions-format head and findings. Include:

- gate and Sections output;
- coverage;
- the repeated G3 runs;
- searches;
- probe results;
- spot-check results.

Classify each defect as requirement, observed result and required result. Do not
repair code or tests. Run G6 after writing it.

## Handoff prompts

Only after the final planning documents and given files are committed and the
coder's checkout is clean:

> Use $phase-coder to implement only Phase 4j from
> docs/phases/phase-04j-store-readers-lifecycle.md in this checkout. Read the required
> project docs and every given test. Run Start and all Acceptance commands;
> append progress. Do not read the verification guide or write a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4j against
> docs/phases/phase-04j-store-readers-lifecycle.md and
> docs/verification/phase-04j-store-readers-lifecycle.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probe, searches and
> scratch-only spot checks; write only docs/reviews/phase-04j-store-readers-lifecycle.md.
