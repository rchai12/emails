# Progress

One entry per phase, written by the coder, in the form `docs/phase-conventions.md` gives.

## Phase 0: skeleton (2026-11-11)
- Tests: 0 -> 96 (given 96)
- New public names: `mailroom`: `__version__`; `clock`: `now`; `ids`: `new_id`; `config`: `DATA_DIR_MESSAGE`, `ConfigError`, `Settings`, `get_settings`, `prepare_data_dir`; `keychain`: `SERVICE`, `NAME_MESSAGE`, `KeychainError`, `SecretMissing`, `KeychainUnavailable`, `get_secret`; `cli`: `app`, `version`
- Changed files: 17
- Deviations:
  - A leading ~ is expanded with Path.expanduser(), which also expands ~user.
- Follow-ups:
  - The given files were untracked and five tracked docs were already modified, so git status lists 17 paths, not only the Scope paths.

## Phase 1a: parser and store (2026-11-11)
- Tests: 96 -> 175 (given 69)
- New public names: `mime`: `SUBJECT_LIMIT`, `NAME_LIMIT`, `ADDRESS_LIMIT`, `HEADER_LIMIT`, `AUTH_RESULTS_LIMIT`, `BODY_LIMIT`, `clean_line`, `clean_text`, `html_to_text`, `parse_message`; `store`: `DB_FILENAME`, `SCHEMA_MESSAGE`, `TEXT_RETENTION`, `StoreError`, `StoredMessage`, `Store`, `open_store`
- Changed files: 4
- Deviations:
  - If get_content() is not text, or get_payload() raises, the body is empty. If the content type cannot be read, the decoded text is kept as plain text.
- Follow-ups:
  - None

## Phase 1b: Gmail client (2026-11-11)
- Tests: 175 -> 212 (given 30)
- New public names: `gmail`: `TOKEN_URL`, `API_URL`, `SCOPE`, `PAGE_SIZE`, `TIMEOUT_SECONDS`, `TOKEN_MARGIN`, `ACCOUNT_MESSAGE`, `MESSAGE_ID_MESSAGE`, `GmailError`, `GmailAuthError`, `GmailUnavailable`, `BookmarkExpired`, `Profile`, `MessageRef`, `History`, `RawMessage`, `GmailClient`, `open_gmail`
- Changed files: 3
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1c: Gmail sync (2026-11-12)
- Tests: 212 -> 239 (given 25)
- New public names: `gmail`: `MessageGone`; `store`: `SyncState`; `gmail_sync`: `FIRST_RUN`, `CATCH_UP_LIMIT`, `CATCH_UP_OVERLAP`, `LINK`, `SyncResult`, `sync_gmail`
- Changed files: 5
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1d: Gmail login (2026-11-12)
- Tests: 239 -> 271 (given 29)
- New public names: `keychain`: `VALUE_MESSAGE`, `set_secret`; `gmail_login`: `AUTH_URL`, `CALLBACK_TIMEOUT`, `REQUEST_TIMEOUT_SECONDS`, `DONE_PAGE`, `CANCELLED_PAGE`, `LoginError`, `new_verifier`, `code_challenge`, `consent_url`, `Callback`, `exchange_code`, `login`, `new_http`; `cli`: `gmail_login_command`
- Changed files: 5
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1e: Sender checks and rules (2026-11-12)
- Tests: 271 -> 306 (given 32)
- New public names: `store`: `SENDER_MESSAGE`, `STATUS_MESSAGE`, `sender_status`, `set_sender_status`, `senders`; `sender_auth`: `AUTHSERV_IDS`, `AuthResult`, `parse_results`, `verified`; `rules`: `Screening`, `screen`
- Changed files: 5
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1f: Extractor (2026-11-12)
- Tests: 306 -> 352 (given 29)
- New public names: `config`: `EXTRACTOR_URL_MESSAGE`, `TIME_ZONE_MESSAGE`, `extractor_url`, `extractor_model`, `time_zone`; `extractor`: `TIMEOUT_SECONDS`, `ModelUnavailable`, `Deadline`, `Extraction`, `Rejected`, `user_message`, `extract`, `open_model_http`
- Changed files: 5
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1g: Triage result (2026-11-12)
- Tests: 352 -> 407 (given 51)
- New public names: `store`: `Verdict`, `StoredTriage`, `save_triage`, `triage`, `untriaged`; `triage`: `should_notify`, `rank`, `triage_message`
- Changed files: 5
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1h: Discord posting (2026-11-12)
- Tests: 407 -> 441 (given 30)
- New public names: `store`: `Post`, `queue_notified`, `pending_posts`, `post`, `mark_posted`; `config`: `DISCORD_CHANNEL_MESSAGE`, `discord_channel_id`; `checkpoint`: `checkpoint_message`; `discord_post`: `TIMEOUT_SECONDS`, `DiscordUnavailable`, `PostReport`, `open_discord_http`, `post_pending`
- Changed files: 7
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1i: Discord answers (2026-11-12)
- Tests: 441 -> 490 (given 40)
- New public names: `store`: `Answer`, `post_by_item`, `record_answer`, `answer`; `config`: `DISCORD_OWNER_MESSAGE`, `discord_owner_id`; `checkpoint`: `answered_message`; `interactions`: `handle_interaction`
- Changed files: 6
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1j: Discord Gateway (2026-11-12)
- Tests: 490 -> 540 (given 35)
- New public names: `gateway`: `GATEWAY_URL_MESSAGE`, `gateway_url_allowed`, `open_gateway`, `GatewayStopped`, `run_gateway`
- Changed files: 3
- Deviations:
  - None
- Follow-ups:
  - probe-01j.py plans server closes of 4008, then treats that close_code as a client rate limit, so the probe does not print FAILURES 0

