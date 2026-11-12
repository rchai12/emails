# Verification guide: Phase 1f (Extractor)

Spec: `docs/phases/phase-01f-extractor.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/extractor.py`
- `tests/integration/test_extractor_more.py`
- `grep -c "^## Phase 1f: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01f-extractor.md tests/fakes.py src/mailroom/extractor_prompt.py tests/unit/test_config_extractor.py tests/integration/test_extractor.py scripts/critical_modules.txt docs/verification/probe-01f.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 29.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 29 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_config_extractor.py tests/integration/test_extractor.py --no-cov -q` | `29 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/extractor.py,src/mailroom/extractor_prompt.py,src/mailroom/config.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1f: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1f` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- tests/fakes.py src/mailroom/extractor_prompt.py tests/unit/test_config_extractor.py tests/integration/test_extractor.py scripts/critical_modules.txt docs/verification/probe-01f.py` | no output |
| G7 | `git status --short` | only the Scope paths |
| G8 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `extractor.py` | write the sent time in UTC instead of the time zone | `tests/integration/test_extractor.py::test_the_user_message_gives_the_sent_time_then_the_email` | `Sent: Tuesday 2026-11-10 02:59` | `Sent: Tuesday 2026-11-10 07:59` |
| S2 | `extractor.py` | match the tags with case | `tests/integration/test_extractor.py::test_without_a_sent_time_the_received_time_is_given_and_tags_are_removed` | `[email tag removed]hi` | `<EMAIL >hi` |
| S3 | `extractor.py` | cut at `>= BODY_LIMIT` instead of `>` | `tests/integration/test_extractor.py::test_a_long_body_is_cut_with_a_note` | no note at exactly the limit | the note at exactly the limit |
| S4 | `extractor.py` | leave `format` out of the request | `tests/integration/test_extractor.py::test_one_request_with_the_named_prompt_schema_and_fixed_sampling` | one request | `ModelUnavailable` `(400)` |
| S5 | `extractor.py` | accept any `done_reason` | `tests/integration/test_extractor.py::test_an_invalid_reply_is_rejected_by_field_name[cut-off]` | `Rejected('done_reason')` | an `Extraction` |
| S6 | `extractor.py` | check booleans by truth (`bool(value)`) instead of type | `tests/integration/test_extractor.py::test_an_invalid_reply_is_rejected_by_field_name[not-a-boolean]` | `Rejected('urgent')` | an `Extraction` |
| S7 | `extractor.py` | check only the length of text fields | `tests/integration/test_extractor.py::test_an_invalid_reply_is_rejected_by_field_name[line-break]` | `Rejected('title')` | an `Extraction` |
| S8 | `extractor.py` | parse the date with `date.fromisoformat` alone | `tests/integration/test_extractor.py::test_an_invalid_reply_is_rejected_by_field_name[not-the-date-form]` | `Rejected('deadline_date')` | an `Extraction` |
| S9 | `extractor.py` | parse the time with `time.fromisoformat` alone | `tests/integration/test_extractor.py::test_an_invalid_reply_is_rejected_by_field_name[seconds]` | `Rejected('deadline_time')` | an `Extraction` |
| S10 | `extractor.py` | allow an empty title when actionable | `tests/integration/test_extractor.py::test_an_invalid_reply_is_rejected_by_field_name[actionable-without-title]` | `Rejected('title')` | an `Extraction` |
| S11 | `extractor.py` | ignore `deadline_date` without `has_deadline` | `tests/integration/test_extractor.py::test_an_invalid_reply_is_rejected_by_field_name[date-without-deadline]` | `Rejected('deadline_date')` | an `Extraction`, `deadline=None` |
| S12 | `extractor.py` | allow an empty reason when suspicious | `tests/integration/test_extractor.py::test_an_invalid_reply_is_rejected_by_field_name[suspicious-without-reason]` | `Rejected('suspicion_reason')` | an `Extraction` |
| S13 | `extractor.py` | treat a read timeout as unavailable | `tests/integration/test_extractor.py::test_a_model_that_takes_too_long_is_rejected` | `Rejected('timeout')` | `ModelUnavailable` `(network)` |
| S14 | `config.py` | accept any host in the address | `tests/unit/test_config_extractor.py::test_a_model_address_off_this_machine_is_refused[other-host]` | `ConfigError` | no exception |
| S15 | `config.py` | give every settings error `DATA_DIR_MESSAGE` | `tests/unit/test_config_extractor.py::test_an_unknown_time_zone_is_refused` | `MAILROOM_TIME_ZONE must be ...` | `MAILROOM_DATA_DIR must be an absolute path` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01f.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks four properties:
- 4,000 replies, each a valid reply with one or two fields changed (wrong types, lengths around each limit, tabs, line breaks, `\u2028`, zero-width and NUL characters, non-ASCII digits, look-alike date and time forms, broken rules between fields, a missing or extra key), are accepted or rejected exactly as an oracle applying requirement 6 says, and accepted ones carry exactly the given values
- only `done_reason` `stop` counts
- on random bodies and subjects full of tag variants, the message holds exactly one `<email>` and one `</email>`, at the ends, around the body as cleaned and cut
- network errors, 4xx and 5xx are `ModelUnavailable` without their text; a read timeout and malformed 200s are `Rejected`

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | no network library but httpx (`urllib.parse` allowed) | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request\|(import\|from) urllib([^.A-Za-z_]\|$)' -- src` |
| Q2 | httpx only in the Gmail modules and the extractor | `git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py'` |
| Q3 | no URL written into the extractor (it comes from settings) | `git grep --untracked -n -E 'https?://' -- src/mailroom/extractor.py src/mailroom/extractor_prompt.py` |
| Q4 | the extractor stores and sends nothing | `git grep --untracked -n -E '^(import\|from) .*(store\|keychain\|sqlite3\|discord)' -- src/mailroom/extractor.py` |
| Q5 | no retries or loops of calls | `git grep --untracked -n -E 'while \|range\(' -- src/mailroom/extractor.py` |
| Q6 | no email text or reply in an error | `git grep --untracked -n -E 'raise [A-Za-z]+\(f\|raise [A-Za-z]+\([a-z_]*(content\|reply\|body\|text\|error)' -- src/mailroom/extractor.py src/mailroom/config.py` |
| Q7 | sampling only from the given `OPTIONS`; no tools or thinking | `git grep --untracked -n -E 'temperature\|seed\|num_ctx\|num_predict\|"tools"\|"think"\|tool_calls' -- src/mailroom/extractor.py` |
| Q8 | nothing is logged or printed | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py'` |
| Q9 | time only through `clock.now()` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py'` |
| Q10 | no coverage or lint exclusions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/extractor.py src/mailroom/config.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- **Field checks.** A table of small checkers keyed by field name, or one function with a branch per field, as long as fields are checked in `FIELDS` order.
- **The address check.** In a pydantic validator, or in `get_settings` after loading.
- **Time zone check.** `ZoneInfo(name)` inside a validator, catching `ZoneInfoNotFoundError` and `ValueError`.
- **`ModelUnavailable`.** An `__init__(detail)` building the text, like the Gmail errors.
- **JSON parsing.** `response.json()` or `json.loads(response.content)`; `json.loads(content)` for the reply.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01f-extractor.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1f`), then run `.venv/bin/python scripts/check_reports.py --phase 1f`; it must print `Reports OK.`
