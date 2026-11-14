# Phase 4a: Graph client

## Goal

Read a live.com mailbox through Microsoft Graph, read-only, against a fake. This is stage 4's first part, as Phase 1b was for Gmail.

`OutlookClient` gets an access token from a refresh token as a public client, and saves the new refresh token Microsoft returns each time. It offers four read calls:
- the profile;
- a first delta round of the inbox since a moment;
- a later delta round from a stored link;
- one message's raw MIME with its folder and link.

Every failure is a named error that carries no token or reply text.

Nothing calls the client yet. Outlook sync is 4b, `mailroom outlook-login` 4c, and the service 4d.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 1090, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_outlook.py` must show `1090 passed`. The ignored file imports `mailroom.outlook`, which you create.

## Facts

Each was checked in Microsoft's documentation (Microsoft identity platform: auth code flow, redirect URIs; Microsoft Graph: delta query, messages delta, MIME, immutable ids). Nothing here was checked against a real Microsoft account.

- **Personal accounts sign in at the `consumers` tenant.** The token endpoint is `https://login.microsoftonline.com/consumers/oauth2/v2.0/token`.
- **A desktop app is a public client.** It "must not use secrets" when it redeems a code or refreshes. The refresh request is a form of `client_id`, `refresh_token`, `grant_type=refresh_token` and `scope`, with no `client_secret`.
- **Refresh tokens rotate.** A refresh answers with a new `refresh_token`, and Microsoft says to "replace the old refresh token with this newly acquired refresh token". The client must therefore write the Keychain, which the Gmail client never does. `keychain.set_secret` exists from 1d.
- **`offline_access` is needed for a refresh token.** The scope is `https://graph.microsoft.com/Mail.Read offline_access`. `Mail.Read` is read-only; `Mail.ReadWrite` and `Mail.Send` are never asked for.
- **Delta works per folder.**
  - `GET /me/mailFolders/inbox/messages/delta` accepts `changeType=created`, `$select`, and `$filter=receivedDateTime ge <time>`. The filter limits a round to 5,000 messages.
  - Pages carry one of `@odata.nextLink` or `@odata.deltaLink`. The tokens are opaque, and the links are to be "copied and applied" exactly, with no query added again.
  - `Prefer: odata.maxpagesize=<n>` sets the page size.
  - A removed item arrives as `{"id", "@removed": {...}}`.
  - An expired link answers `410 Gone`, or a 4xx with the code `syncStateNotFound`.
- **Immutable ids:** with `Prefer: IdType="ImmutableId"` on every request, a message's id survives moves between folders, and delta links work with either id form. Both preferences share one `Prefer` header, separated by a comma (RFC 7240).
- **Raw MIME** is `GET /me/messages/<id>/$value`.
- **A page link is followed only to Graph.** A page link carries the bearer token when followed, so one pointing elsewhere would leak it. The client follows only `https://graph.microsoft.com` links whose path is an inbox delta path.
- **httpx collapses dot segments** (3b), so a message id is used in a path only if it matches `[A-Za-z0-9_=-]{1,512}`.
- **The fake is given.** `tests.fakes.FakeGraph` (its docstring is the contract) is stricter than Microsoft in three ways:
  - only the latest refresh token works;
  - every Graph request must carry the immutable-id preference;
  - only the calls this phase makes are answered.

## Owner's decisions

- **Personal accounts only.** The `consumers` tenant, not `common`. Work accounts would mean registering again.
- **Browser sign-in, like Gmail** (4c): Microsoft's page, answered on a one-request listener on 127.0.0.1 with PKCE.
- **Stage 4's split:** 4a the client, 4b sync, 4c login, 4d the service.

## Architect's decisions

- **Keychain names** are `outlook.<account>.client-id` and `outlook.<account>.refresh-token`. There is no client secret.
- **A missing new refresh token keeps the old one.** One that is present but not a non-empty string is a malformed reply.
- **The client doesn't decide what's new.** Delta returns every created item in its round, including ones later moved out. 4b checks each message's folder at fetch, as Gmail sync checks labels.
- **A bad id in a delta page fails the round** (`response`) rather than being skipped. A skipped id would be mail never seen, and the status line makes a failure visible.
- **One page size** for every round: 50.

## Requirements

