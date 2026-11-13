# Verification guide: Phase 2d (Checkpoint 2)

Spec: `docs/phases/phase-02d-checkpoint-two.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/store/approvals.py`
- `grep -c "^## Phase 2d: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-02d-checkpoint-two.md src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/unit/test_checkpoint_second.py tests/integration/test_store_approvals.py tests/integration/test_interactions_second.py tests/integration/test_interactions.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py scripts/critical_modules.txt docs/verification/probe-02d.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 172.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 67 = 899 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_checkpoint_second.py tests/integration/test_store_approvals.py tests/integration/test_interactions_second.py tests/integration/test_interactions.py tests/integration/test_interactions_more.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py --no-cov -q` | `172 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/interactions.py,src/mailroom/checkpoint.py,src/mailroom/store/approvals.py,src/mailroom/store/__init__.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 2d: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 2d` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/unit/test_checkpoint_second.py tests/integration/test_store_approvals.py tests/integration/test_interactions_second.py tests/integration/test_interactions.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py scripts/critical_modules.txt docs/verification/probe-02d.py` | no output |
| G7 | `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| G8 | `git status --short` | only the Scope paths |
| G9 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `interactions.py` | a recorded `yes` replies with `answered_message` as before | `tests/integration/test_interactions_second.py::test_yes_turns_the_card_into_checkpoint_2` | the checkpoint 2 card | the answered card |
| S2 | `store/approvals.py` | the insert selects from `posts` instead of `answers` (no Yes needed) | `tests/integration/test_store_approvals.py::test_nothing_is_recorded_without_a_yes[unanswered]` | `False` | `True` |
| S3 | `store/approvals.py` | `ON CONFLICT DO NOTHING` removed | `tests/integration/test_store_approvals.py::test_a_decision_after_yes_is_recorded_once_and_read_back[approve]` | second call `False` | `IntegrityError` |
| S4 | `interactions.py` | `approve` records even when `verdict.due` is `None` (the schema then refuses it) | `tests/integration/test_interactions_second.py::test_approve_without_a_proposed_deadline_is_ignored` | `('ignored', {'type': 6})` | `IntegrityError` |
| S5 | `interactions.py` | a stale `yes` while waiting replies `ALREADY_TEXT` | `tests/integration/test_interactions_second.py::test_a_stale_checkpoint_1_card_shows_checkpoint_2_again[yes]` | `'again'` | `'already'` |
| S6 | `interactions.py` | checkpoint 2 presses skip the unanswered check (the store then refuses, so the reply is `ALREADY_TEXT`) | `tests/integration/test_interactions_second.py::test_a_checkpoint_2_press_before_yes_is_ignored[nodeadline]` | `('ignored', {'type': 6})` | `('already', ...)` |
| S7 | `interactions.py` | `today` is `clock.now().date()` in UTC | `tests/integration/test_interactions_second.py::test_a_submitted_task_is_approved_with_the_deadline_read_by_code[local-today]` | `date(2026, 11, 11)` | `date(2026, 11, 12)` |
| S8 | `interactions.py` | an empty deadline text is passed to `read_deadline` too | `tests/integration/test_interactions_second.py::test_a_submitted_task_is_approved_with_the_deadline_read_by_code[empty]` | `'approved'` | `'bad-deadline'` |
| S9 | `interactions.py` | the prefill writes the time as `%H:%M` | `tests/integration/test_interactions_second.py::test_edit_opens_the_task_form_filled_in[afternoon]` | `'2026-11-20 5:00 pm'` | `'2026-11-20 17:00'` |
| S10 | `checkpoint.py` | Approve kept when nothing is proposed | `tests/unit/test_checkpoint_second.py::test_without_a_proposal_there_is_nothing_to_approve` | four buttons | five, with Approve |
| S11 | `checkpoint.py` | the Evidence field left out when the extraction is gone | `tests/unit/test_checkpoint_second.py::test_the_deadline_and_evidence_follow_what_is_known[evidence-expired]` | `'The evidence has expired.'` | no Evidence field |
| S12 | `interactions.py` | the owner check skipped for `nodeadline` | `tests/integration/test_interactions_second.py::test_a_checkpoint_2_press_from_anyone_else_changes_nothing[nodeadline]` | `('ignored', {'type': 6})` | `('approved', ...)` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-02d.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

Beyond the given tests, 300 cards (60% with a proposed deadline) each take 12 random events: any button press, or a title or task form whose texts come from the probe's own table of known readings. A model of the three states says what each event returns. Every event must get exactly one reply that `FakeDiscord` accepts, and the stored answer and approval must match the model after every step. It asserts that every outcome it means to reach was reached at least 10 times. Its unanswered-state model was checked against today's code before the build.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | The task form's deadline is read only by `read_deadline` | `git grep --untracked -n -E 'strptime\|fromisoformat\|dateutil\|dateparser\|re\.compile' -- src/mailroom/interactions.py` |
| Q2 | `approvals` holds no email text | `git grep --untracked -n -E 'body_text\|summary\|\.quote\|suspicion_reason' -- src/mailroom/store/approvals.py` |
| Q3 | No mention can be enabled | `git grep --untracked -n -E '"parse": \["\|@everyone\|@here\|"roles"' -- src/mailroom/checkpoint.py src/mailroom/interactions.py` |
| Q4 | No channel post or tasks call from a press | `git grep --untracked -n -E '/channels/\|/messages\|send_messages\|tasks_app\|tasks-app' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store` |
| Q5 | Time through the module | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store` |
| Q6 | No logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store` |
| Q7 | No coverage or lint exemptions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store/approvals.py src/mailroom/store/__init__.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- The state worked out once at the top of the handler, or press by press, as long as every press and form in Requirement 5 gives the outcome and reply it names.
- `approved_message` given the `Approval` read back from the store, or the one just recorded (they are equal).
- The prefill built with `strftime` or by hand, as long as it is exactly `h:mm am` or `pm` after the ISO date.
- A private helper shared by `checkpoint_message` and `checkpoint2_message` for the From, Subject, colour and footer.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-02d-checkpoint-two.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 2d`), then run `.venv/bin/python scripts/check_reports.py --phase 2d`; it must print `Reports OK.`
