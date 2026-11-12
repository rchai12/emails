# Phase 1a: parser and store

## Goal

Turn a raw email (the RFC 822 bytes every provider can return) into the normalized record, with every untrusted string cleaned and length-limited, and keep records in the SQLite database with deduplication and the 24-hour clearing of email text. No adapter, triage, model or Discord yet: this phase is the provider-neutral core the six stage 1 sub-phases build on.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 96, the tests Phase 0 left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_mime.py --ignore=tests/integration/test_store.py` must show `105 passed` (N plus the 9 given record tests, which test given code). The two ignored files import `mailroom.mime` and `mailroom.store`, which you create.

## Facts

Checked on this machine (Python 3.12.16, SQLite 3.54.1). `P` below is `email.parser.BytesParser(policy=email.policy.default)`.

- **Choosing the body.** `message.get_body(preferencelist=("plain", "html"))` returns the `text/plain` part of a `multipart/alternative`, skips parts with `Content-Disposition: attachment`, returns the `text/html` part of a `multipart/related`, and returns `None` when the only part is an attachment or a `message/rfc822`. A message without `Content-Type` is `text/plain`.
- **Decoding.** `part.get_content()` decodes the transfer encoding and charset, replacing bad bytes with U+FFFD. It raises `LookupError` for an unknown charset (`charset=x-unknown`) and `ValueError` for `Content-Type: charset=\x00`. In both cases `part.get_payload(decode=True)` still returns the decoded bytes.
- **Exceptions from the email package.** Fuzzing 20,000 corrupted headers found these, each pinned by a given test or the probe:
  - reading the header of `From: :;\xe6` raises `AttributeError`
  - reading `From: =?utf-8?q?A=0AB?= <x@example.test>` raises `ValueError` (newline in an address part)
  - `P.parsebytes` itself raises `IndexError` for `Content-Type: ;\xd9*`; parsing with `headersonly=True` raises too
  Other inputs may raise other exception types, so every guard below catches `Exception`.
- **Undecodable header bytes** come back as surrogate escapes, U+DC80 to U+DCFF, one per byte: raw UTF-8 `From: José <j@example.test>` gives the display name `'Jos\udcc3\udca9'`.
- **Addresses.** `header.addresses` gives `Address` objects with `display_name` and `addr_spec`. `From: <<>>` gives `addr_spec` `'<>'`; `From: justaname` gives `'justaname'`; `From: undisclosed-recipients:;` gives no addresses; `From: a@x, b@x` gives two. `From: "billing@bank.example.test" <evil@phish.example.test>` gives the display name `billing@bank.example.test`.
- **Headers.** `str(message["Subject"])` decodes RFC 2047 words and unfolds lines but keeps the tab of a folded line (`'Pay\tnow'`). A header with an empty value reads as `''`. `message.get_all(name)` returns every value in order, or `None`.
- **Dates.** `email.utils.parsedate_to_datetime(text)` returns an aware datetime, a naive one for `-0000`, and raises `ValueError` for `garbage` or `''`.
- **`html.parser.HTMLParser(convert_charrefs=True)`** lower-cases tag and attribute names, decodes entities in text and attribute values (`&nbsp;` becomes U+00A0, an unknown `&bogus;` stays as written), treats the content of `script` and `style` as raw text up to the matching end tag (to the end of the input if there is none), sends `<br/>` to `handle_starttag` and then `handle_endtag`, and does not raise on malformed HTML. An attribute without a value has the value `None`.
- **SQLite.** `STRICT` tables and `INSERT ... ON CONFLICT DO NOTHING` work; the cursor's `rowcount` is 1 for an insert and 0 for a conflict. With `PRAGMA secure_delete = ON`, text set to `NULL` is gone from the file; with it off, two rows with bodies of about 200 characters leave the text readable in the file (`tests/integration/test_store.py` relies on this). A new database file is created with mode `0o644` under umask `022`. The default journal mode, `delete`, leaves no extra file after a commit. `PRAGMA user_version` does not take a `?` parameter. Python 3.12's `sqlite3.connect` takes `autocommit=True`.

## Owner's decisions

- Stage 1 is six sub-phases: **1a** record, parser and store; **1b** Gmail adapter against a fake Gmail; **1c** sender authentication and rules; **1d** extractor (prompt, schema, validation, fake model); **1e** notify decision and Discord checkpoint 1; **1f** the poll loop.
- One raw-MIME parser serves all three providers, so identical emails give identical records.
- HTML is turned into text with the standard library's `html.parser`.
- The database is the standard library's `sqlite3` with plain SQL.

## Architect's decisions

- **The record** (`src/mailroom/record.py`, given) has the eight fields of `docs/architecture.md` plus four triage needs later: `sender_name`, `sent_at` (for relative deadlines), `list_unsubscribe` (1c lowers the score) and `authentication_results` (1c checks DMARC, SPF and DKIM). The adapter supplies the `Envelope` (provider, the provider's own message ID, thread ID, received time, link); the parser adds the rest.
- **Limits**: subject 200 characters, sender name 100, address 254, each `Authentication-Results` value 2000, at most 10 of them, body 100,000.
- **The address is lower-cased whole**, and is `""` unless it looks like `local@domain`. Trust (1c) matches exact addresses, so case must not matter.
- **The parser never raises** because of a message's content, and never drops one: missing triage beats a crash that stalls polling. What it cannot read becomes empty; a message it cannot parse at all keeps its whole raw text as the body.
- **Retention clears `body_text` and `authentication_results`.** The sender, subject and the rest stay, as `docs/ingestion.md` keeps them for pending items. `secure_delete` makes the cleared text leave the file, and the database file is mode `0o600`.
- **Times are stored as UTC text** with microseconds (`2026-11-11T09:00:00.000000+00:00`), so text comparison is time comparison.
- **The schema** (`src/mailroom/schema.py`, given) is numbered migrations in `PRAGMA user_version`. This phase creates only `messages`; each later table arrives with its phase.
- **Critical modules** gain `mime.py` and `store.py`.

## Requirements

1. **Given modules.** `src/mailroom/record.py` (`Envelope`, `Record`, `PROVIDERS`, `FIELD_MESSAGE`, `ID_LIMIT`, `LINK_LIMIT`) and `src/mailroom/schema.py` (`MIGRATIONS`, `SCHEMA_VERSION`) are given. Use them as they are.

2. **`src/mailroom/mime.py`, limits**: `SUBJECT_LIMIT = 200`, `NAME_LIMIT = 100`, `ADDRESS_LIMIT = 254`, `HEADER_LIMIT = 2000`, `AUTH_RESULTS_LIMIT = 10`, `BODY_LIMIT = 100_000`.

3. **Undecodable text.** `clean_line` and `clean_text` first repair surrogates: each run of surrogate escapes (U+DC80 to U+DCFF) is turned back into its bytes (U+DCxx is byte 0xxx) and decoded as UTF-8 with `errors="replace"`; any other surrogate (U+D800 to U+DFFF) becomes U+FFFD. Everything else is unchanged.

4. **`clean_line(text: str, limit: int) -> str`**, for one-line fields. After step 3:
   1. remove every character whose Unicode category is `Cc` or `Cf` and for which `str.isspace()` is false
   2. collapse whitespace: `" ".join(text.split())`
   3. keep the first `limit` characters, then remove trailing spaces

5. **`clean_text(text: str, limit: int) -> str`**, for bodies. After step 3:
   1. replace `"\r\n"`, then each remaining `"\r"`, with `"\n"`
   2. remove every character of category `Cc` or `Cf` except `"\n"` and `"\t"`
   3. remove trailing whitespace from each line (`line.rstrip()`, lines split on `"\n"`)
   4. replace each run of three or more `"\n"` with `"\n\n"`
   5. remove leading and trailing `"\n"`
   6. keep the first `limit` characters, then remove trailing whitespace (`rstrip()`)

6. **`html_to_text(html: str) -> str`**, with `HTMLParser(convert_charrefs=True)`, fed the whole input and closed.
   - **Dropped text.** Text inside `script` and `style` is dropped. Their tags request no break.
   - **Text pieces.** Every other piece of text has each run of whitespace characters (`str.isspace()`) replaced by one space.
   - **Breaks.** A start or end tag of `br`, `div`, `li`, `tr`, `dt`, `dd`, `header`, `footer`, `section`, `article`, `aside`, `address`, `pre` or `hr` requests one newline. A start or end tag of `p`, `h1` to `h6`, `ul`, `ol`, `dl`, `table` or `blockquote` requests two. Before a piece of text is output, the largest number requested since the previous output piece is written as that many `"\n"` (requests are not added up), and the request count goes back to zero. Requests before the first output piece are dropped, as are requests after the last.
   - **Lone spaces.** A piece that is exactly `" "` is dropped (not output) while a request is pending.
   - **Cells.** The end tag of `td` or `th` adds a piece `" "`.
   - **Links.**
     - An `<a>` start tag remembers the first `href` attribute when its value, with leading and trailing whitespace removed, starts with `http://`, `https://` or `mailto:` (any case). Otherwise the `<a>` remembers nothing. Each `<a>` start replaces whatever an earlier unclosed one remembered.
     - At `</a>`, if a link is remembered, compare it with the anchor's text. That text is the pieces output since that `<a>` (not the newlines written for breaks), joined, with whitespace collapsed (`" ".join(text.split())`). If they differ, add the piece `" (<link>)"`, with the link as remembered. Then forget the link.
     - Unclosed anchors add nothing at the end.
   - **Finish.** Join the output. Collapse whitespace within each line (`" ".join(line.split())`, lines split on `"\n"`). Return `clean_text(result, BODY_LIMIT)`.

