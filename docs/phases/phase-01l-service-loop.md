# Phase 1l: Service loop

## Goal

Run everything as one service: `mailroom run`. A background thread holds the Discord Gateway (1j), with its own database connection, so your presses and commands are answered at any time. The main thread runs a round every minute:
- clear email text older than 24 hours
- sync each Gmail account (1c)
- triage what is new (1g)
- post what should reach you (1h)

Each part runs on its own. A part that fails is skipped and tried again next round, and the others carry on. A one-line status (no email text, no secret) goes to the log when a part's state changes. SIGTERM or Ctrl-C stops the service cleanly. Discord alerts for broken credentials and catch-ups are 1m.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 580, the tests Phase 1k left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_service.py --ignore=tests/unit/test_config_service.py --ignore=tests/unit/test_cli_run.py` must show `580 passed`. The ignored files import `mailroom.service`, which you create, or test settings you add.

## Facts

From Python 3.12, pydantic-settings 2.16 and SQLite on this machine.

- **One connection per thread.** A `sqlite3` connection refuses use from another thread (`ProgrammingError`; `check_same_thread` defaults to true), so the listener thread opens its own `Store`. Two connections to one file share it safely: with the default rollback journal, a writer waits up to 5 seconds for another's lock.
- **Waiting.** `threading.Event.wait(timeout)` returns early once the event is set, so a stop never waits out a whole minute.
- **Signals.** launchd stops a service with SIGTERM. `signal.signal` may be called only from the main thread, and a handler that sets the event replaces Python's default (KeyboardInterrupt for SIGINT).
- **List settings.** pydantic-settings decodes a tuple-typed setting from the environment as JSON, so `personal, work` fails with `SettingsError` before any validator runs. `Annotated[tuple[str, ...], NoDecode]` with a `mode="before"` validator that splits on commas works.
- **What each part raises** (earlier phases):
  - `sync_gmail`: `GmailError` subclasses (`GmailAuthError` "gmail sign-in needed: <account>", `GmailUnavailable`), or `KeychainError` for a missing secret
  - `triage_message`: `ModelUnavailable`
  - `post_pending`: `DiscordUnavailable` or `KeychainError`
  - `run_gateway`: `GatewayStopped`, `DiscordUnavailable` or `KeychainError`

  All of these messages are fixed text plus identifiers.
- **Gmail message ids** are unique within a mailbox. The store keys mail by provider and message id, so two Gmail accounts are assumed never to share an id (v1 expects one account per provider; see `docs/decisions.md`).

## Owner's decisions

- **One process, two threads.** `mailroom run` polls in the main thread and listens on the Gateway in a background thread; one launchd service runs both.
- **Keep the rest running.** A failing part is skipped and retried next round; only a status line marks it.
- **Alerts next.** Discord alerts (a credential stopped working, the Gateway stopped, the model unreachable for a while, a catch-up summary) are 1m.

## Architect's decisions

- **Rounds**: one at start, then one every `MAILROOM_POLL_SECONDS` (default 60, from 30 to 600).
- **A part is one account's sync, triage, or posting.** Each catches only the errors its earlier phase documents. Any other error is a bug: it propagates, the service exits, and launchd restarts it.
- **Triage stops for the round when the model is unavailable**, so a down model costs one request per round, not one per email.
- **The listener is not restarted** after it stops. A fatal close (such as a revoked token) won't fix itself, and retrying would burn Discord's 1,000 Identifies a day. Its status line says why; restarting the service retries it.
- **An unexpected error in the listener** is reported by its type only (`failed (KeyError)`), because its message could hold anything.
- **Status lines** are `<part>: <state>`, said when a part's state changes, through a `say` callback; the CLI writes them to stderr for launchd's log. They hold only fixed text and identifiers.
- **Settings**: `MAILROOM_GMAIL_ACCOUNTS` (comma-separated account names) and `MAILROOM_POLL_SECONDS`. The service refuses to start without the accounts, the model, the time zone, the channel and the owner, and names what is missing.
- **Critical modules**: `service.py` (that nothing is lost when a part fails, and nothing private reaches the log).

