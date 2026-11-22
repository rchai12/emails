# Phase 4h: Preserve rotated Outlook credentials

## Goal

When Microsoft issues a new Outlook refresh token and the Keychain refuses to save it,
the client keeps the new token in memory instead of losing it. It reads no mail until
the token is saved, and it tries the save again at the start of every later call. The
owner is pinged at once with a constant-text alert that also states the restart limit.
That alert is resolved only by a round that reads mail. This closes audit finding 8.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is **1413**, from the passing Phase 4g review
(`49f5a71`). The finalized planning/given-file commit made after this document is
the coder's clean start.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_outlook_rotation.py --ignore=tests/integration/test_service_rotation.py`
must show `1413 passed`. Nothing needs a missing-module stub. The two new given files
import before the feature exists: they look up `mailroom.outlook.OutlookTokenUnsaved`
when a test runs.

## Facts

- `OutlookClient._refresh` reads `outlook.<account>.client-id` and
  `outlook.<account>.refresh-token` from the Keychain and posts a refresh grant. When
  the reply carries a different refresh token, it calls `keychain.set_secret` and only
  then stores the access token.
- Microsoft may retire the old refresh token as soon as it issues a new one. The fake
  Graph is stricter: only the latest refresh token works, and every refresh rotates it.
  A retired token gets 400 `invalid_grant`, which the client raises as
  `OutlookAuthError` ("outlook sign-in needed: <account>").
- `keychain.set_secret` raises `KeychainUnavailable("keychain unavailable: <name>")`
  when the backend fails. Today that error leaves `_refresh` and the new token is lost.
  The round shows only `outlook live: keychain unavailable: outlook.live.refresh-token`
  and sends no alert. The next round sends the retired token and gets "sign-in needed".
  A planning spike reproduced this offline.
- `run_service` opens each `OutlookClient` once and reuses it for every round, so state
  on the client lasts between rounds but not across a restart.
- Every Graph request goes through `_get`, which calls `_ensure_token` first.
- `service._outlook_account` reports `OutlookAuthError` and raises the
  `outlook-auth:<account>` alert. Any other `OutlookError` or `KeychainError` is
  reported as a status line only. `Health.report` prints a line only when the state
  changes.
- `alerts.track` with `wait=timedelta(0)` and `ping=True` raises an alert on the first
  failing call. It posts its `resolved` text when a later call passes `failing=False`.
- Validated with a throwaway scratch stand-in only (never copied in):
  - All 1413 existing tests pass unchanged.
  - The given tests pass 6 of 6 runs.
  - On predecessor code, all 18 given cases fail.

## Owner's decisions

- **2026-11-21:** a rotated token the Keychain refuses is kept in memory. The account
  reads no mail and its round reports the save failure until the token is saved. A
  round never reports `ok` before that.
- **2026-11-21:** the owner is pinged at once on the first unsaved round. Once the
  account works again, a notice says so.
- **2026-11-21:** the save is tried once per round for as long as the service runs.
  A restart loses the held token. The alert tells the owner to run
  `mailroom outlook-login <account>` if Mailroom stops before the save works.
- **2026-11-21:** the access token from the unsaved refresh is never used.

## Architect's decisions

- No disk, environment or other fallback for the token. Memory on the client is the
  only place it is held, and it is never logged, printed or put in an error.
- The held token is never sent to Graph before it is saved. Once the save works, the
  client refreshes normally from the Keychain, which now holds that token.
- One save try per Graph call is enough for "one per round", because a failed try
  raises and ends that account's round. There is no retry loop or sleep.
- The unsaved alert is resolved only by a round that synced. After a restart, a
  round's success means the Keychain's token works, so "its sign-in is saved" is true
  either way. A sign-in or unavailable failure leaves the alert open.
- Keychain read failures, `outlook_login`'s own writes and Gmail are unchanged.

## Requirements

1. **New error.** Add `OutlookTokenUnsaved(OutlookError)` to `outlook.py`. Its text is
   exactly `outlook new sign-in not saved: <account>`. It takes only the account,
   and it is not an `OutlookAuthError`.
