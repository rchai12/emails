# Phase 4i: Refuse incomplete stored chains safely

## Goal

A card, task or link whose stored rows are incomplete is kept unsent instead of
crashing the round. The poll round still sends every complete item, and it reports
the kept ones with a status line and one unpinged notice per item. A press or form
on an incomplete email gets a private constant-text reply, and nothing is recorded.
Valid chains still post and approve exactly once. This closes the read side of audit
finding 3.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is **1445**, from the passing Phase 4h review
(`49e2f57`) plus the 8 tooling tests in `879dbf1`. The finalized planning/given-file
commit made after this document is the coder's clean start.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_interactions_incomplete.py --ignore=tests/integration/test_post_incomplete.py --ignore=tests/integration/test_send_incomplete.py --ignore=tests/integration/test_service_incomplete.py`
must show `1445 passed`. Nothing needs a missing-module stub. The four new given files
import only names that exist today. They read `PostReport.skipped` and the new
outcome when a test runs.

## Facts

- `PRAGMA foreign_keys` is off, and the store never deletes a message, triage,
  post, answer, approval, task or link row. A missing row comes from damage outside
  Mailroom, such as a manual edit, a restore or a bug. Database constraints are
  Phase 6a.
- `discord_post.post_pending` builds each card inside `send_messages`. It reads
  `store.get(...).record` and `store.triage(...).verdict` with no `None` check. For a
  follow-up card it also reads `store.approval(posted.follows).title`.
- `send_messages` posts in order. It stops at the first failure and returns
  `PostReport(posted, len(pending) - index, stopped)`. So an exception on one card
  stops every card after it.
- `interactions._handle` checks the owner, channel, action and post row. It then reads
  `stored.record` and `triaged.verdict`, and `store.approval(post.follows).title` for
  a follow-up's notask, mute or link. The link path records its answer before that
  read.
- `tasks_app.send_tasks` reads `store.approval(task.item_id)` and
  `store.get(...).record.link` for each queued task. `_send_links` reads
  `store.get(...).record.link` for each queued link.
- A planning spike reproduced the problem offline:
  - A press on a card whose triage row is gone raises `AttributeError` in the
    listener.
  - A pending card whose message row is gone raises `AttributeError` in
    `post_pending`: no card posts, and all 3 stay pending.
  - `_status` catches only `DiscordUnavailable`, `KeychainError` and
    `TasksUnavailable`, so the poll loop itself stops.
- A poll round re-triages any message with no triage row (`store.untriaged()`). So
  in service rounds a missing triage row heals itself on the next round, and a
  missing message row does not.
- A missing answer row looks the same as a card nobody has answered yet. Checkpoint 2
  presses on such a card already get the deferred acknowledgement and record nothing
  (`test_a_checkpoint_2_press_before_yes_is_ignored`).
- `_finish_combined` and `_decide` read an approval right after writing it in the
  same handler. They are not a read of earlier stored work.
- Existing tests compare whole `PostReport` values, such as
  `PostReport(posted=1, waiting=0, stopped="")`.
- `alerts.py` imports `discord_post`, so `discord_post` cannot import `alerts`.
  `store.queue_alert(key, text, ping)` queues a notice once per key; `alerts.notice`
  is that same call.
- Validated with a throwaway scratch stand-in only (never copied in):
  - All 1445 existing tests pass unchanged.
  - The given tests pass 6 of 6 runs.
  - On predecessor code, all 40 given cases fail.

## Owner's decisions

- **2026-11-21:** task and link sends get the same guard as card posting and presses.
- **2026-11-21:** a poll round keeps an incomplete card, task or link unsent and
  queued, sends the others, shows a status line, and posts one unpinged notice per
  item naming only its item id.
- **2026-11-21:** a press or form on an incomplete email gets a private reply,
  "Mailroom can't act on this email: its stored details are incomplete." Nothing is
  recorded, and no task is made.
- **2026-11-21:** Show full text follows the same rule. A missing triage row refuses it
  too.

## Architect's decisions

- **One rule.** An item is complete when its message row and triage row exist and, if
  its post's card is `followup`, the approval row named by `follows` exists. A card not
  yet chosen needs no target check: `approved_in_thread` returns only an approval
  that exists. Put the rule in `discord_post.py`, so posting and presses share it. The
  helper names are the coder's choice.
- **One notice key for all three paths.** The key is `incomplete:<item id>`. A card,
  its task and a follow-up link that reach the send step are never pending for the
  same item at once. The notice is never tracked or resolved.
- **Nothing is repaired.** A kept row is never deleted, rewritten or guessed around.
  Once the missing row is back, the item sends on the next round as usual.
- **A missing answer row needs no change.** It is the same state as "not answered yet",
  which is already refused safely. The owner's answer covers it.
