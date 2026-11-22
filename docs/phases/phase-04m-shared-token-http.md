# Phase 4m: Share safe HTTP and token mechanics

## Goal

A new module, `mailroom/token_http.py`, names no provider. It owns:

- the cached access token and its expiry;
- the token post and the check of its reply;
- the bearer request, with one retry after a 401;
- mapping a transport failure to the client's own "unavailable" error;
- refusing to send a token to any URL outside the provider's API.

`GmailClient` and `OutlookClient` each hold one `TokenSession`. They keep only their own
rules:

- Gmail: its token form with a client secret, and `invalid_grant` as "sign-in needed".
- Outlook: its token form with a scope, `invalid_grant` and `interaction_required` as
  "sign-in needed", the `Prefer` header, and Phase 4h's rotated refresh token, which is
  saved or held.

Request allowlists, read-only calls and response parsing stay in each client. This
closes the client-copy part of audit finding 4.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is **1577**, from the passing Phase 4l re-review
(`cf14413`). The coder's clean start is the planning and given-file commit made after
this document.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_token_http.py --ignore=tests/integration/test_token_clients.py`
must show `1577 passed`. Nothing needs a missing-module stub. The two new given files
import only names that exist today. They reach `mailroom.token_http` through
`importlib.import_module` in a fixture, so on today's code every case errors with
`ModuleNotFoundError`.

## Facts

- `gmail.py` and `outlook.py` each have the same token mechanics:

  | Piece | Gmail | Outlook |
  |---|---|---|
  | Cache | `_access_token`, `_expiry` | the same, plus `_held` |
  | Margin | `TOKEN_MARGIN = timedelta(seconds=60)` | the same |
  | Check | `_ensure_token`: refresh when there is no token or `clock.now() >= _expiry` | the same, after saving a held token |
  | Retry | `_get`: two tries; a 401 clears the token; two 401s raise `GmailAuthError` | `_get`: the same with `OutlookAuthError`, and a `Prefer` header |
  | Token post | `_refresh`: form with `client_id`, `client_secret`, `refresh_token`, `grant_type` | form with `client_id`, `refresh_token`, `grant_type`, `scope` |
  | Sign-in needed | 400 or 401 with `error == "invalid_grant"` | 400 or 401 with `error` in `{"invalid_grant", "interaction_required"}` |
  | Reply check | 200; a JSON object; `access_token` a `str` and `expires_in` an `int` (not `bool`) | the same; then the rotated `refresh_token` rule |
  | Transport | `_send`: `httpx.TransportError` becomes `GmailUnavailable(account, "network")` | the same with `OutlookUnavailable` |

  Other refusals are `<Provider>Unavailable(account, status)`. An unusable reply is
  `<Provider>Unavailable(account, "response")`. Every one is raised `from None`.
- The access token's expiry is `clock.now() + timedelta(seconds=expires_in) - TOKEN_MARGIN`,
  read after the reply. A refresh that fails leaves no token Gmail or Outlook can use.
- Phase 4h's rule: a rotated refresh token that cannot be saved is held, the access token
  from that reply is never used, and the held token is saved before any later request.
- `open_gmail` and `open_outlook` build `httpx.Client(timeout=30, trust_env=False,
  follow_redirects=False)`. Outlook's `_check_delta_link` limits delta links to
  `https://graph.microsoft.com/v1.0/me/mailFolders…/messages/delta`. That check does not
  reject dot segments such as `/mailFolders/../../x/messages/delta`.
- Tests and probes that reach into the clients:
  - `test_outlook_token_save.py` calls `OutlookClient._ensure_token()`.
  - The client suites (105 cases in `test_gmail.py`, `test_gmail_more.py`,
    `test_outlook.py`, `test_outlook_more.py`, `test_outlook_rotation.py` and
    `test_outlook_token_save.py`) already cover expiry, one retry, a second 401,
    transport failures, token refusals and rotation for each provider.
  - `probe-01b.py` (Gmail client), `probe-04a.py` (Outlook client) and `probe-04h.py`
    (rotation) end `FAILURES 0` today.
- Nothing outside `gmail.py` and `outlook.py` uses `TOKEN_MARGIN`, `_send`, `_refresh`,
  `_access_token`, `_expiry` or `_invalid_grant`.
- `scripts/critical_modules.txt` is what `scripts/check.py` enforces. `docs/testing.md`
  repeats it for readers.
