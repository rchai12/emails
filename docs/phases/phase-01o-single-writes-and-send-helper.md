# Phase 1o: Single writes and send helper

## Goal

Fix the last two findings of the [Phase 1 audit](../phase-01-audit.md).

First, the problem and alert writes can't collide. `mailroom run` has two stores on one file: the round's and the listener's. `open_problem` and `queue_alert` each read a key and then insert it, so when the other store inserts the same key in between, the second insert raises `IntegrityError` and the service exits. Each becomes one statement that does nothing on a duplicate. `close_problem` becomes one statement as well.

Second, cards and alerts are sent by one helper. `send_messages` in `discord_post.py` holds the token read, the channel URL, the headers, the stop rules and the reading of Discord's message id. `post_pending` and `post_alerts` keep only what differs: what is pending, the body, and what is marked. `run_round` reports both through one status helper.

Behaviour is otherwise unchanged: every earlier test passes as it is. Rolling a failed write back, and splitting `store.py`, wait for stage 2.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 674, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_send_messages.py --ignore=tests/integration/test_store_races.py` must show `674 passed`. `test_send_messages.py` imports `send_messages`, which you create. `test_store_races.py` imports fine, but its three tests fail until the writes are single statements.

## Facts

Each was checked on this machine (SQLite 3.54.1, Python's `sqlite3` in its default transaction mode).

- **The race is real.** Two stores on one file. Store B inserts the same key during store A's clock read, which today falls between A's `SELECT` and its `INSERT`. Then `open_problem` raises `IntegrityError: UNIQUE constraint failed: problems.key`, and `queue_alert` raises the same error for `alerts.key`. `test_store_races.py` makes B's write from the fake clock in exactly this way, so no private name is needed.
- **One statement per write.**
  - `INSERT … ON CONFLICT (key) DO NOTHING` gives `cursor.rowcount` `1` when it inserts and `0` on a duplicate. `store.py` already uses `ON CONFLICT DO NOTHING` three times.
  - `… DO NOTHING RETURNING` returns no row on a duplicate. So `open_problem` reads the stored row with a `SELECT` after its insert.
  - `DELETE … RETURNING key, since, alerted` returns the row once, and nothing on a second delete. Fetch the row, then commit.
  - SQLite has had `RETURNING` since 3.35.
- **What SQLite runs.** In the default mode, each insert, update or delete runs as `BEGIN`, the statement, then `COMMIT` on `commit()`. A `SELECT` starts no transaction. The probe traces the statements with `set_trace_callback`.
- **A failed write keeps its lock.** After an `IntegrityError`, that connection's transaction stays open, so the other connection's next write waits 5 seconds (the `sqlite3.connect` default) and then fails with `database is locked`. Closing the connection releases the lock. With this phase's statements, no known write fails. Rolling back on failure is left for stage 2 (owner's decision).
- **The two send loops are the same.** `post_pending` and `post_alerts` differ only in their configuration check, what they read as pending, the body they build, and the store method that marks an item sent. They share the token read (`keychain.get_secret(L.TOKEN_NAME)`, only when something is pending), the URL `f"{L.API_URL}/channels/{settings.discord_channel_id}/messages"`, the `Authorization` and `User-Agent` headers, and the stops: a `TransportError` stops as `"network"`, a status other than 200 as `str(status)`, and a reply without a string `id` as `"response"`. Both report `PostReport(posted, len(pending) - index, stopped)`. Each builds the body just before its send.
- **Earlier tests don't count extra reads.** The alert tests set the clock with a settable fake, never a counted list. The two fixtures that use `fixed_ids` queue each key once. So a clock read and an id on every `open_problem` and `queue_alert` call, duplicates included, changes no earlier test.

## Owner's decisions

- `open_problem`, `queue_alert` and `close_problem` each become one statement.
- Failed writes are not rolled back in this phase; that waits for the `store.py` split in stage 2.
- The shared helper covers cards, alerts and `run_round`'s status lines. `commands.py` keeps its own headers.

## Architect's decisions

- **The duplicate clause names the key.** Use `ON CONFLICT (key) DO NOTHING`, not `INSERT OR IGNORE`, which would also hide a `CHECK` or `NOT NULL` failure.
- **Clock and id first.** `open_problem` reads `clock.now()` once and `queue_alert` calls `ids.new_id()` and `clock.now()` once, every call, before their insert. The given race tests depend on the clock read coming before the write.
- **`open_problem` returns what is stored.** After a race, that is the other store's row, so both stores agree on when the problem began.
- **`send_messages` takes callables.** It is generic over the item type and builds each body only when it reaches that item. It leaves the configuration check to its callers, since alerts also need the owner's id.
- **No new names outside `discord_post.py`.** The status helper in `service.py` is private.

## Requirements

1. **`Store.open_problem(key)`** runs `INSERT INTO problems (key, since, alerted) VALUES (?, ?, 0) ON CONFLICT (key) DO NOTHING`, with `since` from one `clock.now()` read made before it. It commits, then returns the stored row as a `Problem`. It never reads the table before the insert, and never raises on an existing key.
2. **`Store.queue_alert(key, text, ping)`** runs one `INSERT INTO alerts (…) VALUES (…) ON CONFLICT (key) DO NOTHING`, with `ids.new_id()` and `clock.now()` each called once before it. It commits and returns `cursor.rowcount == 1`. It never reads the table before the insert.
3. **`Store.close_problem(key)`** runs `DELETE FROM problems WHERE key = ? RETURNING key, since, alerted`, fetches the row, commits, and returns the `Problem` or `None`. It never reads first, so it does not call `self.problem`.
4. **`send_messages(settings, http, pending, body, mark) -> PostReport`** in `discord_post.py`. `pending` is a `Sequence[T]`, `body` is a `Callable[[T], dict[str, object]]`, and `mark` is a `Callable[[T, str], object]`.
   - With nothing pending, it returns `PostReport(posted=0, waiting=0, stopped="")`, with no token read and no request.
   - Otherwise it reads the token once and sends each item in order with the URL, headers and stops given in Facts. It calls `body(item)` just before that item's send, and `mark(item, message_id)` after a 200 with an id.
   - It reports exactly as the loops do today. A keychain error passes through before any request.
   - `discord_post.py` keeps the only `_message_id`.
5. **`post_pending`** keeps its signature, its configuration check and its `store.queue_notified()`. It sends `store.pending_posts()` through `send_messages`: the body is today's `checkpoint_message(...)` and the mark is `store.mark_posted(post.item_id, message_id)`.
6. **`post_alerts`** keeps its signature and its configuration check. It sends `store.pending_alerts()` through `send_messages`, with today's two bodies (with and without the ping) and `store.mark_alert_posted(alert.alert_id, message_id)` as the mark. `alerts.py` no longer reads the keychain, posts with `http.post`, builds headers, or defines `_message_id`.
7. **`run_round`** reports both Discord parts through one private helper. It takes the part's name and the call, and reports `str(error)` on `DiscordUnavailable` or `KeychainError`, `f"waiting ({report.stopped})"` when the report stopped, and `"ok"` otherwise. The text `waiting (` appears once in `service.py`. The status lines are unchanged.
8. **Progress entry** for `## Phase 1o: Single writes and send helper (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/integration/test_send_messages.py` | `send_messages`: nothing pending, order, marks, token read once, URL and headers, each stop (5 cases) with nothing built after it, a missing token |
| `tests/integration/test_store_races.py` | Two stores on one file: `open_problem` and `queue_alert` racing the other store's write of the same key, and `close_problem` without a read first |
| `docs/verification/probe-01o.py` | The verifier's probe |

Given test count: **11**.

## Tests to write

The given tests cover every requirement's main cases. Requirements 5 to 7 change no behaviour, so the earlier tests of `post_pending`, `post_alerts` and `run_round` keep covering them unchanged. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store.py` | `open_problem`, `queue_alert`, `close_problem` |
| `src/mailroom/discord_post.py` | `send_messages`; `post_pending` uses it |
| `src/mailroom/alerts.py` | `post_alerts` uses `send_messages` |
| `src/mailroom/service.py` | the shared status helper |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Rolling back a failed write (`with self._connection:` or any other form), a busy timeout, or `BEGIN IMMEDIATE`.
- Splitting `store.py`, or changing any other store method, `mark_alerted` included.
- A schema change or a migration.
- `commands.py`'s headers, the interaction callbacks, or the Gateway.
- Waiting on `retry_after`, retrying within a round, or any other change to the stop rules.
- Any change to `PostReport`, a body, a status line, or an error message.
- Any change to a given or earlier test, `AGENTS.md` or the design docs.

## Rules that bite

- **Sends are retry-safe.** Every body keeps its `nonce` and `enforce_nonce`, and nothing is marked sent without Discord's id.
- **Email text stays local.** Only the card body carries email text, built by `checkpoint_message` as today. The helper never logs or reports a body.
- **The bot token is never echoed.** It goes only into the `Authorization` header. Errors stay the pinned ones (`DiscordUnavailable("not configured")`, the stop names).
- **Time and ids through the modules**: `clock.now()` and `ids.new_id()`, never `datetime.now()`, and never `from mailroom.clock import now`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 11 = 685 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_send_messages.py tests/integration/test_store_races.py --no-cov -q` | `11 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/store.py,src/mailroom/discord_post.py,src/mailroom/alerts.py,src/mailroom/service.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `git grep -c 'waiting (' -- src/mailroom/service.py` | `src/mailroom/service.py:1` |
| `grep -c "^## Phase 1o: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1o` | `Reports OK.` |
| `git diff HEAD --stat -- tests/integration/test_send_messages.py tests/integration/test_store_races.py docs/verification/probe-01o.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'http\.post\(|keychain|Bot \{|def _message_id|TransportError' -- src/mailroom/alerts.py
git grep --untracked -n -E 'def _message_id|\.json\(\)\["id"\]' -- src ':!src/mailroom/discord_post.py'
git grep --untracked -n -E 'Bot \{token\}' -- src ':!src/mailroom/discord_post.py' ':!src/mailroom/commands.py'
git grep --untracked -n -E 'sleep\(|retry_after|while ' -- src/mailroom/discord_post.py src/mailroom/alerts.py
git grep --untracked -n -E 'OR IGNORE|BEGIN IMMEDIATE|isolation_level|with self\._connection' -- src/mailroom/store.py
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|asyncio|subprocess|multiprocessing|concurrent|discord)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request' -- src
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/store.py src/mailroom/discord_post.py src/mailroom/alerts.py src/mailroom/service.py
```
