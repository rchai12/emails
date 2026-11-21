# Phase 4g: Bound SQLite contention

## Goal

When the database file is locked by another connection, each side waits a bounded,
explicit time and then fails cleanly. A press is asked privately to try again, and a
poll round is skipped and retried, instead of the error ending the listener or the
service. A wait that runs out leaves no half-written change and no open transaction.
This closes the database side of audit finding 2; the listener side was 4f.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is **1364**, from the passing Phase 4f review
(`2d0a575`). The finalized planning/given-file commit made after this document is
the coder's clean start.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_store_busy.py --ignore=tests/integration/test_interactions_busy.py --ignore=tests/integration/test_service_busy.py --deselect tests/unit/test_store_package.py::test_the_store_keeps_exactly_its_public_methods --deselect "tests/unit/test_store_package.py::test_each_method_lives_in_its_area[set_lock_wait]"`
must show `1363 passed, 2 deselected`. The two deselected cases are this phase's
given edit to an earlier test. They fail until `set_lock_wait` exists. Nothing needs
a missing-module stub, and the three new given files import before the feature exists.

## Facts

- The store uses SQLite's rollback journal (`journal_mode` is `delete`) with
  `secure_delete` on. Every connection waits SQLite's default 5 seconds for a lock.
  Then it raises `sqlite3.OperationalError` with `sqlite_errorcode` 5 (`SQLITE_BUSY`)
  or, for a table lock, 6 (`SQLITE_LOCKED`). Extended codes keep the primary code in
  their low byte: 517 is `SQLITE_BUSY_SNAPSHOT`. `PRAGMA busy_timeout` on an open
  connection replaces its wait. An `OperationalError` built by hand has no
  `sqlite_errorcode` attribute.
- Another connection's write lock (`BEGIN IMMEDIATE`) leaves reads working and makes
  writes wait. A read lock (an open read transaction) lets a write start, but the
  commit must wait.
- `StoreBase._write` rolls back when the body raises, but not when `commit()` itself
  raises. A failed commit leaves the transaction open, so the store keeps its write
  lock and blocks every other writer (seen in a planning spike). Each store write is
  one `_write`, so it is all or nothing once commit failures are rolled back.
- Today a busy error from the poll loop's store escapes `run_round` and ends
  `mailroom run`. From a press, it escapes `handle_interaction` and `run_gateway`,
  and the 4f supervisor restarts the listener with `failed (OperationalError)`.
  Discord never gets an answer to that press.
- Discord must receive an interaction's callback within 3 seconds.
- A press answers with one callback after its store work. Mute writes the sender
  status, then the answer. Both writes are idempotent or conditional: a second
  answer is refused by `NOT EXISTS`, and a sender status is an upsert. So pressing
  again after a busy failure between them finishes the answer once.
- Channel posts carry a nonce with `enforce_nonce`. The fake Discord returns the
  first message for a repeated nonce, as Discord does.
- The 4f given tests and probe wrap `mailroom.service.open_store` with a
  one-argument function. So the service keeps calling `open_store(settings)` and
  sets the wait on the store it gets back.
- Validated with a throwaway scratch stand-in only (never copied in):
  - 857 existing integration and CLI-run tests pass unchanged.
  - The given tests pass 6 of 6 runs.
  - On predecessor code all 43 given cases fail at the missing `is_busy`,
    `set_lock_wait` or `POLL_LOCK_SECONDS` names.

## Owner's decisions

- **2026-11-21:** a press or command that meets a lock timeout gets a private reply,
  `Mailroom is busy right now. Press again in a moment.`. The card and the
  listener are left as they are.
- **2026-11-21:** a poll round that meets a lock timeout is skipped and shown as a
  status line, and the next round tries again. The owner is pinged only once the
  database has stayed locked for 15 minutes, then told once it is free.