2. **Hold on failure.** In `_refresh`, when the rotated token differs and
   `keychain.set_secret` raises `KeychainUnavailable`:
   - keep the rotated token in memory on the client;
   - keep no access token or expiry from that reply;
   - raise `OutlookTokenUnsaved(account)` with no cause or context
     (`from None`).
   Graph has not been called with the new access token.
3. **Save first.** While a token is held, every Graph call first tries
   `keychain.set_secret("outlook.<account>.refresh-token", held)` once, before any HTTP
   request.
   - If it raises `KeychainUnavailable`, raise `OutlookTokenUnsaved(account)` as in
     requirement 2, with no request sent.
   - If it succeeds, the client stops holding the token, so it is never written again.
     The call then continues as usual: with no access token it refreshes from the
     Keychain.
   - A later rotation that cannot be saved holds the newer token in the same way.
4. **Restart limit.** A new `OutlookClient` starts with nothing held. If the Keychain
   still has the retired token, Graph's refusal is the existing `OutlookAuthError` and
   sign-in alert. Nothing else is added for restarts.
5. **Service.** In `_outlook_account`, catch `OutlookTokenUnsaved` before the generic
   `OutlookError` branch.
   - Report its text as the account's status line.
   - Call `alerts.track` with problem `outlook-token:<account>`, `failing=True`,
     `wait=timedelta(0)`, `ping=True`,
     `raised=L.ALERT_OUTLOOK_UNSAVED.format(account=account)` and
     `resolved=L.ALERT_OUTLOOK_SAVED.format(account=account)`.
   - On a successful sync, track the same problem with `failing=False`, beside the
     existing sign-in resolution.
   - The sign-in and generic failure branches do not touch this problem.
6. **Privacy and compatibility.**
   - No token value reaches an error, status line, alert, log or file.
   - Existing tests keep passing unchanged.
   - Time comes only through `clock.now()`.
7. **Progress entry** for `## Phase 4h: Preserve rotated Outlook credentials (YYYY-MM-DD)`
   at the end of docs/progress.md, with actual counts and the new public name.

## Given files

Committed with the finalized spec before coding; never change them as the coder.

| File | What it is |
|---|---|
| `tests/integration/test_outlook_rotation.py` | 10 tests on the client: unsaved error and its text, no mail read, save tried first and once per call, held token saved and used, no second write after a failed refresh, fresh access token, retired token never resent, a later rotation held, restart needs sign-in |
| `tests/integration/test_service_rotation.py` | 8 tests on service rounds: status line and immediate ping, no mail read, one ping across rounds, recovery reads mail and says so, second episode, restart asks for sign-in and is not called saved, other failures leave the alert open, no token text |
| `src/mailroom/discord_layout.py` | Adds only `ALERT_OUTLOOK_UNSAVED` and `ALERT_OUTLOOK_SAVED` |
| `docs/verification/probe-04h.py` | 40 seeded scripts of rounds, Keychain refusals, restarts, logins and token-endpoint failures through real service rounds, checked against an independent oracle |

Given test count: **18** new cases, so the minimum final suite is **1431**.

## Tests to write

Add behavior tests in `tests/integration/test_outlook_token_save.py` (not a `_more`
file). `outlook.py` and `service.py` are critical: every line and branch stays
covered. The given tests already reach 100% on a stand-in. Add tests for behavior
they leave unpinned, for example:

- a reply that carries the same refresh token, or none, needs no write even while
  writes fail;
- a Keychain read failure still reports as before, with no unsaved alert;
- a second Outlook account is unaffected by the first one's held token;
- an unsaved round does not stop the Gmail account in the same round.

