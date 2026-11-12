# Phase 1e: Sender checks and rules

## Goal

Decide, in code and before any model call, what happens to a stored email: whether its sender passed the provider's own authentication checks, whether the sender is on your trusted or muted list, and so whether the email is dropped or goes on to the extractor. Adds the `senders` table that holds the two lists. No Discord commands or buttons yet (1g adds Trust sender, Mute sender and `/trust`), no extractor (1f), and no scores or ranking (1g).

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 271, the tests Phase 1d left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_sender_auth.py --ignore=tests/integration/test_store_senders.py --ignore=tests/integration/test_rules.py` must show `271 passed`. The ignored files import names you create. The given migration is already in place, so the two store test files (given, now expecting schema version 3) pass from the start.

## Facts

From RFC 8601 (Authentication-Results), Gmail's headers as `tests/unit/test_mime.py` samples them, and the code on this machine.

- **The header.** `Authentication-Results: <authserv-id> [version]; <method>=<result> <ptype>.<property>=<value> ...; ...`. Methods include `spf`, `dkim`, `dmarc` and `arc`; results include `pass`, `fail`, `softfail`, `neutral`, `none`, `temperror` and `permerror`. Words are case-insensitive. Comments in parentheses can appear anywhere, can nest, and can contain `=` or `;`. A part with no result is written `none`.
- **Gmail's form.** `mx.google.com; dkim=pass header.i=@<domain> header.s=... header.b=...; spf=pass (google.com: domain of ... designates ... as permitted sender) smtp.mailfrom=<address or domain>; dmarc=pass (p=REJECT ...) header.from=<domain>`. DKIM names its domain with `header.i=@<domain>` (or `header.d=<domain>` on other servers).
- **Which header to believe.** Anyone can put an `Authentication-Results` header in a message they send. The receiving provider adds its own at the top, so only the **first** header is the provider's, and only if its authserv-id is the provider's.
- **The record.** `Record.authentication_results` holds the headers in message order, top first, each cleaned to one line of at most 2,000 characters, at most 10 (`mime`). `Record.sender` is the lower-case address, or `""` when missing or malformed. `Record.list_unsubscribe` is the bulk-mail sign.
- **The store.** `Store` runs `schema.MIGRATIONS` in order; the given migration 3 adds `senders(address TEXT PRIMARY KEY, status TEXT CHECK (status IN ('trusted', 'muted')))`.

## Owner's decisions

- **Only muted senders are dropped.** There is no built-in newsletter list: a newsletter reaches you once, and Mute sender stops it.
- **Trust and mute match an exact address**, never a domain.
- From the design: a trusted sender counts only when the email passes DMARC, or both SPF and DKIM, for the sender's domain; mail from a trusted sender is never dropped; bulk-mail signs lower the score, never drop.

## Architect's decisions

- **Only the provider's own header counts**: the first one, and only if its authserv-id is the provider's (`mx.google.com` for Gmail). Providers without an entry (Outlook and Yahoo, until their stages) are never verified.
- **Alignment.** DMARC must pass with `header.from` equal to the sender's domain. For SPF plus DKIM, each passing domain must be the sender's domain or a subdomain of it (`mail.example.test` for `example.test`, never `badexample.test`).
- **A broken header verifies nothing**: unbalanced parentheses make the whole header unreadable.
- **One status per address**: trusted or muted, never both; setting one replaces the other, and `None` clears it.
- **A muted address is dropped whether or not it verifies.** A forged copy of a muted address can only hide mail claiming to be from someone you muted.
- **The screening result is data for later phases.** `trusted` and `bulk` feed 1g's ranking, and `action` says whether 1f's extractor runs. Nothing is written here.
- **Critical modules**: `sender_auth.py` and `rules.py` (they decide trust and what is dropped).

## Requirements

1. **`store.py`: senders.**
   - `SENDER_MESSAGE = "invalid sender address"` and `STATUS_MESSAGE = "invalid sender status"`.
   - **The address rule.** Each method lowercases the address, then raises `ValueError(SENDER_MESSAGE)` unless it has exactly one `@` with text on both sides, no whitespace, and at most 254 characters.
   - `sender_status(address: str) -> Literal["trusted", "muted"] | None` returns the stored status, or `None`.
   - `set_sender_status(address: str, status: Literal["trusted", "muted"] | None) -> None` stores the status, replacing any other, or deletes the row for `None` (no error if there is none), and commits. Another status raises `ValueError(STATUS_MESSAGE)` before anything is written.
   - `senders(status: Literal["trusted", "muted"]) -> tuple[str, ...]` returns the addresses with that status, sorted. Another status raises `ValueError(STATUS_MESSAGE)`.

2. **`src/mailroom/sender_auth.py`, names.**
   - `AUTHSERV_IDS: dict[str, str] = {"gmail": "mx.google.com"}`
   - `AuthResult`, a `@dataclass(frozen=True)` with `method: str`, `result: str` and `props: tuple[tuple[str, str], ...]`

3. **`parse_results(header: str) -> tuple[str, tuple[AuthResult, ...]]`.** It never raises.
   1. Remove every comment, nested ones included. If the parentheses do not balance (a `)` with none open, or one left open), return `("", ())`.
   2. Split on `;`. The authserv-id is the first word of the first part, lowercased (a version number after it is ignored).
   3. In each later part, split on whitespace. The first word must be `<method>=<result>` with both sides non-empty; otherwise the part is skipped. Method and result are lowercased.
   4. Each later word that holds `=` becomes a prop: the key before the first `=`, lowercased, and the value after it, unchanged. Other words are skipped. Props keep their order.

4. **`verified(record: Record) -> bool`.**
   - **False unless** `AUTHSERV_IDS` has the record's provider, the record has a header, the first header's authserv-id is that provider's, and the sender has a domain (the text after its `@`). Later headers are never read.
   - **True if** a `dmarc` result `pass` has a `header.from` equal to the sender's domain, ignoring case.
   - **Or if** both of these hold, with "aligned" meaning equal to the sender's domain or ending with `"." + domain`, ignoring case:
     - an `spf` result `pass` has an aligned `smtp.mailfrom` (its domain is the text after the last `@`, or the whole value without one)
     - a `dkim` result `pass` has an aligned `header.d`, or, without one, an aligned domain in `header.i` (the text after its `@`)
   - Otherwise false.

5. **`src/mailroom/rules.py`: `Screening`**, a `@dataclass(frozen=True)` with `action: Literal["drop", "extract"]`, `trusted: bool`, `verified: bool` and `bulk: bool`.

6. **`screen(record: Record, store: Store) -> Screening`.**
   - `verified` is `sender_auth.verified(record)`.
   - The status is `store.sender_status(record.sender)`, or `None` without a lookup when `record.sender` is `""`.
   - `action` is `"drop"` when the status is `"muted"`, else `"extract"`.
   - `trusted` is true only when the status is `"trusted"` and `verified` is true.
   - `bulk` is `record.list_unsubscribe`.

7. **Critical modules.** `scripts/critical_modules.txt` (given) lists `sender_auth.py` and `rules.py`.

8. **Progress entry** for `## Phase 1e: Sender checks and rules (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Adds migration 3: the `senders` table |
| `tests/integration/test_store.py` | Two lines now expect schema version 3 |
| `tests/integration/test_store_sync.py` | One line now expects schema version 3 |
| `tests/unit/test_sender_auth.py` | 19 tests (requirements 2 to 4) |
| `tests/integration/test_store_senders.py` | 7 tests (requirement 1) |
| `tests/integration/test_rules.py` | 6 tests (requirements 5 and 6) |
| `scripts/critical_modules.txt` | Adds `sender_auth.py` and `rules.py` |
| `docs/verification/probe-01e.py` | The verifier's probe |

