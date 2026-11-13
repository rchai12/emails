# Phase 2d: Checkpoint 2

## Goal

Build checkpoint 2 ([Approval flow](../approval-flow.md#checkpoint-2-confirm-the-deadline)).

When the owner presses Yes, or submits a title, the same card turns into "Confirm the deadline". It shows the task title, the deadline proposed at triage (2c), and the evidence quote while it still exists. Its buttons are Show full text, Approve, Edit, No deadline and Not a task.

Edit opens a form with the title and the deadline. The owner types the deadline as they would say it, and 2b's reader reads it. The decision is recorded once in a new `approvals` table (migration 9), and the card turns into a closed card showing it.

Nothing is sent to a tasks app yet (2f). Clearly dated emails still go through both checkpoints until the combined card (2e).

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 832, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_checkpoint_second.py --ignore=tests/integration/test_store_approvals.py --ignore=tests/integration/test_interactions_second.py --ignore=tests/integration/test_interactions.py --ignore=tests/integration/test_interactions_more.py --ignore=tests/unit/test_store_package.py` must show `755 passed`.
- The first three import names you create.
- `test_interactions.py` (given edits) imports `checkpoint2_message`, and `test_interactions_more.py` imports from it.
- `test_store_package.py` (given edits) expects the new `approvals` area.

## Facts

Each was checked on this machine.

- **Migration 9 is given.** `src/mailroom/schema.py` ends with migration 9, the table `approvals`:
  - `item_id` is the key, and `outcome` is one of `approve`, `change`, `nodeadline` or `drop`.
  - `title` is empty exactly for `drop`.
  - `deadline_date` and `deadline_time` follow migration 8's formats. `approve` must have a date; `nodeadline` and `drop` must have none.
  - `decided_at` is the time of the decision.
  Anything else raises `sqlite3.IntegrityError`.
- **The layout is given.** `src/mailroom/discord_layout.py` ends with the Phase 2d constants: `SECOND_TITLE`, `SECOND_BUTTONS`, the field names, `NO_PROPOSAL_TEXT`, `NO_DEADLINE_TEXT`, `EVIDENCE_EXPIRED`, `DATE_FORMAT`, `TIME_FORMAT`, `APPROVAL_TEXT`, the task form's ids and labels, `DEADLINE_LIMIT` and `BAD_DEADLINE_TEXT`. The new button actions (`approve`, `change`, `nodeadline`, `drop`) and the form action `task` differ from every checkpoint 1 action, so a press always names its checkpoint.
- **Discord's limits hold.** A row holds at most five buttons, and checkpoint 2 has five. A form holds at most five fields, each label at most 45 characters, and a form title at most 45. `FakeDiscord` checks each reply against these limits, and a reply it refuses makes `handle_interaction` raise.
- **The fake sends forms field by field (given edit).** `FakeDiscord.submit(custom_id, value, fields={...})` now sends the title field and every named field, like Discord, which sends every text input of a form, an empty one with `value: ""`. A form without the `deadline` field counts as an empty deadline.
- **Day names.** `strftime("%A")` gives English day names in Python's default C locale, which the service never changes. So `DATE_FORMAT` and `TIME_FORMAT` render November 20, 2026 at 17:00 as `Friday 2026-11-20 at 17:00`.
- **The prefill reads back.** A proposed deadline is prefilled as the ISO date and, when it has a time, `h:mm am` or `pm` (`2026-11-20 5:00 pm`, `2026-11-20 12:30 am`). Both are in 2b's grammar, so submitting the form unchanged approves the proposal.
- **Earlier tests change in three places (given edits).**
  - Yes, and a submitted title, now reply with `checkpoint2_message(...)` in `test_interactions.py`, where they replied with `answered_message`. Not a task and Mute still reply with `answered_message`.
  - `test_store_package.py` names the new area, its two methods and `Approval`.
  - The schema-version pins say 9.

## Owner's decisions

- Checkpoint 2 replaces the pressed card in place, as the reply to the press. Pressing Yes again on a stale checkpoint 1 card shows checkpoint 2 again.
- The deadline in the Edit form is free text, read by 2b's `read_deadline` against today's date in the owner's time zone. An empty field means no deadline. A text it can't read is refused privately, and nothing is recorded.
- With no proposed deadline, Approve is left out: Edit and No deadline remain.
- Checkpoint 2 has a Not a task button that closes the item.

## Architect's decisions

- **A table of its own.** Checkpoint 2's decision goes in `approvals`, not `answers`, which keeps checkpoint 1's answer as it was. A row can exist only for an item answered `yes` or `edit`, and only once. The single insert decides both.
- **A new store area.** `store/approvals.py` holds `Approval` and `ApprovalStore`, the eighth area class, which `Store` also subclasses.
- **The approved title.** It is the checkpoint 1 answer's title, or the one typed in the task form. `approvals` keeps it with the deadline, and no other email text, which is the exception [Security and privacy](../security-and-privacy.md) already allows.
- **The evidence.** It is the quote inside a code block while the extraction exists, and `EVIDENCE_EXPIRED` after the 24-hour clearing. The Evidence field appears only when a deadline is proposed.
- **A clear state for every press.** Unanswered, waiting at checkpoint 2, or closed: Requirement 5 gives each press and form in each state. A checkpoint 2 press or task form on an unanswered card is ignored, the way any press that doesn't fit is.
- **Today's date only when needed.** The task form reads the clock for today's date only when the deadline text isn't empty. An empty time zone setting reads it as UTC (`mailroom run` refuses to start without one).

## Requirements

1. **`Approval`** in `src/mailroom/store/approvals.py` is a frozen dataclass with these fields, exported from `mailroom.store`:
   - `item_id: str`
   - `outcome: Literal["approve", "change", "nodeadline", "drop"]`
   - `title: str`
   - `due: Due | None`
   - `decided_at: datetime`
2. **`ApprovalStore(StoreBase)`** in the same module, with:
   - `record_approval(item_id: str, outcome: str, title: str, due: Due | None) -> bool`. It reads `clock.now()` once and runs one `INSERT INTO approvals … SELECT … FROM answers WHERE answers.item_id = ? AND answers.answer IN ('yes', 'edit') ON CONFLICT DO NOTHING` inside `_write()`. It returns whether a row was added. A row the schema refuses raises `sqlite3.IntegrityError`, and nothing is kept.
   - `approval(item_id: str) -> Approval | None`.
   `Store` subclasses `ApprovalStore` as its last base. Every earlier method is unchanged.
3. **`checkpoint2_message(record, verdict, item_id, title) -> dict`** in `checkpoint.py` returns exactly the dict the given tests pin. In order:
   - the embed title `SECOND_TITLE`, with checkpoint 1's colour rule and footer;
   - the fields From, Subject, Proposed task (the title in a code block), Deadline, then Evidence when `verdict.due` is set, then the warning when the email is suspected;
   - the Deadline value: the due date with `DATE_FORMAT`, plus `TIME_FORMAT` when there is a time, or `NO_PROPOSAL_TEXT`;
   - one row of `SECOND_BUTTONS` (without `approve` when `verdict.due` is `None`), then a row with Open email when the link fits;
   - `allowed_mentions` with an empty `parse`.
4. **`approved_message(record, verdict, item_id, approval) -> dict`** returns exactly the dict the given tests pin:
   - the same title, colour and footer;
   - the fields From, Subject, then Proposed task and Deadline (the approved due, or `NO_DEADLINE_TEXT`) except for `drop`, then Your answer (`APPROVAL_TEXT[outcome]`);
   - one row with Show full text and, when the link fits, Open email.
5. **`handle_interaction`** keeps every check it makes today, owner and channel included, for the new actions too. Then it acts on the item's state. `full` and `trust` work as today in every state.
   - **Unanswered** (no answer):
     - Checkpoint 1 presses and the title form work as today, except that a recorded `yes` and an accepted title reply `UPDATE_MESSAGE` with `checkpoint2_message(record, verdict, item_id, title)` (outcome `"answered"`).
     - `approve`, `change`, `nodeadline`, `drop` and the task form reply `DEFERRED_UPDATE` (`"ignored"`).
   - **Waiting** (answer `yes` or `edit`, no approval):
     - `yes` or `edit`: `UPDATE_MESSAGE` with checkpoint 2 again, using the answer's title (`"again"`).
     - `notask`, `mute` and the title form: `ALREADY_TEXT` privately (`"already"`).
     - `approve`: when `verdict.due` is `None`, `DEFERRED_UPDATE` (`"ignored"`). Otherwise it records `("approve", answer.title, verdict.due)` (`"approved"`).
     - `nodeadline`: records `("nodeadline", answer.title, None)` (`"approved"`).
     - `drop`: records `("drop", "", None)` (`"dropped"`).
     - `change`: replies `MODAL` with the task form (`"form"`): the title input as at checkpoint 1, with the answer's title; then the deadline input (`DEADLINE_INPUT_ID`, style 1, `min_length` 0, `max_length` `DEADLINE_LIMIT`, `required` false) with the prefill from Facts, or no `value` when nothing is proposed.
     - The task form: the title is checked as at checkpoint 1 (`BAD_TITLE_TEXT`, `"bad-title"`). Then the stripped deadline text: empty means no deadline. Otherwise `read_deadline(text, today)` gives the `Due`, where `today` is `clock.now()` as a date in `settings.time_zone`. `None` is refused with `BAD_DEADLINE_TEXT` privately (`"bad-deadline"`). Then it records `("change", title, due)` (`"approved"`).
     - Each recorded decision replies `UPDATE_MESSAGE` with `approved_message(record, verdict, item_id, store.approval(item_id))`. When `record_approval` returns `False`, it replies `ALREADY_TEXT` (`"already"`).
   - **Closed** (answer `notask` or `mute`, or an approval exists): every other press and both forms reply `ALREADY_TEXT` (`"already"`).
6. **Progress entry** for `## Phase 2d: Checkpoint 2 (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Edited: migration 9 |
| `src/mailroom/discord_layout.py` | Edited: the Phase 2d constants |
| `tests/fakes.py` | Edited: `submit(..., fields=...)` |
| `tests/unit/test_checkpoint_second.py` | The checkpoint 2 card exactly; deadline and evidence as known; no Approve without a proposal; the warning; a title kept in its block; a long link; the decided card for each outcome |
| `tests/integration/test_store_approvals.py` | Recorded once after Yes for five decisions; nothing without a Yes; an unknown item; six decisions the schema refuses |
| `tests/integration/test_interactions_second.py` | Yes leads to checkpoint 2; Approve, No deadline and Not a task; a press from anyone else; Approve without a proposal; presses before Yes; everything after a decision; a stale card; the task form's prefill and submissions; refusals |
| `tests/integration/test_interactions.py`, `tests/unit/test_store_package.py`, `tests/integration/test_store.py`, `tests/integration/test_store_sync.py`, `tests/integration/test_store_due.py` | Edited as in Facts |
| `scripts/critical_modules.txt` | Edited: `store/approvals.py` added |
| `docs/verification/probe-02d.py` | The verifier's probe |

Given test count: **172** (64 new in the three new files, 3 new rows in `test_store_package.py`, and the rest in the edited files).

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage of `interactions.py`, `checkpoint.py`, `store/approvals.py` and `store/__init__.py` (all critical), add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store/approvals.py` | new |
| `src/mailroom/store/__init__.py` | `Approval`, `ApprovalStore` in `Store` |
| `src/mailroom/checkpoint.py` | `checkpoint2_message`, `approved_message` |
| `src/mailroom/interactions.py` | the new presses, states and task form |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- The combined card for clearly dated email (2e), and any change to the checkpoint 1 card or to posting.
- Sending anything to a tasks app, or an outbox (2f).
- Follow-ups for unanswered cards (stage 6), and undoing a decision.
- A date picker, select menus, or any Discord component beyond buttons and text inputs.
- Any change to `deadlines.py`, `schema.py`, `discord_layout.py` or `tests/fakes.py`, or to a given or earlier test, `AGENTS.md` or the design docs.

## Rules that bite

- **Nothing becomes a task without approval.** Only a press or form from the owner in the channel records a decision, and only after a Yes. This phase sends nothing anywhere.
- **Every press checks the owner.** The new actions pass the same owner and channel check as checkpoint 1's.
- **Email-derived text stays in code blocks.** The title and the quote appear only inside `_block`, which replaces backticks. The deadline line is built by code from a date, never copied from the email. `allowed_mentions` stays empty.
- **Retention.** `approvals` holds the approved title and deadline, never the quote, the summary or the body.
- **Code decides.** The owner's deadline text is read by `read_deadline` alone, with no second parser, no model call, and no repair of a text it can't read.
- **Time through the module.** `clock.now()` is called through the module, and only for a non-empty deadline text and in `record_approval`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 67 = 899 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_checkpoint_second.py tests/integration/test_store_approvals.py tests/integration/test_interactions_second.py tests/integration/test_interactions.py tests/integration/test_interactions_more.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py --no-cov -q` | `172 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/interactions.py,src/mailroom/checkpoint.py,src/mailroom/store/approvals.py,src/mailroom/store/__init__.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 2d: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 2d` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/unit/test_checkpoint_second.py tests/integration/test_store_approvals.py tests/integration/test_interactions_second.py tests/integration/test_interactions.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py scripts/critical_modules.txt docs/verification/probe-02d.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'strptime|fromisoformat|dateutil|dateparser|re\.compile' -- src/mailroom/interactions.py
git grep --untracked -n -E 'body_text|summary|\.quote|suspicion_reason' -- src/mailroom/store/approvals.py
git grep --untracked -n -E '"parse": \["|@everyone|@here|"roles"' -- src/mailroom/checkpoint.py src/mailroom/interactions.py
git grep --untracked -n -E '/channels/|/messages|send_messages|tasks_app|tasks-app' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store/approvals.py src/mailroom/store/__init__.py
```
