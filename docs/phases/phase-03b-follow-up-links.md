# Phase 3b: Follow-up links

## Goal

Send a follow-up you added to a task (Add to task, Phase 3a) to that task in the stub tasks app, once. This meets stage 3's test against the stub: a follow-up in an approved thread links to the existing task instead of making a second one, even when it arrives days later.

Each round's `send_tasks` already sends approved tasks (2f). It now goes on to send links:
- after its tasks, when none stopped, it queues every follow-up answered Add to task (migration 13);
- it POSTs each queued link whose task already has its id in the app to `<MAILROOM_TASKS_URL>/tasks/<task id>/links`, keyed by the follow-up's provider and message id.

A link whose task has no id yet waits, and so does a link that fails: both are tried again next round. The 15-minute alert covers links, because they go through the same step.

A task id is put into a URL path from now on, so the app's reply is accepted only when the id is ASCII letters, digits, `-` and `_`.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 1051, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_store_links.py --ignore=tests/unit/test_link_payload.py` must show `19 failed, 1050 passed`.
- The two ignored files import `Link`, which you create.
- The failures are given tests waiting for you: `test_send_links.py`, `test_service_links.py`, and the package table.

## Facts

Each was checked on this machine.

- **Migration 13 is given.** It adds `links`, one row per follow-up added to a task:
  - `item_id`, the follow-up's post (the primary key);
  - `provider` and `message_id`, unique together;
  - `task_item_id`, the followed item, whose task the link goes on;
  - `queued_at` and `sent_at`.
  It holds no email text.
- **A link's task id is read, not stored.** The followed item's row in `tasks` holds the app's id once the task is sent. Joining on `tasks.item_id = links.task_item_id` gives it, or `NULL` while that task is unsent or not queued.
- **Dot segments collapse.** httpx normalizes a request path, so `/tasks/../links` is sent as `/links` and `/tasks/./links` as `/tasks/links`. Percent-encoding doesn't help, because `quote("..", safe="")` is still `..`. An id may name a path only if it matches `[A-Za-z0-9_-]{1,100}` exactly, as ASCII. `\w` and `str.isalnum` would also let through accents and non-ASCII digits.
- **The fake is extended (given).** `FakeTasksApp` answers `POST /tasks/<id>/links`:
  - 404 for an id it never gave;
  - the same key-header rule as tasks;
  - a body of exactly `source`, `provider`, `message_id` and `link`, or 422;
  - 201 `{"id": "link-N"}` for a new key;
  - 200 with the same id for the same key, task and body;
  - 409 for the same key with another task or body.
  `links` maps each key to `(link id, task id, body)`.
- **The round needs no change.** `run_round` already reports `send_tasks` as the part `tasks` and tracks its alert: failing when it stops, working when it posts.
- **Earlier tests change (given edits):** the schema-version pins say 13, and `test_store_package.py` names the four link methods (`tasks`) and `Link`. 2f's tests send no links, so their reports are unchanged.

## Owner's decisions

- From 3a: a follow-up is linked only after Add to task, and the real tasks app comes in 3c, adopting this stub's contract.
- From 2f: what is sent to the tasks app carries no email text, and failures alert after 15 minutes.

## Architect's decisions

- **Links ride on `send_tasks`.** It sends tasks first, then links, in one step. A link can then go out in the same round its task is first sent, and the round, the status line and the alert need no change.
- **Tasks first; links only after.** When a task send stops, links aren't tried that round, so a failing app gets one request per round, not two.
- **The body names only the follow-up email:** source, provider, message id and link. No title, summary or deadline.
- **The key is the follow-up's own** `<provider>:<message id>`, the same form as a task's. A follow-up answered Add to task never becomes a task, so the two keys never collide.
- **The link's reply body isn't read.** A 200 or 201 means sent. The app's link id is never needed.
- **One check for the id**, where it is accepted: `send_tasks` refuses a reply id that isn't `is_task_id`, so no stored id can be used in a path. An id stored before 3b can't exist, because the service has never run against a real app.

## Requirements

