# Verification guide: Phase 4i (Refuse incomplete stored chains safely)

Spec: `docs/phases/phase-04i-incomplete-stored-chains.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh
session. Everything is synthetic: fake Discord, the fake tasks app, the fake model,
MockTransport, the fake Keychain and temporary database files. Never access real
mail, Discord, model, tasks app, Keychain or data folder.

## 1. Coder ran

Before gates, inspect status, the tracked diff and untracked files. Require one
`## Phase 4i: ` progress entry and implementation changes in
`src/mailroom/discord_post.py`, `src/mailroom/tasks_app.py`,
`src/mailroom/interactions.py` and `src/mailroom/service.py`. A stopped entry is not a
completed implementation. Report a missing coder or a stop, without treating every
missing behavior as a new defect.

Require these to be committed: the spec, this guide, the four new given test files,
the `src/mailroom/discord_layout.py` given edit, and the probe. Record the full
planning-baseline commit and verify their bytes match it (G7). A dirty planning tree
must not be called a coder diff. Do not waive this gate or commit.

The only permitted implementation paths are the spec's Scope. Your report adds only
`docs/reviews/phase-04i-incomplete-stored-chains.md`.

## 2. Gates

Run them in order from the repository root. G2 reads G1's coverage data before any
other test run. 40 given cases are new, so the minimum suite is 1445 + 40.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | All checks passed.; tests (core) passed; at least 1485 passed, 0 failed/skipped/xfailed, no warnings; all Sections rows have 0 failed |
| G2 | `.venv/bin/python -m coverage report --include=src/mailroom/discord_post.py,src/mailroom/interactions.py,src/mailroom/tasks_app.py,src/mailroom/service.py --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_interactions_incomplete.py tests/integration/test_post_incomplete.py tests/integration/test_send_incomplete.py tests/integration/test_service_incomplete.py --no-cov -q` | 40 passed |
| G4 | `.venv/bin/python docs/verification/probe-04i.py` | check lines end ok; final FAILURES 0 |
| G5 | `grep -c '^## Phase 4i: ' docs/progress.md` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4i` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04i-incomplete-stored-chains.md docs/verification/phase-04i-incomplete-stored-chains.md tests/integration/test_interactions_incomplete.py tests/integration/test_post_incomplete.py tests/integration/test_send_incomplete.py tests/integration/test_service_incomplete.py src/mailroom/discord_layout.py docs/verification/probe-04i.py` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope, plus this review if already written |

Run G3 two more times; every run must show 40 passed. The tests use no threads or
real timing, so any failure is a finding.

Inspect the full diff for:

- unlisted changes to earlier tests;
- dependencies;
- coverage exclusions;
- new logging or output;
- a caught `AttributeError` or broad `Exception` standing in for a `None` check;
- any row deleted, rewritten or re-created to repair a chain;
- email text (subject, sender, body, link, title) in the notice, reply or status line;
- weak assertions in the coder's tests.

## Requirement checks

Test prefixes: II is `tests/integration/test_interactions_incomplete.py::`, PI is
`tests/integration/test_post_incomplete.py::`, SI is
`tests/integration/test_send_incomplete.py::`, VI is
`tests/integration/test_service_incomplete.py::`.

