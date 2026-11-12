# Phase 0: skeleton

## Goal

Make `mailroom` an installable, tested Python package with the check tooling every later phase uses, and the four seams every later phase builds on: one place for the current time, one for new ids, one for settings (including a private data folder), and one for reading secrets from the Keychain.

Sections: `core`. The `tooling` section (the report checker's tests) runs in the full check.

Follow `docs/phase-conventions.md`. In this phase N is 0: there is no `.venv` and no check run before you start.

## Facts

- **Python.** Python 3.12 is `/opt/homebrew/bin/python3.12` (3.12.16). `python3` on this machine is 3.15 and must not be used.
- **keyring 25.7.** `keyring.get_password(service, username)` returns `None` when nothing is stored. Every error it raises is a subclass of `keyring.errors.KeyringError`: `KeyringLocked` when access is denied, `NoKeyringError` from the failing backend. It looks up the backend on every call through `keyring.core.get_keyring()`, which is why tests can replace `keyring.core._keyring_backend` (and `tests/conftest.py` does, so no test can reach the real Keychain).
- **Typer.** An app with exactly one command and no callback treats that command as the whole program, so `mailroom version` exits with code 2 (checked by a spike). The app needs a `@app.callback()`. Invoking the app with no arguments also exits 2 when `no_args_is_help=True`; no test pins that.
- **pydantic-settings 2.16** reads `MAILROOM_`-prefixed environment variables with `env_prefix="MAILROOM_"`.
- **`Path.home()`** reads `HOME`, which `tests/conftest.py` sets to a temporary folder for each test, so a default computed from `Path.home()` must be computed when settings are read, not when the module is imported.

## Owner's decisions

- Tooling matches conductor: Python 3.12 in `.venv`, setuptools, pytest with pytest-cov, ruff.
- The package and command are `mailroom`.
- Phase 0 is the skeleton plus the core seams. Fakes for mail providers, the model, Discord and the tasks app come in the phase that first needs each.
- Conductor's `scripts/check.py` and `scripts/check_reports.py` are reused, adapted.
- The data folder defaults to `~/Library/Application Support/mailroom`, outside the repository and outside anything iCloud syncs.
- Secrets are read with the `keyring` library.

## Architect's decisions

- **Phase ids** are unpadded (`0`, `1a`); file names pad them to two digits (`phase-00-skeleton.md`). The report checker allows phase `0`.
- **Given files are committed** with this spec, not embedded in it. The 17 files below are already in the repository.
- **Secret names** are 1 to 64 characters: a lowercase letter, then lowercase letters, digits, `.`, `_` or `-`. The whole name must match; a trailing newline is not allowed. The keychain item is service `mailroom`, account = the secret's name.
- **Errors name only the key.** `SecretMissing` and `KeychainUnavailable` share the base `KeychainError`. A keyring error is replaced, not chained (`raise ... from None`), because a library's error text could contain more than a name.
- **The data folder is private:** mode exactly `0o700`, created or tightened by `prepare_data_dir`, whatever the umask.
- **Settings are read on each call** to `get_settings()` (no cache), so tests and the launchd environment always agree with the environment.
- **Critical modules:** `reports.py`, `config.py`, `keychain.py` (`scripts/critical_modules.txt`).

## Requirements

1. **Install.** Create the environment with `/opt/homebrew/bin/python3.12 -m venv .venv` and install with `.venv/bin/python -m pip install -e '.[dev]'` (this step needs the network to reach PyPI; nothing else in this phase does). Install nothing else.
2. **`src/mailroom/__init__.py`** contains `__version__ = "0.1.0"` and no imports.
3. **`src/mailroom/clock.py`**: `now() -> datetime` returns the current moment as an aware datetime in UTC (`tzinfo` is `datetime.UTC`).
4. **`src/mailroom/ids.py`**: `new_id() -> str` returns a new random id of 32 lowercase hex characters (`uuid.uuid4().hex`).
5. **`src/mailroom/config.py`, settings**:
   - `class Settings` (a pydantic-settings `BaseSettings`, prefix `MAILROOM_`) with one field, `data_dir: Path`.
   - Default `data_dir`: `Path.home() / "Library" / "Application Support" / "mailroom"`, computed when settings are read.
   - A leading `~` in `MAILROOM_DATA_DIR` is the home folder (`~` alone, or `~/...`).
   - `get_settings() -> Settings` builds new settings on every call.
   - If `data_dir` is not absolute after `~` is expanded, `get_settings()` raises `ConfigError` whose text is exactly `DATA_DIR_MESSAGE` = `"MAILROOM_DATA_DIR must be an absolute path"`. No pydantic `ValidationError` escapes, and its text is not chained (`from None`).
6. **`src/mailroom/config.py`, data folder**: `prepare_data_dir(settings: Settings) -> Path` creates `settings.data_dir` and any missing parents, sets the data folder's own mode to exactly `0o700` (new or existing, under any umask), and returns `settings.data_dir`. Calling it again is harmless. It changes the mode of the data folder only, never of its parents.
7. **`src/mailroom/keychain.py`, names**: `SERVICE = "mailroom"`, `NAME_MESSAGE = "invalid secret name"`. `get_secret(name: str) -> str` raises `ValueError(NAME_MESSAGE)` for a name that breaks the rule above, before any keychain call.
8. **`src/mailroom/keychain.py`, reading**: for a valid name, `get_secret` calls `keyring.get_password(SERVICE, name)` (on every call; nothing cached) and returns the value.
   - `None` or `""` raises `SecretMissing` with text `"secret not found: <name>"`.
   - Any `keyring.errors.KeyringError` raises `KeychainUnavailable` with text `"keychain unavailable: <name>"`, `from None`.
   - Any other exception propagates unchanged.
   - `KeychainError(Exception)` is the base of both. The module never writes or deletes keychain items.
9. **`src/mailroom/cli.py`**: `app` is a `typer.Typer` with a `@app.callback()` and one command, `version`, which prints `mailroom <__version__>` and a newline (`mailroom 0.1.0`). `pyproject.toml` already maps the `mailroom` command to `mailroom.cli:app`.
10. **Progress entry** for `## Phase 0: skeleton (YYYY-MM-DD)` at the end of `docs/progress.md`, in the form `docs/phase-conventions.md` gives.

## Given files

Already committed; never change them.

| File | What it is |
|---|---|
| `pyproject.toml` | Package metadata, dependencies, the `mailroom` command, ruff, pytest and coverage settings |
| `scripts/check.py` | Lint, format, tests by section, overall and critical coverage (adapted from conductor) |
| `scripts/check_reports.py` | Checks the form of progress entries and reviews |
| `scripts/critical_modules.txt` | The critical modules: `reports.py`, `config.py`, `keychain.py` |
| `src/mailroom/reports.py` | The report checker's module (adapted from conductor; allows phase `0`) |
| `tests/conftest.py` | Blocks the network and the real Keychain; isolates `HOME`, `MAILROOM_*` and the data folder; the `fake_keychain` fixture |
| `tests/fakes.py` | `FakeKeychain`; imports nothing from `mailroom` |
| `tests/support.py` | `run`, `runner`, `fixed_times`, `fixed_ids` |
| `tests/sections.toml` | Sections `tooling` (report tests) and `core` (everything else) |
| `tests/unit/test_reports.py`, `test_reports_more.py`, `test_reports_phase.py`, `test_reports_phase_more.py` | The report checker's tests: 59 |
| `tests/unit/test_clock_ids.py` | 5 tests (requirements 3, 4, and the given helpers) |
| `tests/unit/test_config.py` | 10 tests (requirements 5, 6) |
| `tests/unit/test_keychain.py` | 19 tests (requirements 7, 8) |
| `tests/unit/test_cli.py` | 3 tests (requirements 1, 2, 9) |

Given test count: **96**.

## Tests to write

The given tests cover every requirement. If coverage of a module you write falls short, add a behaviour test in a new file under `tests/unit/` (for example `tests/unit/test_config_more.py`), never by changing a given test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/__init__.py` | create |
| `src/mailroom/clock.py` | create |
| `src/mailroom/ids.py` | create |
| `src/mailroom/config.py` | create |
| `src/mailroom/keychain.py` | create |
| `src/mailroom/cli.py` | create |
| `tests/unit/test_*_more.py` | create, only if coverage needs them |
| `docs/progress.md` | append your entry |

`.venv/`, `*.egg-info/`, `.coverage` and caches are gitignored and do not appear in `git status --short`.

## Out of scope

- Writing or deleting secrets, and any command that stores one (a later phase adds it with the first OAuth flow).
- Any setting other than `data_dir`; caching settings.
- Logging, a `doctor` command, a `--version` flag, or any command other than `version`.
- The database, any mail adapter, Discord, the model, the tasks app, the MCP server, a launchd file.
- Fakes beyond `FakeKeychain`.
- Any change to a given file, `README`, `AGENTS.md` or the design docs.

## Rules that bite

- **Never read the real Keychain.** Do not call `get_secret` or `keyring` outside the tests, not even to try it: `.venv/bin/python -c "..."` against the real Keychain is forbidden (`AGENTS.md` rule 6).
- **Error messages are constant text plus the identifier**: never a value, never a library's error text.
- **Time and ids through the module**: nothing outside `clock.py` reads the time, and nothing outside `ids.py` makes a uuid.
- Commands start with `.venv/bin/python`; no bare `python3`, `pytest` or `ruff`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least 96 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_reports.py tests/unit/test_reports_more.py tests/unit/test_reports_phase.py tests/unit/test_reports_phase_more.py tests/unit/test_clock_ids.py tests/unit/test_config.py tests/unit/test_keychain.py tests/unit/test_cli.py --no-cov -q` | `96 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/__init__.py,src/mailroom/clock.py,src/mailroom/ids.py,src/mailroom/config.py,src/mailroom/keychain.py,src/mailroom/cli.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `.venv/bin/mailroom version` | `mailroom 0.1.0` |
| `grep -c "^## Phase 0: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 0` | `Reports OK.` |
| `git diff HEAD --stat -- pyproject.toml scripts src/mailroom/reports.py tests/conftest.py tests/fakes.py tests/support.py tests/sections.toml tests/unit/test_reports.py tests/unit/test_reports_more.py tests/unit/test_reports_phase.py tests/unit/test_reports_phase_more.py tests/unit/test_clock_ids.py tests/unit/test_config.py tests/unit/test_keychain.py tests/unit/test_cli.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'set_password|delete_password|set_keyring\(|keyring\.core' -- src
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid[0-9]' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'from mailroom\.(clock|ids) import' -- src
git grep --untracked -n -E 'import (socket|ssl|imaplib|smtplib|http|urllib|requests|httpx)([^A-Za-z_]|$)' -- src
git grep --untracked -n -E 'os\.environ|getenv\(' -- src ':!src/mailroom/config.py'
git grep --untracked -n -E 'print\(|logging|logger' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'pragma: no cover' -- src
```