- Validated with a throwaway scratch stand-in only, never copied in:
  - All 1577 earlier tests and the 61 given cases pass on it.
  - The given tests pass 6 of 6 runs.
  - `token_http.py`, `gmail.py` and `outlook.py` are at 100% line and branch coverage
    from the client, Gmail sync and given tests.
  - `probe-01b.py`, `probe-04a.py` and `probe-04h.py` end `FAILURES 0` on it.

## Owner's decisions

- **2026-11-22:** the module is `mailroom/token_http.py`. The other choices were adding
  it to `oauth.py`, which is the browser sign-in module, and `mailroom/provider_http.py`,
  a broader name that invites unrelated helpers.
- **2026-11-22:** each client holds a `TokenSession` helper object, built with its
  refresh function and its own error factories. There is no base class.
- **2026-11-22:** share the token post and its reply check. The session posts the
  provider's form, maps transport and status failures, treats the provider's listed
  codes as sign-in needed, and requires a `str` access token and an `int` lifetime.
  Outlook's rotation and held token stay in `outlook.py`.
- **2026-11-22:** the session refuses to send a token to a URL outside the provider's
  API base. It checks `https`, the exact host, no port and no user info, and a path
  under the base path, before anything is sent. A refused URL is the client's
  unavailable error with `"response"`. Outlook's delta-link check stays.

## Architect's decisions

- **`token_http.py` names no provider.** It imports only the standard library, `httpx`
  and `mailroom.clock`. No text in it names Gmail, Outlook, Google, Microsoft or Graph,
  docstrings and comments included.
- **Errors stay the clients' own.** The session raises only what the factories it was
  given build, so every error class and message is unchanged.
- **`TOKEN_MARGIN` moves.** It exists once, in `token_http`. `gmail.TOKEN_MARGIN` and
  `outlook.TOKEN_MARGIN` stay as names for that same object.
- **A `prepare` hook carries 4h's rule.** The session calls `prepare()` at the start of
  every token check, before it decides whether to refresh. Outlook passes a method that
  saves a held token. Gmail passes nothing.
- **The URL check runs first.** A refused URL calls neither `prepare` nor `refresh` and
  sends nothing.
- **Dot segments are refused.** After `%`-decoding, a path with a `.` or `..` segment is
  outside the API, whatever it starts with. Without this, a path under the base could
  climb out of it.
- **`OutlookClient._ensure_token` stays** as a method that runs the session's token
  check, because an existing test calls it.
- **`token_http.py` is a critical module.** This spec adds it to `docs/testing.md`
  beside `outlook.py`. The coder adds it to `scripts/critical_modules.txt`.

## Requirements

1. **`mailroom/token_http.py`.** Create it with these public names:
   - `TOKEN_MARGIN = timedelta(seconds=60)`.
   - `Grant`, a frozen dataclass with `access_token: str`, `expires_in: int` and
     `body: dict[str, object]` (the whole reply), in that order.
   - `TokenSession(http, *, api_url, token_url, auth_codes, refresh, auth_error,
     unavailable, prepare=<does nothing>)`:
     - `http: httpx.Client`; `api_url: str`; `token_url: str`;
       `auth_codes: frozenset[str]`;
     - `refresh: Callable[[], Grant]`, the client's own refresh;
     - `auth_error: Callable[[], Exception]` and
       `unavailable: Callable[[int | str], Exception]`, the client's error factories;
     - `prepare: Callable[[], None]`.
   - `ensure() -> None`:
     1. Call `prepare()`.
     2. When there is no token, or `clock.now() >= expiry`: forget the token and its
        expiry, call `refresh()`, then keep `grant.access_token` with
        `expiry = clock.now() + timedelta(seconds=grant.expires_in) - TOKEN_MARGIN`.
        An exception from `prepare` or `refresh` propagates unchanged, with no token
        kept.
   - `get(url, *, params=None, headers=None) -> httpx.Response`:
     1. When the URL is outside the API (below), raise `unavailable("response")`.
        Nothing else runs.
     2. Up to two tries: `ensure()`, then `http.get(url, params=params,
        headers={**headers, "Authorization": f"Bearer {token}"})`.
        - A transport failure (`httpx.TransportError`) raises
          `unavailable("network")`.
        - A 401 forgets the token and expiry, and tries again.
        - Any other status, 200 included, is returned to the client.
     3. After two 401s, raise `auth_error()`.
   - `grant(form: dict[str, str]) -> Grant`: post `form` once to `token_url`.
     - A transport failure raises `unavailable("network")`.
     - A 400 or 401 whose JSON body is an object with a string `error` in `auth_codes`
       raises `auth_error()`.
     - Any other status that is not 200 raises `unavailable(status)`.
     - A body that is not JSON, or not a JSON object, raises `unavailable("response")`.
     - So does a reply whose `access_token` is not a `str` or whose `expires_in` is not
       an `int`; a `bool` is not an `int` here.
     - Otherwise return `Grant(access_token, expires_in, body)`.
   - **Outside the API.** Split `url` and `api_url`. The URL is inside only when:
     - its scheme is `https`;
     - its host equals the API host (case-insensitive, as `urlsplit` gives it);
     - it has no port, no user name and no password;
     - its `%`-decoded path equals the API path or starts with the API path plus `/`;
     - no segment of that decoded path is `.` or `..`.

     A query is allowed.
   - Every error the session raises is raised `from None`. No error text echoes a
     token, a form value, a URL or a library message.
