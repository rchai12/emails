# Phase 1f: Extractor

## Goal

Ask the local model what one email needs: send its text to Ollama on this machine with the named prompt, the closed JSON schema and fixed sampling, and turn the reply into an `Extraction`, or into a `Rejected` naming the first field that broke a rule. The model's reply is checked in code and never retried, repaired or guessed around. Adds the settings for the model's address, the model's name and your time zone. Nothing is stored or sent yet: 1g stores the result and decides whether to notify you.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 306, the tests Phase 1e left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_config_extractor.py --ignore=tests/integration/test_extractor.py` must show `306 passed`. The ignored files import names you create.

## Facts

From Ollama's API reference (`docs/api.md` and docs.ollama.com/api/errors), and Python 3.12 and pydantic on this machine.

- **The call.** `POST <host>/api/chat` with `model`, `messages` (roles `system` and `user`), `format` (a JSON schema object; the reply is constrained to it), `stream: false`, `options` (`temperature`, `seed`, `num_ctx`, `num_predict`) and `keep_alive`. The default address is `http://127.0.0.1:11434`.
- **The reply.** A 200 holds `message.content` (the JSON text), `done` and `done_reason`. The reference shows `stop` (and `load`, `unload`) and does not list the others; a reply cut off at `num_predict` does not end with `stop`, so only `stop` counts.
- **Errors** are JSON `{"error": "..."}` with 400, 404 (unknown model), 429, 500 or 502.
- **Lenient parsing.** `date.fromisoformat` also accepts `20261120` and `2026-W47-1`, and `time.fromisoformat` accepts `17:00:30` and `T17:00`. Python's `\d` matches non-ASCII digits. Each value's shape must be checked with `[0-9]` patterns before parsing.
- **Time zones.** `zoneinfo.ZoneInfo(name)` raises `ZoneInfoNotFoundError` for an unknown name and `ValueError` for a name like `../etc/passwd`.
- **Addresses.** `urllib.parse.urlsplit(url)` gives `scheme`, `hostname` (`::1` without brackets), `path`, `query`, `fragment` and `username`. Its `.port` raises `ValueError` for a port above 65535.
- **Settings.** A pydantic `ValidationError` names the field in `errors()[0]["loc"][0]`. Today `get_settings` turns every error into `DATA_DIR_MESSAGE`.
- **Invisible characters.** Line breaks are categories `Cc` (`\n`, `\t`), `Zl` and `Zp` (` `, ` `); zero-width characters are `Cf`.
- **The fake.** `tests.fakes.FakeOllama` answers `POST /api/chat` from its `replies` (a dict, a string, a `(content, done_reason)` pair, a response or an exception), and answers 404 for an unknown model and 400 when `stream` is not `false` or `format` is missing.

## Owner's decisions

- **Ollama** runs the model, through its own API with `format` set to the schema.
- **The model resolves deadlines.** The prompt gives the sent date and your time zone; the model returns the date (and time, if stated), whether it was explicit, and the exact words. Code checks each value; combined approval adds its own checks later.
- **An invalid reply still reaches you.** This phase returns `Rejected(<field>)`; 1g notifies you with the sender, subject and link, marked as unread by the model.

## Architect's decisions

- **Sub-phases move down one.** Storing the result, the notify decision and ranking become **1g**; Discord checkpoint 1 is **1h**; the poll loop is **1i**. The extractor alone fills this phase.
- **The contract is given** in `src/mailroom/extractor_prompt.py`: `PROMPT_NAME`, the system prompt, the 12-field schema, the sampling options and the limits. The schema is flat and uses only what Ollama's grammar handles: strings, booleans and one enum, with no nulls. Lengths and the rules between fields are checked in code.
- **The email is marked off as data.** It sits between `<email>` and `</email>`, and any such tag inside the email's own text becomes `[email tag removed]`. The sent time (code-made) goes outside the tags. The body is cut at 24,000 characters with a note.
- **Strict checks, in field order.** The first field that breaks a rule names the rejection. A title for a non-actionable email and `deadline_explicit` without a deadline are allowed, because they do no harm. A deadline in the past is allowed too (an overdue notice), but a date that does not exist is rejected.
- **Unavailable, not rejected**, when the model can't be reached: no model configured, a network error other than a read timeout, or a status other than 200. 1i tries the email again on a later poll. A read timeout is a bad reply (`Rejected("timeout")`), as you chose.
- **Settings** are named `extractor_url`, `extractor_model` and `time_zone` (`MAILROOM_EXTRACTOR_URL`, `MAILROOM_EXTRACTOR_MODEL`, `MAILROOM_TIME_ZONE`). The address must be on this machine. The model name and time zone have no defaults: an empty one makes the extractor unavailable, rather than guessing your zone.
- **No `think` option** is sent: Ollama's reference does not say how a model without thinking support treats it (see "Verify before building").
- **Critical modules**: `extractor.py` (it decides what model output is accepted); `config.py` already is one.

