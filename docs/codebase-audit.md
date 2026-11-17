# Codebase audit

Read 15 Nov 2026 against commit `879de3b` (through Phase 4d). Compared `src/mailroom` (6,717 lines) and `tests` (14,729 lines) with [Architecture](architecture.md), [Security and privacy](security-and-privacy.md), [Testing](testing.md), and the [Phase 1 audit](phase-01-audit.md).

The service still matches the threat model: read-only mail calls, secrets only from the Keychain, email text kept out of errors and logs, and nothing becomes a task without the owner's Discord user id. The findings below are what will make the next provider, the next card, or a bad Discord frame expensive.

## Closed since the Phase 1 audit

- The single `store.py` (644 lines) is now `src/mailroom/store/`, one module per table, composed in `store/__init__.py`.
- Posts and alerts share `discord_post.send_messages`. A failed write rolls back in `StoreBase._write`.
- Message ids are `<account>/<provider id>`, so two mailboxes cannot collide.
- The data folder is excluded from Time Machine in `config.exclude_from_backup`.

## What holds

- Gmail login accepts only `gmail.readonly`. Outlook login accepts only `Mail.Read` plus `offline_access`. Both use PKCE, a localhost callback, and an OAuth state check.
- Graph delta links are accepted only for `https://graph.microsoft.com` with a `/messages/delta` path. The Gateway connects only to `wss` on `*.discord.gg`.
- SQL uses placeholders. The database is mode `0o600` with `secure_delete` on, inside a `0o700` folder. The rollback journal stays the default, so a write-ahead log cannot keep cleared text.
- Checkpoint cards and Show full text turn mentions off and put email-derived text in a code block. The Gateway logger is silenced.
- Extractor output that fails the closed schema is rejected by field name. Invalid model output is not repaired.
- Body text and extractor output are cleared 24 hours after fetch. Tasks and follow-up links carry no body.

## 1. A listener exception ends Discord input until the process exits

`run_service` starts the Gateway thread once. `_listen` catches `Exception`, records a gateway alert, and returns. The poll loop keeps running, and it restarts the thread only when the process itself starts again.

`run_gateway` catches connection errors around `connect`. It does not catch a bad first frame. `_read_hello` calls `json.loads(raw)["d"]["heartbeat_interval"]` with no handler, so a malformed hello raises out of the thread. `_dispatch` swallows only `DiscordUnavailable`. `handle_interaction` then indexes `event["type"]`, `event["data"]["custom_id"]`, and `member.user.id`. A payload that is not that shape, or a new button path that raises, ends the thread the same way.

While the thread is dead, polling, triage, card posting, and alerts continue. Button presses and slash commands do not. launchd does not restart the process, because the process is still up. The owner gets the gateway alert and has to restart `mailroom run` to listen again.

## 2. Two connections share one file, and a lock error is fatal on exactly one side

`run_service` and `_listen` each call `open_store`. `sqlite3.connect` uses the default 5 second lock wait. There is no `busy_timeout` pragma. Skipping the write-ahead log is the privacy choice in [Architecture](architecture.md); the cost is that writers block each other.

The Phase 1 `IntegrityError` path is closed: inserts use `ON CONFLICT`, and `_write` rolls back on any failure. What remains is any lock timeout or other `sqlite3.OperationalError`.

- On the poll thread it is uncaught in `run_round`, so the process exits and launchd can bring both threads back.
- On the listener thread it is finding 1: the process stays up, and Discord input stays down.

## 3. Related rows are tied only by application SQL

Schema version 13 has no `FOREIGN KEY` and the connection never sets `PRAGMA foreign_keys`. `posts` does not reference `messages`. `answers` does not reference `posts`. `approvals` does not reference `answers`. `tasks` does not reference `approvals`. `links.task_item_id` does not reference `tasks`. `posts.follows` does not reference an approval.

The inserts are careful (`INSERT ... SELECT ... WHERE EXISTS`). The readers are not. After a post is found, these lines use the next row with no `None` check:

- `interactions.handle_interaction` reads `store.get(...).record` and `store.triage(...).verdict`.
- `discord_post.post_pending` does the same inside the send callback.
- Follow-up replies read `store.approval(post.follows).title`.

A missing row raises `AttributeError`. On the poll thread the process exits. On the listener thread, finding 1 applies. A later phase that deletes or rebuilds one table will not get a schema error at the write. It will get a crash at the read.

## 4. Outlook is a second copy of Gmail, and the shared parts still live under Gmail names

Yahoo is already allowed by the `provider` check in migration 1. The next adapter will copy this layout again.

Outlook reaches into Gmail modules for behaviour that is not Gmail-specific:

