# Phase 1m: Alerts

## Goal

Tell you on Discord when the service needs you, and when it's fine again. Four problems are watched:
- a Gmail account needing sign-in
- the Discord listener stopping
- the local model unreachable for 15 minutes
- a catch-up after an outage, which gets one summary

Each problem posts one alert when it starts (or once it has lasted long enough) and one short "works again" message when it ends, never anything in between. Alerts that need you to act mention you. Alerts are queued in the database and posted like the cards: keyed so a retry never doubles one, and kept until Discord accepts them. They hold only fixed text and identifiers, never email text. This finishes stage 1; the owner's acceptance test on real mail comes next.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 607, the tests Phase 1l left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_alert_text.py --ignore=tests/integration/test_alerts.py --ignore=tests/integration/test_alert_post.py --ignore=tests/integration/test_service_alerts.py --ignore=tests/integration/test_service.py --ignore=tests/integration/test_service_more.py` must show `590 passed`. The ignored files import names you create, or now expect the new `discord alerts` status line.

## Facts

- **Mentions** (Discord's reference): `<@USER_ID>` in `content` mentions a user. `allowed_mentions: {"users": [id]}` lets only that user be pinged, and `{"parse": []}` pings no one.
- **The sync result** (1c): `SyncResult(account, kind, stored, offline_since, gap)`. `kind == "catch_up"` after a rejected bookmark; `offline_since` is the last successful sync, and `gap` is true when that was over 14 days ago.
- **What signals what** (1b, 1f, 1j, 1l):
  - A Gmail sign-in problem, including a missing Gmail secret, is `GmailAuthError`; other Gmail failures are `GmailUnavailable`.
  - The model being down is `ModelUnavailable`.
  - The listener's thread ends with the reasons 1l reports.
- **Earlier tests that change**:
  - Every round now says a `discord alerts` status line, so 1l's `test_service.py` and the 1l coder's `test_service_more.py` gain that line where they list a round's lines. A revoked account also posts an alert, so one count now counts only cards (messages with embeds).
  - `probe-01l.py` counts only cards for the same reason.
  - Migration 7 makes the schema version 7, so `test_store.py`'s "newer schema" case now uses 99.

  All are given edits.

## Owner's decisions

- **The four designed alerts**: Gmail sign-in needed, the listener stopped, the model unreachable for a while, and the catch-up summary. Gmail outages that aren't sign-in problems only get a status line.
- **Recovery is announced**, in one short message, and only for a problem that was announced.
- **The model alerts after 15 minutes** unreachable.
- **Action alerts ping you** (sign-in needed, listener stopped); the model, catch-up and recovery messages don't.

## Architect's decisions

- **Two tables** (given migration 7): `problems` holds each open problem, when it began, and whether it was announced. `alerts` is the outbox, with each alert's unique key, text, ping flag, and Discord message id once posted. Neither holds email text, so neither is cleared.
- **Keys make it retry-safe.**
  - A problem's alerts are keyed `<problem>:<since>:raised` and `<problem>:<since>:resolved`, and a catch-up `catch-up:<account>:<offline_since>`, so queuing twice queues once.
  - Posting uses the alert id's first 25 characters as the nonce, as cards do.
- **What counts as fixed.**
  - A Gmail account is fixed by its next successful sync.
  - The model is fixed by a round that triaged at least one email without `ModelUnavailable`. A round with nothing to triage tells nothing either way.
  - The listener is fixed when a later service run's listener is still alive at its second round. One that dies at once never counts as running again.
- **Open problems survive a restart**, so a listener stopped yesterday is announced as running again after you fix it and restart.
- **Alerts are posted after the cards, each round,** with their own status line, `discord alerts`. An alert that can't be posted waits, like a card. No alert is sent when Discord itself can't be reached; the status line covers that.
- **The texts are given** in `discord_layout` (`ALERT_*`).
- **Critical modules**: `alerts.py` (what is announced, once, without email text).

## Examples in plain words

- Your work account's token is revoked: "@you Gmail sign-in needed for work. Run: mailroom gmail-login work". After you sign in again: "Gmail work works again."
- Ollama is restarted and is back in 5 minutes: no message at all. It's down for 20 minutes: one message at minute 15, and one when mail is triaged again.
- The Mac was off for a weekend: "Gmail personal caught up after 2 days offline: 37 new emails."
- You reset the bot token: "@you The Discord listener stopped: gateway stopped (4004)…". You fix it and restart: "The Discord listener is running again."

## Requirements

1. **Migration 7** (given) creates `problems` (`key` primary key, `since`, `alerted`) and `alerts` (`alert_id` primary key, unique `key`, `text`, `ping`, `queued_at`, `discord_message_id`, `posted_at`, the last two set together).

2. **`store.py`.**
   - **Dataclasses**, each `@dataclass(frozen=True)`:
     - `Problem`: `key: str`, `since: datetime`, `alerted: bool`
     - `Alert`: `alert_id: str`, `key: str`, `text: str`, `ping: bool`, `queued_at: datetime`, `discord_message_id: str | None`, `posted_at: datetime | None`
   - **Problems:**
     - `problem(key) -> Problem | None`.
     - `open_problem(key) -> Problem`: when absent, inserts it with `since=clock.now()` and `alerted=False`. Returns the stored one.
     - `mark_alerted(key) -> None`.
     - `close_problem(key) -> Problem | None`: deletes it, returning what was there.
   - **Alerts:**
     - `queue_alert(key, text, ping) -> bool`: when `key` is already queued, returns `False` without calling `ids.new_id()`. Otherwise it inserts with `alert_id=ids.new_id()` and `queued_at=clock.now()`, and returns `True`.
     - `pending_alerts() -> tuple[Alert, ...]` gives those not yet posted, in queue order.
     - `mark_alert_posted(alert_id, discord_message_id) -> bool` reads the clock once and sets both columns only on an alert not yet posted.
   - Every write commits.

3. **`src/mailroom/alerts.py`.**
   - **`MODEL_WAIT = timedelta(minutes=15)`.**
   - **`track(store, problem: str, failing: bool, *, wait: timedelta, raised: str, ping: bool, resolved: str) -> None`.**
     - Failing: `p = store.open_problem(problem)`. If `p` is not alerted and `clock.now() - p.since >= wait`, queue `(f"{problem}:{p.since.isoformat()}:raised", raised, ping)` and `mark_alerted`.
     - Not failing: `p = store.close_problem(problem)`. If `p` was alerted, queue `(f"{problem}:{p.since.isoformat()}:resolved", resolved, False)`.
   - **`notice(store, key: str, text: str) -> None`** queues `(key, text, False)`.

4. **`catch_up_text(account: str, offline: timedelta, count: int, gap: bool) -> str`** returns `L.ALERT_CATCH_UP` filled in (`L` is `discord_layout`), followed by `L.ALERT_GAP` when `gap` is true.
   - `offline`:
     - under an hour: `L.LESS_THAN_AN_HOUR`
     - under 48 hours: the whole hours, as `"1 hour"` or `"N hours"`
     - otherwise: the whole days, as `"N days"`
   - `found`: `"no new emails"`, `"1 new email"` or `"N new emails"`.

5. **`post_alerts(store, settings, http) -> PostReport`** works like 1h's `post_pending`:
   - an empty channel or owner raises `DiscordUnavailable("not configured")`
   - with nothing pending, it returns `PostReport(0, 0, "")` without reading the Keychain
   - it reads the token once, posts in queue order to the same address with the same headers, and uses the same stop rules (`network`, the status, `response`)
   - it marks each alert posted after a 200 with an id

   The body:
   - with `ping`: `{"content": f"<@{owner}> {text}", "allowed_mentions": {"users": [owner]}, "nonce": alert_id[:25], "enforce_nonce": True}`
   - otherwise: `{"content": text, "allowed_mentions": {"parse": []}, "nonce": ..., "enforce_nonce": True}`

6. **`service.run_round`** gains the alerts. Unchanged steps keep their status lines.
   1. **Gmail.**
      - A `GmailAuthError` also calls `track(f"gmail-auth:{account}", True, wait=timedelta(0), raised=L.ALERT_GMAIL_AUTH.format(account=account), ping=True, resolved=L.ALERT_GMAIL_FIXED.format(account=account))`.
      - A success calls the same with `False`. With `result.kind == "catch_up"` and `offline_since` set, a success also calls `notice(f"catch-up:{account}:{offline_since.isoformat()}", catch_up_text(account, clock.now() - offline_since, len(result.stored), result.gap))`.
      - Other failures don't touch the problem.
   2. **Triage.**
      - A `ModelUnavailable` also calls `track("model", True, wait=MODEL_WAIT, raised=L.ALERT_MODEL, ping=False, resolved=L.ALERT_MODEL_FIXED)`.
      - Otherwise, when at least one email was triaged this round, it calls the same with `False`.
   3. **Alerts, last.** `post_alerts(store, settings, discord_http)` reports `("discord alerts", ...)` exactly as posting does: `ok`, `waiting (<stopped>)`, or the error's text for a `DiscordUnavailable` or `KeychainError`.

7. **`service.run_service`.**
   - When the listener ends with one of 1l's reasons, the thread also calls, on its own store, `track("gateway", True, wait=timedelta(0), raised=L.ALERT_GATEWAY.format(reason=<the reported state>), ping=True, resolved=L.ALERT_GATEWAY_FIXED)`.
   - Before every round but the first, if the listener thread is alive, the main thread calls the same with `False`.

8. **Critical modules.** `scripts/critical_modules.txt` (given) lists `alerts.py`.

9. **Progress entry** for `## Phase 1m: Alerts (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Adds migration 7, `problems` and `alerts` |
| `src/mailroom/discord_layout.py` | Adds the `ALERT_*` texts and `LESS_THAN_AN_HOUR` |
| `tests/unit/test_alert_text.py` | 5 tests (requirement 4) |
| `tests/integration/test_alerts.py` | 7 tests (requirements 2 and 3) |
| `tests/integration/test_alert_post.py` | 5 tests (requirement 5) |
| `tests/integration/test_service_alerts.py` | 6 tests (requirements 6 and 7) |
| `tests/integration/test_service.py`, `tests/integration/test_service_more.py` | Gain the `discord alerts` line; one count counts only cards |
| `tests/integration/test_store.py`, `tests/integration/test_store_sync.py` | Schema version 7; the newer-schema case uses 99 |
| `scripts/critical_modules.txt` | Adds `alerts.py` |
| `docs/verification/probe-01m.py` | The verifier's probe |
| `docs/verification/probe-01l.py` | Counts only cards |

Given test count: **23** in the four new files, from 18 test functions.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_alerts_more.py`, never by changing a given test, for at least:
- `post_alerts` with a 200 that has no id (`stopped="response"`), and a network error
- `mark_alert_posted` for an unknown or already posted alert (`False`)
- a catch-up with `offline_since` of `None` (no notice)
- a round where `ModelUnavailable` comes after some emails were triaged (the problem stays open)

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store.py` | add `Problem`, `Alert` and the seven methods |
| `src/mailroom/alerts.py` | create |
| `src/mailroom/service.py` | add the alerts to `run_round` and `run_service` |
| `tests/integration/test_alerts_more.py` | create |
| `docs/progress.md` | append your entry |

## Out of scope

- **More alerts.** Gmail outages, Discord outages (it can't be told), a summary of the day, alert settings, quiet hours.
- **Stage 2 and later.** Checkpoint 2, digests, follow-ups, the tasks app.
- **Other changes.** Editing or deleting an alert message, restarting the listener, logging, any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **No email text leaves except as designed** (`AGENTS.md`): an alert holds only fixed text, account names, counts, durations and the fixed error text 1l already reports.
- **Sends are retry-safe**: each alert is keyed and posted with a nonce; a failed post waits in the database.
- **Pings only you**: a mention names only the owner, with `allowed_mentions` limited to that user.
- **Secrets**: the token is read only to post, and never appears in an alert.
- **Time and ids through the modules**: `clock.now()` and `ids.new_id()`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 23 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_alert_text.py tests/integration/test_alerts.py tests/integration/test_alert_post.py tests/integration/test_service_alerts.py tests/integration/test_service.py tests/integration/test_service_more.py --no-cov -q` | `40 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/alerts.py,src/mailroom/service.py,src/mailroom/store.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1m: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1m` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_alert_text.py tests/integration/test_alerts.py tests/integration/test_alert_post.py tests/integration/test_service_alerts.py tests/integration/test_service.py tests/integration/test_service_more.py tests/integration/test_store.py tests/integration/test_store_sync.py scripts/critical_modules.txt docs/verification/probe-01m.py docs/verification/probe-01l.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|asyncio|multiprocessing|concurrent|discord)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request' -- src
git grep --untracked -n -E 'httpx\.(Client|get|post|put|request|stream)\(' -- src/mailroom/alerts.py src/mailroom/service.py
git grep --untracked -n -E 'discord\.com|discordapp' -- src ':!src/mailroom/discord_layout.py'
git grep --untracked -n -E 'summary|subject|body_text|sender_name|record\.|extraction' -- src/mailroom/alerts.py
git grep --untracked -n -E '@everyone|@here|"roles"|"parse": \["' -- src/mailroom/alerts.py
git grep --untracked -n -E 'sleep\(|while |retry_after' -- src/mailroom/alerts.py
git grep --untracked -n -E 'raise [A-Za-z]+\(f|raise [A-Za-z]+\([a-z_.]*(token|error|value|text|json)' -- src/mailroom/alerts.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/alerts.py src/mailroom/service.py src/mailroom/store.py
```
