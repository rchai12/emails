# Verification guide: Phase 4h (Preserve rotated Outlook credentials)

Spec: `docs/phases/phase-04h-rotated-outlook-token.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh
session. Everything is synthetic: the fake Graph, fake Discord, fake model,
MockTransport, the fake Keychain and temporary database files. Never access real
Microsoft, Discord, mail, model, tasks app, Keychain or data folder.

## 1. Coder ran

Before gates, inspect status, the tracked diff and untracked files. Require one
`## Phase 4h: ` progress entry and implementation changes in `src/mailroom/outlook.py`
and `src/mailroom/service.py`. A stopped entry is not a completed implementation.
Report a missing coder or a stop, without treating every missing behavior as a new
defect.

Require these to be committed: the spec, this guide, the two new given test files,
the `src/mailroom/discord_layout.py` given edit, and the probe. Record the full
planning-baseline commit and verify their bytes match it (G7). A dirty planning tree
must not be called a coder diff. Do not waive this gate or commit.

The only permitted implementation paths are the spec's Scope. Your report adds only
`docs/reviews/phase-04h-rotated-outlook-token.md`.

## 2. Gates

Run them in order from the repository root. G2 reads G1's coverage data before any
other test run. 18 given cases are new, so the minimum suite is 1413 + 18.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | All checks passed.; tests (core) passed; at least 1431 passed, 0 failed/skipped/xfailed, no warnings; all Sections rows have 0 failed |
| G2 | `.venv/bin/python -m coverage report --include=src/mailroom/outlook.py,src/mailroom/service.py --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_outlook_rotation.py tests/integration/test_service_rotation.py --no-cov -q` | 18 passed |
| G4 | `.venv/bin/python docs/verification/probe-04h.py` | check lines end ok; final FAILURES 0 |
| G5 | `grep -c '^## Phase 4h: ' docs/progress.md` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4h` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04h-rotated-outlook-token.md docs/verification/phase-04h-rotated-outlook-token.md tests/integration/test_outlook_rotation.py tests/integration/test_service_rotation.py src/mailroom/discord_layout.py docs/verification/probe-04h.py` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope, plus this review if already written |

Run G3 two more times; every run must show 18 passed. The tests use no threads or
real timing, so any failure is a finding.

Inspect the full diff for:

- unlisted changes to earlier tests;
- dependencies;
- coverage exclusions;
- new logging or output;
- any copy of a token outside the client's memory (file, environment, database);
- retry loops or sleeps around the Keychain;
- a token in any exception's arguments;
- weak assertions in the coder's tests.

## Requirement checks

Test prefixes: OR is `tests/integration/test_outlook_rotation.py::`, SR is
`tests/integration/test_service_rotation.py::`.

| Requirement | Deciding evidence |
|---|---|
| 1: new error | OR test_a_new_token_the_keychain_refuses_is_reported_as_unsaved; Q4 |
| 2: hold on failure | OR test_no_mail_is_read_with_the_access_token_of_an_unsaved_refresh; OR test_the_saved_call_reads_mail_with_a_fresh_access_token; probe mail-read-unsaved |
| 3: save first | OR test_the_next_call_tries_the_save_again_before_any_request; OR test_each_call_tries_the_save_once; OR test_once_the_keychain_works_the_held_token_is_saved_and_used; OR test_a_saved_token_is_not_saved_again_when_the_refresh_after_it_fails; OR test_the_retired_token_is_never_sent_again; OR test_a_later_rotation_that_cannot_be_saved_holds_the_newer_token; probe keychain-token, graph-token, sent-tokens |
| 4: restart limit | OR test_a_restart_before_the_save_needs_sign_in; SR test_a_restart_before_the_save_asks_for_sign_in_and_is_not_called_saved |
| 5: service | SR test_an_unsaved_token_is_its_round_s_status_and_pings_at_once; SR test_the_ping_is_sent_once_however_many_rounds_stay_unsaved; SR test_the_round_after_the_keychain_recovers_saves_reads_and_says_so; SR test_a_second_unsaved_episode_pings_again; SR test_other_outlook_failures_leave_the_unsaved_alert_open; probe alerts and status |
| 6: privacy and compatibility | SR test_no_token_text_reaches_a_status_line_or_alert; probe token-text; full suite; searches; source review |
| 7: progress | G5/G6 and the entry's factual contents |

