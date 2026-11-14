# Phase 4d: Outlook in the service

## Goal

Run live.com accounts in `mailroom run` beside Gmail, and meet stage 4's test: identical emails give identical verdicts from Gmail and live.com.

- **Accounts.** `MAILROOM_OUTLOOK_ACCOUNTS` names the Outlook accounts. The service starts with any account of either provider.
- **Each round** syncs each Outlook account after the Gmail accounts, with its own status line. It raises a sign-in alert, with a ping, when its sign-in fails, and announces the fix. It also posts a catch-up notice naming Outlook.
- **Verification.** Outlook mail is verified from Microsoft's own `Authentication-Results` header, by the same DMARC and SPF/DKIM rule as Gmail, so a trusted sender is trusted on either.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 1184, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_config_outlook.py` must show `19 failed, 1186 passed`.
- The ignored file imports `OUTLOOK_ACCOUNTS_MESSAGE`, which you create.
- The failures are given tests waiting for you:
  - `test_sender_auth_outlook.py` and `test_service_outlook.py`;
  - `test_service.py`'s missing-settings message;
  - the Gmail catch-up tests, because the given `ALERT_CATCH_UP` now has a `{provider}` slot.

## Corrections

- **2026-11-13, after the first review (FAIL).** Two rows of the given `test_microsofts_first_header_decides` expected `False` where Requirement 2's rule ("the same rules as Gmail") gives `True`. The code was right.
  - **`dmarc-other-domain`.** DMARC passed only for another domain, but SPF and DKIM both passed for the sender's domain, which verifies by Gmail's rule.
  - **`dkim-other-domain`.** DKIM passed for `other.example.test`, a subdomain, which aligns with `example.test`.
  Both rows now test what their names say, with an unrelated domain and nothing else passing (`False`). Gmail's unchanged rule gives the same answers on the same results. Against the coder's uncommitted `sender_auth.py`, `config.py`, `alerts.py` and `service.py`, which stay as they are: the 39 given tests pass, the probe prints `FAILURES 0`, and the suite passes 1211. The coder's remaining work is the Acceptance run and the progress entry.

## Facts

Checked in Microsoft's documentation and against today's code.

- **Microsoft's header has no server name.** Microsoft's anti-spam headers page documents its `Authentication-Results` as `spf=… smtp.mailfrom=…`, `dkim=… header.d=…`, `dmarc=… action=… header.from=…` and `compauth=… reason=…`, joined by `;`. It doesn't start with a server name (RFC 8601's authserv-id), as Gmail's `mx.google.com;` does. `compauth` (composite authentication) is a Microsoft-only field.
- **Today's parser misreads it.** `parse_results` takes the first word as the server name, so for Microsoft's header it would read `spf=pass` as the name and drop the SPF result. `verified` knows only `AUTHSERV_IDS = {"gmail": "mx.google.com"}`, and a given test pins that, so every Outlook email is unverified.
- **Trust rests on position, as for Gmail.** A provider adds its header above everything the sender wrote, and Gmail's rule reads only the first. A sender can write a header that looks like Microsoft's, but it sits below Microsoft's own. So the first header decides here too, and it must look like Microsoft's: no server name, and a `compauth` result.
- **The card footer already names Outlook.** `PROVIDER_NAMES["outlook"]` is `Outlook`, and the footer adds the account: `Outlook live`. Threads, follow-ups, tasks and links are keyed by provider and `<account>/<id>`, so they work for Outlook unchanged.
- **The catch-up text named Gmail.** `ALERT_CATCH_UP` and `ALERT_GAP` (given) now take `{provider}`, and Gmail's wording is unchanged. The new texts `ALERT_OUTLOOK_AUTH` and `ALERT_OUTLOOK_FIXED` are given.
- **The round needs no new parameter.** `run_round`'s list of mail clients can hold both `GmailClient` and `OutlookClient`, each sent to its own sync, so its callers and earlier tests don't change.
- **Earlier tests change in one place (given edit):** `test_service.py`'s missing-settings message names both account settings.

## Owner's decisions

- **Outlook verification** uses the first `Authentication-Results` header when it has no server name and carries `compauth`, with Gmail's DMARC and SPF/DKIM rule. Before trusting a sender on Outlook, the owner confirms on a real live.com email that Microsoft's header is first (Verify before building).
- From 4a: personal accounts only, read-only.

## Architect's decisions

- **Any account starts the service.** The required-settings check asks for Gmail accounts or Outlook accounts. When both are empty, the message names `MAILROOM_GMAIL_ACCOUNTS or MAILROOM_OUTLOOK_ACCOUNTS` in Gmail's old place.
- **Outlook's alert keys are distinct:** `outlook-auth:<account>` and `catch-up:outlook:<account>:<since>`. An account name used by both providers never collides. Gmail's keys don't change.
- **Gmail first, then Outlook,** in the order each setting lists them, so status lines and stored mail come in a fixed order.
- **Outlook sign-in alerts like Gmail's:** at once, with a ping, and the fix announced.

## Requirements

1. **`Settings.outlook_accounts: tuple[str, ...] = ()`** (env `MAILROOM_OUTLOOK_ACCOUNTS`) is read exactly as `gmail_accounts` is: comma-separated names matching `record.ACCOUNT_PATTERN`, trimmed, no repeats, and empty means none. Otherwise `get_settings()` raises `ConfigError(OUTLOOK_ACCOUNTS_MESSAGE)`, with `OUTLOOK_ACCOUNTS_MESSAGE = "MAILROOM_OUTLOOK_ACCOUNTS must be account names separated by commas"`.
2. **`verified(record)`** for an `outlook` record is true only when all of these hold:
   - it has at least one `Authentication-Results` header, and the first one's first `;`-part begins with a `method=result` word (no server name);
   - that header has a `compauth` result;
   - the sender has a domain;
   - by the results of that header alone, DMARC passes for the sender's domain, or SPF and DKIM both pass for it, by the same rules as Gmail.

   Gmail's behaviour, `parse_results`, and `AUTHSERV_IDS` are unchanged.