- **Waiting is unchanged.** `waiting` still counts the queued items not yet tried at a
  failure. For cards, that count leaves out the kept cards.

## Requirements

1. **Report.** Add `skipped: int = 0` as the last field of `PostReport`. Existing
   three-field reports and comparisons keep working.
2. **Notice.** For each kept item, queue
   `store.queue_alert(f"incomplete:{item_id}", L.ALERT_INCOMPLETE.format(item=item_id), False)`
   (or the equivalent `alerts.notice` call, where imports allow). Queue it every time
   the item is kept; the key makes it post once. It names nothing but the item id.
3. **Card posting.** In `post_pending`, after `queue_notified`:
   - check every pending post with the completeness rule before building any card;
   - do not build, send or mark an incomplete one; queue its notice;
   - send the complete ones in their usual order with `send_messages`;
   - return that report with `skipped` set to the number of incomplete pending posts.
4. **Task and link sends.** In `send_tasks`:
   - a queued task whose approval row or message row is missing sends no request and
     stays queued; queue its notice and go on to the next task;
   - in `_send_links`, a queued link whose message row is missing is handled the same
     way;
   - every report the call returns, including one that stopped early, carries
     `skipped`: the number of tasks and links kept so far in this call.
5. **Presses and forms.** In `_handle`, keep the existing ignore checks first: owner,
   channel, action and post row. Then, for button presses (kind 3) and form
   submissions (kind 5), an item that fails the completeness rule gets
   `_private(L.INCOMPLETE_TEXT)` and the outcome `"incomplete"`. This comes before
   every action, including Show full text and Trust. Nothing is recorded: no answer,
   approval, sender status, task or link. Slash commands are unchanged.
6. **Status line.** In `service._status`, when a report did not stop and
   `report.skipped > 0`, report `L.INCOMPLETE_STATE.format(count=report.skipped)`
   instead of `ok`. A stopped report still shows `waiting (...)`. The `tasks` alert
   rules in `_tasks` are unchanged.
7. **Privacy and compatibility.**
   - The notice, reply and status line carry no email text. Error messages stay
     constant text plus identifiers.
   - Existing tests keep passing unchanged.
   - Time and ids come only through `clock.now()` and `ids.new_id()`.
8. **Progress entry** for `## Phase 4i: Refuse incomplete stored chains safely (YYYY-MM-DD)`
   at the end of docs/progress.md, with actual counts.

## Given files

Committed with the finalized spec before coding; never change them as the coder.

| File | What it is |
|---|---|
| `tests/integration/test_interactions_incomplete.py` | 27 cases: every button with the message row gone, then with the triage row gone; both forms; a follow-up whose task approval is gone; a combined card; a stranger is still ignored while the owner gets the notice; the notice names nothing from the email |
| `tests/integration/test_post_incomplete.py` | 7 cases: a kept card while the others post (message, triage), the notice queued once over rounds, a follow-up whose target is gone, a kept card posting once its row is back, complete cards skip nothing, a failed send after a kept card |
| `tests/integration/test_send_incomplete.py` | 5 cases: a task whose approval is gone is never sent, a task whose message row is gone, a link whose message row is gone, complete tasks skip nothing, a failed send after a kept task still counts it |
| `tests/integration/test_service_incomplete.py` | 1 case: a poll round posts past an incomplete card, says `ok (1 incomplete)`, and posts one notice across rounds |
| `src/mailroom/discord_layout.py` | Adds only `INCOMPLETE_TEXT`, `ALERT_INCOMPLETE` and `INCOMPLETE_STATE` |
| `docs/verification/probe-04i.py` | 40 seeded trials of damaged cards, presses and tasks through `post_pending`, `handle_interaction` and `send_tasks`, checked against an independent oracle |

Given test count: **40** new cases, so the minimum final suite is **1485**.

## Tests to write

Add behavior tests in `tests/integration/test_incomplete_chains.py` (not a `_more`
file). `discord_post.py`, `interactions.py`, `tasks_app.py` and `service.py` are
critical: every line and branch stays covered. The given tests already reach 100% on
a stand-in. Add tests for behavior they leave unpinned, for example:

- a kept task while the tasks app fails on the next one keeps both queued;
- a follow-up link whose message row comes back is sent once, under its usual key;
- a slash command still works while an email's rows are incomplete;
- a card kept for a missing message row in a `run_round` also leaves the alerts step
  running, with the notice posted that round.