1. **`store/tasks.py`** gains `Link` and four methods on `TaskStore`. They are exported from `mailroom.store`.
   - `Link` is a frozen dataclass with the fields `item_id`, `provider`, `message_id`, `task_item_id`, `task_id: str | None` (read from the followed item's task), `queued_at: datetime` and `sent_at: datetime | None`, in that order.
   - `queue_linked() -> int` reads `clock.now()` once. In one `_write()`, it inserts a link for every answer `link` whose post has a `follows` and no link yet, with that post's provider, message id and `follows`. It returns how many it added.
   - `pending_links() -> tuple[Link, ...]` returns the unsent links whose task has an id, ordered by `queued_at`, then `item_id`.
   - `mark_link_sent(item_id: str) -> bool` reads `clock.now()` once. It sets `sent_at` only on a queued, unsent link, and returns whether it did.
   - `link(item_id: str) -> Link | None`.
2. **`is_task_id(task_id: str) -> bool`** in `tasks_app.py` is true exactly when `task_id` matches `[A-Za-z0-9_-]{1,100}` in full.
3. **`send_tasks`** accepts a task reply's `id` only when it is a string and `is_task_id`. Otherwise it stops with `"response"`, as it does today for an id that isn't text.
4. **`link_payload(link: Link, email_link: str) -> dict[str, object]`** returns exactly `{"source": "email", "provider": link.provider, "message_id": link.message_id, "link": email_link}`.
5. **`send_tasks`, after its tasks:**
   - If a task send stopped, it returns as today.
   - Otherwise it calls `store.queue_linked()`. For each `pending_links()` in order, it POSTs `link_payload(link, store.get(link.provider, link.message_id).record.link)` as JSON to `settings.tasks_url + "/tasks/" + link.task_id + "/links"`, with `Idempotency-Key: task_key(link.provider, link.message_id)`.
   - A 200 or 201 is `mark_link_sent(link.item_id)`.
   - Otherwise it stops, leaving that link and every later one queued: `"network"` for an `httpx.TransportError`, and the status code as text otherwise.
   - It returns `PostReport` with `posted` = tasks sent + links sent, and `waiting` = links not sent (0 when all went). `stopped` is the link's reason, or `""`.
6. **Progress entry** for `## Phase 3b: Follow-up links (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Edited: migration 13 |
| `tests/fakes.py` | Edited: `FakeTasksApp` answers `POST /tasks/<id>/links` |
| `tests/integration/test_store_links.py` | Queued once with its task; other answers not queued; waits for the task's id; sent once; nothing for an unknown or unqueued link; queue order; a version 12 database migrates |
| `tests/unit/test_link_payload.py` | The link's body; thirteen ids, valid or not |
| `tests/integration/test_send_links.py` | Sent once to its task under its key; waits while the task can't be sent; four failures stay queued and resend the same body; ids that can't name a path refused; a follow-up three days later still linked |
| `tests/integration/test_service_links.py` | Stage 3's test through the round: a follow-up an hour or three days later is added to the task, and no second task is made |
| `tests/unit/test_store_package.py`, `tests/integration/test_store.py`, `test_store_sync.py`, `test_store_due.py`, `test_store_combined.py`, `test_store_tasks.py`, `test_store_followup.py` | Edited as in Facts |
| `docs/verification/probe-03b.py` | The verifier's probe |

Given test count: **152** (39 new: 34 in the four new files and 5 new rows in `test_store_package.py`; the rest are in the edited files).

## Tests to write

The given tests cover every requirement's main cases. `store/tasks.py` and `tasks_app.py` are critical. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store/tasks.py` | `Link` and its four methods |
| `src/mailroom/store/__init__.py` | export `Link` |
| `src/mailroom/tasks_app.py` | `is_task_id`, `link_payload`, links in `send_tasks` |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- The real tasks app, its sign-in, or a change to the contract beyond the links endpoint (3c).
- Updating the task's title or deadline from a follow-up, or sending the follow-up's summary.
- Changing a Discord card when a link is sent, or a "linked" notice.
- Changes to `service.py`, `alerts.py` or the status line.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Nothing changes in the tasks app without approval.** A link is queued only from the answer `link`, which only the owner's Add to task press records (3a).
- **Sends are retry-safe.** A link's key is the follow-up's provider and message id. Its body is built only from data kept long term, so a retry, even days later, sends the same one.
- **Email text stays local.** A link carries only what Requirement 4 lists.
- **Network.** Requests go only to `settings.tasks_url`, under `/tasks` and `/tasks/<id>/links`, with an id `is_task_id` accepted.
- **Time through the module.** `clock.now()` is called through the module, only where Requirement 1 says.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 39 = 1090 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_store_links.py tests/unit/test_link_payload.py tests/integration/test_send_links.py tests/integration/test_service_links.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py tests/integration/test_store_followup.py --no-cov -q` | `152 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/store/tasks.py,src/mailroom/store/__init__.py,src/mailroom/tasks_app.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python docs/verification/probe-03b.py` | last line `FAILURES 0` |
| `grep -c "^## Phase 3b: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 3b` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py tests/fakes.py tests/integration/test_store_links.py tests/unit/test_link_payload.py tests/integration/test_send_links.py tests/integration/test_service_links.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_store_tasks.py tests/integration/test_store_followup.py docs/verification/probe-03b.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'body_text|summary|subject|quote|confidence|extraction|sender' -- src/mailroom/tasks_app.py src/mailroom/store/tasks.py
git grep --untracked -n -E 'new_id|uuid|ids\.' -- src/mailroom/tasks_app.py src/mailroom/store/tasks.py
git grep --untracked -n -E '\\w|isalnum|isalpha|isdigit|quote\(' -- src/mailroom/tasks_app.py
git grep --untracked -n -E '"https?://|follow_redirects=True|trust_env=True' -- src/mailroom/tasks_app.py
git grep --untracked -n -E 'response\.text|str\((error|exc|e)\)|\{(error|exc|e)(!r)?\}' -- src/mailroom/tasks_app.py
git grep --untracked -n -E 'send_tasks|queue_linked|/links' -- src/mailroom/interactions.py src/mailroom/gateway.py
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/tasks_app.py src/mailroom/store
```
