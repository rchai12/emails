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