## 3. Spot checks

Run spot checks only in disposable scratch copies of the current implementation and
tests.

- Use the existing venv and `PYTHONPATH=src:.`, and confirm `mailroom.__file__` is
  inside the copy.
- Set `PYTHONDONTWRITEBYTECODE=1` and remove the copy's `__pycache__` folders first.
  Two same-size mutations written within one second can otherwise run stale bytecode.
- Never mutate the implementation under review.
- Start each row from the original bytes and run the deciding test with `--no-cov`.
  Then discard only your mutation and compare bytes.
- If private helpers differ, locate the equivalent code; do not prescribe helper
  names.

| # | Function/boundary | One-line mutation | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | rotation save | Let `KeychainUnavailable` propagate, as before | OR test_a_new_token_the_keychain_refuses_is_reported_as_unsaved | OutlookTokenUnsaved | KeychainUnavailable |
| S2 | rotation save | Raise unsaved without holding the token | OR test_once_the_keychain_works_the_held_token_is_saved_and_used | profile returned | OutlookAuthError |
| S3 | access token | Keep the access token and expiry from the unsaved reply | OR test_the_saved_call_reads_mail_with_a_fresh_access_token | access-1 and access-2 issued; mail read with access-2 | no second token; mail read with access-1 |
| S4 | save first | Try the held save after refreshing instead of before | OR test_the_retired_token_is_never_sent_again | token 1 sent once | token 1 sent again |
| S5 | save first | Never try the held save again | OR test_the_next_call_tries_the_save_again_before_any_request | two tries | one try |
| S6 | save first | Keep holding the token after a successful save | OR test_a_saved_token_is_not_saved_again_when_the_refresh_after_it_fails | one write | two writes |
| S7 | error | Drop `from None` | OR test_a_new_token_the_keychain_refuses_is_reported_as_unsaved | no cause/context | context kept |
| S8 | error | Subclass `OutlookAuthError` | OR test_a_new_token_the_keychain_refuses_is_reported_as_unsaved | not an auth error | auth error |
| S9 | alert | `wait=timedelta(minutes=15)` | SR test_an_unsaved_token_is_its_round_s_status_and_pings_at_once | [UNSAVED_ALERT] | [] |
| S10 | alert | `ping=False` | SR test_an_unsaved_token_is_its_round_s_status_and_pings_at_once | pinged text | no `<@owner>` |
| S11 | resolution | Also resolve in the generic failure branch | SR test_other_outlook_failures_leave_the_unsaved_alert_open | [UNSAVED_ALERT] | SAVED added |
| S12 | resolution | Also resolve in the sign-in branch | SR test_a_restart_before_the_save_asks_for_sign_in_and_is_not_called_saved | [UNSAVED_ALERT, SIGN_IN] | SAVED added |
| S13 | resolution | Never resolve on success | SR test_the_round_after_the_keychain_recovers_saves_reads_and_says_so | ends with SAVED | no SAVED |
| S14 | service branch | Remove the unsaved catch (falls to the generic branch) | SR test_an_unsaved_token_is_its_round_s_status_and_pings_at_once | ping | no ping |

These mutations were run against a throwaway scratch stand-in at planning time, not
against the coder's code. A different failure needs diagnosis, and a passing
mutation may mean a weak test rather than a product defect. Report the difference.

## 4. Probe

`.venv/bin/python docs/verification/probe-04h.py --oracle-only` checks the script
corpus alone:

- 40 seeded scripts of 12 steps;
- each kind (saved round, refused round, restart, login, token-endpoint 503) at least
  40 times;
