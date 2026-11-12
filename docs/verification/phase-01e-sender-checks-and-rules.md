# Verification guide: Phase 1e (Sender checks and rules)

Spec: `docs/phases/phase-01e-sender-checks-and-rules.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/sender_auth.py`
- `src/mailroom/rules.py`
- `tests/unit/test_sender_auth_more.py`
- `grep -c "^## Phase 1e: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01e-sender-checks-and-rules.md src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_sender_auth.py tests/integration/test_store_senders.py tests/integration/test_rules.py scripts/critical_modules.txt docs/verification/probe-01e.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 32.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 32 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_sender_auth.py tests/integration/test_store_senders.py tests/integration/test_rules.py --no-cov -q` | `32 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/sender_auth.py,src/mailroom/rules.py,src/mailroom/store.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1e: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1e` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/schema.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_sender_auth.py tests/integration/test_store_senders.py tests/integration/test_rules.py scripts/critical_modules.txt docs/verification/probe-01e.py` | no output |
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
| S1 | `sender_auth.py` | read every header, not only the first | `tests/unit/test_sender_auth.py::test_a_sender_is_verified_only_by_its_provider_s_own_checks[forged-second-header]` | `False` | `True` |
| S2 | `sender_auth.py` | skip the authserv-id check | `tests/unit/test_sender_auth.py::test_a_sender_is_verified_only_by_its_provider_s_own_checks[other-server]` | `False` | `True` |
| S3 | `sender_auth.py` | compare with `"mx.google.com"` for every provider instead of `AUTHSERV_IDS` | `tests/unit/test_sender_auth.py::test_a_sender_is_verified_only_by_its_provider_s_own_checks[unknown-provider]` | `False` | `True` |
| S4 | `sender_auth.py` | align with `endswith(domain)`, without the dot | `tests/unit/test_sender_auth.py::test_a_sender_is_verified_only_by_its_provider_s_own_checks[look-alike]` | `False` | `True` |
| S5 | `sender_auth.py` | accept SPF or DKIM (`or` instead of `and`) | `tests/unit/test_sender_auth.py::test_a_sender_is_verified_only_by_its_provider_s_own_checks[spf-only]` | `False` | `True` |
| S6 | `sender_auth.py` | read only `header.d` for DKIM (ignore `header.i`) | `tests/unit/test_sender_auth.py::test_a_sender_is_verified_only_by_its_provider_s_own_checks[spf-and-dkim]` | `True` | `False` |
| S7 | `sender_auth.py` | do not remove comments | `tests/unit/test_sender_auth.py::test_comments_case_and_broken_headers[nested-comment]` | one prop | extra prop `('(dmarc', 'pass')` |
| S8 | `sender_auth.py` | ignore a stray `)` instead of refusing the header | `tests/unit/test_sender_auth.py::test_comments_case_and_broken_headers[stray-close]` | `('', ())` | `('mx.google.com', ...)` |
| S9 | `sender_auth.py` | keep the result's case | `tests/unit/test_sender_auth.py::test_comments_case_and_broken_headers[case-and-version]` | `'pass'` | `'Pass'` |
| S10 | `sender_auth.py` | keep the version after the authserv-id | `tests/unit/test_sender_auth.py::test_comments_case_and_broken_headers[case-and-version]` | `'mx.google.com'` | `'mx.google.com 1'` |
| S11 | `store.py` | store the address without lowercasing it | `tests/integration/test_store_senders.py::test_a_sender_is_kept_in_lowercase_and_listed_in_order` | `'trusted'` | `None` |
| S12 | `store.py` | insert a status without replacing the old one (`INSERT OR IGNORE`) | `tests/integration/test_store_senders.py::test_a_sender_has_one_status_and_can_be_cleared` | `'muted'` | `'trusted'` |
| S13 | `rules.py` | trust a trusted address without checking `verified` | `tests/integration/test_rules.py::test_a_trusted_address_that_fails_the_checks_is_not_trusted` | `trusted=False` | `trusted=True` |
| S14 | `rules.py` | drop a muted sender only when verified | `tests/integration/test_rules.py::test_mail_from_a_muted_sender_is_dropped[forged]` | `action='drop'` | `action='extract'` |
| S15 | `rules.py` | look up the status for an empty sender too | `tests/integration/test_rules.py::test_mail_without_a_sender_is_screened_without_a_lookup` | a `Screening` | `ValueError` `invalid sender address` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01e.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks three properties:
- on 3,000 random headers (any case, extra spaces, version numbers, comments holding a fake `pass` or a `;`, other servers, extra forged headers after the first), `verified` equals an oracle that reads the structured results; a pass in any header after the provider's own never counts
- `parse_results` and `verified` never raise on random text and return the right types
- on random senders, statuses, headers and bulk flags, `screen` equals the rules: drop only muted, trust only verified trusted, never look up an empty sender

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | the checks import only `re`, `dataclasses`, `typing` and mailroom | `git grep --untracked -n -E '^(import\|from) ' -- src/mailroom/sender_auth.py src/mailroom/rules.py \| grep -v -E ':(import re\|from dataclasses import\|from typing import\|from mailroom(\.[a-z_]+)? import )'` |
| Q2 | no network or DNS | `git grep --untracked -n -E 'httpx\|socket\|dns\|resolver\|getaddrinfo\|subprocess' -- src/mailroom/sender_auth.py src/mailroom/rules.py src/mailroom/store.py` |
| Q3 | error messages are constant (no f-string) | `git grep --untracked -n -E 'raise [A-Za-z]+\(f' -- src/mailroom/sender_auth.py src/mailroom/rules.py` |
| Q4 | alignment always needs the dot | `git grep --untracked -n -E 'endswith\([a-z_]*domain\)' -- src/mailroom/sender_auth.py` |
| Q5 | only the first header is read | `git grep --untracked -n -E 'authentication_results\[(-1\|1\|[a-z_]+)\]\|for [a-z_]+ in [a-z_.]*authentication_results' -- src/mailroom/sender_auth.py src/mailroom/rules.py` |
| Q6 | nothing is logged or printed | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py'` |
| Q7 | time only through `clock.now()` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py'` |
| Q8 | no coverage or lint exclusions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/sender_auth.py src/mailroom/rules.py src/mailroom/store.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- **Comment removal.** A depth counter, a loop of regex replacements of innermost `(...)`, or a small scanner, as long as nesting and unbalanced parentheses behave as required.
- **Props.** Kept as a tuple of pairs as required; lookups through a helper that returns the first or any matching value.
- **Store SQL.** `INSERT ... ON CONFLICT (address) DO UPDATE` or `INSERT OR REPLACE`; `DELETE` for `None`.
- **The address check.** A regex or plain string tests.
- **Literal types.** Typed with `Literal` or as `str`.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01e-sender-checks-and-rules.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1e`), then run `.venv/bin/python scripts/check_reports.py --phase 1e`; it must print `Reports OK.`