| Requirement | Deciding evidence |
|---|---|
| 1: report | PI test_complete_cards_post_exactly_once_and_skip_nothing; SI test_complete_tasks_are_sent_once_and_skip_nothing; existing whole-report comparisons in the full suite |
| 2: notice | PI test_an_incomplete_card_is_kept_and_the_others_still_post; PI test_the_notice_is_queued_once_and_the_card_stays_kept; SI test_a_task_whose_approval_is_gone_is_never_sent; probe alerts, task-alerts |
| 3: card posting | PI test_an_incomplete_card_is_kept_and_the_others_still_post; PI test_a_follow_up_card_whose_task_approval_is_gone_is_kept; PI test_a_kept_card_posts_once_its_rows_are_back; PI test_a_failed_send_after_a_kept_card_counts_only_the_unsent_rest; probe post-report, skipped-count, posted-set, kept-set, marked-sent |
| 4: task and link sends | SI test_a_task_whose_approval_is_gone_is_never_sent; SI test_a_task_whose_message_row_is_gone_is_kept_and_the_next_is_sent; SI test_a_link_whose_message_row_is_gone_is_kept; SI test_a_failed_task_send_after_a_kept_task_still_counts_it; probe task-report, task-sent-set, task-kept-set |
| 5: presses and forms | II test_a_press_on_an_email_whose_message_row_is_gone_gets_the_notice; II test_a_press_on_an_email_whose_triage_row_is_gone_gets_the_notice; II test_a_form_on_an_incomplete_email_gets_the_notice_and_records_nothing; II test_a_follow_up_whose_task_approval_is_gone_gets_the_notice; II test_a_combined_card_whose_message_row_is_gone_approves_nothing; II test_only_the_owner_gets_the_notice_and_others_are_still_ignored; probe press-reply, press-recorded, sender-changed, complete-refused |
| 6: status line | VI test_a_round_posts_past_an_incomplete_card_and_says_so |
| 7: privacy and compatibility | II test_the_notice_names_nothing_from_the_email; probe email-text; full suite; searches; source review |
| 8: progress | G5/G6 and the entry's factual contents |

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
  names. "Card check" is the completeness rule, wherever the coder put it.

| # | Function/boundary | One-line mutation | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | card check | Skip the message-row check | PI test_an_incomplete_card_is_kept_and_the_others_still_post[messages] | 2 posted, 1 kept | AttributeError |
| S2 | card check | Skip the triage-row check | II test_a_press_on_an_email_whose_triage_row_is_gone_gets_the_notice[yes] | incomplete notice | AttributeError |
| S3 | card check | Skip the follow-up target check | PI test_a_follow_up_card_whose_task_approval_is_gone_is_kept | kept, skipped 1 | AttributeError |
| S4 | notice | Ping the owner | PI test_an_incomplete_card_is_kept_and_the_others_still_post[triage] | ping False | ping True |
| S5 | notice | One key for every item | SI test_a_task_whose_approval_is_gone_is_never_sent | key incomplete:<item> | key incomplete |
| S6 | post_pending | Send incomplete cards too | PI test_an_incomplete_card_is_kept_and_the_others_still_post[messages] | 2 posted | AttributeError |
| S7 | post_pending | Report no skipped cards | PI test_the_notice_is_queued_once_and_the_card_stays_kept | skipped 1 | skipped 0 |
| S8 | post_pending | Skip without the notice | PI test_a_follow_up_card_whose_task_approval_is_gone_is_kept | one alert | no alert |
| S9 | _handle | Acknowledge silently | II test_a_press_on_an_email_whose_message_row_is_gone_gets_the_notice[full] | incomplete, notice | ignored, type 6 |
| S10 | _handle | Guard only buttons, not forms | II test_a_form_on_an_incomplete_email_gets_the_notice_and_records_nothing[task] | incomplete | AttributeError |
| S11 | send_tasks | Skip the approval check | SI test_a_task_whose_approval_is_gone_is_never_sent | only m2 sent | AttributeError |
| S12 | send_tasks | Skip the message check | SI test_a_task_whose_message_row_is_gone_is_kept_and_the_next_is_sent | m1 kept | AttributeError |
| S13 | send_tasks | Stop at the first incomplete task | SI test_a_task_whose_message_row_is_gone_is_kept_and_the_next_is_sent | m2 sent | nothing sent |
| S14 | _send_links | Skip the link's message check | SI test_a_link_whose_message_row_is_gone_is_kept | link kept | AttributeError |
| S15 | send_tasks | Drop the task count from links | SI test_a_task_whose_approval_is_gone_is_never_sent | skipped 1 | skipped 0 |
| S16 | send_tasks | Drop skipped on a failed send | SI test_a_failed_task_send_after_a_kept_task_still_counts_it | skipped 1 | skipped 0 |
| S17 | _status | Say ok for skipped items | VI test_a_round_posts_past_an_incomplete_card_and_says_so | ok (1 incomplete) | ok |

These mutations were run against a throwaway scratch stand-in at planning time, not
against the coder's code. A different failure needs diagnosis, and a passing
mutation may mean a weak test rather than a product defect. Report the difference.

## 4. Probe

`.venv/bin/python docs/verification/probe-04i.py --oracle-only` checks the trial
corpus alone:

