# Phase 3a: Follow-up card

## Goal

When a new email arrives in a thread whose earlier email you approved as a task, ask whether it belongs to that task ([Approval flow](../approval-flow.md#follow-ups)).

When such an email is posted, code chooses its card once, just before the first send, as in Phase 2e:
- the **follow-up card** when its thread already has an approved item (Approve, Edit or No deadline, never Not a task);
- otherwise checkpoint 1 or the combined card, exactly as today.

The post records the item it follows (migration 12).

The follow-up card shows sender, subject, summary and the existing task's title. Its buttons are Show full text, Add to task, New task, Not a task, Mute sender and Trust sender.
- **Add to task** records the answer `link` and closes the card.
- **New task** is checkpoint 1's Yes, so the card goes on to checkpoint 2.
- **Not a task** and **Mute** close it as at checkpoint 1.

Nothing is sent to the tasks app for a link yet (3b). Stage 3's real tasks app is connected once it exists (3c).

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 1010, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_checkpoint_followup.py --ignore=tests/integration/test_post_followup.py` must show `12 failed, 1011 passed, 15 errors`.
- The two ignored files import `followup_message`, which you create.
- The failures and errors are given tests waiting for you: `choose_card(..., follows=)`, `Post.follows`, `approved_in_thread`, and the package table. The 15 errors are `test_interactions_followup.py`'s fixture.

## Facts

Each was checked on this machine.

- **Migration 12 is given.** SQLite can't change a `CHECK`, so it rebuilds `posts` and `answers`, copying every row.
  - `posts.card` may now be `'followup'`, and the new column `posts.follows` holds the followed item's id. The rule is `CHECK ((card IS 'followup') = (follows IS NOT NULL))`.
  - `IS` matters here. With `=`, a `NULL` card and a target compare to `NULL`, which a `CHECK` lets through. That was tried, and it accepted a post with no card and a target.
  - `answers.answer` may now be `'link'`, with an empty title like Not a task.
  - On a version 11 database with posts and answers, every row and both unique keys survived. A rebuild that fails inside its transaction leaves the old table once rolled back.
- **The layout is given.** `discord_layout.py` gains `ANSWER_TEXT["link"]`, `FOLLOWUP_TITLE`, `FOLLOWUP_TASK_NAME`, `FOLLOWUP_FIRST_ROW` (full, link, yes, notask) and `FOLLOWUP_SECOND_ROW` (mute, trust).
- **The target comes from `approvals`, not `tasks`.** Tasks are queued only while `MAILROOM_TASKS_URL` is set (2f). A follow-up must be recognised either way, so "the thread has an approved item" is read from the approvals joined to their posts and messages.
- **The thread is the stored thread id,** `<account>/<provider id>`, matched exactly with its provider. Two accounts can't share a thread, and no fuzzy matching is done.
- **Earlier tests change (given edits):** the schema-version pins say 12, and `test_store_package.py` names `approved_in_thread` (approvals).
  - `Post` gains `follows` with a default, so earlier `Post(...)` comparisons still match.
  - Posts that never choose `followup` read `follows` as `None`, and every earlier card behaves as before.

## Owner's decisions

- **Stage 3 splits.** 3a is the follow-up card and its answers; 3b sends the link to the stub tasks app; 3c connects the owner's own tasks app once it exists, adopting 2f's contract.
- **A follow-up asks first.** Its card offers Add to task, New task and Not a task. Nothing is linked without a press.

## Architect's decisions

- **Only notified mail.** A follow-up that triage doesn't notify stays silent, as any email does.
- **The latest approval wins.** A thread with several approved items is followed to the one decided last (then the larger item id). The choice is stored, so a retry and every press use the same target, even if a later approval would now win.
- **Follow-up before combined.** A clearly dated follow-up still gets the follow-up card. New task then goes on to checkpoint 2, which shows the proposed deadline.
- **The rest is checkpoint 1.** After New task, the post behaves exactly like a checkpoint 1 post answered Yes (Phase 2d): the title form when there is no title, checkpoint 2, and every refusal. Edit title isn't on the card, so its press is ignored.
- **A closed follow-up keeps its look.** Add to task, Not a task and Mute show the follow-up card with the answer, through `answered_message`'s new `task_title`.

## Requirements

1. **`Post`** gains `follows: str | None = None`, read from `posts.follows`. **`choose_card(item_id: str, card: str, follows: str | None = None) -> str | None`** sets both only where the card is `NULL`, in one statement, then returns the stored card. A combination the schema refuses raises `sqlite3.IntegrityError` and sets nothing.
2. **`Answer.answer`** may be `"link"`. `record_answer(item_id, "link", "")` works like Not a task (the schema is given).
3. **`ApprovalStore.approved_in_thread(provider: str, thread_id: str) -> Approval | None`** returns the approval with the latest `decided_at`, then the largest `item_id`, among those that meet all of these:
   - its outcome is not `drop`;
   - its post's message has this provider and this exact `thread_id`.
   It returns `None` when there is none. It reads no clock.
4. **`followup_message(record, verdict, item_id, task_title: str) -> dict`** in `checkpoint.py` returns exactly the dict the given tests pin:
   - checkpoint 1's embed with the title `FOLLOWUP_TITLE`: From, Subject and Summary as at checkpoint 1, then `FOLLOWUP_TASK_NAME` with `task_title` in a code block, then checkpoint 1's suspected-spam warning when there is one;
   - checkpoint 1's colour rule and footer;
   - `FOLLOWUP_FIRST_ROW`, then `FOLLOWUP_SECOND_ROW` with Open email when the link fits;
   - `allowed_mentions` with an empty `parse`;
   - checkpoint 1's nonce and `enforce_nonce`.
   It shows no proposed task.
5. **`answered_message(record, verdict, item_id, answer, title, task_title: str = "")`**: with a `task_title`, its card starts from `followup_message(..., task_title)` instead of `checkpoint_message`. Everything else is as today.
6. **`post_pending`**, in its body callback, first looks up `store.approved_in_thread(post.provider, record.thread_id)`.
   - If it finds one, it wants `"followup"` with `follows=` that item. Otherwise it wants what it wants today, with `follows=None`.
   - It calls `choose_card`, then reads the stored post again.
   - It builds `followup_message` with `store.approval(post.follows).title` for a stored `"followup"`, and the other cards as today.
   - A retry builds from the stored target, never a new lookup's.
7. **`handle_interaction`** keeps every check it makes today, and `"link"` becomes a press action. For a post whose `card` is `"followup"`, after `full` and `trust`, which work as always:
   - **Unanswered:**
     - `link` records `record_answer(item_id, "link", "")` and replies `UPDATE_MESSAGE` with `answered_message(..., "link", "", task_title=...)` (`"answered"`);
     - `yes` and the title form are exactly checkpoint 1's;
     - `notask` and `mute` are checkpoint 1's, but reply with `task_title=` (`"answered"`);
     - `edit`, `approve`, `change`, `nodeadline` and `drop` reply `DEFERRED_UPDATE` (`"ignored"`).
   - **Answered:** as a checkpoint 1 post today: checkpoint 2 while waiting, `ALREADY_TEXT` once closed. `link` after any answer replies `ALREADY_TEXT` (`"already"`).
   - The task title is `store.approval(post.follows).title`.
   - On a post whose `card` is not `"followup"`, `link` replies `DEFERRED_UPDATE` (`"ignored"`) and records nothing.
8. **Progress entry** for `## Phase 3a: Follow-up card (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Edited: migration 12 |
| `src/mailroom/discord_layout.py` | Edited: the Phase 3a constants and `ANSWER_TEXT["link"]` |
| `tests/unit/test_checkpoint_followup.py` | The follow-up card exactly; warning and cleared summary; the task title kept in its block; three closed forms; a long link |
| `tests/integration/test_store_followup.py` | Card and target chosen once; half a follow-up refused; `link` closes an item; the latest approval in a thread; drop, undecided, another thread or provider; ties by item; a version 11 database keeps its rows |
| `tests/integration/test_post_followup.py` | A reply in an approved thread posted as a follow-up, dated or not; checkpoint 1 when the thread's item was dropped or undecided, or in another thread; a retry keeps its target after a later approval in the thread |
| `tests/integration/test_interactions_followup.py` | Add to task; New task on to checkpoint 2; Not a task and Mute; presses the card lacks; everything after Add to task; Add to task after New task; New task after clearing; a press from anyone else; Add to task on other cards |
| `tests/unit/test_store_package.py`, `tests/integration/test_store.py`, `test_store_sync.py`, `test_store_due.py`, `test_store_combined.py`, `test_store_tasks.py` | Edited as in Facts |
| `docs/verification/probe-03a.py` | The verifier's probe |

Given test count: **143** (41 new: 40 in the four new files and 1 new row in `test_store_package.py`; the rest are in the edited files).

## Tests to write

The given tests cover every requirement's main cases. `store/posts.py`, `store/approvals.py`, `checkpoint.py`, `discord_post.py` and `interactions.py` are critical. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store/posts.py` | `Post.follows`, `choose_card`'s `follows`, `Answer`'s `link` |
| `src/mailroom/store/approvals.py` | `approved_in_thread` |
| `src/mailroom/checkpoint.py` | `followup_message`, `answered_message`'s `task_title` |
| `src/mailroom/discord_post.py` | the follow-up choice in `post_pending` |
| `src/mailroom/interactions.py` | the follow-up card's presses |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Sending a link to the tasks app, or any change to `tasks_app.py` or the payload (3b).
- The real tasks app (3c).
- Updating the existing task's title or deadline from a follow-up.
- Matching emails across threads, by subject, or by sender.
- A follow-up for mail triage doesn't notify, a "this thread has a task" note on other cards, follow-up reminders or digests (stage 6).
- Any change to `schema.py`, `discord_layout.py`, a given or earlier test, `AGENTS.md` or the design docs.

## Rules that bite

- **Nothing becomes a task without approval.** Add to task only records an answer; nothing leaves the machine. New task goes through checkpoint 2 as before.
- **Every press checks the owner.** `link` passes the same owner and channel check as every action.
- **Sends are retry-safe.** The card and its target are chosen and stored before the first send and never changed. A retry rebuilds the same card with the same nonce.
- **Email-derived text stays in code blocks.** The existing task's title is a title from an email, so it appears only inside `_block`, and `allowed_mentions` stays empty.
- **Code decides.** The target is an exact provider and thread id match on stored approvals, never the model.
- **Time through the module.** No new clock reads.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 41 = 1051 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_checkpoint_followup.py tests/integration/test_store_followup.py tests/integration/test_post_followup.py tests/integration/test_interactions_followup.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py --no-cov -q` | `143 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/store/posts.py,src/mailroom/store/approvals.py,src/mailroom/checkpoint.py,src/mailroom/discord_post.py,src/mailroom/interactions.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python docs/verification/probe-03a.py` | last line `FAILURES 0` |
| `grep -c "^## Phase 3a: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 3a` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_checkpoint_followup.py tests/integration/test_store_followup.py tests/integration/test_post_followup.py tests/integration/test_interactions_followup.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py docs/verification/probe-03a.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'tasks_app|send_tasks|/links' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/discord_post.py src/mailroom/store
git grep --untracked -n -E 'LIKE|instr\(|lower\(|subject|sender' -- src/mailroom/store/approvals.py
git grep --untracked -n -E '"parse": \["|@everyone|@here|"roles"' -- src/mailroom/checkpoint.py src/mailroom/interactions.py
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/store src/mailroom/checkpoint.py src/mailroom/discord_post.py src/mailroom/interactions.py
```
