# Verification guide: Phase 1n (Account ids and backups)

Spec: `docs/phases/phase-01n-account-ids-and-backups.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `.venv/bin/python -c "from mailroom.record import ACCOUNT_PATTERN, stored_id, account_of; from mailroom.config import BACKUP_VALUE, exclude_from_backup"` exits 0
- `grep -c "^## Phase 1n: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01n-account-ids-and-backups.md tests/unit/test_record_ids.py tests/unit/test_config_backup.py tests/unit/test_cli_run_backup.py tests/unit/test_checkpoint_account.py tests/integration/test_gmail_sync_accounts.py tests/integration/test_gmail_sync.py tests/integration/test_gmail_sync_more.py tests/integration/test_service.py docs/verification/probe-01n.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 72.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 37 = 674 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_record_ids.py tests/unit/test_config_backup.py tests/unit/test_cli_run_backup.py tests/unit/test_checkpoint_account.py tests/integration/test_gmail_sync_accounts.py tests/integration/test_gmail_sync.py tests/integration/test_gmail_sync_more.py tests/integration/test_service.py --no-cov -q` | `72 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/record.py,src/mailroom/config.py,src/mailroom/gmail.py,src/mailroom/gmail_sync.py,src/mailroom/checkpoint.py,src/mailroom/cli.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1n: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1n` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- tests/unit/test_record_ids.py tests/unit/test_config_backup.py tests/unit/test_cli_run_backup.py tests/unit/test_checkpoint_account.py tests/integration/test_gmail_sync_accounts.py tests/integration/test_gmail_sync.py tests/integration/test_gmail_sync_more.py tests/integration/test_service.py docs/verification/probe-01n.py` | no output |
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
| S1 | `gmail_sync.py` | the duplicate check looks up the bare Gmail id (`store.get("gmail", ref.id)`) | `tests/integration/test_gmail_sync_accounts.py::test_a_message_stored_for_one_account_is_skipped_only_there` | `fetched(personal) == ['m1']` | `['m1', 'm1']` |
| S2 | `gmail_sync.py` | the `Envelope` gets the bare thread id (`thread_id=message.thread_id`) | `tests/integration/test_gmail_sync.py::test_the_stored_record_comes_from_gmail_and_the_parser` | `thread_id` `'personal/t1'` | `'t1'` |
| S3 | `gmail_sync.py` | the link is built from the stored id instead of the bare Gmail id | `tests/integration/test_gmail_sync_accounts.py::test_two_accounts_keep_messages_that_share_a_gmail_id` | link ends `#all/m1` | ends `#all/personal/m1` |
| S4 | `checkpoint.py` | the footer's first part is the provider name alone | `tests/unit/test_checkpoint_account.py::test_the_footer_names_the_account_the_email_came_to[personal]` | `'Gmail personal · Verified sender'` | `'Gmail · Verified sender'` |
| S5 | `record.py` | `account_of` returns the text before the first `/` without checking `ACCOUNT_PATTERN` | `tests/unit/test_record_ids.py::test_the_account_is_read_back_from_a_stored_id[capital]` | `None` | `'Personal'` |
| S6 | `record.py` | `stored_id` skips the account check | `tests/unit/test_record_ids.py::test_a_stored_id_refuses_an_account_settings_would_refuse[slash]` | `ValueError` | no error |
| S7 | `config.py` | `prepare_data_dir` no longer calls `exclude_from_backup` | `tests/unit/test_config_backup.py::test_preparing_the_data_folder_excludes_it_from_backup` | the attribute is `BACKUP_VALUE` | `None` |
| S8 | `config.py` | `exclude_from_backup` ignores `setxattr`'s return value | `tests/unit/test_config_backup.py::test_a_folder_that_cannot_be_excluded_raises_the_fixed_message` | `ConfigError` | no error |
| S9 | `cli.py` | `run` catches only `ServiceError` again | `tests/unit/test_cli_run_backup.py::test_run_reports_a_data_folder_it_cannot_exclude_and_exits_1` | output `'could not exclude the data folder from Time Machine\n'` | output `''` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01n.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

Beyond the given tests, it checks three things. Thousands of random accounts round-trip through `stored_id` and `account_of`, and bad ones (each a valid name with one change) are refused. Two to four mailboxes share Gmail ids across repeated syncs, with every message stored once per account, ids, threads and links right, each fetched once, and the account in every footer. Folders with random names, `prepare_data_dir`'s included, carry `tmutil`'s exact attribute.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | No network, no subprocess, no `tmutil` or PyObjC in `src` | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|subprocess\|multiprocessing)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request\|os\.system\|os\.popen\|tmutil\|objc' -- src` |
| Q2 | One account pattern: only `record.py` holds it (today `config.py` and `gmail.py` match; the phase removes both) | `git grep --untracked -n -E 'a-z0-9-' -- src ':!src/mailroom/record.py'` |
| Q3 | Error messages are constants: no errno text | `git grep --untracked -n -E 'strerror\|get_errno\|errno\.' -- src` |
| Q4 | Error messages are constants: no f-string or library error in `config.py`'s raises | `git grep --untracked -n -E 'raise [A-Za-z]+\(f\|raise [A-Za-z]+\([a-z_.]*(folder\|path\|error)' -- src/mailroom/config.py` |
| Q5 | Read-only mail: no modify, trash, send, insert or label change | `git grep --untracked -n -E '/(modify\|trash\|untrash\|send\|batchModify\|batchDelete\|import\|insert)["/?]\|addLabelIds\|removeLabelIds' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py` |
| Q6 | No logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q7 | Time and ids through the modules | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q8 | No coverage or lint exemptions in the touched modules | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/record.py src/mailroom/config.py src/mailroom/gmail_sync.py src/mailroom/checkpoint.py src/mailroom/cli.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `account_of` written with `str.partition` or `split("/", 1)`, and `stored_id` with `re.fullmatch` or a compiled pattern.
- `exclude_from_backup` loading the C library once at import, or on each call, with `CDLL(None)` or `CDLL(ctypes.util.find_library("c"))`.
- `BACKUP_VALUE` written as a `bytes` literal or as `plistlib.dumps(...)` at import, as long as it equals the given test's value.
- `cli.run` catching `(service.ServiceError, ConfigError)` in one `except`, or in two.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01n-account-ids-and-backups.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1n`), then run `.venv/bin/python scripts/check_reports.py --phase 1n`; it must print `Reports OK.`