7. **`parse_message(raw: bytes, envelope: Envelope) -> Record`**, parsing. Parse with `email.parser.BytesParser(policy=email.policy.default).parsebytes(raw)`.
   - **Unparseable message.** If parsing raises any `Exception`, return a `Record` with the envelope's fields and these values:
     - `sender`, `sender_name` and `subject` are `""`
     - `sent_at` is `None`
     - `list_unsubscribe` is `False`
     - `authentication_results` is `()`
     - `body_text` is `clean_text(raw.decode("utf-8", errors="replace"), BODY_LIMIT)`
   - **Unreadable header.** Reading a header means `message[name]`, `str(...)` of it, its `.addresses`, or `message.get_all(name)`. If reading one raises any `Exception`, that header counts as missing.
   - **Envelope fields.** The record's `provider`, `message_id`, `thread_id`, `received_at` and `link` are the envelope's.
   - **Never raises.** `parse_message` raises for no `bytes` input.

8. **`parse_message`, the sender.**
   - **Which address.** Take the first address of `From`. With no `From` or no addresses, `sender` and `sender_name` are `""`.
   - **`sender`.** The address's `addr_spec`, lower-cased, if it matches `[^@\s<>]+@[^@\s<>]+` in full and has at most `ADDRESS_LIMIT` characters; otherwise `""`.
   - **`sender_name`.** `clean_line(display_name, NAME_LIMIT)`. It is set even when `sender` is `""`.

