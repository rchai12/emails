# Review: Phase 1n

- Verdict: PASS
- Passed: 674
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `ACCOUNT_PATTERN`, `stored_id`, `account_of`, `BACKUP_VALUE`, and `exclude_from_backup` import, and `grep -c "^## Phase 1n: " docs/progress.md` prints `1`. The baseline given files are committed. `git status --short` lists only the seven Scope paths.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `674 passed` in 3.17s, 0 failed, 0 skipped, no warnings. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          615 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (548 statements, 106 branches). G2: `72 passed`. G4: `1`. G5: `Reports OK.` G6 is empty. G7 lists only the Scope paths. G8 freeze matches the Phase 1m list, 35 packages, including `websockets==17.3`. Q1 through Q8 print nothing. Probe: `oracle self-check: ok`, `ids round-trip and bad accounts are refused: ok`, `accounts sharing Gmail ids never collide: ok`, `data folders are excluded from Time Machine: ok`, `FAILURES 0`.

Spot checks S1 through S9 each failed as designed, then the files were restored (`git diff HEAD` and `git status --short` matched the snapshots). S1 fetched `['m1', 'm1']`. S2 stored `thread_id='t1'`. S3 built a link ending `#all/personal/m1`. S4 showed `Gmail · Verified sender`. S5 returned `'Personal'`. S6 and S8 did not raise. S7 left the attribute `None`. S9 printed `''`.

`BACKUP_VALUE` is 61 bytes and equals `plistlib.dumps("com.apple.backupd", fmt=plistlib.FMT_BINARY)`.

| Requirement | Where it is checked |
| --- | --- |
| 1 One account pattern | `test_record_ids.py`; Q2 prints nothing |
| 2 `stored_id` | `test_a_stored_id_is_the_account_a_slash_and_the_provider_id`, `test_a_stored_id_refuses_an_account_settings_would_refuse` |
| 3 `account_of` | `test_the_account_is_read_back_from_a_stored_id` |
| 4 Gmail sync writes account ids | `test_two_accounts_keep_messages_that_share_a_gmail_id`, `test_a_message_stored_for_one_account_is_skipped_only_there`, `test_the_stored_record_comes_from_gmail_and_the_parser` |
| 5 Footer names the account | `test_the_footer_names_the_account_the_email_came_to`, `test_the_answered_card_keeps_the_account` |
| 6 Backup constants | `test_config_backup.py` |
| 7 `exclude_from_backup` | `test_a_folder_that_cannot_be_excluded_raises_the_fixed_message`, `test_a_folder_name_outside_ascii_is_excluded` |
| 8 `prepare_data_dir` calls it | `test_preparing_the_data_folder_excludes_it_from_backup`, `test_preparing_stops_when_the_folder_cannot_be_excluded` |
| 9 `mailroom run` catches `ConfigError` | `test_run_reports_a_data_folder_it_cannot_exclude_and_exits_1` |
| 10 Progress entry | G4, G5 |
