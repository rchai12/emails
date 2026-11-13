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
