# Phase 2e: Combined card

## Goal

Give a clearly dated email one card instead of two ([Approval flow](../approval-flow.md#combined-approval-for-clearly-dated-emails)).

When a notified email is posted, code chooses its card once, just before the first send attempt:
- the combined card when the verdict is clearly dated (2c), its extraction is still there, and the proposed deadline hasn't passed;
- checkpoint 1 otherwise.

The post records the choice (migration 10), so a retried send, and every later press, follow the card Discord actually shows.

The combined card shows sender, subject, summary, title, deadline and evidence. Its buttons are Show full text, Approve, Edit, No deadline, Not a task, Mute sender and Trust sender. Approve, Edit's task form, or No deadline records a Yes and the checkpoint 2 decision together, in one write. Not a task and Mute close it as at checkpoint 1.

Nothing is sent to a tasks app yet (2f).

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 901, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_deadline_passed.py --ignore=tests/unit/test_checkpoint_combined.py --ignore=tests/integration/test_store_combined.py --ignore=tests/integration/test_post_combined.py --ignore=tests/integration/test_interactions_combined.py --ignore=tests/unit/test_store_package.py` must show `856 passed`.
- The first five files import names you create, or their fixtures call `choose_card`.
- `test_store_package.py` (given edits) expects `choose_card` and `record_combined`.

## Facts

Each was checked on this machine.

- **Migration 10 is given.** It adds `posts.card`, which is `NULL`, `'first'` or `'combined'`.
  - SQLite checks an added column's `CHECK` against existing rows, so a stricter form ("a posted row must have a card") refused a database with a posted row.
  - The column therefore allows `NULL`, meaning "not chosen yet". Posts from before 2e keep `NULL`, and they were all checkpoint 1 cards.
- **A retry must reuse the first card.** `send_messages` builds each body just before its send, and a retried send reuses the post's nonce. Discord, and `FakeDiscord`, return the message already made for a nonce. If a retry rebuilt a different card, the stored card and the one on Discord would disagree. Choosing the card once and storing it before the first send prevents that.
- **The layout is given.** `discord_layout.py` ends with `COMBINED_TITLE`, `COMBINED_FIRST_ROW` (full, approve, change, nodeadline, notask) and `COMBINED_SECOND_ROW` (mute, trust). The combined card reuses checkpoint 2's actions for a decision and checkpoint 1's for closing. Which card a press came from is read from `posts.card`, never guessed from the action.
- **When "passed" is checked.** `deadlines.py` decides "passed" inside `clearly_dated`, privately. Posting needs the same rule on its own, so this phase makes it public as `deadline_passed`, with the same meaning (Phase 2b, Architect's decisions).
- **Earlier tests change in two places (given edits).** `test_store_package.py` names `choose_card` (posts) and `record_combined` (approvals), and the schema-version pins say 10. `Post` gains `card` with a default, so earlier `Post(...)` comparisons, which never post, still match.
- **2d's tests keep passing.** They post with `posted_store`, which never chooses a card, so their posts read `card` as `None`. That means checkpoint 1, and their behaviour is unchanged.

## Owner's decisions

- The card is chosen at posting, not only at triage: a clearly dated email whose deadline has passed by then gets checkpoint 1. The post records which card it got.
- A combined decision records both the checkpoint 1 answer and the checkpoint 2 decision, in one write. Not a task and Mute record only the answer.

## Architect's decisions

- **Chosen once, before the first send.** `post_pending`'s body callback asks the store to set the card only when it is still `NULL`, then builds that card. A failed or lost send keeps the choice, and the retry rebuilds the same card.
- **Combined needs the text.** An extraction cleared after 24 hours means checkpoint 1, which already shows "The summary has expired.". A combined card is never built without a title and a summary.
- **A cleared title asks for one.** A combined card pressed after the text is cleared has no title for Approve or No deadline. Like checkpoint 1's Yes without a title, they then open the task form, prefilled with the subject and the proposed deadline.
- **Decided cards reuse 2d's.** Approve, Edit and No deadline show `approved_message`, and Not a task and Mute show `answered_message`. No new closed card.
- **Closed first.** On a combined card with an answer, every answering press and form is refused with `ALREADY_TEXT`, before checking whether that card has the action.

## Requirements

1. **`deadline_passed(day: date, at: time | None, time_zone: str, now: datetime) -> bool`** in `deadlines.py`:
   - with `at`, true when the local moment is at or before `now`;
   - without, true when `day` is before `now`'s local date.
   `clearly_dated` keeps its behaviour, and it may use this.
2. **`Post`** gains `card: str | None = None`, read from `posts.card`. **`PostStore.choose_card(item_id: str, card: str) -> str | None`** sets the card only where it is `NULL`, then returns the stored card (`None` for an unknown item). A card the schema refuses raises `sqlite3.IntegrityError`.
3. **`ApprovalStore.record_combined(item_id: str, outcome: str, title: str, due: Due | None) -> bool`**, for `approve`, `nodeadline` or `change`:
   - it reads `clock.now()` once;
   - in one `_write()`, it inserts the answer (`edit` for `change`, `yes` otherwise, with `title`) as `record_answer` does, only for an existing post with no answer;
   - if that added nothing, it returns `False`;
   - then it inserts the approval as `record_approval` does, and returns `True`.
   A refused approval raises `IntegrityError` and keeps neither row.
4. **`combined_message(record, verdict, item_id) -> dict`** in `checkpoint.py`, for a verdict with an extraction and a `due`, returns exactly the dict the given tests pin:
   - the embed title `COMBINED_TITLE`, with checkpoint 1's colour rule and footer;
   - the fields From, Subject, Summary, Proposed task, Deadline (as at checkpoint 2) and Evidence (the quote in a code block);
   - `COMBINED_FIRST_ROW`, then `COMBINED_SECOND_ROW` with Open email when the link fits;
   - `allowed_mentions` with an empty `parse`;
   - checkpoint 1's nonce and `enforce_nonce`.
5. **`post_pending`** builds each body just before its send, as today, but first chooses the card:
   - It wants `"combined"` when `verdict.dated` is true, `verdict.extraction` is not `None`, `verdict.due` is not `None`, and `deadline_passed(due.date, due.time, settings.time_zone, clock.now())` is false. Otherwise it wants `"first"`.
   - It calls `store.choose_card(post.item_id, wanted)`.
   - It builds `combined_message` for `"combined"`, and `checkpoint_message` otherwise.
   It reads the clock only for a dated verdict with an extraction and a due. Everything else about posting is unchanged.
6. **`handle_interaction`** keeps every check it makes today. For a post whose `card` is `"combined"`, after `full` and `trust`, which work as always:
   - **Answered** (any answer): every other press and both forms reply `ALREADY_TEXT` (`"already"`).
   - **Unanswered:**
     - `approve` and `nodeadline`: with no extraction, or an empty title, they reply the task form, prefilled with `record.subject[:FORM_TITLE_LIMIT]` and the proposed deadline (`"form"`). Otherwise they record `record_combined(item_id, action, extraction.title, due or None)`, where `approve` keeps `verdict.due` and `nodeadline` gives `None` (`"approved"`).
     - `change`: the task form with the extraction's title (or the subject) and the proposed deadline (`"form"`).
     - The task form: read as at checkpoint 2, then `record_combined(item_id, "change", title, due)` (`"approved"`).
     - `notask` and `mute`: as at checkpoint 1 (`"answered"`).
     - `yes`, `edit`, `drop` and the title form: `DEFERRED_UPDATE` (`"ignored"`).
     - A recorded decision replies `UPDATE_MESSAGE` with `approved_message(record, verdict, item_id, store.approval(item_id))`. `record_combined` returning `False` replies `ALREADY_TEXT`.
   A post whose `card` is `None` or `"first"` behaves exactly as in Phase 2d.
7. **Progress entry** for `## Phase 2e: Combined card (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Edited: migration 10 |
| `src/mailroom/discord_layout.py` | Edited: the Phase 2e constants |
| `tests/unit/test_deadline_passed.py` | Seven moments around a deadline, local days included |
| `tests/unit/test_checkpoint_combined.py` | The combined card exactly; no time and a long link; email text kept in its blocks |
| `tests/integration/test_store_combined.py` | A card chosen once; an unknown card refused; four combined decisions recorded as both answers; nothing after an answer or for an unknown item; a refused decision keeps neither; a version 9 database migrates |
| `tests/integration/test_post_combined.py` | Dated email posted as combined; checkpoint 1 when the deadline passed before posting, when not dated, or when the text is cleared; a retry after the deadline passed keeps the first card and makes one message |
| `tests/integration/test_interactions_combined.py` | Approve and No deadline; Edit's form; a submitted task; refused forms; Not a task and Mute; presses the card lacks; everything after a decision; Approve after the text is cleared; a press from anyone else; a checkpoint 1 card unchanged |
| `tests/unit/test_store_package.py`, `tests/integration/test_store.py`, `tests/integration/test_store_sync.py`, `tests/integration/test_store_due.py` | Edited as in Facts |
| `docs/verification/probe-02e.py` | The verifier's probe |

Given test count: **131** (56 new in the five new files, 2 new rows in `test_store_package.py`, and the rest in the edited files).

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage of the critical modules this phase touches, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/deadlines.py` | `deadline_passed` |
| `src/mailroom/store/posts.py` | `Post.card`, `choose_card` |
| `src/mailroom/store/approvals.py` | `record_combined` |
| `src/mailroom/checkpoint.py` | `combined_message` |
| `src/mailroom/discord_post.py` | the card choice in `post_pending` |
| `src/mailroom/interactions.py` | the combined card's presses and form |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Sending to a tasks app, or an outbox (2f).
- Recomputing `dated` itself, or changing triage, the extractor or `clearly_dated`'s results.
- A new closed card, a new button, or a change to checkpoint 1's or checkpoint 2's cards.
- Editing a posted card when its deadline passes, follow-ups, digests (stage 6).
- Any change to `schema.py`, `discord_layout.py`, or a given or earlier test, `AGENTS.md` or the design docs.

## Rules that bite

- **Nothing becomes a task without approval.** A combined decision is recorded only from the owner's press or form in the channel, on an unanswered combined post.
- **Every press checks the owner.** The combined card's presses pass the same owner and channel check.
- **Sends are retry-safe.** The card is chosen and stored before the first send and never changed. A retry rebuilds the same card with the same nonce, and makes no second message.
- **Email-derived text stays in code blocks.** The summary, title and quote appear only inside `_block`, and `allowed_mentions` stays empty.
- **Code decides.** The card choice uses the stored `dated` and `due` with `deadline_passed`, never the model.
- **Time through the module.** `clock.now()` is called through the module, and only where Requirements 3, 5 and 6 say.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 58 = 959 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_deadline_passed.py tests/unit/test_checkpoint_combined.py tests/integration/test_store_combined.py tests/integration/test_post_combined.py tests/integration/test_interactions_combined.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py --no-cov -q` | `131 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/deadlines.py,src/mailroom/store/posts.py,src/mailroom/store/approvals.py,src/mailroom/checkpoint.py,src/mailroom/discord_post.py,src/mailroom/interactions.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 2e: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 2e` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/unit/test_deadline_passed.py tests/unit/test_checkpoint_combined.py tests/integration/test_store_combined.py tests/integration/test_post_combined.py tests/integration/test_interactions_combined.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py docs/verification/probe-02e.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'clearly_dated|read_deadline' -- src/mailroom/discord_post.py
git grep --untracked -n -E 'ZoneInfo|astimezone' -- src/mailroom/discord_post.py
git grep --untracked -n -E '"parse": \["|@everyone|@here|"roles"' -- src/mailroom/checkpoint.py src/mailroom/interactions.py
git grep --untracked -n -E 'tasks_app|tasks-app|/channels/' -- src/mailroom/interactions.py src/mailroom/store
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/deadlines.py src/mailroom/store src/mailroom/checkpoint.py src/mailroom/discord_post.py src/mailroom/interactions.py
```
