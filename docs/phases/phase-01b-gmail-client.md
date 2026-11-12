# Phase 1b: Gmail client

## Goal

Read one Gmail account through the Gmail REST API: get an access token from the stored refresh token, and make the four read calls sync needs (profile, history, inbox listing, raw message), with every failure turned into one of a few errors that never carry a response's text. No sync loop, bookmark storage or login yet: 1c uses this client to sync, and 1d adds the login that stores the refresh token.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 175, the tests Phase 1a left passing.

Install first (requirement 1). Then Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_gmail.py` must show `175 passed`. The ignored file imports `mailroom.gmail`, which you create.

## Facts

From the Gmail API and Google OAuth reference pages, and httpx 0.28.1 on this machine. `tests/fakes.py`'s `FakeGmail` follows these shapes.

- **Token refresh.** `POST https://oauth2.googleapis.com/token`, form-encoded: `client_id`, `client_secret`, `refresh_token`, `grant_type=refresh_token`. Success is 200 with `access_token`, `expires_in` (seconds), `scope`, `token_type` (`Bearer`). A revoked or expired refresh token gets error `invalid_grant` (the fake answers 400).
- **Profile.** `GET https://gmail.googleapis.com/gmail/v1/users/me/profile` returns `emailAddress`, `messagesTotal`, `threadsTotal` and `historyId` (a string).
- **History.** `GET .../users/me/history` takes `startHistoryId` (required), `maxResults` (default 100, at most 500), `pageToken`, `labelId` and a repeated `historyTypes` (`messageAdded`, `messageDeleted`, `labelAdded`, `labelRemoved`). It returns `history[]`, `nextPageToken` and `historyId`, the mailbox's current history ID.
  - Each record has `id`, `messages[]` and type lists: `messagesAdded[]` entries hold `message`, and `labelsAdded[]` entries hold `message` and the added `labelIds[]`.
  - Messages in records usually carry only `id` and `threadId`, so `labelId=INBOX` is what keeps history to the inbox.
  - An out-of-date `startHistoryId` gets 404; a history ID usually lasts a week but can last only hours.
- **List.** `GET .../users/me/messages` takes `maxResults` (at most 500), `pageToken`, `q` (Gmail search syntax) and repeated `labelIds`. It returns `messages[]` (`id` and `threadId` only), `nextPageToken` and `resultSizeEstimate`. Spam and trash are left out unless `includeSpamTrash` is set.
- **Get.** `GET .../users/me/messages/{id}?format=raw` returns `id`, `threadId`, `labelIds`, `internalDate` (epoch milliseconds, as a string) and `raw`, the whole RFC 822 message in base64url.
- **What the docs leave open.** They do not say whether `raw` is padded or whether empty lists are left out, so the client must accept `raw` with or without `=` padding and treat a missing list as empty. `base64.urlsafe_b64decode` needs the padding: add `"=" * (-len(text) % 4)` first. It raises `binascii.Error` (a `ValueError`) on bad input.
- **httpx.**
  - `httpx.MockTransport(handler)` lets tests answer every request with no socket.
  - A list value in `params` is sent as a repeated parameter (`historyTypes=messageAdded&historyTypes=labelAdded`).
  - `data=` is sent form-encoded.
  - Every network failure, timeouts included, is an `httpx.TransportError`.
  - `response.json()` raises a `ValueError` on bad JSON.
  - `Client.timeout`, `Client.trust_env` and `Client.follow_redirects` are readable attributes.

## Owner's decisions

- Gmail is three sub-phases: **1b** this client, **1c** sync, **1d** the login command. Stage 1 continues with 1e sender checks and rules, 1f the extractor, 1g Discord checkpoint 1, 1h the poll loop.
- Every outside call uses **httpx**.
- **One Gmail account in v1, built for more**: secrets and (in 1c) bookmarks are keyed by an account name.
- A first sync reads the last 3 days of the inbox (built in 1c).

## Architect's decisions