## Phase 1k: Discord commands (2026-11-12)
- Tests: 540 -> 580 (given 33)
- New public names: `config`: `DISCORD_GUILD_MESSAGE`, `discord_guild_id`; `commands`: `register_commands`, `handle_command`; `cli`: `discord_commands`
- Changed files: 6
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1l: Service loop (2026-11-12)
- Tests: 580 -> 607 (given 22)
- New public names: `config`: `GMAIL_ACCOUNTS_MESSAGE`, `POLL_MESSAGE`, `gmail_accounts`, `poll_seconds`; `service`: `ServiceError`, `Health`, `run_round`, `run_service`; `cli`: `run`
- Changed files: 10
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1m: Alerts (2026-11-13)
- Tests: 607 -> 637 (given 23)
- New public names: `store`: `Problem`, `Alert`, `problem`, `open_problem`, `mark_alerted`, `close_problem`, `queue_alert`, `pending_alerts`, `mark_alert_posted`; `alerts`: `MODEL_WAIT`, `track`, `notice`, `catch_up_text`, `post_alerts`
- Changed files: 5
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1n: Account ids and backups (2026-11-13)
- Tests: 637 -> 674 (given 37)
- New public names: `record`: `ACCOUNT_PATTERN`, `stored_id`, `account_of`; `config`: `BACKUP_ATTRIBUTE`, `BACKUP_VALUE`, `BACKUP_MESSAGE`, `exclude_from_backup`
- Changed files: 7
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 1o: Single writes and send helper (2026-11-13)
- Tests: 674 -> 685 (given 11)
- New public names: `discord_post`: `send_messages`
- Changed files: 5
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 2a: Store package (2026-11-13)
- Tests: 685 -> 730 (given 45)
- New public names: None
- Changed files: 3
- Deviations:
  - None
- Follow-ups:
  - probe-02a.py seed 21 never queues two notified rows while ids.new_id fails after a successful call, so partial stays 0 and the probe does not print FAILURES 0

## Phase 2b: Clearly dated (2026-11-13)
- Tests: 730 -> 810 (given 80)
- New public names: `deadlines`: `CONFIDENCE`, `WINDOW`, `read_deadline`, `clearly_dated`
- Changed files: 2
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 2c: Dated at triage (2026-11-13)
- Tests: 810 -> 832 (given 22)
- New public names: `store`: `Due`
- Changed files: 4
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 2d: Checkpoint 2 (2026-11-13)
- Tests: 832 -> 901 (given 67)
- New public names: `store`: `Approval`, `record_approval`, `approval`; `checkpoint`: `checkpoint2_message`, `approved_message`
- Changed files: 7
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 2e: Combined card (2026-11-13)
- Tests: 901 -> 961 (given 58)
- New public names: `deadlines`: `deadline_passed`; `store`: `choose_card`, `record_combined`; `checkpoint`: `combined_message`
- Changed files: 9
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 2f: Stub tasks app (2026-11-13)
- Tests: 961 -> 1010 (given 49)
- New public names: `config`: `TASKS_URL_MESSAGE`, `tasks_url`; `store`: `Task`, `queue_approved`, `pending_tasks`, `mark_task_sent`, `task`; `tasks_app`: `TasksUnavailable`, `task_key`, `task_payload`, `open_tasks_http`, `send_tasks`; `alerts`: `TASKS_WAIT`
- Changed files: 7
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 3a: Follow-up card (2026-11-13)
- Tests: 1010 -> 1051 (given 41)
- New public names: `store`: `approved_in_thread`; `checkpoint`: `followup_message`
- Changed files: 6
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 3b: Follow-up links (2026-11-13)
- Tests: 1051 -> 1090 (given 39)
- New public names: `store`: `Link`, `queue_linked`, `pending_links`, `mark_link_sent`, `link`; `tasks_app`: `is_task_id`, `link_payload`
- Changed files: 4
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 4a: Graph client (2026-11-13)
- Tests: 1090 -> 1142 (given 39)
- New public names: `outlook`: `TOKEN_URL`, `API_URL`, `SCOPE`, `PAGE_SIZE`, `TIMEOUT_SECONDS`, `TOKEN_MARGIN`, `ACCOUNT_MESSAGE`, `MESSAGE_ID_MESSAGE`, `IMMUTABLE_ID`, `OutlookError`, `OutlookAuthError`, `OutlookUnavailable`, `DeltaExpired`, `MessageGone`, `Profile`, `MessageRef`, `Delta`, `RawMessage`, `OutlookClient`, `open_outlook`
- Changed files: 2
- Deviations:
  - None
- Follow-ups:
  - None

## Phase 4b: Outlook sync (2026-11-13)
- Tests: 1142 -> 1160 (given 18)
- New public names: `outlook_sync`: `INBOX_LINK`, `WEB_LINK_PREFIX`, `sync_outlook`
- Changed files: 4
- Deviations:
  - None
- Follow-ups:
  - The given sync file collects 17 tests, so its pytest line is 17 passed. One behaviour test covers a store that declines the record.
  - probe-04b.py ends FAILURES 1. Trial 4 moves AAMk8 into the inbox after expire_deltas, and the catch-up window is by received time, so the message stays unstored. The probe only excuses moves already in moved_in when expire_deltas runs.

## Phase 4c: Outlook login (2026-11-13)
- Tests: 1160 -> 1184 (given 23)
- New public names: `outlook_login`: `AUTH_URL`, `CLIENT_ID_LABEL`, `consent_url`, `exchange_code`, `login`, `new_http`
- Changed files: 5
- Deviations:
  - None
- Follow-ups:
  - None