## Examples in plain words

- You start `mailroom run`: the log shows "discord gateway: running", "gmail personal: ok", "triage: ok", "discord posting: ok", then stays quiet while all is well.
- Ollama is restarting: the log shows "triage: model unavailable (network)" once; mail waits, and the next round after it's back triages it and logs "triage: ok".
- Your work account's token is revoked: "gmail work: gmail sign-in needed: work"; your personal account carries on.
- You reset the bot token: "discord gateway: gateway stopped (4004)"; polling and posting go on, and presses wait until you fix it and restart.

## Requirements

1. **`config.py`: two settings.**
   - `gmail_accounts: Annotated[tuple[str, ...], NoDecode] = ()` (`MAILROOM_GMAIL_ACCOUNTS`). It is split on commas and each name trimmed; an empty value gives `()`. Each name must match `[a-z][a-z0-9-]{0,31}` (Gmail's account rule), and none may be empty or repeated. Otherwise `GMAIL_ACCOUNTS_MESSAGE = "MAILROOM_GMAIL_ACCOUNTS must be account names separated by commas"`.
   - `poll_seconds: int = 60` (`MAILROOM_POLL_SECONDS`), a whole number from 30 to 600. Otherwise `POLL_MESSAGE = "MAILROOM_POLL_SECONDS must be a whole number from 30 to 600"`.
   - `get_settings` raises `ConfigError` with the field's message, never the value.

2. **`src/mailroom/service.py`: `ServiceError(Exception)`**, and **`Health(say: Callable[[str], None])`** with `report(part: str, state: str) -> None`. It calls `say(f"{part}: {state}")` only when `state` differs from the last state reported for `part`. It is safe to call from both threads (a lock).

3. **`run_round(store: Store, settings: Settings, gmail_clients: Sequence[GmailClient], model_http: httpx.Client, discord_http: httpx.Client, health: Health) -> None`**, in this order:
   1. `store.clear_expired_text()`.
   2. **Each Gmail client, in order:** `sync_gmail(client, store)`. A `GmailError` or `KeychainError` reports `(f"gmail {client.account}", str(error))`; success reports `"ok"`.
   3. **Triage:** `triage_message(store, provider, message_id, settings, model_http)` for each key of `store.untriaged()`, in order. A `ModelUnavailable` reports `("triage", str(error))` and ends triage for this round. Otherwise report `("triage", "ok")`.
   4. **Posting:** `post_pending(store, settings, discord_http)`. A `DiscordUnavailable` or `KeychainError` reports `("discord posting", str(error))`. Otherwise report `"ok"`, or `f"waiting ({report.stopped})"` when `stopped` is set.

   Every other exception propagates.

4. **`run_service(settings: Settings, *, say: Callable[[str], None], stop: threading.Event, open_gmail=gmail.open_gmail, open_model_http=extractor.open_model_http, open_discord_http=discord_post.open_discord_http, gateway=gateway.run_gateway) -> None`.**
   1. **Settings.** If any of these are empty, raise `ServiceError("not configured: " + ", ".join(<their names>))`, in this order, before anything else:
      - `MAILROOM_GMAIL_ACCOUNTS`
      - `MAILROOM_EXTRACTOR_MODEL`
      - `MAILROOM_TIME_ZONE`
      - `MAILROOM_DISCORD_CHANNEL_ID`
      - `MAILROOM_DISCORD_OWNER_ID`
   2. **Open** a `Health(say)`, `open_store(settings)`, a client per account with `open_gmail(account)`, `open_model_http()` and `open_discord_http()`.
   3. **The listener.** Report `("discord gateway", "running")`. Then start a daemon thread named `mailroom-gateway`, which:
      - opens its own `open_store(settings)` and `open_discord_http()`
      - calls `gateway(store, settings, http, stop=stop.is_set)`
      - on a `GatewayStopped`, `DiscordUnavailable` or `KeychainError`, reports `("discord gateway", str(error))`
      - on any other `Exception`, reports `("discord gateway", f"failed ({type(error).__name__})")`
      - closes its store and client, and is never restarted
   4. **Rounds.** While `stop` is not set: `run_round(...)`, then `stop.wait(settings.poll_seconds)`.
   5. **Finally** (also when a round raises): set `stop`, join the thread for up to 10 seconds, then close the store and every client.

5. **`cli.py`: `mailroom run`.**
   1. `get_settings()`; a `ConfigError` goes to stderr, exit 1.
   2. Make a `threading.Event`, and set it from `signal.signal` handlers for SIGTERM and SIGINT.
   3. Call `service.run_service(settings, say=<write the line to stderr>, stop=<the event>)`, through the module.
   4. A `ServiceError` goes to stderr, exit 1. A normal return exits 0.

6. **Critical modules.** `scripts/critical_modules.txt` (given) lists `service.py`.

7. **Progress entry** for `## Phase 1l: Service loop (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/integration/test_service.py` | 12 tests (requirements 2 to 4) |
| `tests/unit/test_config_service.py` | 7 tests (requirement 1) |
| `tests/unit/test_cli_run.py` | 3 tests (requirement 5) |
| `scripts/critical_modules.txt` | Adds `service.py` |
| `docs/verification/probe-01l.py` | The verifier's probe |

Given test count: **22**, from 17 test functions.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_service_more.py`, never by changing a given test, for at least:
- a round that raises an unexpected error: the service still stops the listener and closes everything, and the error propagates
- `GmailUnavailable` from one account (a 500)
- a listener that ends with `DiscordUnavailable` or `KeychainError`
- an empty `MAILROOM_GMAIL_ACCOUNTS` value giving `()`

## Scope

| Path | Change |
|---|---|
| `src/mailroom/config.py` | add `gmail_accounts`, `poll_seconds` and their messages |
| `src/mailroom/service.py` | create |
| `src/mailroom/cli.py` | add `run` |
| `tests/integration/test_service_more.py` | create |
| `docs/progress.md` | append your entry |

## Out of scope

- **Alerts** on Discord, the catch-up summary, notices for a part failing for a long time (1m).
- **Running it for you.** A launchd plist, installing it, log files, log rotation, a PID file.
- **Stage 2 and later.** Checkpoint 2, digests, the 30-minute follow-up, the tasks app, Outlook, Yahoo.
- **Other changes.** Restarting the listener, a retry within a round, a thread pool, asyncio, logging, changes to earlier modules, any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **No email text or secrets in the log** (`AGENTS.md`): a status line is a part name and an error's fixed text, or an exception's type name. Never a summary, subject, body, token or the message of an unexpected exception.
- **Nothing is lost**: a part that fails leaves its work for the next round; mail, verdicts and posts already stored stay stored.
- **Nothing happens for anyone but you**: unchanged; presses still go through 1i's checks.
- **Network**: the service makes no call of its own. It calls the earlier parts with their own clients. Tests reach everything through the fakes.
- **Time through the module**: `clock.now()`; the waiting is `stop.wait`, never `time.sleep`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 22 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_service.py tests/unit/test_config_service.py tests/unit/test_cli_run.py --no-cov -q` | `22 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/service.py,src/mailroom/config.py,src/mailroom/cli.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1l: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1l` | `Reports OK.` |
| `git diff HEAD --stat -- tests/integration/test_service.py tests/unit/test_config_service.py tests/unit/test_cli_run.py scripts/critical_modules.txt docs/verification/probe-01l.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|asyncio|multiprocessing|concurrent|discord)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request' -- src
git grep --untracked -n -E '(import|from) threading' -- src ':!src/mailroom/service.py' ':!src/mailroom/cli.py'
git grep --untracked -n -E 'signal\.' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'httpx\.(Client|get|post|put|request|stream)\(|http\.(get|post|put|request|send|stream)\(' -- src/mailroom/service.py
git grep --untracked -n -E 'time\.sleep|while True|except:|BaseException|os\._exit|sys\.exit' -- src/mailroom/service.py
git grep --untracked -n -E 'summary|subject|body_text|sender_name|get_secret|\.token' -- src/mailroom/service.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/service.py src/mailroom/config.py src/mailroom/cli.py
```