9. **`parse_message`, other headers.**
   - **`subject`.** `clean_line(str(Subject), SUBJECT_LIMIT)`, or `""` if there is no `Subject`.
   - **`sent_at`.** `email.utils.parsedate_to_datetime(str(Date))` converted to UTC. A naive result counts as UTC. A missing date, or one that raises `ValueError` or `TypeError`, gives `None`.
   - **`list_unsubscribe`.** `True` when `List-Unsubscribe` is present and its value is not empty after `strip()`.
   - **`authentication_results`.**
     1. Take every `Authentication-Results` value, in order.
     2. Clean each with `clean_line(str(value), HEADER_LIMIT)`.
     3. Drop the ones that come out empty.
     4. Keep the first `AUTH_RESULTS_LIMIT` as a tuple.

10. **`parse_message`, the body.**
    - **Choose the part** with `message.get_body(preferencelist=("plain", "html"))`. If that raises or returns `None`, `body_text` is `""`.
    - **Decode it** with `part.get_content()`. If that raises any `Exception`, use `part.get_payload(decode=True)` decoded as UTF-8 with `errors="replace"`. The text is `""` if the payload is not `bytes` or decoding it raises.
    - **Clean it.** A `text/html` part's text goes through `html_to_text`; then the body is `clean_text(text, BODY_LIMIT)`.

11. **`src/mailroom/store.py`, opening.**
    - **Names.**
      - `DB_FILENAME = "mailroom.sqlite3"`
      - `SCHEMA_MESSAGE = "unsupported schema version"`
      - `class StoreError(Exception)`
    - **`class Store`.** `Store(path: Path)` opens the database at `path` with one `sqlite3` connection, sets `PRAGMA secure_delete = ON` on it, and sets the file's mode to exactly `0o600`. It leaves the journal mode at its default.
    - **Migrations.** Let `v` be the database's `PRAGMA user_version`.
      - If `v > len(MIGRATIONS)`, the store closes the connection and raises `StoreError(f"{SCHEMA_MESSAGE}: {v}")`.
      - Otherwise it runs each `MIGRATIONS[i]` for `i` from `v` up, each in one transaction with `PRAGMA user_version = i + 1`.
    - **Closing.** `close()` closes the connection. A `Store` is a context manager: `__enter__` returns it, and `__exit__` closes it.
    - **`open_store(settings: Settings) -> Store`** calls `prepare_data_dir(settings)` and opens `Store(settings.data_dir / DB_FILENAME)`.