Given test count: **32** (in the three new test files).

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/unit/test_sender_auth_more.py` (or `tests/integration/test_store_senders_more.py`), never by changing a given test, for at least:
- a part whose first word has no `=`, or an empty side (`dmarc=`), is skipped (requirement 3)
- `smtp.mailfrom` given as a bare domain, and `dkim` with both `header.d` and `header.i`, where `header.d` decides (requirement 4)

## Scope

| Path | Change |
|---|---|
| `src/mailroom/sender_auth.py` | create |
| `src/mailroom/rules.py` | create |
| `src/mailroom/store.py` | add the two messages and the three methods |
| `tests/unit/test_sender_auth_more.py` | create |
| `tests/integration/test_store_senders_more.py` | create, only if coverage needs it |
| `docs/progress.md` | append your entry |

## Out of scope

- **Acting on the lists.** Discord buttons and commands, a CLI for trust or mute (1g). An audit log entry for a change (later).
- **Scores and ranking.** Sender scores, "Not a task" counts, digest order, notify thresholds (1g).
- **More checks.** ARC, BIMI, DNS lookups, the public suffix list, domain-wide trust or mute, a newsletter list, Outlook's or Yahoo's authserv-ids.
- **The pipeline.** Calling `screen` from the sync or a poll loop (1h), the extractor (1f).
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Code decides** (`AGENTS.md`, determinism rules): trust and dropping are decided here in code, never by a model.
- **Email-derived strings are untrusted**: header text and the sender address are data. They never reach an error message, and a malformed header is unreadable, never a crash.
- **No network**: no DNS lookups or any other call. This phase reads only the record and the database.
- **Tests use synthetic headers and addresses only.**

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 32 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_sender_auth.py tests/integration/test_store_senders.py tests/integration/test_rules.py --no-cov -q` | `32 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/sender_auth.py,src/mailroom/rules.py,src/mailroom/store.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1e: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1e` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_sender_auth.py tests/integration/test_store_senders.py tests/integration/test_rules.py scripts/critical_modules.txt docs/verification/probe-01e.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '^(import|from) ' -- src/mailroom/sender_auth.py src/mailroom/rules.py | grep -v -E ':(import re|from dataclasses import|from typing import|from mailroom(\.[a-z_]+)? import )'
git grep --untracked -n -E 'httpx|socket|dns|resolver|getaddrinfo|subprocess' -- src/mailroom/sender_auth.py src/mailroom/rules.py src/mailroom/store.py
git grep --untracked -n -E 'raise [A-Za-z]+\(f' -- src/mailroom/sender_auth.py src/mailroom/rules.py
git grep --untracked -n -E 'endswith\([a-z_]*domain\)' -- src/mailroom/sender_auth.py
git grep --untracked -n -E 'authentication_results\[(-1|1|[a-z_]+)\]|for [a-z_]+ in [a-z_.]*authentication_results' -- src/mailroom/sender_auth.py src/mailroom/rules.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/sender_auth.py src/mailroom/rules.py src/mailroom/store.py
```
