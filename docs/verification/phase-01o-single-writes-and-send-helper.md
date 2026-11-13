# Verification guide: Phase 1o (Single writes and send helper)

Spec: `docs/phases/phase-01o-single-writes-and-send-helper.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `.venv/bin/python -c "from mailroom.discord_post import send_messages"` exits 0
- `grep -c "^## Phase 1o: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01o-single-writes-and-send-helper.md tests/integration/test_send_messages.py tests/integration/test_store_races.py docs/verification/probe-01o.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 11.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 11 = 685 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_send_messages.py tests/integration/test_store_races.py --no-cov -q` | `11 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/store.py,src/mailroom/discord_post.py,src/mailroom/alerts.py,src/mailroom/service.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `git grep -c 'waiting (' -- src/mailroom/service.py` | `src/mailroom/service.py:1` |
| G5 | `grep -c "^## Phase 1o: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 1o` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- tests/integration/test_send_messages.py tests/integration/test_store_races.py docs/verification/probe-01o.py` | no output |
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
| S1 | `store.py` | `open_problem`'s insert loses `ON CONFLICT (key) DO NOTHING` | `tests/integration/test_store_races.py::test_opening_a_problem_another_store_just_opened_returns_theirs` | `Problem` with `since` THEIRS | `IntegrityError` |
| S2 | `store.py` | `queue_alert`'s insert loses `ON CONFLICT (key) DO NOTHING` | `tests/integration/test_store_races.py::test_queueing_an_alert_another_store_just_queued_keeps_theirs` | `False` | `IntegrityError` |
| S3 | `store.py` | `queue_alert` returns `True` whatever the row count | `tests/integration/test_store_races.py::test_queueing_an_alert_another_store_just_queued_keeps_theirs` | `False` | `True` |
| S4 | `store.py` | `close_problem` calls `found = self.problem(key)` before its delete | `tests/integration/test_store_races.py::test_closing_a_problem_is_one_statement_and_happens_once` | the `Problem` | `AssertionError` from `read_first` |
| S5 | `discord_post.py` | `send_messages` builds every body before the first send | `tests/integration/test_send_messages.py::test_a_failure_stops_at_that_item_and_builds_nothing_after_it[server-error]` | built `['first', 'second']` | `['first', 'second', 'third']` |
| S6 | `discord_post.py` | `send_messages` reads the token before checking whether anything is pending | `tests/integration/test_send_messages.py::test_nothing_to_send_reads_no_token_and_sends_nothing` | keychain calls `[]` | `[('mailroom', 'discord.bot-token')]` |
| S7 | `discord_post.py` | a stop reports `waiting` as `len(pending) - index - 1` | `tests/integration/test_send_messages.py::test_a_failure_stops_at_that_item_and_builds_nothing_after_it[server-error]` | `waiting=2` | `waiting=1` |
| S8 | `alerts.py` | `post_alerts` builds the ping body for every alert | `tests/integration/test_alert_post.py::test_alerts_are_posted_in_order_and_only_action_alerts_ping` | second content `'Gmail personal caught up.'` | `'<@444444444444444444> Gmail personal caught up.'` |
| S9 | `alerts.py` | `post_alerts`' mark does nothing | `tests/integration/test_alert_post.py::test_alerts_are_posted_in_order_and_only_action_alerts_ping` | `pending_alerts()` `()` | two alerts |
| S10 | `service.py` | the status helper catches only `DiscordUnavailable` | `tests/integration/test_service.py::test_a_missing_bot_token_is_reported_and_posting_waits` | `'discord posting: secret not found: discord.bot-token'` | `SecretMissing` raised |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01o.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

Beyond the given tests, it checks three things. With SQLite's trace on, each problem and alert write runs one write statement and no read of its table before it. Two stores race at random over many turns against a model built from the turns alone. And `send_messages` runs repeated rounds through random Discord failures, lost replies included, until each item is marked once with Discord's id. The probe reads `store._connection` to trace the SQL; that is the probe's business, not a finding against the code.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | `alerts.py` sends only through the helper | `git grep --untracked -n -E 'http\.post\(\|keychain\|Bot \{\|def _message_id\|TransportError' -- src/mailroom/alerts.py` |
| Q2 | One reader of Discord's message id | `git grep --untracked -n -E 'def _message_id\|\.json\(\)\["id"\]' -- src ':!src/mailroom/discord_post.py'` |
| Q3 | Bot headers only in `discord_post.py` and `commands.py` | `git grep --untracked -n -E 'Bot \{token\}' -- src ':!src/mailroom/discord_post.py' ':!src/mailroom/commands.py'` |
| Q4 | No waiting or retry loop in the senders | `git grep --untracked -n -E 'sleep\(\|retry_after\|while ' -- src/mailroom/discord_post.py src/mailroom/alerts.py` |
| Q5 | No rollback, busy timeout or blanket ignore in this phase | `git grep --untracked -n -E 'OR IGNORE\|BEGIN IMMEDIATE\|isolation_level\|with self\._connection' -- src/mailroom/store.py` |
| Q6 | No new network or concurrency imports | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|asyncio\|subprocess\|multiprocessing\|concurrent\|discord)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request' -- src` |
| Q7 | No logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q8 | Time and ids through the modules | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q9 | No coverage or lint exemptions in the touched modules | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/store.py src/mailroom/discord_post.py src/mailroom/alerts.py src/mailroom/service.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `send_messages` declared with PEP 695 syntax (`def send_messages[T](...)`) or a `TypeVar`.
- `open_problem` reading the row back with `self.problem(key)` or its own `SELECT` after the insert (never before it).
- `post_pending`'s body and mark as lambdas, nested functions, or private module functions.
- The status helper taking the call as a callable, or taking the report and the error separately.
- Today's text of the status lines kept by an f-string or by concatenation.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01o-single-writes-and-send-helper.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1o`), then run `.venv/bin/python scripts/check_reports.py --phase 1o`; it must print `Reports OK.`