- `outlook_sync` imports `FIRST_RUN`, `CATCH_UP_LIMIT`, `CATCH_UP_OVERLAP`, and `SyncResult` from `gmail_sync`.
- `outlook_login` imports `Callback`, `LoginError`, `code_challenge`, and `new_verifier` from `gmail_login`.
- `cli.outlook_login_command` catches `gmail_login.LoginError`.

Changing the catch-up window in `gmail_sync` changes Outlook, and the owner of that constant is a Gmail file. Outlook's login errors are a Gmail exception class.

These pairs are the same algorithm with different client calls:

| Shared behaviour | Gmail | Outlook |
| --- | --- | --- |
| First run, history or delta, catch-up | `gmail_sync.sync_gmail`, `_choose`, `_store_message` | `outlook_sync.sync_outlook`, `_choose`, `_store_message` |
| Token cache, refresh, retry once on 401, map transport errors | `GmailClient._ensure_token`, `_refresh`, `_get`, `_send` | `OutlookClient._ensure_token`, `_refresh`, `_get`, `_send` |
| Poll one account and raise or clear the auth alert | `service._gmail_account`, `_gmail` | `service._outlook_account`, `_outlook` |
| Login command | `cli.gmail_login_command` | `cli.outlook_login_command` |
| Account-list validator | `Settings._check_gmail_accounts` | `Settings._check_outlook_accounts` |

`sender_auth.verified` repeats the same DMARC-or-(SPF-and-DKIM) return after the Outlook branch. `run_round` picks the account function with `isinstance(client, OutlookClient)`. A third provider adds another branch in the service, another alert helper, and another login command.

`gmail_login.login` and `outlook_login.login` also build an `httpx.Client` in the CLI and never close it. The process exits right after, so this only matters if login is later called from a long-lived process.

## 5. `interactions.py` is the file a new card has to get right

At 561 lines it is the largest module the running service uses. `handle_interaction` is one ordered tree: slash command, owner and channel, card kind, then first answer, second answer, combined, follow-up, or form. A button missing from `_PRESS_ACTIONS` is acknowledged with a deferred update and returned as `"ignored"`. A typo in a new `custom_id` looks finished to Discord and records nothing.

`_finish_combined` and `_decide` are the same sequence: write the decision, or reply that it was already answered, then replace the card with `approved_message`. `_form` and `_task_form` both build the title input (type 4, same custom id, same length limits). The file imports `checkpoint._block`, so a rename of that private helper breaks Discord replies.

`deadlines.py` (235 lines) is the other concentrated policy module. `clearly_dated` is what lets an email skip a checkpoint. A new date phrase has to be added to the right pattern among `_MONTH_DAY`, `_DAY_MONTH`, `_ISO`, `_NAMED_DAY`, and `_CLOCK`. The size fits the job. The risk is that the skip rule and the parser live in one place and a miss is silent: the email takes the longer card, or, if a pattern is too wide, it skips a checkpoint it should have shown.

## 6. `Store` is eight mixins on one connection

`Store` inherits message, sync, sender, triage, post, alert, approval, and task stores. No method names collide today. None of the mixins define `__init__`, so `StoreBase.__init__` runs once and migrates once. The first mixin that adds `__init__` and calls `StoreBase.__init__` directly will open a second connection or skip migration.

Callers see one class. The method's module is a search away. Each new table adds another base class and another re-export in `store/__init__.py`.

Row readers bind columns by position: `_read_post`, `_read_task`, `_read_link`, `_approval`, and `MessageStore.get`. The posts `SELECT` list is written three times (`pending_posts`, `post`, `post_by_item`). A new column has to change every copy and the unpacker. A swapped column fails only when that row is read.

`_read_due` is implemented twice, in `store/triage.py` and `store/approvals.py`, with the same date and `HH:MM` rules.

## 7. Smaller copies that will drift

- `extractor._plain` and `interactions._accepted_title` both reject Unicode categories `Cc`, `Cf`, `Zl`, and `Zp`, with a separate `_BAD_CATEGORIES` in each file. A change to what counts as a plain title has to be made twice, or model titles and owner-typed titles follow different rules.
- `tasks_app.send_tasks` and `_send_links` repeat the posted, waiting, and stopped loop from `discord_post.send_messages`. The tasks loop needs status 200 or 201 and an `Idempotency-Key`, so it cannot call `send_messages` as written. The two loops can still disagree about how a transport error is counted.
- `checkpoint.py` shares identity fields, colour, footer, and buttons. Each public card still assembles the same embed envelope: `allowed_mentions`, component rows, footer, and colour. Five builders (`checkpoint_message`, `followup_message`, `checkpoint2_message`, `combined_message`, `approved_message`) have to stay in step when that envelope changes.
- `Settings` checks the channel id, owner id, and guild id with the same 17-to-20 digit pattern and three copies of the validator.

