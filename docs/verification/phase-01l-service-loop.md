# Verification guide: Phase 1l (Service loop)

Spec: `docs/phases/phase-01l-service-loop.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/service.py`
- `tests/integration/test_service_more.py`
- `grep -c "^## Phase 1l: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01l-service-loop.md tests/integration/test_service.py tests/unit/test_config_service.py tests/unit/test_cli_run.py scripts/critical_modules.txt docs/verification/probe-01l.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 22.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 22 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_service.py tests/unit/test_config_service.py tests/unit/test_cli_run.py --no-cov -q` | `22 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/service.py,src/mailroom/config.py,src/mailroom/cli.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1l: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1l` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- tests/integration/test_service.py tests/unit/test_config_service.py tests/unit/test_cli_run.py scripts/critical_modules.txt docs/verification/probe-01l.py` | no output |
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
| S1 | `service.py` | `Health.report` says every state, changed or not | `tests/integration/test_service.py::test_status_lines_are_said_only_when_a_part_changes` | `[]` | three lines |
| S2 | `service.py` | Put one `try` around the whole account loop | `tests/integration/test_service.py::test_one_broken_account_does_not_stop_the_others` | `gmail personal: ok` said | no `gmail personal` line |
| S3 | `service.py` | Carry on triaging after `ModelUnavailable` | `tests/integration/test_service.py::test_an_unreachable_model_leaves_mail_for_the_next_round` | one model request | `IndexError` (the fake has no second reply) |
| S4 | `service.py` | Report posting `ok` even when `stopped` is set | `tests/integration/test_service.py::test_a_discord_failure_leaves_posts_queued` | `discord posting: waiting (503)` | `discord posting: ok` |
| S5 | `service.py` | Skip `clear_expired_text` | `tests/integration/test_service.py::test_each_round_clears_text_older_than_a_day` | `text_cleared_at` set | `None` |
| S6 | `service.py` | Hand the listener the main thread's store | `tests/integration/test_service.py::test_the_service_polls_every_interval_and_listens_on_its_own_thread` | no `failed` line | `discord gateway: failed (ProgrammingError)` |
| S7 | `service.py` | Restart the listener each round after it stops | `tests/integration/test_service.py::test_a_stopped_gateway_is_reported_once_and_polling_goes_on` | `calls == [1]` | more than one call |
| S8 | `service.py` | Report an unexpected listener error with `str(error)` | `tests/integration/test_service.py::test_an_unexpected_gateway_error_names_only_its_type` | `failed (KeyError)` | the error's text, with `$42.00` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01l.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks, beyond the given tests: 8 trials of 46 rounds with mail arriving in two accounts while revoked and missing tokens, Gmail 500s, an unreachable model, and Discord 429s, 503s and lost replies come and go; after six clean rounds every delivered email is triaged, queued and posted exactly once, each part's status lines never repeat a state and end at `ok`, and no line holds email text or a secret.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | No other network or concurrency library | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|asyncio\|multiprocessing\|concurrent\|discord)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request' -- src` |
| Q2 | Threads only in the service and the CLI | `git grep --untracked -n -E '(import\|from) threading' -- src ':!src/mailroom/service.py' ':!src/mailroom/cli.py'` |
| Q3 | Signals only in the CLI | `git grep --untracked -n -E 'signal\.' -- src ':!src/mailroom/cli.py'` |
| Q4 | The service makes no network call of its own | `git grep --untracked -n -E 'httpx\.(Client\|get\|post\|put\|request\|stream)\(\|http\.(get\|post\|put\|request\|send\|stream)\(' -- src/mailroom/service.py` |
| Q5 | No sleeping, busy loop, bare except or hard exit | `git grep --untracked -n -E 'time\.sleep\|while True\|except:\|BaseException\|os\._exit\|sys\.exit' -- src/mailroom/service.py` |
| Q6 | No email text or secret handled by the service | `git grep --untracked -n -E 'summary\|subject\|body_text\|sender_name\|get_secret\|\.token' -- src/mailroom/service.py` |
| Q7 | No email text or token in logs | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q8 | Time and ids only through `clock` and `ids` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q9 | Full coverage is earned, not excused | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/service.py src/mailroom/config.py src/mailroom/cli.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `Health` keeping its last states in a dict under a lock, or any equivalent.
- Building the Gmail clients before or after opening the store.
- The listener's thread function as a closure or a private helper.
- Closing the clients in any order in the final block.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01l-service-loop.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1l`), then run `.venv/bin/python scripts/check_reports.py --phase 1l`; it must print `Reports OK.`
