# Verification guide: Phase 4d (Outlook in the service)

Spec: `docs/phases/phase-04d-outlook-service.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:


- `grep -c "^## Phase 4d: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-04d-outlook-service.md src/mailroom/discord_layout.py tests/unit/test_sender_auth_outlook.py tests/unit/test_config_outlook.py tests/integration/test_service_outlook.py tests/integration/test_service.py docs/verification/probe-04d.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 39.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 27 = 1211 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_sender_auth_outlook.py tests/unit/test_config_outlook.py tests/integration/test_service_outlook.py tests/integration/test_service.py --no-cov -q` | `39 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/sender_auth.py,src/mailroom/config.py,src/mailroom/alerts.py,src/mailroom/service.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `.venv/bin/python docs/verification/probe-04d.py` | last line `FAILURES 0` |
| G5 | `grep -c "^## Phase 4d: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4d` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- src/mailroom/discord_layout.py tests/unit/test_sender_auth_outlook.py tests/unit/test_config_outlook.py tests/integration/test_service_outlook.py tests/integration/test_service.py docs/verification/probe-04d.py` | no output |
| G8 | `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| G9 | `git status --short` | only the Scope paths |
| G10 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `sender_auth.py` | Drop the `compauth` requirement | `tests/unit/test_sender_auth_outlook.py::test_microsofts_first_header_decides[no-compauth]` | `False` | `True` |
| S2 | `sender_auth.py` | Skip a leading server name instead of refusing it | `tests/unit/test_sender_auth_outlook.py::test_microsofts_first_header_decides[server-name]` | `False` | `True` |
| S3 | `sender_auth.py` | Accept any header of the email, not only the first | `tests/unit/test_sender_auth_outlook.py::test_only_the_first_header_counts` | `False` (weak header first) | `True` |
| S4 | `service.py` | Raise Gmail's sign-in text for an Outlook account | `tests/integration/test_service_outlook.py::test_a_signed_out_outlook_account_pings_you_and_its_fix_is_announced` | `'<@…> Outlook sign-in needed for live. …'` | `'<@…> Gmail sign-in needed for live. …'` |
| S5 | `service.py` | Post the Outlook catch-up without `provider="outlook"` | `tests/integration/test_service_outlook.py::test_an_outlook_catch_up_is_announced_with_its_provider` | `'Outlook live caught up …'` | `'Gmail live caught up …'` |
| S6 | `service.py` | Catch only `OutlookAuthError` around Outlook sync | `tests/integration/test_service_outlook.py::test_one_provider_failing_does_not_stop_the_other` | the status line `outlook live: outlook unavailable: live (503)` | `OutlookUnavailable` raised from `run_round` |
| S7 | `service.py` | Keep requiring Gmail accounts | `tests/integration/test_service_outlook.py::test_the_service_runs_with_outlook_alone_and_closes_its_clients` | the service runs two rounds | `ServiceError` raised |
| S8 | `service.py` | Don't close the Outlook clients | `tests/integration/test_service_outlook.py::test_the_service_runs_with_outlook_alone_and_closes_its_clients` | `True` | `False` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-04d.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks what the given tests don't reach, in two ways.
- **Same results, same answer:** over 4,000 random combinations of SPF, DKIM and DMARC results, written as Gmail writes them and as Microsoft does, Gmail and Outlook verification agree.
- **No forgery:** over 3,000 forged or misplaced Microsoft-shaped headers (second in line, a server name added, `compauth` removed), none verifies, while Microsoft's own passing header does.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Outlook squeezed into `AUTHSERV_IDS`, which a given test pins to Gmail alone | `git grep --untracked -n -E 'AUTHSERV_IDS *=.*outlook\|"outlook": *"' -- src/mailroom/sender_auth.py` |
| Q2 | Reading a header other than the first | `git grep --untracked -n -E 'authentication_results\[(1\|-1)\]\|for .* in record\.authentication_results' -- src/mailroom/sender_auth.py` |
| Q3 | Trusting another Microsoft header | `git grep --untracked -n -E 'X-Forefront\|X-Microsoft-Antispam\|ARC-Authentication' -- src` |
| Q4 | Time or ids read around the seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q5 | Logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q6 | Coverage or lint switched off | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/sender_auth.py src/mailroom/config.py src/mailroom/alerts.py src/mailroom/service.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Parsing Microsoft's header through `parse_results` with a private flag or wrapper, if `parse_results(header)` itself behaves as before.
- One private status helper shared by both providers' sync, if each prints its own part name and alerts as the spec says.
- Dispatching on `isinstance`, or on a provider attribute, if both client types work in one list.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-04d-outlook-service.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 4d`), then run `.venv/bin/python scripts/check_reports.py --phase 4d`; it must print `Reports OK.`