Use synthetic data. Do not edit given or earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/discord_post.py` | `PostReport.skipped`, the completeness rule, the notice, card posting |
| `src/mailroom/tasks_app.py` | Kept tasks and links, `skipped` on every report |
| `src/mailroom/interactions.py` | The incomplete reply for presses and forms |
| `src/mailroom/service.py` | The `ok (N incomplete)` status line |
| `tests/integration/test_incomplete_chains.py` | New coder-written behavior tests |
| `docs/progress.md` | Append Phase 4i entry |

New tests fall in `core`; tests/sections.toml stays unchanged.

## Out of scope

- Deleting, repairing or re-creating any stored row; schema changes or foreign keys
  (6a); new store methods that write.
- Changes to alerts.py, the store package, checkpoint.py, commands.py, gateway.py,
  layouts beyond the given texts, fakes, given files, earlier tests, dependencies or
  design documents.
- The approval read right after a write in `_finish_combined` and `_decide`;
  checkpoint 2 presses with no answer row; handler refactoring (4q).
- Pings, tracked problems or resolutions for kept items; logs or exception text in any
  output.

## Rules that bite

All checks are synthetic and offline: fake Discord, the fake tasks app, the fake model,
the fake Keychain and temporary database files. Never touch real mail, Discord, the
tasks app, the Keychain or the data folder. Never catch `AttributeError` or a broad
`Exception` to hide a missing row: check for `None`. The guard runs after the owner
check, because the given tests pin that a stranger is still ignored. A kept card must
never reach `mark_posted`, and a kept task never reaches the tasks app.

## Acceptance

Run from the repository root, in order. The coverage row reads the data the check
left; the given-only run has --no-cov and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line All checks passed.; tests (core) passed; at least 1485 passed, 0 failed/skipped/xfailed, no warnings; every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include=src/mailroom/discord_post.py,src/mailroom/interactions.py,src/mailroom/tasks_app.py,src/mailroom/service.py --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_interactions_incomplete.py tests/integration/test_post_incomplete.py tests/integration/test_send_incomplete.py tests/integration/test_service_incomplete.py --no-cov -q` | 40 passed |
| `.venv/bin/python docs/verification/probe-04i.py` | each check line ends ok; final FAILURES 0 |
| `grep -c '^## Phase 4i: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4i` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04i-incomplete-stored-chains.md docs/verification/phase-04i-incomplete-stored-chains.md tests/integration/test_interactions_incomplete.py tests/integration/test_post_incomplete.py tests/integration/test_send_incomplete.py tests/integration/test_service_incomplete.py src/mailroom/discord_layout.py docs/verification/probe-04i.py` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may additionally write its named review |

### Searches

Each prints nothing (git grep exit 1 means no matches; above 1 is an error).

```zsh
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|time\.sleep|from mailroom\.(clock|ids) import' -- src/mailroom/discord_post.py src/mailroom/tasks_app.py src/mailroom/interactions.py src/mailroom/service.py
git grep --untracked -n -E 'except (AttributeError|TypeError|KeyError|Exception|BaseException)|getattr\(|hasattr\(|suppress\(|pragma: no cover|noqa' -- src/mailroom/discord_post.py src/mailroom/tasks_app.py src/mailroom/interactions.py
git grep --untracked -n -E 'DELETE FROM|INSERT INTO|UPDATE (messages|triage|approvals|posts|tasks|links)' -- src/mailroom/discord_post.py src/mailroom/tasks_app.py src/mailroom/interactions.py src/mailroom/service.py
git grep --untracked -n -E 'ALERT_INCOMPLETE\.format\([^)]*(record|sender|subject|link|title|message_id|provider)|INCOMPLETE_(TEXT|STATE) *\+' -- src/mailroom
```

## Architect validation and handoff

No feature implementation was built. The given tests collect on predecessor imports,
and all 40 new cases fail there.

A throwaway scratch stand-in (about 60 changed lines, deleted with the scratch clone)
did the following. It is not a reference for the coder.

- It passed the given tests 6 of 6 runs.
- It passed all 1445 existing tests unchanged, for a 1485 suite.
- It left the four changed modules at 100% line and branch coverage.
- 17 of 17 mutations of it were caught. They covered:
  - each part of the completeness rule: message row, triage row, follow-up target;
  - a pinged notice, one shared key, and no notice at all;
  - sending incomplete cards, and reporting no skipped cards;
  - a silent acknowledgement for presses, and guarding buttons but not forms;
  - each task and link check, stopping at the first kept task, and dropping
    `skipped` from a later or failed report;
  - an `ok` status line for kept items.

The probe results:

- Oracle-only mode passes.
- On predecessor code it ends FAILURES 1 (80 trial parts raise `AttributeError`).
- On the stand-in it ends FAILURES 0.
- It catches 13 of the 17 mutations. It does not drive forms, links, a failed task
  send or status lines, so the other 4 are left to given tests, which catch them.

The searches are silent on predecessor and stand-in, and each catches a planted
line. Start shows 1445 passed. Given files are linted and formatted.

Before coder use, commit the finalized planning docs and given artifacts, including
the roadmap and history updates, and require a clean checkout.