- **Account names** are 1 to 32 characters: a lowercase letter, then lowercase letters, digits or `-`. Secrets are `gmail.<account>.client-id`, `gmail.<account>.client-secret` and `gmail.<account>.refresh-token`, read in that order on each refresh, never cached.
- **The access token lives only in memory.** It is used while `clock.now()` is before the time it was obtained plus `expires_in` minus 60 seconds, and is refreshed after that.
- **One retry, only for a rejected token**: a 401 from the API refreshes the token and repeats the request once. Every other failure is raised for 1h to handle; no retries or backoff here.
- **Four errors** under `GmailError`, each with constant text plus the account and at most a status code. `GmailAuthError` means "sign in again" (1d's login fixes it). `GmailUnavailable` means "try later". `BookmarkExpired` means "catch up" (1c). A response's body is never put in an error.
- **Inbox only.** History asks for `labelId=INBOX`. It keeps every `messagesAdded` message, and a `labelsAdded` message only when `INBOX` is among the labels added: mail you move from spam into the inbox is triaged. Listing asks for `labelIds=INBOX` and never sets `includeSpamTrash`. Whether a fetched message is still in the inbox is 1c's check (`label_ids`).
- **The client is safe with untrusted ids**: a message id must match `[A-Za-z0-9_-]{1,256}` before it goes into a URL.
- **`open_gmail`** builds the real `httpx.Client`: a 30-second timeout, no proxy or `.netrc` from the environment (`trust_env=False`), no redirects.
- **Critical module**: `gmail.py` (it holds the read-only boundary and handles secrets).

## Requirements

1. **Install.** `pyproject.toml` (given) adds `httpx>=0.28.1,<0.29`. Run `.venv/bin/python -m pip install -e '.[dev]'` (this needs the network to reach PyPI; nothing else in this phase does). Install nothing else.

2. **`src/mailroom/gmail.py`, names.**
   - `TOKEN_URL = "https://oauth2.googleapis.com/token"`
   - `API_URL = "https://gmail.googleapis.com/gmail/v1/users/me"`
   - `SCOPE = "https://www.googleapis.com/auth/gmail.readonly"` (for 1d)
   - `PAGE_SIZE = 500`, `TIMEOUT_SECONDS = 30.0`, `TOKEN_MARGIN = timedelta(seconds=60)`
   - `ACCOUNT_MESSAGE = "invalid account name"`, `MESSAGE_ID_MESSAGE = "invalid message id"`

3. **Errors.** `class GmailError(Exception)`, and three subclasses of it. Each is raised `from None`.
   - `GmailAuthError`, text `gmail sign-in needed: <account>`
   - `GmailUnavailable`, text `gmail unavailable: <account> (<detail>)`, where the detail is the HTTP status number, `network` or `response`
   - `BookmarkExpired`, text `gmail history expired: <account>`

4. **Results**, each a `@dataclass(frozen=True)`:
   - `Profile(email_address: str, history_id: str)`
   - `MessageRef(id: str, thread_id: str)`
   - `History(added: tuple[MessageRef, ...], history_id: str)`
   - `RawMessage(id: str, thread_id: str, label_ids: tuple[str, ...], internal_date: datetime, raw: bytes)`

5. **`GmailClient(account: str, http: httpx.Client)`.**
   - **Construction.** It raises `ValueError(ACCOUNT_MESSAGE)` for an account that breaks the rule above, before anything else. It keeps both arguments as the attributes `account` and `http`, and reads no secret and makes no request when built.
   - **Requests.** All requests go through `http`, using only `http.get` and `http.post` (never `http.request`, `http.send` or `http.stream`). The client makes only these:
     - `POST TOKEN_URL`
     - `GET` of `API_URL + "/profile"`, `API_URL + "/history"`, `API_URL + "/messages"`, and `API_URL + "/messages/<id>"`

6. **Getting a token.**
   - **When.** Before each API request, if there is no token, or `clock.now()` is at or after its expiry, the client refreshes.
   - **The request.**
     1. Read the three secrets with `keychain.get_secret`, in the order above.
     2. `POST TOKEN_URL` with `data=` holding exactly `client_id`, `client_secret`, `refresh_token` and `grant_type=refresh_token`.
     3. A 200 with a string `access_token` and an integer `expires_in` sets the token, and sets its expiry to `clock.now() + timedelta(seconds=expires_in) - TOKEN_MARGIN`.
   - **What goes wrong.**
     - `keychain.SecretMissing` raises `GmailAuthError`. Other keychain errors propagate unchanged.
     - A 400 or 401 whose JSON `error` is `"invalid_grant"` raises `GmailAuthError`.
     - Any other status raises `GmailUnavailable` with the status.
   - **Using it.** API requests send `Authorization: Bearer <token>`; the token endpoint gets no `Authorization` header.

7. **A rejected token.** If an API request gets 401, the client drops its token, refreshes, and sends the same request once more. A second 401 raises `GmailAuthError`.

8. **`profile() -> Profile`** from `GET /profile`: `emailAddress` and `historyId`, both strings.

9. **`history(start_history_id: str) -> History`.**
   - **The request.** `GET /history` with params `startHistoryId`, `labelId="INBOX"`, `historyTypes=["messageAdded", "labelAdded"]` and `maxResults=PAGE_SIZE`. Each following page adds `pageToken` from the previous page's `nextPageToken`, until there is none.
   - **Which messages.** Every `messagesAdded[].message`, and every `labelsAdded[].message` whose entry's `labelIds` contains `"INBOX"`. They are kept in the order they appear across pages, with only the first occurrence of each id.
   - **The bookmark.** `history_id` is the last page's `historyId`.
   - **Errors.** A missing `history` counts as empty. A 404 raises `BookmarkExpired`.

10. **`list_inbox(after: datetime) -> tuple[MessageRef, ...]`.**
    - **The request.** `GET /messages` with params `q=f"after:{int(after.timestamp())}"`, `labelIds=["INBOX"]` and `maxResults=PAGE_SIZE`, following `nextPageToken` like history.
    - **The result.** Message refs in the order returned, first occurrence of each id. A missing `messages` counts as empty.

11. **`fetch(message_id: str) -> RawMessage`.**
    - **The id.** It raises `ValueError(MESSAGE_ID_MESSAGE)` before any request unless the id matches `[A-Za-z0-9_-]{1,256}` in full.
    - **The request.** `GET /messages/<id>` with the single param `format="raw"`.
    - **The result.**
      - `raw` is the base64url text decoded, with padding added if missing.
      - `internal_date` is `datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=int(internalDate))`.
      - `label_ids` is a tuple, empty when `labelIds` is missing.

12. **Failures of the API.**
    - **404** raises `BookmarkExpired` in `history` only. Elsewhere it is like any other status.
    - **Any status other than 200** (after requirement 7's retry) raises `GmailUnavailable` with the status.
    - **An `httpx.TransportError`** raises `GmailUnavailable` with `network`.
    - **Bad JSON**, or a field that is missing or of the wrong type, raises `GmailUnavailable` with `response`. A field is wrong if it is not a string where a string is expected, `expires_in` is not an integer, or `raw` is not valid base64url.
    - **No body in errors.** No error's text or arguments include a response body, a token or a secret.

13. **`open_gmail(account: str) -> GmailClient`** returns a client with `httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)`.

14. **Critical modules.** `scripts/critical_modules.txt` (given) lists `gmail.py`.

15. **Progress entry** for `## Phase 1b: Gmail client (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `pyproject.toml` | Adds the `httpx` dependency |
| `tests/fakes.py` | Adds `FakeGmail`: the token endpoint and the four calls, for `httpx.MockTransport` |
| `tests/integration/test_gmail.py` | 30 tests (requirements 2 to 13) |
| `scripts/critical_modules.txt` | Adds `gmail.py` |
| `docs/verification/probe-01b.py` | The verifier's probe |

Given test count: **30**.

## Tests to write

The given tests cover the main cases. Reaching full coverage of `gmail.py` will need tests of your own in `tests/integration/test_gmail_more.py`, never by changing a given test, for at least:
- a token endpoint answering 500 (`GmailUnavailable`, `(500)`)
- a token response without `access_token` (`(response)`)
- `fetch` with `raw` that is not base64url (`(response)`)
- a history page whose `historyId` is missing (`(response)`)

## Scope

| Path | Change |
|---|---|
| `src/mailroom/gmail.py` | create |
| `tests/integration/test_gmail_more.py` | create, only if coverage needs it |
| `docs/progress.md` | append your entry |

## Out of scope

- **Sync and login.** Storing bookmarks, a sync loop, catch-up, building `Envelope`s or links, the 3-day first run (1c). The browser login and any keychain write (1d).
- **Retries.** Retries of any failure other than requirement 7's, backoff, rate limiting, batching requests.
- **Other calls.** Any Gmail call not listed: no `modify`, `trash`, `send`, `batchModify`, `insert`, `import`, `delete`, `watch` or `labels`. No `format=full` or `metadata`.
- **Other changes.** Settings, a CLI command, logging. Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Mail access is read-only** (`AGENTS.md` rule 3): `GET` only to the Gmail API, `POST` only to the token endpoint.
- **Network**: only `oauth2.googleapis.com` and `gmail.googleapis.com`, and tests reach neither: they use `httpx.MockTransport` with `FakeGmail`. Never run the client against the real Google endpoints, not even to try it.
- **Secrets** come only through `keychain.get_secret`, and never appear in an error, a URL or a log. Never read the real Keychain.
- **Email text stays local**: a message's `raw` is returned to the caller and nowhere else.
- **Time through the module**: `clock.now()`, never `datetime.now()`, and never `from mailroom.clock import now`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 30 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_gmail.py --no-cov -q` | `30 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/gmail.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1b: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1b` | `Reports OK.` |
| `git diff HEAD --stat -- pyproject.toml tests/fakes.py tests/integration/test_gmail.py scripts/critical_modules.txt docs/verification/probe-01b.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing, except the fifth, which prints exactly one line (the token `POST`).

```zsh
git grep --untracked -n -E 'import (socket|ssl|imaplib|smtplib|http|urllib|requests|aiohttp)([^A-Za-z_]|$)|from (socket|ssl|imaplib|smtplib|http|urllib|requests|aiohttp)([^A-Za-z_]|$)' -- src
git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py'
git grep --untracked -n -E 'https?://' -- src/mailroom/gmail.py | grep -v -E '"https://(oauth2|gmail|www)\.googleapis\.com/'
git grep --untracked -n -E '\.(put|patch|delete|request|send|stream)\(|"(POST|PUT|PATCH|DELETE)"' -- src/mailroom/gmail.py
git grep --untracked -n -E '\.post\(' -- src/mailroom/gmail.py
git grep --untracked -n -E -i '/(modify|trash|untrash|send|batchModify|batchDelete|insert|import|watch|stop|labels|drafts|settings)([^A-Za-z_]|$)|"(full|metadata|minimal)"' -- src/mailroom/gmail.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/gmail.py
```
