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
