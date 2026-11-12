# Testing strategy

Applies to every phase. Phase specs list the specific tests; this file sets the rules and the layers.

## Layers

| Layer | Location | What it covers | Runs |
|---|---|---|---|
| Unit | `tests/unit/` | Pure functions and single modules: settings, the keychain reader, parsing, rules, ranking, validation | Every run; fast |
| Integration | `tests/integration/` | Modules together: an adapter against a fake provider, triage with a fake model, the database in a temporary folder | Every run |
| End-to-end | `tests/e2e/` | Commands through Typer's `CliRunner`; an email from fetch to Discord prompt to approved task, with every outside system faked | Every run |
| Evaluation | by hand (a later phase) | Extractor accuracy against the real local model on synthetic emails | By hand, never in `scripts/check.py` |

## Rules

1. **Synthetic data only** (`AGENTS.md` rule 2). Test emails are invented, never copied from a mailbox.
2. **No network.** `tests/conftest.py` blocks every connection and name lookup that is not to 127.0.0.1, ::1, localhost or a Unix socket. A test that needs an HTTP answer starts its own server on 127.0.0.1.
3. **No real Keychain.** `tests/conftest.py` replaces the keyring backend with one that fails on every call, so a test that forgets the fake fails instead of reading a real secret. A test that needs secrets takes the `fake_keychain` fixture (`tests/fakes.py`) and fills `fake_keychain.secrets`.
4. **No real mail provider, model, Discord or tasks app.** Each gets a fake in `tests/fakes.py` in the phase that first needs it, checked against the real system's documented request and response shapes. Behaviour that depends on the real model is measured by the evaluation, not asserted in tests.
5. **Deterministic**: no dependence on today's date, the machine's time zone, dict or file-system order, or randomness. Time comes from replacing `mailroom.clock.now`, ids from replacing `mailroom.ids.new_id` (`tests/support.py` has `fixed_times` and `fixed_ids`).
6. **Isolated settings.** `tests/conftest.py` removes every `MAILROOM_*` variable from the environment, sets `HOME` to a fresh temporary folder, and sets `MAILROOM_DATA_DIR` to another, for each test. A phase that adds a setting adds nothing here: the prefix covers it.
7. **Every bug fix adds a test** that fails before the fix.
8. **Coverage**: branch coverage on every run, overall at least 90%. Every line and branch of each critical module is covered; `scripts/check.py` checks it.
9. **Expected values are literal**: whole lines, whole messages and whole rows written out, never built by the code under test or by `str.format`.
10. Tests for a module live in the matching layer folder, named `test_<module>.py`. Shared helpers live in `tests/support.py`; fakes live in `tests/fakes.py`, which imports nothing from `mailroom`.

## Critical modules

A bug here lets the service leak a secret or email text, act without approval, or accept output it should refuse, so every line and branch must be covered. The list lives in `scripts/critical_modules.txt` (paths relative to `src/mailroom/`), which `scripts/check.py` reads; a phase that adds a critical module adds it there and here.

- `reports.py` (progress entries and reviews; Phase 0)
- `config.py` (where the data folder is, and that it is private; Phase 0)
- `keychain.py` (secrets read only by name, and never echoed; Phase 0)
- `mime.py` (untrusted email text cleaned, limited, and never a crash; Phase 1a)
- `store.py` (deduplication, and email text cleared from the file after 24 hours; Phase 1a)
- `gmail.py` (read-only Gmail calls, secrets never echoed; Phase 1b)
- `gmail_sync.py` (what reaches the database: inbox only, once each, nothing lost on a failure; Phase 1c)

## Commands

```zsh
.venv/bin/python scripts/check.py                   # lint, format, tests with coverage, critical coverage
.venv/bin/python scripts/check.py --first core      # the core section first; the full check only once it passes
.venv/bin/python scripts/check.py --section tooling # one section alone, no coverage (names in tests/sections.toml)
.venv/bin/python -m pytest                          # the tests alone, with coverage
```

A new test file belongs in the section of the code it tests: add a pattern to `tests/sections.toml` when `core` would take it otherwise.