12. **`store.py`, records.**
    - **Times.** A time is stored as `t.astimezone(UTC).isoformat(timespec="microseconds")`, and read back with `datetime.fromisoformat`.
    - **Columns.**
      - `authentication_results` is a JSON array of strings.
      - `list_unsubscribe` is `0` or `1`.
      - `sent_at` is `NULL` when `None`.
    - **`add(record: Record) -> bool`.**
      - Inserts the record with `fetched_at = clock.now()`, calling `clock.now()` exactly once per call.
      - Returns `True` if the row is new. Returns `False`, changing nothing, if a row with the same `(provider, message_id)` exists, even when its text was cleared.
      - Commits before returning.
    - **`@dataclass(frozen=True) class StoredMessage`** has `record: Record`, `fetched_at: datetime` and `text_cleared_at: datetime | None`.
    - **`get(provider: str, message_id: str) -> StoredMessage | None`.**
      - Returns the stored row, or `None` if there is none.
      - In a cleared row, `record.body_text` is `""` and `record.authentication_results` is `()`.
      - `get` does not read the clock.

13. **`store.py`, retention.** `TEXT_RETENTION = timedelta(hours=24)`.
    - **`clear_expired_text() -> int`** reads `now = clock.now()` exactly once.
    - **Which rows.** It touches every row with `text_cleared_at` `NULL` and `fetched_at <= now - TEXT_RETENTION`.
    - **What it does.** It sets their `body_text` and `authentication_results` to `NULL` and their `text_cleared_at` to `now`, commits, and returns how many rows it changed.

14. **Critical modules.** `scripts/critical_modules.txt` (given) now lists `mime.py` and `store.py`: every line and branch of both must be covered.

15. **Progress entry** for `## Phase 1a: parser and store (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/record.py` | `Envelope` and `Record`, with field checks |
| `src/mailroom/schema.py` | `MIGRATIONS` (the `messages` table) and `SCHEMA_VERSION` |
| `scripts/critical_modules.txt` | Adds `mime.py` and `store.py` |
| `tests/unit/test_record.py` | 9 tests (requirement 1) |
| `tests/unit/test_mime.py` | 49 tests (requirements 2 to 10) |
| `tests/integration/test_store.py` | 11 tests (requirements 11 to 13) |

Given test count: **69**.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage of `mime.py` and `store.py`, add behaviour tests in new files, `tests/unit/test_mime_more.py` and `tests/integration/test_store_more.py`, never by changing a given test. For example, a header for which `get_all` raises can be simulated with a `monkeypatch` of `EmailMessage.get_all`.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/mime.py` | create |
| `src/mailroom/store.py` | create |
| `tests/unit/test_mime_more.py` | create, only if coverage needs it |
| `tests/integration/test_store_more.py` | create, only if coverage needs it |
| `docs/progress.md` | append your entry |

## Out of scope

- Any provider adapter, fetching, polling or sync bookmark; the Yahoo `Message-ID` fallback and thread derivation (phase 5).
- Reading `Authentication-Results` for meaning (1c), rules, scores, the extractor, Discord.
- Any table other than `messages`, a migration tool, a database command in the CLI, a scheduler for `clear_expired_text`.
- Forwarded messages as attachments (`message/rfc822`), attachments, images and their `alt` text, hidden-text detection, `pre` whitespace.
- `VACUUM`, WAL, connection pools, threads.
- Logging. Nothing in this phase logs or prints.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Email text stays local.** Nothing in `mime.py` or `store.py` logs, prints, or puts email text in an exception. `StoreError`'s text is `SCHEMA_MESSAGE` and a number.
- **Synthetic data only** in any test you add: invented addresses under `example.test`, never a real email.
- **Time through the module**: `clock.now()`, never `datetime.now()`, and never `from mailroom.clock import now`.
- **No network**: `mime.py` and `store.py` import nothing that can open a connection.
- **SQL takes values as `?` parameters.** The one exception is `PRAGMA user_version = <int>`, built from the migration index.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 69 passed, 0 failed, 0 skipped; `critical coverage: passed` |
| `.venv/bin/python -m pytest tests/unit/test_record.py tests/unit/test_mime.py tests/integration/test_store.py --no-cov -q` | `69 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/mime.py,src/mailroom/store.py,src/mailroom/record.py,src/mailroom/schema.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1a: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1a` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/record.py src/mailroom/schema.py scripts/critical_modules.txt tests/unit/test_record.py tests/unit/test_mime.py tests/integration/test_store.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing, except the fifth, which prints exactly one line.

```zsh
git grep --untracked -n -E 'import (socket|ssl|imaplib|smtplib|http|urllib|requests|httpx)([^A-Za-z_]|$)|from (socket|ssl|imaplib|smtplib|http|urllib|requests|httpx)([^A-Za-z_]|$)' -- src
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.clock import' -- src ':!src/mailroom/clock.py'
git grep --untracked -n -E -i 'journal_mode|wal_|vacuum' -- src
git grep --untracked -n -E -i 'secure_delete' -- src/mailroom/store.py
git grep --untracked -n -E 'execute(script|many)?\(f' -- src/mailroom/store.py | grep -v user_version
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/mime.py src/mailroom/store.py
```