2. **`gmail.py`.**
   - `GmailClient.__init__` builds one `TokenSession` with `api_url=API_URL`,
     `token_url=TOKEN_URL`, `auth_codes=frozenset({"invalid_grant"})`, its refresh, and
     factories for `GmailAuthError(account)` and `GmailUnavailable(account, detail)`.
   - Every API request goes through the session's `get`. The refresh reads the three
     Keychain secrets (a missing one raises `GmailAuthError`) and returns
     `session.grant(<the same form as today>)`.
   - Remove `_access_token`, `_expiry`, `_ensure_token`, `_send`, `_invalid_grant` and
     the `clock` import. `TOKEN_MARGIN` stays as `token_http.TOKEN_MARGIN`.
3. **`outlook.py`.**
   - `OutlookClient.__init__` builds one `TokenSession` with `api_url=API_URL`,
     `token_url=TOKEN_URL`, `auth_codes=_AUTH_ERRORS`, its refresh, factories for
     `OutlookAuthError(account)` and `OutlookUnavailable(account, detail)`, and a
     `prepare` that saves a held token (Phase 4h).
   - Every Graph request goes through the session's `get`, with the same `Prefer` header
     as today.
   - The refresh reads the two Keychain secrets (a missing one raises
     `OutlookAuthError`) and calls `session.grant(<the same form as today>)`. Then it
     applies today's rotation rule to `grant.body`: a present `refresh_token` that is
     not a non-empty `str` is `OutlookUnavailable(account, "response")`; a different one
     is saved, and when the save raises `OutlookTokenUnsaved` it is held and the error
     propagates. It returns the grant.
   - `_ensure_token()` stays and runs the session's `ensure()`.
   - Remove `_access_token`, `_expiry`, `_send`, `_oauth_error` and the `clock` import.
     `TOKEN_MARGIN` stays as `token_http.TOKEN_MARGIN`.
4. **Compatibility.** Existing tests and probes keep passing unchanged. These stay the
   same:
   - every request, its order, URL, form and headers;
   - every error class, message and detail;
   - token expiry and reuse;
   - Phase 4h's held-token behavior;
   - `open_gmail` and `open_outlook`.
5. **Critical module.** Add `token_http.py` to `scripts/critical_modules.txt`, after
   `outlook_login.py`. The `docs/testing.md` line comes with this spec.
6. **Progress entry** for `## Phase 4m: Share safe HTTP and token mechanics (YYYY-MM-DD)`
   at the end of `docs/progress.md`, with actual counts.

## Given files

Committed with the finalized spec before coding. The coder never changes them.

