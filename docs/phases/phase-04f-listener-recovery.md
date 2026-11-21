# Phase 4f: Supervise listener recovery

## Goal

A Discord listener that fails for a recoverable reason restarts on its own with a
bounded wait, while polling goes on. A terminal Gateway outcome is alerted and stays
stopped, and shutdown interrupts a restart wait. This closes the listener-side part
of audit findings 1 and 2. Lock-wait policy belongs to 4g, not this phase.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is **1337**, from the passing Phase 4e review
(`5d97024`). The finalized planning/given-file commit made after this document is
the coder's clean start.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_service_listener.py`
must show `1337 passed`. Nothing needs a missing-module stub. The given test file
imports successfully and is set aside because its behavior is not built yet.

## Facts

- Today `run_service` starts one `mailroom-gateway` thread running `_listen`, which
  opens a store and a Discord client, calls the gateway once, and on any exception
  reports a status line, raises the `gateway` alert ("won't answer until the service
  is restarted") and returns. Polling continues with no listener (audit finding 1).
- After 4e, `run_gateway` recovers malformed input itself but lets a handler or store
  exception propagate (pinned by `test_unexpected_handler_bug_is_not_swallowed`).
  Supervising those exceptions is this phase's job.
- `run_gateway` raises `GatewayStopped` for Discord's fatal closes and
  `DiscordUnavailable("not configured")` for missing settings. `keychain.get_secret`
  raises `SecretMissing` for a missing token and `KeychainUnavailable` when the
  Keychain itself fails; both are `KeychainError`.
- A SQLite connection opened on one thread raises `ProgrammingError` from any other
  thread whether or not it is closed, and Python checks the thread before the closed
  state. The given tests therefore observe closes by wrapping the module name
  `mailroom.service.open_store`, which an existing service test already patches.
- `alerts.track` keys alerts by problem and the time the problem opened, so a raised
  and a resolved alert are each queued once per problem episode.
- Validated with a throwaway scratch supervisor only (never copied in): the 40
  existing service and CLI-run tests pass unchanged, and the given tests pass 20 of
  20 runs. On predecessor code all 20 given cases fail at the missing
  `restart_wait` keyword or `RESTART_SECONDS` name.

## Owner's decisions

- **2026-11-21:** a recoverable failure restarts quietly (status line only). The owner
  is pinged only when the listener has kept failing for 15 minutes, then told once
  it is answering again.
- **2026-11-21:** restart forever, waiting 1, 2, 4, 8, 16, 32, then 60 seconds; the
  wait resets once a listener survives a full poll round.
- **2026-11-21:** a missing bot token stays terminal; an unavailable Keychain is
  recoverable.

## Architect's decisions

- The supervisor is private code in `service.py` on the existing single
  `mailroom-gateway` thread; no new module, dependency, schema, log or retry inside
  `run_gateway`. 4e's gateway behavior is unchanged.
- Restart waits use one new keyword seam on `run_service`, so tests need no real
  sleeping. Its default is the service's own stop event, which is what makes a
  wait interruptible by shutdown.
- Listener health is judged by the poll loop once per round, as the existing
  `gateway` resolution already is. All `listener` alert writes are on the poll
  thread's store; terminal `gateway` alerts stay on the listener's store as today.
- The existing `gateway` problem, texts, keys and "running again" resolution are
  unchanged; recoverable failures use a separate `listener` problem.
- Known limit, accepted: with `MAILROOM_POLL_SECONDS` shorter than the 60-second cap,
  a listener failing once a minute can look healthy for a round and reset its wait.

## Requirements

1. **Seam and constants.** `run_service` gains keyword-only
   `restart_wait: Callable[[float], bool] | None = None`, after `gateway`. `None`
   means `stop.wait` (the `stop` passed to `run_service`). It returns True when the
   service is stopping. Add `service.RESTART_SECONDS = (1, 2, 4, 8, 16, 32, 60)`,
   read when each wait is chosen (a test replaces it), and
   `service.LISTENER_WAIT = timedelta(minutes=15)`. Other parameters, their order
   and defaults are unchanged.
2. **Classification.** `GatewayStopped`, `DiscordUnavailable` and `SecretMissing`
   from an attempt are terminal. `KeychainUnavailable`, any other `Exception`, and
   a normal return while the stop event is not set are recoverable. A normal return
   with the stop event set ends the supervisor without a failure. `BaseException`
   that is not an `Exception` is not caught.
3. **Terminal outcome.** Exactly as today: status line `discord gateway: <str(error)>`,
   the `gateway` alert with that reason queued on that attempt's store, both
   resources closed, the thread ends, and no restart wait or later attempt.
4. **Attempts and resources.** Each attempt runs on the one `mailroom-gateway`
   thread and opens its own store with the module name `open_store(settings)`, then
   its own client with `open_discord_http()`, in that order, then calls
   `gateway(store, settings, http, stop=stop.is_set)`. Whatever was opened is
   closed on every exit, before any restart wait or next attempt. A failure while
   opening either one is a recoverable `Exception`. At most one attempt runs at a time.
5. **Recoverable status.** Its reason is `str(error)` for `KeychainUnavailable`,
   `ended` for an unexpected return, and `failed (<exception type name>)` otherwise;
   never exception text. Report `discord gateway: <reason>`, then wait. Before each
   attempt, report `discord gateway: running` (Health drops the repeat for the first).
6. **Backoff.** The k-th consecutive recoverable failure (k from 1) waits
   `RESTART_SECONDS[min(k - 1, 6)]` through `restart_wait`. If it returns True, or the
   stop event is set, start no further attempt and end. Nothing else resets k but
   requirement 7's healthy round.
7. **Health, once per round.** The poll loop notes the supervisor's total count of
   recoverable failures at every round. From the second round on, while the thread
   is alive, before `run_round` and next to the existing `gateway` resolution: the
   listener is healthy when that count is unchanged since the previous round and an
   attempt is running now. Healthy resets k to 0. Then call
   `alerts.track(store, "listener", not healthy, wait=LISTENER_WAIT,
   raised=L.ALERT_LISTENER.format(reason=<last recoverable reason>), ping=True,
   resolved=L.ALERT_LISTENER_FIXED)` on the poll loop's store. While the thread is
   not alive, the poll loop does not track `listener`.
8. **Shutdown and independence.** `run_service`'s existing `finally` sets the stop
   event and joins the thread; a pending default restart wait returns at once, so
   no attempt starts after it. A listener failure never stops, delays or raises out
   of the poll loop, and the poll loop never waits for the listener except in that
   join. Cross-thread supervisor state is guarded by a lock or is a single
   assignment of an immutable value.
9. **Privacy and compatibility.** No email text, exception text or secret reaches a
   status line or alert. Existing service tests, the `gateway` alert texts and keys,
   the status lines of terminal outcomes and `test_an_unexpected_gateway_error_names_only_its_type`
   keep passing unchanged. Time comes only through `clock.now()` via `alerts.track`.
10. **Progress entry** for `## Phase 4f: Supervise listener recovery (YYYY-MM-DD)` at
    the end of docs/progress.md, with actual counts and new public names.

## Given files

Committed with the finalized spec before coding; never change them as the coder.

| File | What it is |
|---|---|
| `tests/integration/test_service_listener.py` | 20 tests from 15 functions: recoverable kinds, open failure, backoff cap and reset, one listener, later press, terminal outcomes, shutdown, and the 15-minute listener alert |
| `src/mailroom/discord_layout.py` | Adds only `ALERT_LISTENER` and `ALERT_LISTENER_FIXED` |
| `docs/verification/probe-04f.py` | 48 seeded failure scripts checked for attempts, backoff, closes, concurrency, alerts and privacy |

Given test count: **20**, all new, so the minimum final suite is **1357**.

## Tests to write

Add behavior tests in `tests/integration/test_service_supervision.py` (not a `_more`
file). `service.py` is critical: every line and branch stays covered. Cover the
branches the given tests leave open, for example a recoverable exception raised
while the stop event is already set, a store-open failure, a `restart_wait` that
returns True with the stop event still clear, and the poll loop skipping `listener`
once the thread has ended. Use synthetic exceptions with private-looking text and
assert it never appears. Do not edit given or earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/service.py` | Supervisor, `restart_wait`, constants, poll-loop health tracking |
| `tests/integration/test_service_supervision.py` | New coder-written behavior/coverage tests |
| `docs/progress.md` | Append Phase 4f entry |

New tests fall in `core`; tests/sections.toml stays unchanged.

## Out of scope

- SQLite lock waits or busy handling (4g), token persistence (4h), missing-row
  guards (4i), shared Discord service migration (Stage 7).
- Changes to gateway.py, interactions.py, alerts.py, store, layouts, fakes, given
  files, earlier tests, dependencies or design documents.
- Restarting the poll loop, retrying terminal outcomes, a restart limit, logs,
  metrics, or exception text in any output.

## Rules that bite

All checks are synthetic and offline: fake gateways, MockTransport, the fake
Keychain. No real Discord, mail, model, tasks app, Keychain or data folder. A
supervisor catch must not swallow terminal outcomes as recoverable, and must not
hide a poll-loop error: the poll loop's own exceptions still end the service, as
`test_an_unexpected_round_error_stops_the_listener_and_closes_everything` pins.

## Acceptance

Run from the repository root, in order. The coverage row reads the data the check
left; the given-only run has --no-cov and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line All checks passed.; tests (core) passed; at least 1357 passed, 0 failed/skipped/xfailed, no warnings; every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include=src/mailroom/service.py --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_service_listener.py --no-cov -q` | 20 passed |
| `.venv/bin/python docs/verification/probe-04f.py` | each check line ends ok; final FAILURES 0 |
| `grep -c '^## Phase 4f: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4f` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04f-listener-recovery.md docs/verification/phase-04f-listener-recovery.md tests/integration/test_service_listener.py src/mailroom/discord_layout.py docs/verification/probe-04f.py` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may additionally write its named review |

### Searches

Each prints nothing (git grep exit 1 means no matches; above 1 is an error).

```zsh
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|time\.sleep|from mailroom\.(clock|ids) import' -- src/mailroom/service.py
git grep --untracked -n -E 'print\(|logger\.|logging\.|warnings\.warn|except BaseException|pragma: no cover|noqa|str\(error\)\}|\{error\}' -- src/mailroom/service.py
```

## Architect validation and handoff

No feature implementation was built. The given tests collect on predecessor imports
and all 20 fail at the missing keyword or constant. A throwaway scratch supervisor
(about 45 lines, deleted with the scratch clone) passed them 20 of 20 runs and the
40 existing service/CLI tests unchanged. Of 13 mutations of it, 12 were caught and
the 13th (ignoring the wait's result) is equivalent, since the loop rechecks the stop
event. It is not a reference for the coder. The probe's oracle-only mode passes; on
predecessor code it ends FAILURES 1 (48 TypeErrors), and on the scratch supervisor
FAILURES 0. Start shows 1337 passed. Given files are linted and formatted.

Before coder use, commit the finalized planning docs and given artifacts, including
the roadmap and history updates, and require a clean checkout.