## 8. A rotated Outlook refresh token can be dropped

`OutlookClient._refresh` writes a new refresh token with `keychain.set_secret` before it stores the access token. If the Keychain write raises, the new token is not kept on the client, and the exception leaves `_refresh`. `_outlook_account` treats `KeychainError` as a generic Outlook failure, so this round does not raise the sign-in alert. The next poll uses the previous refresh token. If Microsoft has already retired it, the account needs `outlook-login`, and the first failure does not say sign-in is required.

## 9. Tests: one fake module, and 26 files named `_more`

`tests/fakes.py` is 1,348 lines and holds every fake. Approximate sizes: `FakeDiscord` 350, `FakeGraph` 305, `FakeGmail` 292, `FakeTasksApp` 130. The file imports nothing from `mailroom`, which is the right boundary. It is still the file every provider, Discord, and tasks change has to edit.

[Testing](testing.md) says a module's tests live in `test_<module>.py`. Twenty-six files use a `_more` suffix, including `test_triage_more.py` (5 lines), `test_store_posts_more.py` (8), and three others under 15 lines. Splits that name a behaviour are readable: `test_interactions_second.py`, `test_interactions_combined.py`, `test_interactions_followup.py`. The `_more` files are the overflow of a phase, and a reader of `test_interactions.py` does not see those cases.

`tests/e2e/` does not exist. The testing doc describes that layer (commands through `CliRunner`, one email from fetch to an approved task). The CLI tests that exist are `tests/unit/test_cli.py`, `test_cli_run.py`, and `test_cli_run_backup.py`.

## 10. `reports.py` is a large critical module the service never runs

`reports.py` is 391 lines and is on the critical-module list, with four test modules (`test_reports.py`, `test_reports_more.py`, `test_reports_phase.py`, `test_reports_phase_more.py`). The running service does not import it. `scripts/check_reports.py` does. Phase 0 put the progress and review checker in the package. It belongs in the size table so it is not read as mail logic. Moving it is a phase decision: the checker and its tests are part of `scripts/check.py`'s critical-coverage gate.

## File sizes

Production modules of 200 lines or more:

| Lines | File | Why it is this size |
| --- | --- | --- |
| 561 | `interactions.py` | Every button, form, and card outcome |
| 391 | `reports.py` | Progress and review markdown checker |
| 344 | `outlook.py` | Graph client, including token rotation and delta links |
| 309 | `mime.py` | Parser that must not raise |
| 306 | `gmail.py` | Gmail client |
| 305 | `service.py` | Poll loop plus a copied Outlook path |
| 285 | `checkpoint.py` | Five card builders |
| 280 | `gateway.py` | Identify, heartbeat, resume |
| 245 | `extractor.py` | Closed schema for model output |
| 235 | `deadlines.py` | Clearly-dated parsing |
| 230 | `discord_layout.py` | Constants the cards and the bot share |
| 218 | `schema.py` | Migrations 1 through 13, append-only |
| 217 | `config.py` | One validator per setting |
| 213 | `gmail_login.py` | OAuth callback that Outlook also uses |

Nothing here is thousands of lines. The ones that are hard to change safely are `interactions.py` (one tree, silent ignore), `service.py` (a branch per provider), and `tests/fakes.py` (every external system).

## Specified, and worth leaving alone

- `mime.py` catches `Exception` around header and body reads. The parser must return a record and must not raise. That is the contract in [Architecture](architecture.md).
- The database stays on the rollback journal. A write-ahead log would keep cleared email text.
- `yahoo` is in the provider check before a Yahoo adapter exists. The schema is allowed to arrive with the phase that needs the table; the check is ahead of the adapter on purpose.
- Button custom ids and `discord_layout` constants are a contract with posts already in Discord. Renaming them would orphan cards.

## Order if you act on this

1. Restart the Gateway thread after a failure, and treat a malformed frame as a resume, before adding another button type. That is the failure mode that leaves the process up and the owner unable to approve mail.
2. Move `SyncResult`, the catch-up windows, and the OAuth callback out of the Gmail modules before a Yahoo adapter. Otherwise Yahoo will import Gmail, or a third copy will appear.
3. Use one `_read_due`, and make the chained reads in `handle_interaction` and `post_pending` tolerate a missing row. Foreign keys can follow when a migration is already planned; SQLite cannot add them by altering a `STRICT` table in place.
4. Add tests to the module file, or to a file named for the behaviour. Stop adding `_more` files. Split `tests/fakes.py` when the next provider's fake arrives, along the class boundaries that are already there.
