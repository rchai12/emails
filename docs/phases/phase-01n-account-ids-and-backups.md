# Phase 1n: Account ids and backups

## Goal

Fix the first two findings of the [Phase 1 audit](../phase-01-audit.md). First, two Gmail accounts can no longer collide. Every stored message id and thread id is written `<account>/<Gmail id>`, so the same Gmail id in two mailboxes becomes two stored emails. The card's footer names the account the email came to (`Gmail personal`). Second, the data folder is excluded from Time Machine every time it is prepared, so no backup keeps email text past 24 hours. If the exclusion can't be set, the service refuses to start. The other audit fixes (single-statement inserts for problems and alerts, one shared Discord send helper) are Phase 1o.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 637, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_record_ids.py --ignore=tests/unit/test_config_backup.py --ignore=tests/unit/test_cli_run_backup.py --ignore=tests/unit/test_checkpoint_account.py --ignore=tests/integration/test_gmail_sync_accounts.py --ignore=tests/integration/test_gmail_sync.py --ignore=tests/integration/test_gmail_sync_more.py --ignore=tests/integration/test_service.py` must show `602 passed`. The first three ignored files import names you create. The other five expect stored ids written `<account>/<Gmail id>` or the account in the footer, so some of their tests fail until you build this phase.

## Facts

Each was checked on this machine.

- **What Time Machine reads.** `tmutil addexclusion <folder>` (the sticky form, with no `-p` and no root) writes one extended attribute on the folder: name `com.apple.metadata:com_apple_backup_excludeItem`, value the binary property list of the string `com.apple.backupd`. That value is exactly `plistlib.dumps("com.apple.backupd", fmt=plistlib.FMT_BINARY)`, 61 bytes. The attribute moves with the folder.
- **Setting it from Python.** `os.setxattr` does not exist in Python on macOS. The C library's `setxattr` does: `int setxattr(const char *path, const char *name, const void *value, size_t size, u_int32_t position, int options)`, reached as `ctypes.CDLL(None, use_errno=True).setxattr`. It returns `0` on success and `-1` on failure. A missing folder returns `-1` (errno `ENOENT`). Writing the attribute again replaces the old value. Pass the path as `os.fsencode(folder)` so names outside ASCII work. Nothing in `ctypes` logs.
- **Checking it.** `/usr/bin/xattr -px <name> <path>` prints the value in hex and exits 0, or exits 1 when the attribute is absent. The given tests read the attribute with it. `tmutil isexcluded` is no check here: everything under `/private/tmp` reports as excluded, whatever its attribute.
- **Account names never hold `/`.** Both `config._ACCOUNT` and `gmail._ACCOUNT` compile `[a-z][a-z0-9-]{0,31}`, and `GmailClient("Bad", ...)` raises before any sync. So the text before the first `/` of a stored id is always the account, even when a provider's own id holds a `/`.
- **Nothing downstream reads a Gmail id.** Only `gmail_sync.py` turns a stored id back into a Gmail call or link. Triage, posts, answers and alerts treat `message_id` as an opaque key. Item ids come from `ids.new_id()`, so Discord nonces are unchanged. `ID_LIMIT` is 1000, far above 33 + 1 + a Gmail id.
- **The card already falls back.** `checkpoint_message` builds the footer from `L.PROVIDER_NAMES[record.provider]`, then the sender's standing, then `Bulk mail`, joined by `L.FOOTER_JOIN` (`" · "`). `answered_message` reuses `checkpoint_message`'s embed, so it gets the same footer.

## Owner's decisions

- At least two Gmail accounts will be used. Stored message and thread ids are written `<account>/<provider id>`, and the card footer names the account (`Gmail personal`). This is in [Decisions](../decisions.md).
- The data folder is excluded from Time Machine by writing the attribute directly, not by running `tmutil`.
- If the folder can't be excluded, the service refuses to start with a fixed message.
- No migration. Mailroom has never stored real mail, so no bare ids exist in any database.

## Architect's decisions

- **The account lives in the id, not in a new field.** `Record` and `Envelope` keep their shape. The card reads the account back from `message_id` with `account_of`.
- **One account pattern.** `record.ACCOUNT_PATTERN` is the only copy of the pattern. `config` and `gmail` compile it.
- **`stored_id` checks the account.** `GmailClient` already refuses a bad name, so this is a second guard. It does not check the provider id, because `Envelope` does that.
- **The link keeps the bare Gmail id.** Gmail knows nothing of `personal/`.
- **A bare id shows the provider alone.** No database holds one, but the fallback keeps the card total, and the earlier card tests (records with `message_id="m1"`) stay unchanged.
- **The exclusion runs in `prepare_data_dir`, every time.** That function is the one place the folder is made, it runs at every store open, and setting the attribute is idempotent. `prepare_data_dir` calls `exclude_from_backup` through the module's global name, with no `try`, so a given test can replace it and see the error pass through.
- **`mailroom run` reports the failure like a settings error.** `run_service` opens the store before anything else, so the error reaches `cli.run`, which prints it and exits 1.

## Requirements

1. **One account pattern.** `src/mailroom/record.py` gains `ACCOUNT_PATTERN = "[a-z][a-z0-9-]{0,31}"`. `config._ACCOUNT` and `gmail._ACCOUNT` become `re.compile(ACCOUNT_PATTERN)`, and no other copy of the pattern stays in `src`.
2. **`stored_id(account: str, provider_id: str) -> str`** in `record.py` returns `f"{account}/{provider_id}"`. If `account` does not fully match `ACCOUNT_PATTERN` (`re.fullmatch`), it raises `ValueError(f"{FIELD_MESSAGE}: account")`.
3. **`account_of(message_id: str) -> str | None`** in `record.py` returns the text before the first `/` when there is a `/` and that text fully matches `ACCOUNT_PATTERN`. Otherwise it returns `None`.
4. **Gmail sync writes account ids.** In `sync_gmail`, with `client.account`:
   - The duplicate check is `store.get("gmail", stored_id(account, ref.id))`. It runs before the fetch, outside the `try` that skips unusable messages, so a refused account raises.
   - The `Envelope` gets `message_id=stored_id(account, ref.id)` and `thread_id=stored_id(account, message.thread_id)`.
   - The link and every Gmail API call keep the bare Gmail id.
   - `SyncResult.stored` holds the stored ids, in the same order as before.
5. **The footer names the account.** In `checkpoint_message`, the footer's first part is `f"{L.PROVIDER_NAMES[record.provider]} {account}"` when `account_of(record.message_id)` returns a name, and the provider name alone when it returns `None`. The rest of the footer is unchanged. `answered_message` follows, since it reuses the card.
6. **Backup constants** in `src/mailroom/config.py`:
   - `BACKUP_ATTRIBUTE = "com.apple.metadata:com_apple_backup_excludeItem"`
   - `BACKUP_VALUE`, a `bytes` literal equal to `plistlib.dumps("com.apple.backupd", fmt=plistlib.FMT_BINARY)`
   - `BACKUP_MESSAGE = "could not exclude the data folder from Time Machine"`
7. **`exclude_from_backup(folder: Path) -> None`** in `config.py` calls the C library's `setxattr` (see Facts) with `os.fsencode(folder)`, `BACKUP_ATTRIBUTE` encoded, `BACKUP_VALUE`, its length, position `0` and options `0`. Set `argtypes` and `restype`. A nonzero return raises `ConfigError(BACKUP_MESSAGE) from None`. The message never includes the path, the errno, or `os.strerror`.
8. **`prepare_data_dir`** calls `exclude_from_backup(folder)` after the `chmod`, through the module global, with no `try`.
9. **`mailroom run`** catches `ConfigError` raised by `service.run_service` too. It prints the message to stderr and exits 1, just as it does for `ServiceError`.
10. **Progress entry** for `## Phase 1n: Account ids and backups (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/unit/test_record_ids.py` | One pattern; `stored_id` (built and refused); `account_of` |
| `tests/unit/test_config_backup.py` | The constants; `exclude_from_backup` (set, repeated, non-ASCII, missing folder); `prepare_data_dir` excludes, and stops on failure |
| `tests/unit/test_cli_run_backup.py` | `mailroom run` prints the backup message and exits 1 |
| `tests/unit/test_checkpoint_account.py` | Footer with the account, the bare-id fallback, the answered card |
| `tests/integration/test_gmail_sync_accounts.py` | Two mailboxes sharing a Gmail id; the duplicate check per account |
| `tests/integration/test_gmail_sync.py` | Edited: stored ids, envelopes and lookups now `personal/...`; links unchanged |
| `tests/integration/test_gmail_sync_more.py` | Edited: one lookup now `personal/m1` |
| `tests/integration/test_service.py` | Edited: two lookups now `personal/m1` |
| `docs/verification/probe-01n.py` | The verifier's probe |