## Verify before building

On the Mac Studio, with the chosen model pulled:
- Ollama accepts this `format` schema with that model, and a reply ends with `done_reason` `stop`.
- If the model is a thinking model, check whether `message.content` holds only the JSON. If not, a new prompt version must add `think: false`.
- A 24,000-character email fits in `num_ctx` 32768 and answers within 120 seconds while the Mac's other services are busy.

## Requirements

1. **`config.py`: three settings.**
   - `extractor_url: str = "http://127.0.0.1:11434"`. It must split into scheme `http`; hostname `127.0.0.1`, `localhost` or `::1`; an optional port that `.port` can read; and an empty path, query and fragment, with no user name. Otherwise it is refused with `EXTRACTOR_URL_MESSAGE = "MAILROOM_EXTRACTOR_URL must be http:// on 127.0.0.1, localhost or [::1], with no path"`.
   - `extractor_model: str = ""`.
   - `time_zone: str = ""`. A non-empty value must load with `zoneinfo.ZoneInfo`, else it is refused with `TIME_ZONE_MESSAGE = "MAILROOM_TIME_ZONE must be an IANA time zone name"`.
   - `get_settings` raises `ConfigError` with the message for the field the first error names: `DATA_DIR_MESSAGE`, `EXTRACTOR_URL_MESSAGE` or `TIME_ZONE_MESSAGE`. It never includes the value.

2. **`src/mailroom/extractor.py`, results.**
   - `Deadline`, a `@dataclass(frozen=True)`: `date: datetime.date`, `time: datetime.time | None`, `explicit: bool`, `quote: str`.
   - `Extraction`, a `@dataclass(frozen=True)`: `summary: str`, `actionable: bool`, `urgent: bool`, `title: str`, `deadline: Deadline | None`, `suspicious: bool`, `suspicion_reason: str`, `confidence: str`.
   - `Rejected`, a `@dataclass(frozen=True)`: `reason: str`, a field name or one of `timeout`, `response`, `done_reason`, `content`, `fields`.
   - `ModelUnavailable(Exception)`, built as `ModelUnavailable(detail)` with text `model unavailable (<detail>)`, where the detail is `not configured`, `network` or the HTTP status number. Always raised `from None`.
   - `TIMEOUT_SECONDS = 120.0`.

3. **`user_message(record: Record, time_zone: str) -> str`.**
   - **The first line** is `Sent: ` and `record.sent_at`, or (when that is `None`) `Received: ` and `record.received_at`. The time is converted to `ZoneInfo(time_zone)` and written as `%A %Y-%m-%d %H:%M`, then ` (<time_zone>)`.
   - **Then**, joined by `"\n"`: `<email>`; `From: <sender_name> <<sender>>`; `Subject: <subject>`; an empty line; the body; `</email>`.
   - **Tags.** In the sender name, subject and body, every match of `</?email\s*>` (ignoring case) becomes `extractor_prompt.TAG_NOTE`.
   - **The cut.** Then a body longer than `BODY_LIMIT` is cut to `BODY_LIMIT` characters, followed by `"\n"` and `CUT_NOTE`.

4. **`extract(record: Record, settings: Settings, http: httpx.Client) -> Extraction | Rejected`: the call.**
   - An empty `settings.extractor_model` or `settings.time_zone` raises `ModelUnavailable("not configured")` before any request.
   - Otherwise it makes exactly one `http.post(settings.extractor_url + "/api/chat", json=...)` with exactly `model`, `messages` (`{"role": "system", "content": SYSTEM_PROMPT}` then `{"role": "user", "content": user_message(record, settings.time_zone)}`), `format=SCHEMA`, `stream=False`, `options=OPTIONS` and `keep_alive=KEEP_ALIVE`, all from `extractor_prompt`.
   - **Failures of the call.** `httpx.ReadTimeout` returns `Rejected("timeout")`. Any other `httpx.TransportError` raises `ModelUnavailable("network")`. A status other than 200 raises `ModelUnavailable(<status>)`.

5. **The reply.**
   1. The body must be a JSON object whose `message` is an object with a string `content`, else `Rejected("response")`.
   2. `done_reason` must be `"stop"`, else `Rejected("done_reason")`.
   3. `content` must parse as a JSON object, else `Rejected("content")`.
   4. Its keys must be exactly `extractor_prompt.FIELDS`, else `Rejected("fields")`.
   5. The fields are then checked in `FIELDS` order (requirement 6); the first that fails gives `Rejected(<its name>)`.

