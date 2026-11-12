# Rules for AI coding agents

This file applies to every phase. Read it, then `docs/architecture.md`, then `docs/testing.md`, then `docs/phase-conventions.md` (what every phase spec and guide assume), then the phase spec you were assigned.

## Scope discipline

- Implement **only** the phase you were assigned. Do not build features from later phases, even if it seems convenient.
- If the spec is ambiguous, pick the simplest option that satisfies the acceptance criteria and record the decision in `docs/progress.md`.
- If the spec seems wrong or impossible, stop and explain instead of improvising a large workaround.
- Do not add dependencies that the phase spec does not list. If you believe one is needed, stop and ask.
- When finished, append an entry to `docs/progress.md` in the form `docs/phase-conventions.md` gives.

## Running commands

- The project's interpreter is `.venv/bin/python`. Every command names it: `.venv/bin/python -m pytest`, `.venv/bin/python -m ruff check .`, `.venv/bin/mailroom version`.
- Never type `python`, `python3`, `ruff`, or `pytest` on their own. On this machine `python` does not exist, `python3` is Python 3.15 without the project's packages, and a bare `ruff` may be a different installation.
- Do not activate the virtual environment. Each command runs in a new shell, so activation is lost before the next command.
- From Phase 1 on, `.venv/` exists. It is gitignored. Do not create another virtual environment and do not reinstall packages unless the phase spec has a step for it.
- If a command prints `command not found` or `No module named ...`, it was not typed as written. Stop and fix the command; do not skip the step.
- Before reporting a phase, run `.venv/bin/python scripts/check.py` as the spec's acceptance gives it. It must end with `All checks passed.`

## Privacy and safety rules (non-negotiable)

1. **No real mail, accounts or services.** Never connect to Gmail, Microsoft Graph, Yahoo, Discord, the tasks app or the local model while working, and never read the macOS Keychain. Tests replace all of them. The owner runs the real thing after verification.
2. **Synthetic data only** in tests and fixtures: invented senders, subjects, bodies, addresses and tokens. Never copy anything from a mailbox, the data folder, or the Keychain.
3. **Mail access is read-only.** No code may send, move, label, flag, delete, or mark mail as read. For Yahoo IMAP: `EXAMINE`, never `SELECT`; `BODY.PEEK[]`, never `BODY[]`; never `STORE`, `COPY`, `MOVE`, `EXPUNGE` or `APPEND`.
4. **Email text stays on this machine.** It goes only to the local model, and to Discord only through Show full text's ephemeral reply. Never send it anywhere else, log it, or put it in an error message.
5. **Nothing becomes a task without the owner's approval** on Discord, and every button press and command checks the owner's Discord user ID.
6. **Secrets come only from the Keychain**, through `mailroom.keychain`. Never from environment variables, files, code, or the repository. Never print, log, or put a secret in an error message.
7. **Network.** Code may connect only to what the phase spec names. Tests touch no network: `tests/conftest.py` blocks every connection that is not to 127.0.0.1 or a Unix socket.
8. **No telemetry.** No tracing, analytics, crash reporting, or update checks.
9. **The data folder** (`MAILROOM_DATA_DIR`, by default `~/Library/Application Support/mailroom`) holds email text. Never commit anything from it, never print it into a document.

## Determinism rules

- **Code decides where it can.** Thresholds, ranking, "clearly dated", trust and every policy are code, never asked of the model.
- **The model suggests, code decides.** Every model call has a named prompt, a closed output schema and fixed sampling. Invalid model output is rejected and logged by field name; never retried, repaired, or guessed around.
- **Time and ids come from one place.** Read the current time only through `mailroom.clock.now()` and new ids only through `mailroom.ids.new_id()`, called through the module (`clock.now()`, not `from mailroom.clock import now`), so tests can replace them.
- **Sends are retry-safe.** Anything sent to Discord or the tasks app is keyed by provider and message ID, so a retry never duplicates it.

## Architecture rules

- See `docs/architecture.md` for the components and their boundaries.
- All configuration comes from `mailroom.config.get_settings()` (environment variables with prefix `MAILROOM_`). No hardcoded paths, no secrets in settings.
- Use `pathlib.Path`. Development and deployment happen on macOS.
- **Error messages are constant text plus identifiers** (a message id, a secret's name, a field name, a line number). They never echo email text, a model reply, a secret, or the text of an exception from a library that may contain one.
- **Email-derived strings are untrusted**: titles, summaries, sender names and spam reasons are plain text with a length limit, never rendered as links or markdown that can act.

## Code style

- Python 3.12+, type hints on all public functions.
- `ruff check .` and `ruff format --check .` must pass.
- Prefer small, pure functions. Docstrings only where the intent is not obvious.
- `pytest` must pass, including all tests from previous phases.

## Testing

Follow `docs/testing.md`: put tests in the right layer (`tests/unit`, `tests/integration`, `tests/e2e`), keep them deterministic and offline, keep coverage above the configured threshold, and add a failing-first test for every bug fix. If you add code to a module listed under "Critical modules", cover every line and branch.
