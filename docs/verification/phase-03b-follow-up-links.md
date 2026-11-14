# Verification guide: Phase 3b (Follow-up links)

Spec: `docs/phases/phase-03b-follow-up-links.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:


- `grep -c "^## Phase 3b: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-03b-follow-up-links.md src/mailroom/schema.py tests/fakes.py tests/integration/test_store_links.py tests/unit/test_link_payload.py tests/integration/test_send_links.py tests/integration/test_service_links.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py tests/integration/test_store_followup.py docs/verification/probe-03b.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 152.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 39 = 1090 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_store_links.py tests/unit/test_link_payload.py tests/integration/test_send_links.py tests/integration/test_service_links.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py tests/integration/test_store_followup.py --no-cov -q` | `152 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/store/tasks.py,src/mailroom/store/__init__.py,src/mailroom/tasks_app.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `.venv/bin/python docs/verification/probe-03b.py` | last line `FAILURES 0` |
| G5 | `grep -c "^## Phase 3b: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 3b` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- src/mailroom/schema.py tests/fakes.py tests/integration/test_store_links.py tests/unit/test_link_payload.py tests/integration/test_send_links.py tests/integration/test_service_links.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py tests/integration/test_store_followup.py docs/verification/probe-03b.py` | no output |
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
| S1 | `tasks_app.py` | Accept any reply id of 1 to 100 characters (no `is_task_id`). The task is then marked `'a.b'`, its link goes to `/tasks/a.b/links`, and the fake, which never made that task, answers 404 | `tests/integration/test_send_links.py::test_a_task_id_that_cannot_name_a_path_is_not_accepted[a.b]` | `PostReport(posted=0, waiting=1, stopped='response')` | `PostReport(posted=1, waiting=1, stopped='404')` |
| S2 | `tasks_app.py` | Match the id with `[\w-]{1,100}` | `tests/unit/test_link_payload.py::test_a_task_id_is_ascii_letters_digits_dash_and_underscore[accent]` | `False` | `True` |
| S3 | `store/tasks.py` | Drop "its task has an id" from `pending_links` | `tests/integration/test_store_links.py::test_a_link_waits_until_its_task_has_an_id` | `()` | a `Link` with `task_id=None` |
| S4 | `store/tasks.py` | Drop `answer = 'link'` from `queue_linked` | `tests/integration/test_store_links.py::test_other_answers_on_a_follow_up_are_not_queued` | `0` | `2` |
| S5 | `tasks_app.py` | Key the link with the followed email's provider and message id | `tests/integration/test_send_links.py::test_a_follow_up_added_to_a_task_is_sent_to_it_once` | `'gmail:m2'` | `'gmail:m1'` |
| S6 | `tasks_app.py` | Build the link's `link` from the followed email's record | `tests/integration/test_send_links.py::test_a_follow_up_added_to_a_task_is_sent_to_it_once` | `'https://mail.google.com/mail/#all/m2'` | the m1 link |
| S7 | `store/tasks.py` | Drop "still unsent" from `mark_link_sent` | `tests/integration/test_store_links.py::test_a_sent_link_leaves_the_queue` | `False` | `True` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-03b.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks what the given tests don't reach. Over random threads, answers and app failures across many rounds, before and after the text is cleared, the app must end with exactly one task per approved email and one link per follow-up added to a task. Each link must be on its followed task's id, and each key must carry one body on every attempt. No link may be sent before its task has an id: the fake would answer 404, and the probe never injects one.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Email text in a task or link | `git grep --untracked -n -E 'body_text\|summary\|subject\|quote\|confidence\|extraction\|sender' -- src/mailroom/tasks_app.py src/mailroom/store/tasks.py` |
| Q2 | A key made fresh per send | `git grep --untracked -n -E 'new_id\|uuid\|ids\.' -- src/mailroom/tasks_app.py src/mailroom/store/tasks.py` |
| Q3 | An id check that lets through non-ASCII, or quoting in place of the check | `git grep --untracked -n -E '\\w\|isalnum\|isalpha\|isdigit\|quote\(' -- src/mailroom/tasks_app.py` |
| Q4 | A hardcoded address, or a client that follows redirects or reads proxies | `git grep --untracked -n -E '"https?://\|follow_redirects=True\|trust_env=True' -- src/mailroom/tasks_app.py` |
| Q5 | A reply's body or an exception's text echoed | `git grep --untracked -n -E 'response\.text\|str\((error\|exc\|e)\)\|\{(error\|exc\|e)(!r)?\}' -- src/mailroom/tasks_app.py` |
| Q6 | Sending from the listener thread | `git grep --untracked -n -E 'send_tasks\|queue_linked\|/links' -- src/mailroom/interactions.py src/mailroom/gateway.py` |
| Q7 | Time or ids read around the seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q8 | Logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q9 | Coverage or lint switched off | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/tasks_app.py src/mailroom/store` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- A second `is_task_id` check just before a link's path is built, as well as the one at acceptance. S1's broken value then differs, which is a note, not a finding.
- Building the link URL with `httpx.URL` or a joined path, as long as it is `<tasks_url>/tasks/<id>/links`.
- `queue_linked` with `INSERT … SELECT … ON CONFLICT DO NOTHING` or `NOT EXISTS`, in one statement.
- A private helper shared by the task and link loops, if the reports and stops are as Requirement 5 says.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-03b-follow-up-links.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 3b`), then run `.venv/bin/python scripts/check_reports.py --phase 3b`; it must print `Reports OK.`