- 40 seeded trials of 3 to 5 emails each;
- every card damage (none, message row, triage row, follow-up target) and every task
  damage (none, message row, approval row) appears;
- every trial damages at least one card and at least one task;
- more than half the card plans differ.

The normal probe runs each trial twice over. First, damaged cards go through two
`post_pending` calls and one button press per card, with a seeded action. Second,
approved tasks with damaged rows go through two `send_tasks` calls. It writes damage
with a second SQLite connection, so no store method is trusted to make it. It checks:

- the report of each call, including `skipped`;
- that exactly the complete cards post, by nonce, once;
- that kept cards stay pending and are never marked posted;
- one unpinged notice per kept item, keyed `incomplete:<item>`, across both calls;
- the incomplete reply on every press on a kept card, with no answer, approval or
  sender change;
- that no complete card is refused;
- that exactly the complete tasks reach the tasks app, and the kept ones stay queued;
- that no notice or reply carries the email's subject or sender.

It does not drive forms, links, failed task sends or status lines; the given tests do.
It reports failure names and counts, never payloads, and always reaches `FAILURES N`.
Never edit the probe; an oracle self-check failure belongs to the architect.

## 5. Searches

Each prints nothing; grep exit 1 is no match, exit above 1 is an error.

| # | Rule | Command |
|---|---|---|
| Q1 | Time and id seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|time\.sleep\|from mailroom\.(clock\|ids) import' -- src/mailroom/discord_post.py src/mailroom/tasks_app.py src/mailroom/interactions.py src/mailroom/service.py` |
| Q2 | Check for `None`; never catch or probe around a missing row | `git grep --untracked -n -E 'except (AttributeError\|TypeError\|KeyError\|Exception\|BaseException)\|getattr\(\|hasattr\(\|suppress\(\|pragma: no cover\|noqa' -- src/mailroom/discord_post.py src/mailroom/tasks_app.py src/mailroom/interactions.py` |
| Q3 | No repair: these modules write no rows directly | `git grep --untracked -n -E 'DELETE FROM\|INSERT INTO\|UPDATE (messages\|triage\|approvals\|posts\|tasks\|links)' -- src/mailroom/discord_post.py src/mailroom/tasks_app.py src/mailroom/interactions.py src/mailroom/service.py` |
| Q4 | No email text in the notice, reply or status line | `git grep --untracked -n -E 'ALERT_INCOMPLETE\.format\([^)]*(record\|sender\|subject\|link\|title\|message_id\|provider)\|INCOMPLETE_(TEXT\|STATE) *\+' -- src/mailroom` |

Escaped pipes in the table stand for ordinary alternation pipes. Q4 is a name-based
search. Source review also checks that the notice is formatted from the item id only,
under any variable name.

## 6. Reasonable variations

- The completeness rule as one helper in `discord_post.py`, or a private helper per
  module that applies the same rule.
- Queuing the notice with `store.queue_alert` or `alerts.notice`, where imports allow.
- Filtering pending cards before `send_messages`, or skipping inside a loop that
  reports the same counts.
- Checking the follow-up target for a card already marked `followup` only; a card not
  yet chosen gets its target from `approved_in_thread`.
- Private helpers inside the Scope modules, and extra behavior tests in the coder's
  test file.

Not variations:

- catching `AttributeError` or `Exception` instead of checking for `None`;
- marking a kept card posted, or sending a kept task or link;
- deleting, repairing or re-creating any row;
- pinging the owner, or tracking and resolving the notice;
- a notice or reply with any email text;
- checking completeness before the owner, channel or action checks.

## 7. Verdict

Write `docs/reviews/phase-04i-incomplete-stored-chains.md`, starting
`# Review: Phase 4i`, with the exact conventions-format head and findings. Include:

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

> Use $phase-coder to implement only Phase 4i from
> docs/phases/phase-04i-incomplete-stored-chains.md in this checkout. Read the required
> project docs and every given test. Run Start and all Acceptance commands;
> append progress. Do not read the verification guide or write a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4i against
> docs/phases/phase-04i-incomplete-stored-chains.md and
> docs/verification/phase-04i-incomplete-stored-chains.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probe, searches and
> scratch-only spot checks; write only docs/reviews/phase-04i-incomplete-stored-chains.md.
