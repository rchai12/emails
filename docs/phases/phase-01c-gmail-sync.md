# Phase 1c: Gmail sync

## Goal

Bring new inbox mail from one Gmail account into the database: keep a sync bookmark per account, read the last 3 days on a first run, follow Gmail's history after that, and catch up from a listing when the bookmark has expired. Each new message is fetched once, parsed by the shared parser and stored, and a failure part-way loses nothing. No poll loop, Discord message or triage yet: 1g posts the catch-up message from this phase's result, and 1h calls the sync every minute or two.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 212, the tests Phase 1b left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_store_sync.py --ignore=tests/integration/test_gmail_sync.py` must show `212 passed`. The ignored files import names you create. The given schema change is already in place, so `tests/integration/test_store.py` (given, now expecting schema version 2) passes from the start.

## Facts

From the code on this machine (`mailroom.gmail`, `mailroom.record`, `mailroom.mime`, `mailroom.store`) and `tests/fakes.py`.

- **The client** (`GmailClient`, Phase 1b): `profile()` gives `Profile(email_address, history_id)`; `history(start)` gives `History(added, history_id)` and raises `BookmarkExpired` on a 404; `list_inbox(after)` gives `MessageRef(id, thread_id)`s newest first; `fetch(id)` gives `RawMessage(id, thread_id, label_ids, internal_date, raw)` and raises `ValueError("invalid message id")` before any request for an id that is not `[A-Za-z0-9_-]{1,256}`. Today a 404 from `fetch` raises `GmailUnavailable` `(404)`; no test pins that.
- **History ids.** The profile's `historyId` is the mailbox's current one. Anything that changes the mailbox after it is read appears in a later `history` call, so a bookmark read *before* listing misses nothing; a message seen twice is skipped by deduplication.
- **What history reports.** 1b asks only for `messageAdded` and `labelAdded` in the inbox. Archiving, deleting or a move to spam is not reported, so a message can be in the history and no longer in the inbox. Its `label_ids` at fetch time say where it is now.
- **The record.** `Envelope(provider, message_id, thread_id, received_at, link)` raises `ValueError("invalid record field: <name>")` for an id with a space or unprintable character or over 1,000 characters, a link that is not `https://` or has a space, or a `received_at` without a time zone. `mime.parse_message(raw: bytes, envelope: Envelope) -> Record` never raises.
- **The store.** `Store.get(provider, message_id)` returns `None` for an unknown message. `Store.add(record)` returns `True` only when it adds a new row, and commits each row. Times are stored as UTC text by the private `_stamp` and read back by `_read_time`.
- **The link.** `urllib.parse.quote(address, safe="@")` turns `owner+mail@example.test` into `owner%2Bmail@example.test`, and encodes `#`, spaces, `%` and non-ASCII letters, so an address cannot break the link.
- **The fake.** `FakeGmail` answers `404` to `fetch` of an id that is not in `messages`, and to `history` when `startHistoryId` is below `oldest_history_id`. Tests change `messages[id]["labelIds"]` directly to archive a message without a history record.

## Owner's decisions