1. **`src/mailroom/outlook.py`, names:**
   - `TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"`
   - `API_URL = "https://graph.microsoft.com/v1.0/me"`
   - `SCOPE = "https://graph.microsoft.com/Mail.Read offline_access"`
   - `PAGE_SIZE = 50`
   - `TIMEOUT_SECONDS = 30.0`
   - `TOKEN_MARGIN = timedelta(seconds=60)`
   - `ACCOUNT_MESSAGE = "invalid account name"`
   - `MESSAGE_ID_MESSAGE = "invalid message id"`
   - `IMMUTABLE_ID = 'IdType="ImmutableId"'`
2. **Errors.** `OutlookError(Exception)` and four subclasses, each raised `from None`:
   - `OutlookAuthError(account)` reads `"outlook sign-in needed: <account>"`;
   - `OutlookUnavailable(account, detail)` reads `"outlook unavailable: <account> (<detail>)"`;
   - `DeltaExpired(account)` reads `"outlook delta expired: <account>"`;
   - `MessageGone(account)` reads `"outlook message gone: <account>"`.
3. **Results**, each a frozen dataclass:
   - `Profile(email_address: str, inbox_id: str)`
   - `MessageRef(id: str, thread_id: str)`
   - `Delta(added: tuple[MessageRef, ...], delta_link: str)`
   - `RawMessage(id: str, thread_id: str, folder_id: str, received_at: datetime, web_link: str, raw: bytes)`
4. **`OutlookClient(account: str, http: httpx.Client)`** raises `ValueError(ACCOUNT_MESSAGE)` for a name that isn't `record.ACCOUNT_PATTERN`. It keeps `account` and `http` as attributes.
5. **Tokens.**
   - **Requesting one.** Before a Graph request, with no access token or with `clock.now()` at or past its expiry, the client reads both secrets and POSTs the refresh form to `TOKEN_URL`. A `SecretMissing` raises `OutlookAuthError` before any request.
   - **A 200 reply** must have a string `access_token` and an integer `expires_in`. The expiry is `now + expires_in - TOKEN_MARGIN`.
   - **The new refresh token.** When the reply has a `refresh_token`, it must be a non-empty string. If it differs from the stored one, the client saves it with `keychain.set_secret`.
   - **Failures.** A 400 or 401 whose `error` is `invalid_grant` or `interaction_required` raises `OutlookAuthError`. Any other non-200 raises `OutlookUnavailable` with the status. A malformed reply raises `OutlookUnavailable("response")`, and a transport error `OutlookUnavailable("network")`.
6. **Graph requests** are GETs with `Authorization: Bearer <token>` and `Prefer: IMMUTABLE_ID`, plus `, odata.maxpagesize=50` for delta rounds. A 401 drops the token, refreshes and sends the same request once more. A second 401 raises `OutlookAuthError`.
7. **`profile() -> Profile`**:
   - `GET API_URL` with `$select=mail,userPrincipalName`: `mail` when it is a non-empty string, else `userPrincipalName`;
   - `GET API_URL/mailFolders/inbox` with `$select=id`.
8. **Delta rounds.**
   - **`first_delta(since: datetime)`** sends `GET API_URL/mailFolders/inbox/messages/delta` with `changeType=created`, `$select=conversationId,receivedDateTime` and `$filter=receivedDateTime ge <since in UTC, YYYY-MM-DDTHH:MM:SSZ>`.
   - **`next_delta(delta_link: str)`** sends `GET` to exactly that link.
   - **Both** follow each `@odata.nextLink` until a page has `@odata.deltaLink`, and return `Delta` with every item that has no `@removed`, in order, once each, as `MessageRef(id, conversationId)`.
   - **Following a link.** A link is followed (and `next_delta` accepted) only if:
     - its scheme is `https` and its host exactly `graph.microsoft.com`;
     - it has no port and no user;
     - its percent-decoded path starts with `/v1.0/me/mailFolders` and ends with `/messages/delta`.
     Otherwise the call raises `OutlookUnavailable("response")` without sending it.
   - **Expiry.** A 410, or a 400 or 404 whose `error.code` is `syncStateNotFound` (any case), raises `DeltaExpired`.
   - **A malformed page** raises `OutlookUnavailable("response")`: an item id that doesn't match `[A-Za-z0-9_=-]{1,512}`, a non-string `conversationId`, or a page with neither link.