| File | What it is |
|---|---|
| `tests/integration/test_token_http.py` | 56 cases against a scripted token server and API for an invented provider. They cover a first request (token form, bearer header, the client's headers and params), no extra headers, reuse until the 60-second margin and a refresh at it, `prepare` before every token check, a 401 then success, two 401s, the next request after that, other statuses returned, a transport failure, a failed refresh that leaves no token, and a client refresh error passed through. Twelve URLs outside the API are refused with nothing sent and no `prepare`; five inside it are sent, and the host is compared without case. The grant cases cover the whole reply, the lifetime setting the expiry, listed codes on 400 and 401, eight other refusals with their status, eight unusable replies, and a transport failure that does not echo the form |
| `tests/integration/test_token_clients.py` | 5 cases. Each client builds one session with its API URL, token URL and codes (Outlook with a `prepare`). Every Gmail and Outlook request and token post goes through the session, with today's form fields. Both clients' `TOKEN_MARGIN` is the session's object |
| `docs/verification/probe-04m.py` | It imports `token_http` in a fresh interpreter (no provider module loads) and inspects its imports. It runs 200 seeded random scripts of clock moves, token replies and API replies against its own oracle of every request and outcome, and 400 seeded random URLs built from good and bad parts against its own decision. Both real clients must build one session and send everything through it, and 60 seeded random call scripts per provider, against FakeGmail and FakeGraph, must match one oracle of the session |

Given test count: **61** new cases, so the minimum final suite is **1638**.

## Tests to write

Add behavior tests in `tests/integration/test_token_clients_more.py`. `token_http.py`,
`gmail.py` and `outlook.py` are critical: cover every line and branch. Add tests for
behavior the given and existing tests leave unpinned, at least:

- An Outlook delta `@odata.nextLink` that passes `_check_delta_link` but has a `..`
  segment, such as `https://graph.microsoft.com/v1.0/me/mailFolders/../../x/messages/delta`,
  is refused with `OutlookUnavailable(account, "response")`. No request is sent to it.
- A Gmail refresh with a missing Keychain secret raises `GmailAuthError` and posts
  nothing; then, with the secret back, the next call refreshes and succeeds.
- A client header named `Authorization`, passed to `TokenSession.get`, never replaces
  the session's bearer token. No given or existing test pins this.

Assert through requests and the fake Keychain, not private fields.

Use synthetic data. Do not edit given or earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/token_http.py` | New: `TOKEN_MARGIN`, `Grant` and `TokenSession` |
| `src/mailroom/gmail.py` | One session; the Gmail refresh form; old token mechanics removed |
| `src/mailroom/outlook.py` | One session with `prepare`; the Outlook refresh form and rotation; old token mechanics removed |
| `scripts/critical_modules.txt` | Add `token_http.py` |
| `tests/integration/test_token_clients_more.py` | New coder-written behavior tests |
| `docs/progress.md` | Append the Phase 4m entry |

New tests fall in `core`, so `tests/sections.toml` stays unchanged.

## Out of scope

- A new provider, a generic HTTP client, or any request a client does not make today.
- `oauth.py`, `gmail_login.py` and `outlook_login.py`. The browser sign-in's token
  exchange is Phase 4k's `token_reply` and stays separate.
- Response parsing, paging, delta-link rules, message-id checks and the read-only
  request list of each client.
- The service's per-provider wiring and auth alerts. Those are 4n.
- Changes to timeouts, redirects, proxies, scopes, Keychain names or the 4h policy.
- Changes to fakes, given files, earlier tests, earlier probes, dependencies or design
  documents. The `docs/testing.md` line comes with this spec.

## Rules that bite

All checks are synthetic and offline, against FakeGmail, FakeGraph and scripted
`httpx.MockTransport` handlers. Never touch real mail, Google, Microsoft, the Keychain
or the data folder.

- **Check the URL first.** Refuse it before `prepare`, before any refresh and before
  any request. A token must never reach another host, port, user info or a path outside
  the API.
- **Decode, then look for dot segments.** `%2e%2e` is `..`. Compare the decoded path.
  `startswith(base)` alone lets `/v2/users/meX` through; require `base` or `base + "/"`.
- **The bearer header wins.** Build headers as the client's headers plus
  `Authorization`, so a client header can never replace the token.
- **Forget on 401 and on refresh.** Clear the token and its expiry before calling
  `refresh`, and after a 401. A failed refresh must leave no token to reuse.
- **`prepare` runs on every token check**, first, even when the token is still good.
  Outlook's held token is saved there.
- **`type(x) is int`, not `isinstance`.** `True` is an `int` to `isinstance`.
- **Raise `from None`, and catch only `httpx.TransportError`** (and `ValueError` while
  reading JSON). A broad catch hides keychain and programming errors that tests expect
  to propagate.
- **Keep each client's own errors.** Do not add a session error class that reaches the
  service; the factories build the provider's errors.

## Acceptance

Run from the repository root, in order. The coverage row reads the data the check left;
the given-only run has `--no-cov` and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | The last line is `All checks passed.`. The tests (core) passed: at least 1638 passed; 0 failed, skipped or xfailed; no warnings. Every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include='src/mailroom/token_http.py,src/mailroom/gmail.py,src/mailroom/outlook.py' --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_token_http.py tests/integration/test_token_clients.py --no-cov -q` | 61 passed |
| `.venv/bin/python docs/verification/probe-04m.py` | each check line ends ok; final FAILURES 0 |
| `.venv/bin/python docs/verification/probe-01b.py` | final FAILURES 0 |
| `.venv/bin/python docs/verification/probe-04a.py` | final FAILURES 0 |
| `.venv/bin/python docs/verification/probe-04h.py` | final FAILURES 0 |
| `grep -c '^token_http.py$' scripts/critical_modules.txt` | 1 |
| `grep -c '^## Phase 4m: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4m` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04m-shared-token-http.md docs/verification/phase-04m-shared-token-http.md tests/integration/test_token_http.py tests/integration/test_token_clients.py docs/verification/probe-04m.py docs/testing.md` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may also write its named review |

### Searches

Each prints nothing. A git grep exit of 1 means no matches, and an exit above 1 is an
error.

```zsh
git grep --untracked -n -E '_access_token|_expiry|range\(2\)|TransportError|TOKEN_MARGIN = timedelta|clock|def _send|_invalid_grant|_oauth_error|Bearer' -- src/mailroom/gmail.py src/mailroom/outlook.py
git grep --untracked -n -i -E 'gmail|outlook|google|microsoft|graph' -- src/mailroom/token_http.py
git grep --untracked -n -E '\.http\.(get|post)\(' -- src/mailroom/gmail.py src/mailroom/outlook.py
git grep --untracked -n -e 'import' --and -e 'mailroom' --and --not -e '^from mailroom import clock$' -- src/mailroom/token_http.py
git grep --untracked -n -E 'except (Exception|BaseException)[ :]|except:|pragma: no cover|noqa|datetime\.now|from mailroom\.(clock|ids) import|print\(|logging|finally:|isinstance\(expires_in' -- src/mailroom/token_http.py src/mailroom/gmail.py src/mailroom/outlook.py
```

## Architect validation and handoff

No feature implementation was built. The given tests collect on predecessor imports,
and all 61 new cases error there with `ModuleNotFoundError: mailroom.token_http`.

A throwaway scratch stand-in (about 300 changed lines: the 124-line new module, and 127
lines removed from the clients for 50 added; deleted with the scratch clone) did the following. It is not a reference for the coder.

- It passed the given tests 6 of 6 runs, and all 1577 earlier tests.
- It left `token_http.py`, `gmail.py` and `outlook.py` at 100% line and branch coverage
  from the client, Gmail sync and given tests.
- `probe-01b.py`, `probe-04a.py` and `probe-04h.py` ended FAILURES 0 on it.
- 17 of 17 mutations of it were caught by a given or existing test:
  - no margin, the token kept at its exact expiry, and a failed refresh keeping the old
    token;
  - no retry after a 401, and a rejected token kept;
  - any host, any port, dot segments, and a bare path prefix let through;
  - listed codes honoured only on 400, and a `bool` lifetime accepted;
  - `prepare` skipped, and only timeouts mapped to "network";
  - Outlook without `prepare`, without its `Prefer` header, or without its scope;
  - Gmail treating `interaction_required` as sign-in needed.

An 18th mutation, a client header named `Authorization` replacing the bearer token, was
missed by every given and existing test. The spec asks the coder's tests to pin it, and
the guide makes it a spot check with the coder's delta-link test.

The probe results:

- On predecessor code it ends FAILURES 4, since `mailroom.token_http` does not exist.
  Its client-script check already passes there, as it should: it checks behavior that
  must not change.
- On the stand-in it ends FAILURES 0.
- It catches 11 of those 17 mutations. It leaves to the tests the failed-refresh token,
  `prepare`, Outlook's `prepare`, `Prefer` and scope, and Gmail's codes.

The searches print nothing on the stand-in, and each catches a planted line. On
predecessor code, searches 1 and 3 print the old token mechanics and direct requests.
Start shows 1577 passed. The given files are linted and formatted.

Before coder use, commit the finalized planning docs and given artifacts, including the
roadmap, history and `docs/testing.md` updates, and require a clean checkout.