- at least 10 restarts that lose a held token, 10 recoveries, 5 sign-in recoveries and
  5 refused rounds that need no refresh;
- three hand-worked cases.

The normal probe runs each script through real `run_round` calls with one client kept
between rounds. The fake Graph only accepts its latest token, and the fake Keychain
refuses writes on refused rounds. Rounds alternate 5 minutes and 2 hours apart, so
some reuse a live access token. The oracle models:

- Graph's current token;
- the Keychain's token;
- the held token and the access token's expiry;
- the open alerts.

After every round it checks:

- the account's last status line;
- that no Graph mail request is made unless the round is ok;
- the Keychain and Graph tokens;
- every refresh token sent, in order;
- the posted alerts, in order across rounds and as a set within one round;
- that no token text appears in lines or posts.

It reports failure names and counts, never payloads, and always reaches `FAILURES N`.
Never edit the probe; an oracle self-check failure belongs to the architect.

## 5. Searches

Each prints nothing; grep exit 1 is no match, exit above 1 is an error.

| # | Rule | Command |
|---|---|---|
| Q1 | Time seam, no sleeping | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|time\.sleep\|time\.monotonic\|from mailroom\.(clock\|ids) import' -- src/mailroom/outlook.py src/mailroom/service.py` |
| Q2 | No disk or environment fallback, output, broad catch or bypass | `git grep --untracked -n -E 'open\(\|write_text\|write_bytes\|Path\(\|print\(\|logging\|logger\|pickle\|json\.dump\|os\.environ\|getenv\|tempfile\|shelve\|pragma: no cover\|noqa\|except BaseException\|except Exception' -- src/mailroom/outlook.py` |
| Q3 | Keychain writes stay where they were | `git grep --untracked -n -E 'set_secret\(' -- src/mailroom ':(exclude)src/mailroom/keychain.py' ':(exclude)src/mailroom/outlook.py' ':(exclude)src/mailroom/outlook_login.py' ':(exclude)src/mailroom/gmail_login.py'` |
| Q4 | No token in an error or formatted text | `git grep --untracked -n -E 'OutlookTokenUnsaved\([^)]*,\|\{(rotated\|token\|refresh_token\|held)[^}]*\}' -- src/mailroom/outlook.py src/mailroom/service.py` |

Escaped pipes in the table stand for ordinary alternation pipes. Q4 is a name-based
search. Source review also checks that no f-string or error in either file formats
the held token under any other name.

## 6. Reasonable variations

- The held token as one private attribute or a small private holder.
- The save-first step in `_ensure_token`, `_get` or a helper called from both, if it
  runs before any HTTP request.
- Keeping the unsaved reply's access token out of the client by not assigning it, or
  by clearing it.
- A private helper beside `_outlook` for the new alert.

Not variations:

- writing the token anywhere but the Keychain;
- sending the held token to Graph before it is saved;
- more than one save try per call, or a sleep;
- an alert that waits, or does not ping;
- resolving the alert on anything but a successful sync.

## 7. Verdict

Write `docs/reviews/phase-04h-rotated-outlook-token.md`, starting `# Review: Phase 4h`,
with the exact conventions-format head and findings. Include:

- gate and Sections output;
- coverage;
- the repeated G3 runs;
- searches;
- probe results;
- spot-check results.

Classify each defect as requirement, observed result and required result. Do not
repair code or tests. Run G6 after writing it.

## Handoff prompts

Only after the final planning documents and given files are committed and the
coder's checkout is clean:

> Use $phase-coder to implement only Phase 4h from
> docs/phases/phase-04h-rotated-outlook-token.md in this checkout. Read the required
> project docs and every given test. Run Start and all Acceptance commands;
> append progress. Do not read the verification guide or write a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4h against
> docs/phases/phase-04h-rotated-outlook-token.md and
> docs/verification/phase-04h-rotated-outlook-token.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probe, searches and
> scratch-only spot checks; write only docs/reviews/phase-04h-rotated-outlook-token.md.