6. **Each field.** "Plain" means a string with no character of Unicode category `Cc`, `Cf`, `Zl` or `Zp`; "filled" means non-empty after `strip()`.
   - `actionable`, `urgent`, `has_deadline`, `deadline_explicit`, `suspicious`: exactly `bool` (not `0`, `1` or `"true"`).
   - `summary`: plain, at most `SUMMARY_LIMIT`, filled.
   - `title`: plain, at most `TITLE_LIMIT`, and filled when `actionable`.
   - `deadline_date`: a string. With `has_deadline` it must match `[0-9]{4}-[0-9]{2}-[0-9]{2}` and be a real date; without, it must be `""`.
   - `deadline_time`: a string. With `has_deadline` it must be `""` or match `[0-9]{2}:[0-9]{2}` and be a real time; without, it must be `""`.
   - `deadline_quote`: plain, at most `QUOTE_LIMIT`; filled with `has_deadline`, `""` without.
   - `suspicion_reason`: plain, at most `REASON_LIMIT`; filled when `suspicious`, `""` when not.
   - `confidence`: `"high"`, `"medium"` or `"low"`.
   - **The result.** An `Extraction` with the values as given. `deadline` is `None` without `has_deadline`; with it, it is `Deadline(<the date>, <the time or None for "">, deadline_explicit, deadline_quote)`.

7. **`open_model_http() -> httpx.Client`** returns `httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)`.

8. **Critical modules.** `scripts/critical_modules.txt` (given) lists `extractor.py`.

9. **Progress entry** for `## Phase 1f: Extractor (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/fakes.py` | Adds `FakeOllama` |
| `src/mailroom/extractor_prompt.py` | The prompt name and text, schema, fields, sampling and limits |
| `tests/unit/test_config_extractor.py` | 6 tests (requirement 1) |
| `tests/integration/test_extractor.py` | 23 tests (requirements 2 to 6) |
| `scripts/critical_modules.txt` | Adds `extractor.py` |
| `docs/verification/probe-01f.py` | The verifier's probe |

Given test count: **29**.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_extractor_more.py` (and `tests/unit/test_config_extractor_more.py` if needed), never by changing a given test, for at least:
- a 200 whose body is not JSON, or has no `message` (`Rejected("response")`)
- `content` that is a JSON list (`Rejected("content")`)
- `[::1]` and `localhost` addresses accepted; a user name in the address refused
- `open_model_http()`'s timeout, `trust_env` and `follow_redirects`

## Scope

| Path | Change |
|---|---|
| `src/mailroom/extractor.py` | create |
| `src/mailroom/config.py` | add the three settings, their two messages and the per-field message |
| `tests/integration/test_extractor_more.py` | create |
| `tests/unit/test_config_extractor_more.py` | create, only if coverage needs it |
| `docs/progress.md` | append your entry |

## Out of scope

- **Using the result.** Storing it, clearing it after 24 hours, the notify decision, ranking, the "clearly dated" checks, the evidence quote's presence in the email (1g and stage 2).
- **More model work.** Retries, a second model, streaming, `think`, tools, few-shot examples, any prompt text not in the given file, batching emails.
- **Other changes.** A CLI command, logging, an OpenAI-compatible client. Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **The model suggests, code decides** (`AGENTS.md`): one named prompt, a closed schema, fixed sampling. An invalid reply is rejected by field name and never retried or repaired.
- **Email text stays on this machine**: it goes only to the model at `extractor_url`, which must be loopback. Tests reach it only through `FakeOllama`. Never run the extractor against a real Ollama.
- **No email text or model reply in an error.** `ModelUnavailable` carries only a detail word or a status; `Rejected` carries only a field name.
- **Email-derived strings are untrusted**: the email's text is data inside the tags, and the model's strings are plain text within their limits.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 29 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_config_extractor.py tests/integration/test_extractor.py --no-cov -q` | `29 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/extractor.py,src/mailroom/extractor_prompt.py,src/mailroom/config.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1f: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1f` | `Reports OK.` |
| `git diff HEAD --stat -- tests/fakes.py src/mailroom/extractor_prompt.py tests/unit/test_config_extractor.py tests/integration/test_extractor.py scripts/critical_modules.txt docs/verification/probe-01f.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request|(import|from) urllib([^.A-Za-z_]|$)' -- src
git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py'
git grep --untracked -n -E 'https?://' -- src/mailroom/extractor.py src/mailroom/extractor_prompt.py
git grep --untracked -n -E '^(import|from) .*(store|keychain|sqlite3|discord)' -- src/mailroom/extractor.py
git grep --untracked -n -E 'while |range\(' -- src/mailroom/extractor.py
git grep --untracked -n -E 'raise [A-Za-z]+\(f|raise [A-Za-z]+\([a-z_]*(content|reply|body|text|error)' -- src/mailroom/extractor.py src/mailroom/config.py
git grep --untracked -n -E 'temperature|seed|num_ctx|num_predict|"tools"|"think"|tool_calls' -- src/mailroom/extractor.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/extractor.py src/mailroom/config.py
```