Use synthetic data and assert that no token text appears. Do not edit given or
earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/outlook.py` | `OutlookTokenUnsaved`, held token, save-first |
| `src/mailroom/service.py` | Unsaved branch, `outlook-token:` alert and its resolution |
| `tests/integration/test_outlook_token_save.py` | New coder-written behavior tests |
| `docs/progress.md` | Append Phase 4h entry |

New tests fall in `core`; tests/sections.toml stays unchanged.

## Out of scope

- Any disk, file, environment or database copy of a token; retry loops or sleeps.
- Changes to keychain.py, outlook_login.py, outlook_sync.py, gmail*.py, alerts.py,
  layouts beyond the given texts, fakes, given files, earlier tests, dependencies or
  design documents.
- Shared token mechanics (4m), missing-row guards (4i), Gmail token handling.
- Logs, metrics or exception text in any output.

## Rules that bite

All checks are synthetic and offline: the fake Graph, fake Discord, fake model, the
fake Keychain and temporary database files. Never touch real mail, Microsoft, Discord,
the tasks app, the Keychain or the data folder. Never put a token in an error's
arguments, even ones that are not printed. Never catch `OutlookTokenUnsaved` in the
generic branch: the given tests pin the immediate ping.

## Acceptance

Run from the repository root, in order. The coverage row reads the data the check
left; the given-only run has --no-cov and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line All checks passed.; tests (core) passed; at least 1431 passed, 0 failed/skipped/xfailed, no warnings; every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include=src/mailroom/outlook.py,src/mailroom/service.py --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_outlook_rotation.py tests/integration/test_service_rotation.py --no-cov -q` | 18 passed |
| `.venv/bin/python docs/verification/probe-04h.py` | each check line ends ok; final FAILURES 0 |
| `grep -c '^## Phase 4h: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4h` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04h-rotated-outlook-token.md docs/verification/phase-04h-rotated-outlook-token.md tests/integration/test_outlook_rotation.py tests/integration/test_service_rotation.py src/mailroom/discord_layout.py docs/verification/probe-04h.py` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may additionally write its named review |

### Searches

Each prints nothing (git grep exit 1 means no matches; above 1 is an error).

```zsh
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|time\.sleep|time\.monotonic|from mailroom\.(clock|ids) import' -- src/mailroom/outlook.py src/mailroom/service.py
git grep --untracked -n -E 'open\(|write_text|write_bytes|Path\(|print\(|logging|logger|pickle|json\.dump|os\.environ|getenv|tempfile|shelve|pragma: no cover|noqa|except BaseException|except Exception' -- src/mailroom/outlook.py
git grep --untracked -n -E 'set_secret\(' -- src/mailroom ':(exclude)src/mailroom/keychain.py' ':(exclude)src/mailroom/outlook.py' ':(exclude)src/mailroom/outlook_login.py' ':(exclude)src/mailroom/gmail_login.py'
git grep --untracked -n -E 'OutlookTokenUnsaved\([^)]*,|\{(rotated|token|refresh_token|held)[^}]*\}' -- src/mailroom/outlook.py src/mailroom/service.py
```

## Architect validation and handoff

No feature implementation was built. The given tests collect on predecessor imports,
and all 18 new cases fail there.

A throwaway scratch stand-in (about 40 changed lines, deleted with the scratch clone)
did the following. It is not a reference for the coder.

- It passed the given tests 6 of 6 runs.
- It passed all 1413 existing tests unchanged, for a 1431 suite.
- It left `outlook.py` and `service.py` at 100% line and branch coverage.
- 14 of 14 mutations of it were caught. They covered:
  - the write-error catch, the held token and dropping it on failure;
  - the access token kept from an unsaved reply;
  - saving after the refresh instead of before;
  - never clearing the held token, and never retrying the save;
  - a chained error, and the error as an `OutlookAuthError`;
  - a waiting or silent alert;
  - resolving on sign-in or other failures, never resolving, and the generic branch.

The probe results:

- Oracle-only mode passes.
- On predecessor code it ends FAILURES 1.
- On the stand-in it ends FAILURES 0.
- It catches a kept access token, a dropped held token, no ping, resolution on other
  failures, a held token never cleared, and an uncaught write error.

The searches are silent on predecessor and stand-in, and each catches a planted
line. Start shows 1413 passed. Given files are linted and formatted.

Before coder use, commit the finalized planning docs and given artifacts, including
the roadmap and history updates, and require a clean checkout.