- **2026-11-21:** the listener's store waits 1.5 seconds for a lock, which leaves
  time to answer within Discord's 3 seconds. The poll loop's store waits 10 seconds.

## Architect's decisions

- No WAL, no new connection type, no change to `open_store` or `Store(path)`. One
  new store method sets an open store's wait. Stores opened elsewhere, such as CLI
  commands, keep SQLite's default.
- Lock errors are classified only by SQLite's error code, through one predicate.
  Message text is never used. Every other `OperationalError` behaves as before:
  it propagates.
- No SQL is retried or replayed inside the store. Recovery is the owner pressing
  again, or the next poll round, which reruns that round's normal work.
- The 15-minute ping cannot use the alert queue, because a database held locked
  cannot store it. The poll loop keeps the episode in memory and posts the ping
  directly, keyed by one nonce per episode. The "free again" notice uses the queue,
  since the database is writable by then. A service restart forgets an open
  episode (accepted).
- Known limit, accepted: a press makes several store calls and each may wait up to
  1.5 seconds. Under heavy, intermittent contention a press can therefore miss
  Discord's 3 seconds. Discord shows its own failure, and pressing again is safe.

## Requirements

1. **Store wait.** Add `StoreBase.set_lock_wait(seconds: float) -> None` in
   `store/base.py`. It sets this store's connection to wait `seconds` for a lock,
   and a later call replaces it. Journal mode, `secure_delete`, isolation and
   `open_store` stay as they are.
2. **Busy predicate.** Add `is_busy(error: BaseException) -> bool` in
   `store/base.py`, exported from `mailroom.store` and its `__all__`. It returns
   True exactly when `error` is an `sqlite3.OperationalError` whose integer
   `sqlite_errorcode`, masked with `0xFF`, is 5 or 6. Everything else is False,
   including a missing code, other `sqlite3` error classes and any other exception.
3. **Atomic writes.** When `_write`'s `commit()` raises, roll back before the error
   propagates, as for a failure in the body. No other store change.
4. **Waits used by the service.** Add `service.POLL_LOCK_SECONDS = 10.0`,
   `service.LISTENER_LOCK_SECONDS = 1.5` and
   `service.STORE_WAIT = timedelta(minutes=15)`. Each is read when it is used, and
   tests replace them.
   - `run_service` calls `set_lock_wait(POLL_LOCK_SECONDS)` on its store right after
     `open_store(settings)`.
   - Each listener attempt calls `set_lock_wait(LISTENER_LOCK_SECONDS)` on its own
     store right after opening it.
5. **Busy press.** `handle_interaction` keeps its signature. A busy error (requirement
   2) raised while it handles an event is caught. It sends the callback
   `_private(L.BUSY_TEXT)` and returns `"busy"`. A non-busy error propagates
   unchanged, with no callback. Owner, channel and shape checks run as before, so a
   press they refuse is never answered as busy. `gateway.py` is unchanged.
6. **Busy round.** In the poll loop, a round's guarded part is everything a round does
   except the poll wait: the 4f listener and `gateway` tracking, `run_round`, and
   requirement 7's end-of-episode work.
   - A busy error there skips the rest of that round.
   - The loop reports `store: busy` and waits `poll_seconds` as usual, then tries
     the next round.
   - A non-busy error propagates and ends the service, as today.
   - A busy round never stops, restarts or delays the listener.