3. **`alerts.catch_up_text(account, offline, count, gap, provider: str = "gmail")`** fills `{provider}` with `PROVIDER_NAMES[provider]`, in both texts.
4. **`run_round(store, settings, mail_clients, model_http, discord_http, tasks_http, health)`**. The third parameter is renamed and may mix both client types, synced in order:
   - **A `GmailClient`** works as today.
   - **An `OutlookClient`** runs `outlook_sync.sync_outlook` and reports the part `outlook <account>`:
     - `OutlookAuthError` reports the error's text and tracks `outlook-auth:<account>` as failing, at once, with a ping, raised `ALERT_OUTLOOK_AUTH` and resolved `ALERT_OUTLOOK_FIXED`;
     - another `OutlookError` or a `KeychainError` reports the error's text;
     - success reports `ok`, resolves that problem, and, for a catch-up, posts the notice under `catch-up:outlook:<account>:<since>` with `catch_up_text(..., provider="outlook")`.
5. **`run_service`** gains `open_outlook: Callable[[str], OutlookClient] = outlook.open_outlook`.
   - It opens one client per `settings.outlook_accounts`, and passes the Gmail clients, then the Outlook ones, to every round.
   - It closes every client's `http` with the others.
   - The required-settings check is Architect's decisions' "any account".
6. **Progress entry** for `## Phase 4d: Outlook in the service (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Verify before building

For the owner, on the real account, before trusting a sender on Outlook:
- Open a live.com email's source. Confirm that the first `Authentication-Results` header is Microsoft's (no server name, with `compauth`), and that it sits above any header the sender could have written.
- If Microsoft writes a server name there, or the header isn't first, Outlook verification is revisited before anyone is trusted. Until then a trusted sender's Outlook mail stays unverified, which only costs the trust.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/discord_layout.py` | Edited: `ALERT_OUTLOOK_AUTH`, `ALERT_OUTLOOK_FIXED`, `{provider}` in `ALERT_CATCH_UP` and `ALERT_GAP` |
| `tests/unit/test_sender_auth_outlook.py` | Ten first headers, verified or not; only the first counts; Microsoft's header on Gmail mail; no sender domain |
| `tests/unit/test_config_outlook.py` | The accounts setting, four bad lists, the same name for both providers |
| `tests/integration/test_service_outlook.py` | A round with both providers; one failing alone; a signed-out account alerted and fixed; a catch-up named Outlook; identical verdicts for three emails; the service with Outlook alone |
| `tests/integration/test_service.py` | Edited: the missing-settings message |
| `docs/verification/probe-04d.py` | The verifier's probe |

Given test count: **39** (27 new in the three new files; 12 in the edited `test_service.py`).

## Tests to write

The given tests cover every requirement's main cases. `sender_auth.py`, `config.py`, `alerts.py` and `service.py` are critical. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/config.py` | `outlook_accounts`, `OUTLOOK_ACCOUNTS_MESSAGE` |
| `src/mailroom/sender_auth.py` | Outlook's rule in `verified` |
| `src/mailroom/alerts.py` | `catch_up_text`'s `provider` |
| `src/mailroom/service.py` | Outlook clients in the round and the service |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Any change to `outlook.py`, `outlook_sync.py` or `outlook_login.py`.
- Yahoo (stage 5), or reading other Microsoft headers (`X-Forefront-Antispam-Report`, ARC).
- Using `compauth` or Microsoft's spam verdict as a verdict of its own.
- A `mailroom run` flag per provider, or new commands.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **A forged sender gains nothing.** Only the first header counts, and it must look like Microsoft's. A passing header written by the sender sits below and is never read.
- **Code decides.** Verification and trust come from headers and the trusted list, never from the model, on either provider.
- **Mail access is read-only,** through 4a's client only.
- **Each part fails on its own.** An Outlook failure never stops Gmail, triage or posting, and the reverse.
- **Secrets and email text** never appear in a status line or an alert: only fixed text and account names.
- **Time through the module,** as today.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 27 = 1211 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_sender_auth_outlook.py tests/unit/test_config_outlook.py tests/integration/test_service_outlook.py tests/integration/test_service.py --no-cov -q` | `39 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/sender_auth.py,src/mailroom/config.py,src/mailroom/alerts.py,src/mailroom/service.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python docs/verification/probe-04d.py` | last line `FAILURES 0` |
| `grep -c "^## Phase 4d: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 4d` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/discord_layout.py tests/unit/test_sender_auth_outlook.py tests/unit/test_config_outlook.py tests/integration/test_service_outlook.py tests/integration/test_service.py docs/verification/probe-04d.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'AUTHSERV_IDS *=.*outlook|"outlook": *"' -- src/mailroom/sender_auth.py
git grep --untracked -n -E 'authentication_results\[(1|-1)\]|for .* in record\.authentication_results' -- src/mailroom/sender_auth.py
git grep --untracked -n -E 'X-Forefront|X-Microsoft-Antispam|ARC-Authentication' -- src
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/sender_auth.py src/mailroom/config.py src/mailroom/alerts.py src/mailroom/service.py
```
