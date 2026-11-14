# Verification guide: Phase 4a (Graph client)

Spec: `docs/phases/phase-04a-graph-client.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/outlook.py`
- `grep -c "^## Phase 4a: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-04a-graph-client.md tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook.py docs/verification/probe-04a.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 39.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 39 = 1129 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_outlook.py --no-cov -q` | `39 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/outlook.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `.venv/bin/python docs/verification/probe-04a.py` | last line `FAILURES 0` |
| G5 | `grep -c "^## Phase 4a: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4a` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook.py docs/verification/probe-04a.py` | no output |
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
| S1 | `outlook.py` | Don't save the new refresh token | `tests/integration/test_outlook.py::test_a_token_is_asked_for_as_a_public_client_and_the_new_refresh_token_saved` | `'refresh-token-2'` | `'refresh-token-1'` |
| S2 | `outlook.py` | Follow page links without checking them. The client then sends its token to the other host, which the fake answers 400 | `tests/integration/test_outlook.py::test_a_page_link_anywhere_else_is_never_followed[other-host]` | `'outlook unavailable: live (response)'` | `'outlook unavailable: live (400)'` |
| S3 | `outlook.py` | Leave out `Prefer: IdType="ImmutableId"` | `tests/integration/test_outlook.py::test_the_profile_falls_back_to_the_sign_in_name_and_finds_the_inbox` | a `Profile` | `OutlookUnavailable` raised (`400`) |
| S4 | `outlook.py` | Treat only 410 as an expired link | `tests/integration/test_outlook.py::test_an_expired_delta_link_asks_for_a_new_round[sync-state-not-found]` | `DeltaExpired` | `OutlookUnavailable` (`400`) |
| S5 | `outlook.py` | Let the id pattern accept `/`. `a/b` then reaches the fake as id `a`, which answers 404 | `tests/integration/test_outlook.py::test_a_message_id_that_cannot_name_a_path_is_refused_before_any_request[slash]` | `ValueError` | `MessageGone` |
| S6 | `outlook.py` | Accept a time without a zone (`astimezone` then reads it as local time) | `tests/integration/test_outlook.py::test_a_message_with_an_unreadable_time_is_refused[no-zone]` | `OutlookUnavailable` | a `RawMessage` returned |
| S7 | `outlook.py` | Set the expiry without `TOKEN_MARGIN` | `tests/integration/test_outlook.py::test_the_token_is_kept_until_a_minute_before_it_expires` | `2` | `1` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-04a.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks what the given tests don't reach. Over 1,500 runs, with one reply in each corrupted at random (a field dropped or retyped, a page link pointed elsewhere, a status changed, bytes that aren't JSON), the client must:
- raise only `OutlookError` or `ValueError`;
- talk only to the two Microsoft hosts;
- send its token only to Graph;
- never carry a token, a secret or reply text in an error.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | A Graph call that changes mail | `git grep --untracked -n -E 'http\.(patch\|put\|delete)\(\|/send\|/move\|/copy\|isRead\|markAsRead\|createReply\|createForward' -- src/mailroom/outlook.py` |
| Q2 | A scope wider than Mail.Read, or a tenant other than consumers | `git grep --untracked -n -E 'Mail\.(ReadWrite\|Send\|ReadBasic)\|microsoft\.com/\.default\|/common/\|/organizations/' -- src` |
| Q3 | A client secret in a public client | `git grep --untracked -n -E 'client_secret\|client-secret' -- src/mailroom/outlook.py` |
| Q4 | A reply's body or an exception's text echoed | `git grep --untracked -n -E 'response\.text\|str\((error\|exc\|e)\)\|\{(error\|exc\|e)(!r)?\}' -- src/mailroom/outlook.py` |
| Q5 | A client that follows redirects, reads proxies or skips TLS checks | `git grep --untracked -n -E 'follow_redirects=True\|trust_env=True\|verify=False' -- src` |
| Q6 | Time or ids read around the seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q7 | Logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q8 | Coverage or lint switched off | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/outlook.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Building a request with `httpx`'s `params=` or by joining a query string, if the parameters and headers are the ones Requirements 7 to 9 name.
- One private request helper shared by every call, with the 401 retry and the error mapping in it.
- Checking the link with `urlsplit` or `httpx.URL`, if every rule in Requirement 8 holds.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-04a-graph-client.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 4a`), then run `.venv/bin/python scripts/check_reports.py --phase 4a`; it must print `Reports OK.`
