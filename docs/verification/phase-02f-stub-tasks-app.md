# Verification guide: Phase 2f (Stub tasks app)

Spec: `docs/phases/phase-02f-stub-tasks-app.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/tasks_app.py`
- `grep -c "^## Phase 2f: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-02f-stub-tasks-app.md src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py scripts/critical_modules.txt tests/unit/test_config_tasks.py tests/unit/test_task_payload.py tests/integration/test_store_tasks.py tests/integration/test_send_tasks.py tests/integration/test_service_tasks.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_service.py tests/integration/test_service_more.py tests/integration/test_service_alerts.py docs/verification/probe-02f.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 158.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 49 = 1010 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_config_tasks.py tests/unit/test_task_payload.py tests/integration/test_store_tasks.py tests/integration/test_send_tasks.py tests/integration/test_service_tasks.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_service.py tests/integration/test_service_more.py tests/integration/test_service_alerts.py --no-cov -q` | `158 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/tasks_app.py,src/mailroom/store/tasks.py,src/mailroom/store/__init__.py,src/mailroom/config.py,src/mailroom/alerts.py,src/mailroom/service.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `.venv/bin/python docs/verification/probe-02f.py` | last line `FAILURES 0` |
| G5 | `grep -c "^## Phase 2f: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 2f` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py scripts/critical_modules.txt tests/unit/test_config_tasks.py tests/unit/test_task_payload.py tests/integration/test_store_tasks.py tests/integration/test_send_tasks.py tests/integration/test_service_tasks.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_service.py tests/integration/test_service_more.py tests/integration/test_service_alerts.py docs/verification/probe-02f.py` | no output |
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
| S1 | `tasks_app.py` | Send without the `Idempotency-Key` header | `tests/integration/test_send_tasks.py::test_an_approved_task_is_sent_once_under_its_key` | `PostReport(posted=1, waiting=0, stopped='')` | `stopped='400'` |
| S2 | `tasks_app.py` | Accept any `id` the reply holds (no string or length check). The schema doesn't stop it: a STRICT `TEXT` column turns `7` into `'7'` | `tests/integration/test_send_tasks.py::test_a_failed_send_keeps_the_task_queued_for_the_next_round[id-not-text]` | `stopped='response'` | `posted=1` |
| S3 | `store/tasks.py` | Drop the `outcome != 'drop'` condition from `queue_approved` | `tests/integration/test_store_tasks.py::test_a_dropped_undecided_or_closed_item_is_not_queued` | `0` | `1` |
| S4 | `store/tasks.py` | Drop the "still unsent" condition from `mark_task_sent` | `tests/integration/test_store_tasks.py::test_a_sent_task_keeps_its_id_and_leaves_the_queue` | `False` | `True` |
| S5 | `tasks_app.py` | Write the deadline's time with `isoformat()` | `tests/unit/test_task_payload.py::test_the_payload_carries_only_the_approved_task_and_the_email_link[approve]` | `'17:00'` | `'17:00:00'` |
| S6 | `service.py` | Run the tasks step after Discord posting | `tests/integration/test_service.py::test_a_round_syncs_triages_and_posts` | third line `'tasks: ok'` | `'discord posting: ok'` |
| S7 | `service.py` | Track `TasksUnavailable` as failing | `tests/integration/test_service_tasks.py::test_without_a_tasks_app_address_the_round_says_so_and_never_alerts` | `[]` | `['Approved tasks have not reached …']` |
| S8 | `service.py` | Don't close the tasks client when the service stops | `tests/integration/test_service_tasks.py::test_the_service_opens_one_tasks_client_and_closes_it` | `True` | `False` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-02f.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks what the given tests don't reach. Over random decisions and random failures across many rounds, before and after the text is cleared, each approved email must make exactly one task, under its key, with the body the probe's own table gives. Every retry must send that same body, the store must hold the app's id, and no request may contain the email's subject or body.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | The payload or queue reads email text | `git grep --untracked -n -E 'body_text\|summary\|subject\|quote\|confidence\|extraction\|sender' -- src/mailroom/tasks_app.py src/mailroom/store/tasks.py` |
| Q2 | A key or id made fresh per send, not from provider and message id | `git grep --untracked -n -E 'new_id\|uuid\|ids\.' -- src/mailroom/tasks_app.py src/mailroom/store/tasks.py` |
| Q3 | A hardcoded tasks app address | `git grep --untracked -n -E '"https?://' -- src/mailroom/tasks_app.py` |
| Q4 | A client that follows redirects, reads proxy settings or skips TLS checks | `git grep --untracked -n -E 'follow_redirects=True\|trust_env=True\|verify=False' -- src` |
| Q5 | A reply's body or an exception's text echoed into an error or status | `git grep --untracked -n -E 'response\.text\|str\((error\|exc\|e)\)\|\{(error\|exc\|e)(!r)?\}' -- src/mailroom/tasks_app.py` |
| Q6 | Sending from the listener thread | `git grep --untracked -n -E 'tasks_app\|send_tasks\|queue_approved' -- src/mailroom/interactions.py src/mailroom/gateway.py` |
| Q7 | Time or ids read around the seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q8 | Logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q9 | Coverage or lint switched off | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/tasks_app.py src/mailroom/store src/mailroom/config.py src/mailroom/alerts.py src/mailroom/service.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `send_tasks` building the URL with `httpx.URL` or `urljoin`, as long as the request goes to `<tasks_url>/tasks`.
- A private dataclass or helper for reading the reply's id, or a shared reader with `discord_post._message_id` that keeps that module's behaviour.
- `queue_approved` written as `INSERT … SELECT … ON CONFLICT DO NOTHING` or with `NOT EXISTS`, if it is one statement in one `_write()`.
- Accepting any 2xx with a valid id, not only 200 and 201: a note, not a finding.
- `_status` extended to catch `TasksUnavailable`, or a separate small helper for the tasks part.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-02f-stub-tasks-app.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 2f`), then run `.venv/bin/python scripts/check_reports.py --phase 2f`; it must print `Reports OK.`