- A first sync reads the last **3 days** of the inbox (Phase 1b's planning).
- **Mail that leaves the inbox before it is fetched is skipped**: archived, deleted, moved to spam or trash. A deleted message never blocks the sync.
- **The link picks the account by address**: `https://mail.google.com/mail/?authuser=<address>#all/<message id>`, so it opens the right mailbox when several Google accounts are signed in.

## Architect's decisions

- **One function, `sync_gmail(client, store)`**, does one sync and returns a `SyncResult`. It holds no state between calls; the bookmark lives in the new `sync_state` table (given migration 2), keyed by provider and account.
- **The profile comes first** in every sync: it gives the address for links and, on a first run or a catch-up, the new bookmark, read before anything is listed.
- **The bookmark is saved last**, with the time the sync started, only after every message has been handled. A failure leaves the old bookmark, keeps what was already stored, and the next sync repeats the work; deduplication makes that safe and skips the fetch of a stored message.
- **Catch-up** lists inbox mail received after the last successful sync minus one hour (an overlap, since `internalDate` and history order can disagree slightly), but never more than 14 days back. `gap` is set when the last successful sync is more than 14 days old, so 1g's message can say so.
- **A message that cannot be used is skipped**, never retried: gone (`MessageGone`, a new 1b error for a 404 on `fetch`), an id `fetch` refuses, or an envelope the record refuses. Every other error propagates; the poll loop (1h) decides what to do.
- **Identities.** `message_id` is the ref's id (the one `fetch` checked), `thread_id` and `received_at` come from the fetched message.
- **Critical module**: `gmail_sync.py`, since it decides what reaches triage.

## Requirements

1. **`store.py`: `SyncState`**, a `@dataclass(frozen=True)` with `bookmark: str` and `synced_at: datetime`.

2. **`store.py`: two methods on `Store`.**
   - `sync_state(provider: str, account: str) -> SyncState | None` reads the `sync_state` row, with `synced_at` back as an aware UTC `datetime`; `None` if there is no row.
   - `save_sync_state(provider: str, account: str, state: SyncState) -> None` inserts the row or replaces the one already there, storing `synced_at` as UTC text like every other time in the file, and commits.

3. **`gmail.py`: `MessageGone(GmailError)`**, text `gmail message gone: <account>`, raised `from None` by `fetch` when the API answers 404 (after 1b's single 401 retry). Every other call's 404 is unchanged: `BookmarkExpired` in `history`, `GmailUnavailable` `(404)` elsewhere.

4. **`src/mailroom/gmail_sync.py`, names.**
   - `FIRST_RUN = timedelta(days=3)`, `CATCH_UP_LIMIT = timedelta(days=14)`, `CATCH_UP_OVERLAP = timedelta(hours=1)`
   - `LINK = "https://mail.google.com/mail/?authuser={address}#all/{message_id}"`

5. **`SyncResult`**, a `@dataclass(frozen=True)`:
   - `account: str`, the client's account
   - `kind: Literal["first", "history", "catch_up"]`
   - `stored: tuple[str, ...]`, the ids of messages this sync added to the database, in the order handled
   - `offline_since: datetime | None`, the previous `synced_at` on a catch-up, else `None`
   - `gap: bool`, `True` only on a catch-up whose previous `synced_at` is more than `CATCH_UP_LIMIT` before now

6. **`sync_gmail(client: GmailClient, store: Store) -> SyncResult`: the start.**
   1. Read `now = clock.now()` once.
   2. Read `state = store.sync_state("gmail", client.account)`.
   3. Call `client.profile()`, before any other Gmail call.

7. **Which messages.**
   - **First run** (no state): refs from `client.list_inbox(now - FIRST_RUN)`; the new bookmark is the profile's `history_id`.
   - **History** (a state): refs from `client.history(state.bookmark).added`; the new bookmark is that history's `history_id`.
   - **Catch-up** (`history` raised `BookmarkExpired`): refs from `client.list_inbox(max(state.synced_at - CATCH_UP_OVERLAP, now - CATCH_UP_LIMIT))`; the new bookmark is the profile's `history_id`.

8. **Each ref, in order.**
   1. Skip it if `store.get("gmail", ref.id)` is not `None`, without fetching it.
   2. `client.fetch(ref.id)`. Skip it on `MessageGone` or `ValueError`.
   3. Skip it unless its `label_ids` contain `"INBOX"` and contain neither `"SPAM"` nor `"TRASH"`.
   4. Build `Envelope(provider="gmail", message_id=ref.id, thread_id=<fetched thread_id>, received_at=<fetched internal_date>, link=LINK.format(address=quote(<profile email_address>, safe="@"), message_id=ref.id))`. Skip it on `ValueError`.
   5. `store.add(mime.parse_message(<fetched raw>, envelope))`; if that returns `True`, add `ref.id` to `stored`.

9. **The end.** After every ref, `store.save_sync_state("gmail", client.account, SyncState(bookmark=<new bookmark>, synced_at=now))`, then return the `SyncResult`.

10. **Failures.** Any exception other than those requirement 8 skips (every other `GmailError`, a store error) propagates unchanged, and `sync_state` is not saved. Messages stored before it stay stored. No retry, no logging.

11. **Critical modules.** `scripts/critical_modules.txt` (given) lists `gmail_sync.py`.

12. **Progress entry** for `## Phase 1c: Gmail sync (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Adds migration 2: the `sync_state` table |
| `tests/integration/test_store.py` | Two lines now expect schema version 2 |
| `tests/integration/test_store_sync.py` | 4 tests (requirements 1 and 2) |
| `tests/integration/test_gmail_sync.py` | 21 tests (requirements 3 to 10) |
| `scripts/critical_modules.txt` | Adds `gmail_sync.py` |
| `docs/verification/probe-01c.py` | The verifier's probe |

Given test count: **25** (in `test_store_sync.py` and `test_gmail_sync.py`).

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_gmail_sync_more.py`, never by changing a given test, for at least:
- a 404 from `profile` is still `GmailUnavailable` `(404)`, not `MessageGone` (requirement 3)

## Scope

| Path | Change |
|---|---|
| `src/mailroom/gmail_sync.py` | create |
| `src/mailroom/store.py` | add `SyncState` and the two methods |
| `src/mailroom/gmail.py` | add `MessageGone` and raise it from `fetch` |
| `tests/integration/test_gmail_sync_more.py` | create |
| `docs/progress.md` | append your entry |

## Out of scope

- **Running it.** A poll loop, a schedule, a CLI command, settings for accounts (1h). The Discord message about a catch-up (1g). Triage of what was stored (1e onward). Calling `clear_expired_text`.
- **More than asked.** Retries, backoff, parallel or batched fetches, a page or message limit, logging, metrics.
- **Other providers and the login** (1d, stages 4 and 5).
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Mail access is read-only** (`AGENTS.md` rule 3): the sync uses only `GmailClient`'s four read calls, and nothing in `gmail.py` gains a write call.
- **Email text stays local**: a fetched message goes to the parser and the store, nowhere else; no error or result holds any of it.
- **Deduplication**: a message is stored once, keyed by provider and message ID, however often a sync repeats.
- **Tests use the fakes** (`FakeGmail`, the fake keychain, a temporary data folder), never a real account or the real data folder.
- **Time through the module**: `clock.now()`, never `datetime.now()`, and never `from mailroom.clock import now`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 25 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_store_sync.py tests/integration/test_gmail_sync.py --no-cov -q` | `25 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/gmail_sync.py,src/mailroom/store.py,src/mailroom/gmail.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1c: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1c` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_gmail_sync.py scripts/critical_modules.txt docs/verification/probe-01c.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing, except the fourth, which prints exactly one line (the token `POST`).

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|http|requests|aiohttp)([^A-Za-z_]|$)|urllib\.request|(import|from) urllib([^.A-Za-z_]|$)' -- src
git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py'
git grep --untracked -n -E '\.(put|patch|delete|request|send|stream)\(|"(POST|PUT|PATCH|DELETE)"' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py
git grep --untracked -n -E '\.post\(' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py
git grep --untracked -n -E -i '/(modify|trash|untrash|send|batchModify|batchDelete|insert|import|watch|stop|labels|drafts|settings)([^A-Za-z_]|$)|"(full|metadata|minimal)"' -- src/mailroom/gmail.py src/mailroom/gmail_sync.py
git grep --untracked -n -E 'https?://' -- src/mailroom/gmail_sync.py | grep -v -F '"https://mail.google.com/mail/?authuser={address}#all/{message_id}"'
git grep --untracked -n -E 'sqlite3|\.execute|\._[a-z]' -- src/mailroom/gmail_sync.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/gmail_sync.py src/mailroom/store.py src/mailroom/gmail.py
```
