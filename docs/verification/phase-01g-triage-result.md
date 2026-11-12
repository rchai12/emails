# Verification guide: Phase 1g (Triage result)

Spec: `docs/phases/phase-01g-triage-result.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/triage.py`
- `tests/integration/test_store_triage_more.py`
- `tests/integration/test_triage_more.py`
- `grep -c "^## Phase 1g: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01g-triage-result.md src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_triage_decide.py tests/integration/test_store_triage.py tests/integration/test_triage.py scripts/critical_modules.txt docs/verification/probe-01g.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 51.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 51 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_triage_decide.py tests/integration/test_store_triage.py tests/integration/test_triage.py --no-cov -q` | `51 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/triage.py,src/mailroom/store.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1g: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1g` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_triage_decide.py tests/integration/test_store_triage.py tests/integration/test_triage.py scripts/critical_modules.txt docs/verification/probe-01g.py` | no output |
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
| S1 | `triage.py` | In `should_notify`, drop step 6 (`medium` with bulk) | `tests/unit/test_triage_decide.py::test_only_sure_non_tasks_and_dropped_mail_are_not_notified[bulk-medium-confidence]` | `False` | `True` |
| S2 | `triage.py` | In `should_notify`, drop step 3 (trusted) | `tests/unit/test_triage_decide.py::test_only_sure_non_tasks_and_dropped_mail_are_not_notified[trusted]` | `True` | `False` |
| S3 | `triage.py` | In `rank`, count a deadline without a time as `time.min` instead of `time.max` | `tests/unit/test_triage_decide.py::test_two_emails_rank_in_the_documented_order[a-time-before-the-end-of-the-day]` | first `'a'` | first `'b'` |
| S4 | `triage.py` | In `rank`, give an unknown extraction a confidence after `low` | `tests/unit/test_triage_decide.py::test_an_email_with_no_extraction_ranks_as_if_nothing_is_known[newer-unreadable-before-known-low]` | first `'b'` | first `'a'` |
| S5 | `triage.py` | In `rank`, put the oldest `received_at` first | `tests/unit/test_triage_decide.py::test_two_emails_rank_in_the_documented_order[newest-first]` | first `'b'` | first `'a'` |
| S6 | `store.py` | In `clear_expired_text`, skip the `triage` update | `tests/integration/test_store_triage.py::test_the_extraction_is_cleared_with_the_email_text` | `text_cleared_at` 2026-11-11 08:15 | `text_cleared_at=None` |
| S7 | `store.py` | In `save_triage`, insert without the `messages` condition (plain `VALUES ... ON CONFLICT DO NOTHING`) | `tests/integration/test_store_triage.py::test_a_verdict_for_a_message_whose_text_is_cleared_is_refused` | `False` | `True` |
| S8 | `triage.py` | In `triage_message`, skip step 2 (the stored verdict) | `tests/integration/test_triage.py::test_a_message_already_triaged_is_not_sent_to_the_model_again` | equal verdict, no request | `IndexError` (the fake has no reply) |
| S9 | `triage.py` | In `triage_message`, catch `ModelUnavailable` and store a rejected verdict | `tests/integration/test_triage.py::test_an_unavailable_model_stores_nothing` | `ModelUnavailable` raised | no exception |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01g.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks, beyond the given tests: the notify rule on 4,000 random verdicts; `rank` on 600 random lists of up to 8 emails against a step-by-step comparison (trust, spam, urgency, deadline with and without a time, confidence, unreadable and cleared verdicts, newest, provider and message id); 300 verdicts with awkward text (quotes, backslashes, non-ASCII, JSON-looking text) read back exactly; and clearing at 5 later times removing exactly the extractions whose email was fetched 24 hours earlier, changing no other field.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Network only through httpx; no Discord yet | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|discord)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request\|(import\|from) urllib([^.A-Za-z_]\|$)' -- src` |
| Q2 | httpx only where a phase allowed it (`triage.py` only to name the client's type) | `git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py'` |
| Q3 | `triage.py` reaches the model only through `extract` | `git grep --untracked -n -E 'httpx\.[A-Za-z]+\(\|http\.(get\|post\|put\|patch\|delete\|request\|send\|stream)\(' -- src/mailroom/triage.py` |
| Q4 | No import cycle: `store.py` imports neither the rules nor triage | `git grep --untracked -n -E '^(import\|from) .*(rules\|triage)([^A-Za-z_]\|$)' -- src/mailroom/store.py` |
| Q5 | Verdicts and dedup keys are kept; the schema changes only by migration | `git grep --untracked -n -E 'DELETE FROM triage\|DROP TABLE\|ALTER TABLE' -- src` |
| Q6 | No retry loop around the model | `git grep --untracked -n -E 'while \|range\(' -- src/mailroom/triage.py` |
| Q7 | No email text in logs | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py'` |
| Q8 | Time only through `clock.now()` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py'` |
| Q9 | Full coverage is earned, not excused | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/triage.py src/mailroom/store.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Any JSON layout for `extraction`, as long as it reads back to an equal `Extraction` and is `NULL` after clearing.
- One SQL statement or two for `clear_expired_text`, and either order of the two updates, inside one commit.
- `rank` built from one key tuple, from a comparison function, or from several stable sorts.
- `triage_message` returning the built verdict even if `save_triage` returned `False`.
- `import httpx` in `triage.py` (or under `TYPE_CHECKING`) to name the client's type.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01g-triage-result.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1g`), then run `.venv/bin/python scripts/check_reports.py --phase 1g`; it must print `Reports OK.`