9. **`fetch(message_id: str) -> RawMessage`**:
   - It raises `ValueError(MESSAGE_ID_MESSAGE)` for an id that doesn't match `[A-Za-z0-9_=-]{1,512}`, before any request.
   - It sends `GET API_URL/messages/<id>` with `$select=conversationId,parentFolderId,receivedDateTime,webLink`, then `GET API_URL/messages/<id>/$value` (the body bytes, whatever their content type).
   - A 404 on either raises `MessageGone`.
   - `received_at` is `receivedDateTime` read with `datetime.fromisoformat`. It must carry a zone, and is converted to UTC.
10. **Other failures, and the constructor.**
    - On any Graph call, a non-200 not named above raises `OutlookUnavailable(<status>)` (a 429 included). A body that isn't the expected JSON, or a missing or mistyped field, raises `OutlookUnavailable("response")`. A transport error raises `OutlookUnavailable("network")`.
    - **`open_outlook(account: str) -> OutlookClient`** uses `httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)`.
11. **Progress entry** for `## Phase 4a: Graph client (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Verify before building

For the owner, before 4c is used on the real account:
- Register the app in Microsoft Entra for **personal Microsoft accounts only**, as a **Mobile and desktop** app with public client flows allowed. Add the redirect `http://127.0.0.1` in the app's manifest (`replyUrlsWithType`), because the portal's box refuses an `http` loopback address. Add the delegated permissions `Mail.Read` and `offline_access`.
- Confirm that a real message's immutable id matches `[A-Za-z0-9_=-]{1,512}`. If it doesn't, the pattern is changed before 4b.
- Confirm that `GET /me` answers `mail` or `userPrincipalName` with the live.com address.
- Note how long an unused refresh token lasts for a personal account. Sync every minute keeps it in use; a long outage may need `mailroom outlook-login` again.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/fakes.py` | Edited: `FakeGraph` |
| `scripts/critical_modules.txt` | Edited: `outlook.py` added |
| `tests/integration/test_outlook.py` | Tokens (public client, rotation saved, margin, a rejected token, six failures, a missing secret, no new refresh token); the profile; a first round since a moment; a later round over pages with a removal; five links never followed; two kinds of expiry; a fetch; a message gone; six refused ids; six Graph failures; two unreadable times; an invalid account; the client's settings |
| `docs/verification/probe-04a.py` | The verifier's probe |

Given test count: **39**, all new.

## Tests to write

The given tests cover every requirement's main cases. `outlook.py` is critical. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/outlook.py` | create |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Sync, bookmarks, first runs, catch-up, records (4b).
- The login command and the authorization-code exchange (4c).
- Settings, the service, alerts or the card footer (4d).
- Retrying, backing off, or honouring `Retry-After` within a call.
- Any Graph call that changes mail: no `PATCH`, `POST`, `DELETE`, `move`, `copy`, `send` or `isRead`.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Mail access is read-only.** Only GETs to Graph, and only `Mail.Read`.
- **Secrets come only from the Keychain,** and the rotated refresh token goes back there. None is ever put in an error, a log or a printed line.
- **The token goes only to Graph.** A page link elsewhere is never followed.
- **Network.** Only `login.microsoftonline.com` (the token) and `graph.microsoft.com`. Tests use the fake.
- **Error messages are constants plus the account,** never a reply's text.
- **Time through the module:** `clock.now()` only when deciding on and setting the token's expiry.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 39 = 1129 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_outlook.py --no-cov -q` | `39 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/outlook.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python docs/verification/probe-04a.py` | last line `FAILURES 0` |
| `grep -c "^## Phase 4a: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 4a` | `Reports OK.` |
| `git diff HEAD --stat -- tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook.py docs/verification/probe-04a.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'http\.(patch|put|delete)\(|/send|/move|/copy|isRead|markAsRead|createReply|createForward' -- src/mailroom/outlook.py
git grep --untracked -n -E 'Mail\.(ReadWrite|Send|ReadBasic)|microsoft\.com/\.default|/common/|/organizations/' -- src
git grep --untracked -n -E 'client_secret|client-secret' -- src/mailroom/outlook.py
git grep --untracked -n -E 'response\.text|str\((error|exc|e)\)|\{(error|exc|e)(!r)?\}' -- src/mailroom/outlook.py
git grep --untracked -n -E 'follow_redirects=True|trust_env=True|verify=False' -- src
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/outlook.py
```
