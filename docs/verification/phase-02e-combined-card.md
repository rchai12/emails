# Verification guide: Phase 2e (Combined card)

Spec: `docs/phases/phase-02e-combined-card.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `.venv/bin/python -c "from mailroom.checkpoint import combined_message; from mailroom.deadlines import deadline_passed"` exits 0
- `grep -c "^## Phase 2e: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-02e-combined-card.md src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_deadline_passed.py tests/unit/test_checkpoint_combined.py tests/integration/test_store_combined.py tests/integration/test_post_combined.py tests/integration/test_interactions_combined.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py docs/verification/probe-02e.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 131.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 58 = 959 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_deadline_passed.py tests/unit/test_checkpoint_combined.py tests/integration/test_store_combined.py tests/integration/test_post_combined.py tests/integration/test_interactions_combined.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py --no-cov -q` | `131 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/deadlines.py,src/mailroom/store/posts.py,src/mailroom/store/approvals.py,src/mailroom/checkpoint.py,src/mailroom/discord_post.py,src/mailroom/interactions.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 2e: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 2e` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_deadline_passed.py tests/unit/test_checkpoint_combined.py tests/integration/test_store_combined.py tests/integration/test_post_combined.py tests/integration/test_interactions_combined.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py docs/verification/probe-02e.py` | no output |
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
| S1 | `store/posts.py` | `choose_card` updates without `WHERE card IS NULL` | `tests/integration/test_store_combined.py::test_a_card_is_chosen_once_and_kept` | second call `'combined'` | `'first'` |
| S2 | `discord_post.py` | the wanted card ignores `deadline_passed` | `tests/integration/test_post_combined.py::test_otherwise_it_is_posted_as_checkpoint_1[deadline-passed-before-posting]` | the checkpoint 1 card sent | the combined card sent |
| S3 | `discord_post.py` | the body is built from the wanted card, not from what `choose_card` returns | `tests/integration/test_post_combined.py::test_a_retry_after_the_deadline_passed_keeps_the_card_first_chosen` | the combined card sent twice | the second send is checkpoint 1 |
| S4 | `store/approvals.py` | the approval is inserted even when the answer insert added nothing | `tests/integration/test_store_combined.py::test_an_item_already_answered_records_nothing_more[yes]` | `False` | `True` |
| S5 | `store/approvals.py` | the answer and the approval written in two separate `_write()` blocks | `tests/integration/test_store_combined.py::test_a_decision_the_schema_refuses_keeps_neither_answer` | `(None, None)` | the `yes` answer kept |
| S6 | `interactions.py` | a combined `approve` calls `record_approval` instead of `record_combined` (it then finds no Yes) | `tests/integration/test_interactions_combined.py::test_one_press_records_yes_and_the_decision[approve]` | `'approved'` | `'already'` |
| S7 | `interactions.py` | the no-extraction branch for `approve` removed | `tests/integration/test_interactions_combined.py::test_approve_after_the_text_is_cleared_asks_for_the_title[approve]` | `'form'` | `AttributeError` |
| S8 | `deadlines.py` | `deadline_passed` compares the UTC date | `tests/unit/test_deadline_passed.py::test_a_deadline_has_passed_at_or_after_its_moment[local-day-not-utc]` | `False` | `True` |
| S9 | `checkpoint.py` | `combined_message` drops the nonce | `tests/unit/test_checkpoint_combined.py::test_the_combined_card_shows_everything_on_one_card` | with `nonce` | without |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-02e.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

Beyond the given tests, it checks two things. Posting runs 80 trials of several emails over ten hourly rounds, with Discord failing at random and the first round always failing at its first post. Each post's stored card must match the probe's own choice at that post's first send, every body sent for it must be that card, and no email may make two messages. It asserts that it reached combined cards, checkpoint 1 cards, and dated emails that posted as checkpoint 1 because their deadline passed first. Presses run 200 combined cards through random presses and forms against a two-state model, checking the stored answer and approval after every step.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Posting uses `deadline_passed`, not 2b's whole rule | `git grep --untracked -n -E 'clearly_dated\|read_deadline' -- src/mailroom/discord_post.py` |
| Q2 | Posting leaves time zones to `deadlines.py` | `git grep --untracked -n -E 'ZoneInfo\|astimezone' -- src/mailroom/discord_post.py` |
| Q3 | No mention can be enabled | `git grep --untracked -n -E '"parse": \["\|@everyone\|@here\|"roles"' -- src/mailroom/checkpoint.py src/mailroom/interactions.py` |
| Q4 | No channel post or tasks call from a press or the store | `git grep --untracked -n -E 'tasks_app\|tasks-app\|/channels/' -- src/mailroom/interactions.py src/mailroom/store` |
| Q5 | Time and ids through the modules | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q6 | No logging or printing | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q7 | No coverage or lint exemptions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/deadlines.py src/mailroom/store src/mailroom/checkpoint.py src/mailroom/discord_post.py src/mailroom/interactions.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `clearly_dated` rewritten to use `deadline_passed`, as long as every 2b test passes unchanged.
- The card choice in a private helper of `discord_post.py`, or inline in the body callback.
- `record_combined` sharing private SQL or helpers with `record_answer` and `record_approval`.
- The combined branch of `handle_interaction` as its own private function.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-02e-combined-card.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 2e`), then run `.venv/bin/python scripts/check_reports.py --phase 2e`; it must print `Reports OK.`
