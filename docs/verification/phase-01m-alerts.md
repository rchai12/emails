# Verification guide: Phase 1m (Alerts)

Spec: `docs/phases/phase-01m-alerts.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/alerts.py`
- `tests/integration/test_alerts_more.py`
- `grep -c "^## Phase 1m: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01m-alerts.md src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_alert_text.py tests/integration/test_alerts.py tests/integration/test_alert_post.py tests/integration/test_service_alerts.py tests/integration/test_service.py tests/integration/test_service_more.py tests/integration/test_store.py tests/integration/test_store_sync.py scripts/critical_modules.txt docs/verification/probe-01m.py docs/verification/probe-01l.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 23.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 23 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_alert_text.py tests/integration/test_alerts.py tests/integration/test_alert_post.py tests/integration/test_service_alerts.py tests/integration/test_service.py tests/integration/test_service_more.py --no-cov -q` | `40 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/alerts.py,src/mailroom/service.py,src/mailroom/store.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1m: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1m` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_alert_text.py tests/integration/test_alerts.py tests/integration/test_alert_post.py tests/integration/test_service_alerts.py tests/integration/test_service.py tests/integration/test_service_more.py tests/integration/test_store.py tests/integration/test_store_sync.py scripts/critical_modules.txt docs/verification/probe-01m.py docs/verification/probe-01l.py` | no output |
| G7 | `git status --short` | only the Scope paths |
| G8 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `alerts.py` | In `track`, ignore `wait` | `tests/integration/test_alerts.py::test_a_problem_alerts_once_after_it_has_lasted_long_enough` | `[]` at 14:59 | `[('down', False)]` |
| S2 | `alerts.py` | Announce a fix even when the problem was never announced | `tests/integration/test_alerts.py::test_a_fixed_problem_says_so_only_if_it_was_announced` | 2 alerts | 3 alerts |
| S3 | `alerts.py` | Use one key for the raised and resolved alerts | `tests/integration/test_alerts.py::test_a_fixed_problem_says_so_only_if_it_was_announced` | `('up', False)` queued | only `('down', False)` |
| S4 | `alerts.py` | Send pinging alerts with `allowed_mentions` `{"parse": []}` | `tests/integration/test_alert_post.py::test_alerts_are_posted_in_order_and_only_action_alerts_ping` | `{"users": ["444444444444444444"]}` | `{"parse": []}` |
| S5 | `alerts.py` | Always write "new emails" | `tests/unit/test_alert_text.py::test_the_catch_up_summary_reads_naturally[one-hour]` | `1 new email` | `1 new emails` |
| S6 | `service.py` | Track the model with `wait=timedelta(0)` | `tests/integration/test_service_alerts.py::test_an_unreachable_model_is_announced_after_15_minutes_and_its_return_too` | `[]` before minute 15 | the model alert already posted |
| S7 | `service.py` | Mark the listener fixed when the service starts, not before the second round | `tests/integration/test_service_alerts.py::test_a_listener_that_dies_at_once_is_never_called_running_again` | 1 alert | 3 alerts |
| S8 | `service.py` | Track the sign-in problem for every `GmailError` | `tests/integration/test_service_more.py::test_a_gmail_500_is_reported_and_the_round_goes_on` | 1 message | 2 messages |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01m.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks, beyond the given tests: 12 trials of 64 rounds, a minute apart, with mail arriving in two accounts while their tokens are revoked and restored at random, model outages of random length, and Discord 429s, 503s and lost replies. The alert messages that reach Discord must equal, in order and once each, the list an oracle builds from the schedule alone (sign-in alerts at once with a ping, "works again" on the next sync, the model alert only after 15 minutes of failed triage, "back" only after it was announced); none may hold email text, and none may be left unposted.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | No other network or concurrency library | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|asyncio\|multiprocessing\|concurrent\|discord)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request' -- src` |
| Q2 | Alerts and the service open no client of their own | `git grep --untracked -n -E 'httpx\.(Client\|get\|post\|put\|request\|stream)\(' -- src/mailroom/alerts.py src/mailroom/service.py` |
| Q3 | Discord's address only in the given layout | `git grep --untracked -n -E 'discord\.com\|discordapp' -- src ':!src/mailroom/discord_layout.py'` |
| Q4 | No email text in an alert | `git grep --untracked -n -E 'summary\|subject\|body_text\|sender_name\|record\.\|extraction' -- src/mailroom/alerts.py` |
| Q5 | Pings only the owner | `git grep --untracked -n -E '@everyone\|@here\|"roles"\|"parse": \["' -- src/mailroom/alerts.py` |
| Q6 | No sleeping or retry loop | `git grep --untracked -n -E 'sleep\(\|while \|retry_after' -- src/mailroom/alerts.py` |
| Q7 | No token or response text in an error | `git grep --untracked -n -E 'raise [A-Za-z]+\(f\|raise [A-Za-z]+\([a-z_.]*(token\|error\|value\|text\|json)' -- src/mailroom/alerts.py` |
| Q8 | No email text or token in logs | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q9 | Time and ids only through `clock` and `ids` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q10 | Full coverage is earned, not excused | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/alerts.py src/mailroom/service.py src/mailroom/store.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `track` reading the clock through `open_problem` and again for the comparison, as long as each comparison uses `clock.now()`.
- Building the alert body with a private helper shared with nothing else.
- The listener's `track` call inside the same `except` blocks that report its state.
- Checking the thread with `is_alive()` at the top of the loop, skipping the first pass.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01m-alerts.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1m`), then run `.venv/bin/python scripts/check_reports.py --phase 1m`; it must print `Reports OK.`