7. **Episode and alerts.** An episode starts on the first busy round after a completed
   round, or at startup. It records `since = clock.now()` and one 25-character nonce,
   `ids.new_id()[:25]`. It ends on the next round that completes.
   - On a busy round where `clock.now() - since >= STORE_WAIT` and the ping is not
     yet posted, post one channel message through the poll loop's Discord client
     (for example with `discord_post.send_messages`). Its body is
     `{"content": f"<@{owner}> {L.ALERT_STORE_BUSY}", "allowed_mentions": {"users": [owner]}, "nonce": <nonce>, "enforce_nonce": True}`.
     It counts as posted only when Discord confirms it. A `KeychainError`, a non-200
     response, a transport error or a lost reply leaves it unposted for the next busy
     round, with the same nonce. None of these raises out of the loop.
   - The round that ends an episode reports `store: ok`. If the episode's ping was
     posted, the round also calls
     `alerts.notice(store, f"store:{since.isoformat()}:resolved", L.ALERT_STORE_FIXED)`
     inside the guarded part. If that call is busy, the episode stays open.
   - No `store:` status line or store alert appears in a service that never meets a
     lock. A new episode gets a new `since` and nonce.
8. **No leaks, no duplicates.** After any busy failure, once the other connection lets
   go, the file can be write-locked at once. Nothing is half-written. Pressing again
   records one answer. No approval, post or task is duplicated.
9. **Privacy and compatibility.**
   - No email text, SQL, exception text or secret reaches a reply, status line or
     alert.
   - Existing tests, including the 4f given tests, keep passing unchanged.
   - Time comes only through `clock.now()`, and ids only through `ids.new_id()`.
10. **Progress entry** for `## Phase 4g: Bound SQLite contention (YYYY-MM-DD)` at the
    end of docs/progress.md, with actual counts and new public names.

## Given files

Committed with the finalized spec before coding; never change them as the coder.

| File | What it is |
|---|---|
| `tests/integration/test_store_busy.py` | 24 cases from 12 functions: wait length, reads under a write lock, rollback journal kept, contention that clears, commit failure rolled back, many-row write kept whole, error classification |
| `tests/integration/test_interactions_busy.py` | 10 cases from 7 functions: busy press, command and form reply; press again answers once; Mute split between its two writes; refused press not answered as busy; non-lock error not hidden |
| `tests/integration/test_service_busy.py` | 9 tests: the 10 s and 1.5 s waits, skipped round then catch-up, no line when untroubled, no alert under 15 minutes, one ping then "free again", lost-reply retry with the same nonce, a second episode, listener left running, non-lock error still fatal |
| `tests/unit/test_store_package.py` | Adds only `"set_lock_wait": "base"` to `METHODS` (one new parametrized case) |
| `src/mailroom/discord_layout.py` | Adds only `BUSY_TEXT`, `ALERT_STORE_BUSY` and `ALERT_STORE_FIXED` |
| `docs/verification/probe-04g.py` | 40 seeded lock/operation scripts on a real store and real SQLite errors, checked against an independent oracle |

Given test count: **44** new cases (43 in the new files, 1 in the package test), so
the minimum final suite is **1408**.

## Tests to write

Add behavior tests in `tests/integration/test_lock_waits.py` (not a `_more` file).
`service.py`, `interactions.py`, `store/base.py` and `store/__init__.py` are critical:
every line and branch stays covered. Cover the branches the given tests leave open,
for example:

- a ping that fails on a missing bot token, then posts on a later busy round;
- a ping answered with a non-200 status;
- a busy end-of-episode notice that keeps the episode open;
- a busy error raised by the listener or `gateway` tracking rather than `run_round`;
- a busy reply whose callback Discord refuses.