Given test count: **72** (37 new, 35 in the three edited files).

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/record.py` | `ACCOUNT_PATTERN`, `stored_id`, `account_of` |
| `src/mailroom/config.py` | the pattern import, backup constants, `exclude_from_backup`, the call in `prepare_data_dir` |
| `src/mailroom/gmail.py` | the pattern import only |
| `src/mailroom/gmail_sync.py` | stored ids |
| `src/mailroom/checkpoint.py` | the footer |
| `src/mailroom/cli.py` | `run` catches `ConfigError` |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- A migration, or any rewrite of existing rows. No bare ids exist.
- An `account` field on `Record` or `Envelope`, or an `account` column in any table.
- Running `tmutil` or any other subprocess, or using PyObjC.
- Checking the exclusion again each round, a status line for it, or a `doctor` command.
- Deleting existing Time Machine snapshots, or excluding any folder but the data folder.
- Any other change to the card layout: no new field, and no account in the title.
- Phase 1o's work: single-statement inserts in `open_problem` and `queue_alert`, and a shared Discord send helper. Also the `store.py` split.
- Outlook or Yahoo.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Read-only mail.** The sync adds no Gmail call, and every call it makes keeps the bare Gmail id. No `modify`, `trash`, `send`, or label change.
- **Error messages are constants.** `BACKUP_MESSAGE` and `f"{FIELD_MESSAGE}: account"` only. Never the folder path, the errno, `os.strerror`, or a chained library error (`from None`).
- **No network, no subprocess** in `src`. Tests may run `/usr/bin/xattr`; the code may not.
- **The account is plain text** in the footer, which Discord does not render as markdown. It is always a validated account name, never email text.
- **Time through the module**: `clock.now()`, never `datetime.now()`, and never `from mailroom.clock import now`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 37 = 674 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_record_ids.py tests/unit/test_config_backup.py tests/unit/test_cli_run_backup.py tests/unit/test_checkpoint_account.py tests/integration/test_gmail_sync_accounts.py tests/integration/test_gmail_sync.py tests/integration/test_gmail_sync_more.py tests/integration/test_service.py --no-cov -q` | `72 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/record.py,src/mailroom/config.py,src/mailroom/gmail.py,src/mailroom/gmail_sync.py,src/mailroom/checkpoint.py,src/mailroom/cli.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1n: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1n` | `Reports OK.` |
| `git diff HEAD --stat -- tests/unit/test_record_ids.py tests/unit/test_config_backup.py tests/unit/test_cli_run_backup.py tests/unit/test_checkpoint_account.py tests/integration/test_gmail_sync_accounts.py tests/integration/test_gmail_sync.py tests/integration/test_gmail_sync_more.py tests/integration/test_service.py docs/verification/probe-01n.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|subprocess|multiprocessing)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request|os\.system|os\.popen|tmutil|objc' -- src
git grep --untracked -n -E 'a-z0-9-' -- src ':!src/mailroom/record.py'
git grep --untracked -n -E 'strerror|get_errno|errno\.' -- src
git grep --untracked -n -E 'raise [A-Za-z]+\(f|raise [A-Za-z]+\([a-z_.]*(folder|path|error)' -- src/mailroom/config.py
git grep --untracked -n -E '/(modify|trash|untrash|send|batchModify|batchDelete|import|insert)["/?]|addLabelIds|removeLabelIds' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/record.py src/mailroom/config.py src/mailroom/gmail_sync.py src/mailroom/checkpoint.py src/mailroom/cli.py
```
