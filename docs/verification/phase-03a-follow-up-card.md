# Verification guide: Phase 3a (Follow-up card)

Spec: `docs/phases/phase-03a-follow-up-card.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:


- `grep -c "^## Phase 3a: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-03a-follow-up-card.md src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_checkpoint_followup.py tests/integration/test_store_followup.py tests/integration/test_post_followup.py tests/integration/test_interactions_followup.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py docs/verification/probe-03a.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 143.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 41 = 1051 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_checkpoint_followup.py tests/integration/test_store_followup.py tests/integration/test_post_followup.py tests/integration/test_interactions_followup.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py --no-cov -q` | `143 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/store/posts.py,src/mailroom/store/approvals.py,src/mailroom/checkpoint.py,src/mailroom/discord_post.py,src/mailroom/interactions.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `.venv/bin/python docs/verification/probe-03a.py` | last line `FAILURES 0` |
| G5 | `grep -c "^## Phase 3a: " docs/progress.md` | `1` |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 3a` | `Reports OK.` |
| G7 | `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_checkpoint_followup.py tests/integration/test_store_followup.py tests/integration/test_post_followup.py tests/integration/test_interactions_followup.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py docs/verification/probe-03a.py` | no output |
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
| S1 | `store/approvals.py` | Drop `outcome != 'drop'` from `approved_in_thread` | `tests/integration/test_store_followup.py::test_a_dropped_or_undecided_item_is_not_a_target` | `None` | an `Approval` with outcome `'drop'` |
| S2 | `store/approvals.py` | Order by `decided_at` ascending (the earliest wins) | `tests/integration/test_store_followup.py::test_the_thread_gives_its_latest_approved_item` | `'c' * 32` | `'a' * 32` |
| S3 | `store/approvals.py` | Match on `thread_id` alone, not provider | `tests/integration/test_store_followup.py::test_another_thread_or_provider_is_not_a_target` | `None` (for `outlook`) | an `Approval` |
| S4 | `discord_post.py` | Check the combined card before the follow-up | `tests/integration/test_post_followup.py::test_a_reply_in_an_approved_thread_is_posted_as_a_follow_up[clearly-dated]` | embed title `'Follow-up to a task?'` | `'Approve this task?'` |
| S5 | `discord_post.py` | On every attempt, build the card from a fresh `approved_in_thread` instead of the stored `follows` | `tests/integration/test_post_followup.py::test_a_retry_keeps_its_target_after_a_later_approval_in_the_thread` | both requests name `'Pay the October bill'` | the retry names `'Pay the November bill'` |
| S6 | `interactions.py` | Accept `link` on any card | `tests/integration/test_interactions_followup.py::test_add_to_task_on_another_card_is_ignored` | `'ignored'` | `'answered'` |
| S7 | `interactions.py` | Reply with `answered_message` without `task_title` | `tests/integration/test_interactions_followup.py::test_add_to_task_records_the_link_and_closes_the_card` | embed title `'Follow-up to a task?'` | `'Is this a task?'` |
| S8 | `interactions.py` | Let `edit` on an unanswered follow-up open the title form, as at checkpoint 1 | `tests/integration/test_interactions_followup.py::test_a_press_the_follow_up_card_does_not_have_is_ignored[edit]` | `'ignored'` | `'form'` |
| S9 | `checkpoint.py` | Build the follow-up card's buttons from `FIRST_ROW` | `tests/unit/test_checkpoint_followup.py::test_the_follow_up_card_names_the_existing_task` | second button `'Add to task'` | `'Yes'` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-03a.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks what the given tests don't reach, in two ways. Over random threads, random approvals between rounds and random Discord failures, each post's card and target must be the ones chosen at its first send attempt, never retargeted by a later approval, and every request must carry that card. Over random presses and title forms, a three-state model of the follow-up card (open, waiting for checkpoint 2, closed) must match every outcome and what is stored.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Anything sent to the tasks app from this phase's code | `git grep --untracked -n -E 'tasks_app\|send_tasks\|/links' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/discord_post.py src/mailroom/store` |
| Q2 | A fuzzy thread match: by subject, sender, case or substring | `git grep --untracked -n -E 'LIKE\|instr\(\|lower\(\|subject\|sender' -- src/mailroom/store/approvals.py` |
| Q3 | A mention allowed in a card or reply | `git grep --untracked -n -E '"parse": \["\|@everyone\|@here\|"roles"' -- src/mailroom/checkpoint.py src/mailroom/interactions.py` |
| Q4 | Time or ids read around the seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q5 | Logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q6 | Coverage or lint switched off | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/store src/mailroom/checkpoint.py src/mailroom/discord_post.py src/mailroom/interactions.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Reading the target's title once in `post_pending` with a small private helper, or `store.approval(post.follows)` in place.
- `approved_in_thread` written with `EXISTS`, a subquery, or joins, if it is one query with exact matches.
- Routing a follow-up's checkpoint 2 presses through the existing 2d helpers unchanged.
- `answered_message` building the follow-up base through a private helper shared with `followup_message`.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-03a-follow-up-card.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 3a`), then run `.venv/bin/python scripts/check_reports.py --phase 3a`; it must print `Reports OK.`