Use synthetic data and assert that no private-looking text appears. Do not edit
given or earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store/base.py` | `set_lock_wait`, `is_busy`, commit-failure rollback |
| `src/mailroom/store/__init__.py` | Export `is_busy` |
| `src/mailroom/interactions.py` | Busy reply in `handle_interaction` |
| `src/mailroom/service.py` | Lock-wait constants, waits set, busy round, episode ping and notice |
| `tests/integration/test_lock_waits.py` | New coder-written behavior/coverage tests |
| `docs/progress.md` | Append Phase 4g entry |

New tests fall in `core`; tests/sections.toml stays unchanged.

## Out of scope

- WAL or other journal modes, connection pools, a separate alert database, retry
  loops or SQL replay inside the store, and changing `open_store`'s signature.
- Changes to gateway.py, alerts.py, discord_post.py, layouts beyond the given texts,
  fakes, given files, earlier tests, dependencies or design documents.
- Token persistence (4h), missing-row guards (4i), the shared Discord service
  (Stage 7).
- Logs, metrics or exception text in any output.

## Rules that bite

All checks are synthetic and offline: fake Discord, fake Gmail, fake model, the fake
Keychain and temporary database files. Never touch real mail, Discord, the tasks app,
the Keychain or the data folder. Never decide "busy" from message text. Never catch
a non-lock error as busy, since `test_an_unexpected_round_error_stops_the_listener_and_closes_everything`
and the given non-lock tests pin that it still ends the run or propagates.

## Acceptance

Run from the repository root, in order. The coverage row reads the data the check
left; the given-only run has --no-cov and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line All checks passed.; tests (core) passed; at least 1408 passed, 0 failed/skipped/xfailed, no warnings; every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include=src/mailroom/service.py,src/mailroom/interactions.py,src/mailroom/store/base.py,src/mailroom/store/__init__.py --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_store_busy.py tests/integration/test_interactions_busy.py tests/integration/test_service_busy.py tests/unit/test_store_package.py --no-cov -q` | 102 passed |
| `.venv/bin/python docs/verification/probe-04g.py` | each check line ends ok; final FAILURES 0 |
| `grep -c '^## Phase 4g: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4g` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04g-sqlite-contention.md docs/verification/phase-04g-sqlite-contention.md tests/integration/test_store_busy.py tests/integration/test_interactions_busy.py tests/integration/test_service_busy.py tests/unit/test_store_package.py src/mailroom/discord_layout.py docs/verification/probe-04g.py` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may additionally write its named review |

### Searches

Each prints nothing (git grep exit 1 means no matches; above 1 is an error).

```zsh
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|time\.sleep|time\.monotonic|from mailroom\.(clock|ids) import' -- src/mailroom/service.py src/mailroom/interactions.py src/mailroom/store/base.py
git grep --untracked -n -E 'print\(|logger\.|logging\.|warnings\.warn|pragma: no cover|noqa|\{error\}|str\(error\)\}|except BaseException' -- src/mailroom/interactions.py src/mailroom/store/__init__.py
git grep --untracked -n -i -w -E 'wal|journal_mode|locking_mode|isolation_level|secure_delete *= *off' -- src/mailroom
git grep --untracked -n -E 'busy_timeout|sqlite3\.connect|sqlite_errorcode|sqlite_errorname|database is locked' -- src/mailroom ':(exclude)src/mailroom/store/base.py'
```

## Architect validation and handoff

No feature implementation was built. The given tests collect on predecessor imports
and all 43 new cases fail at the missing names. The edited package test fails its 2
`set_lock_wait` cases.

A throwaway scratch stand-in (about 90 changed lines, deleted with the scratch clone) did the
following. It is not a reference for the coder.

- It passed the given tests 6 of 6 runs, under 3 seconds each.
- It passed 857 existing integration and CLI-run tests unchanged.
- 17 of 17 mutations of it were caught. They covered the commit rollback, the code
  mask, the error class, the code check, the press catch, both waits, the ping,
  its 15-minute wait, its nonce, its once-only rule, the episode start and end, the
  resolved notice, non-lock errors and the untroubled status.

The probe results:

- Oracle-only mode passes.
- On predecessor code it ends FAILURES 2 (ImportError).
- On the stand-in it ends FAILURES 0.
- It catches a missing commit rollback, a code-blind predicate, a missing press
  catch and a public busy reply.

The searches are silent on predecessor and stand-in, and each catches a planted
line. Start shows 1363 passed, 2 deselected. Given files are linted and formatted.

Before coder use, commit the finalized planning docs and given artifacts, including
the roadmap and history updates, and require a clean checkout.
