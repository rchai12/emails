# Phase 2f: Stub tasks app

## Goal

Send each fully approved task to a tasks app, once. Approval means Approve, Edit or No deadline at checkpoint 2 or on the combined card. See [Interfaces](../interfaces.md#outbound-approved-task-to-the-tasks-app).

Each round of the poll loop does two things, before posting to Discord:
- it queues every approved item not yet queued (migration 11);
- it POSTs each queued task to `MAILROOM_TASKS_URL` with `Idempotency-Key: <provider>:<message id>`, then stores the id the app returns.

A failed send stays queued and is tried again next round. A retry sends the same key and the same body, so the app never makes a second task. After 15 minutes of failed sends there is one Discord alert, and one more when sends work again.

The real tasks app's API is not known yet. This phase builds against a stub contract that the given `FakeTasksApp` defines, and stage 3 adapts it to the real app. The Discord card does not change when a task is sent.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 961, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_config_tasks.py --ignore=tests/unit/test_task_payload.py --ignore=tests/integration/test_store_tasks.py --ignore=tests/integration/test_send_tasks.py` must show `34 failed, 937 passed`.
- The four ignored files import names you create.
- The 34 failures are given edits waiting for you:
  - `test_store_package.py` expects the `tasks` area;
  - the service tests call `run_round` with a tasks client and `run_service` with `open_tasks_http`;
  - `test_service_tasks.py` needs the feature.

## Facts

Each was checked on this machine.

- **Migration 11 is given.** It adds `tasks`:
  - `item_id` (primary key), `provider`, `message_id` (unique together) and `queued_at`;
  - `task_id` (1 to 100 characters) and `sent_at`, both `NULL` until sent, or both set.
  - It holds no email text.
- **The approved data is all kept long term.** The payload is built from three places, none of which the 24-hour clearing touches:
  - the approval's title and deadline (`approvals`);
  - the message's provider, id and link (`messages`);
  - the time zone setting.
  So a retry rebuilds the same body even after the text is cleared (given test `test_a_lost_reply_is_resent_under_the_same_key_after_the_text_is_cleared`).
- **Reading the app's reply.** I fuzzed 5,000 corrupted 201 replies. `response.json()["id"]` raised only `ValueError` (`JSONDecodeError`, and `UnicodeDecodeError` on bad bytes), `TypeError` (a list or `null`) and `KeyError`, or returned a value that is not a string. This is the same set `discord_post._message_id` catches.
- **The upsert parses.** `INSERT INTO tasks (...) SELECT ... FROM approvals JOIN posts ON ... WHERE ... ON CONFLICT DO NOTHING` works, and its `rowcount` counts only the new rows.
- **The status order keeps earlier tests.** Several earlier tests read a round's lines by position: `[-1]` is `discord alerts`, and `[-2]` is `discord posting`. The tasks step therefore runs after triage and before Discord posting. An alert it raises is still posted in the same round, because alerts post last.
- **The given fake** is `tests.fakes.FakeTasksApp` (its docstring is the contract):
  - `URL` is `http://127.0.0.1:8765`, and only `POST /tasks` is answered.
  - A missing key gets 400. A body with any other field, or a wrong type, gets 422.
  - A new key gets 201 `{"id": "task-N"}`. The same key and body get 200 with the same id. The same key with a different body gets 409.
  - `failures` takes a `Response`, an exception, `"lost-reply"` (the task is made, then `ReadTimeout`), or `None` (no failure).
- **Earlier tests change (given edits):**
  - `test_service.py`: `World` gains `tasks` and `tasks_http()`, the fixture sets `MAILROOM_TASKS_URL`, `serve` passes `open_tasks_http`, and three round lists plus the service's first lines gain `"tasks: ok"`.
  - `test_service_more.py`: the same URL, and one list.
  - `test_service_alerts.py`: `World.round` passes a tasks client. Its settings have no URL, so its rounds say `tasks: tasks app unavailable (not configured)`, and none of its checks read that line.
  - `test_store_package.py`: the `tasks` area, its four methods and `Task`.
  - The schema-version pins say 11.

## Owner's decisions

- **A stub HTTP client with our own contract**, tested against a fake. The address must be on this Mac. Stage 3 adapts the contract and adds sign-in.
- **The payload carries no evidence quote and no confidence.** It has source, title, deadline, provider, message id and link. `interfaces.md` was updated to match.
- **Failures alert after 15 minutes**, once, like the model's alert, and once more when sends work again.

## Architect's decisions

- **Queued by the round, not the press.** `send_tasks` calls `store.queue_approved()` first, just as `post_pending` calls `queue_notified()`. The listener thread and `ApprovalStore` are unchanged, and a task waits at most one poll interval.
- **The queue is the record of what was sent.** A row with a `task_id` was accepted by the app. The app's id is kept so stage 3 can link follow-ups in a thread to it.
- **Not configured is not an outage.** With `MAILROOM_TASKS_URL` empty (the default), `send_tasks` raises `TasksUnavailable("not configured")` before queuing anything. The round prints that once and never alerts. The owner can run the service before a tasks app exists, and approved items are queued as soon as an address is set.
- **An alert only for real failed sends.** A round whose send stopped counts as failing. A round that sent at least one task counts as working. A round with nothing to send changes nothing, so no recovery is announced without a send.
- **Every refusal stays queued.** A 4xx such as 409 or 422 is not dropped: the task waits and the 15-minute alert tells the owner. Nothing approved is ever thrown away.
- **Deadline with its zone.** A date and time alone mean nothing to another program, so the deadline carries `time_zone`, the owner's setting.
- **`PostReport` is reused** for `send_tasks`'s result. It has the same three fields, and `_status` already reads it.

## Requirements

1. **`Settings.tasks_url: str = ""`** (env `MAILROOM_TASKS_URL`).
   - Empty is accepted.
   - Anything else must pass the same rule as `extractor_url`: `http://` on `127.0.0.1`, `localhost` or `[::1]`, with no user, path, query or fragment, and a valid port.
   - Otherwise `get_settings()` raises `ConfigError(TASKS_URL_MESSAGE)`, where `TASKS_URL_MESSAGE = "MAILROOM_TASKS_URL must be empty or http:// on 127.0.0.1, localhost or [::1], with no path"`.
2. **`store/tasks.py`**, the store's ninth area: `Task` and `TaskStore`, mixed into `Store` and exported from `mailroom.store`.
   - `Task` is a frozen dataclass with the fields `item_id`, `provider`, `message_id`, `queued_at: datetime`, `task_id: str | None` and `sent_at: datetime | None`, in that order.
   - `queue_approved() -> int` reads `clock.now()` once. In one `_write()`, it inserts a task for every approval whose outcome is not `drop` and which has no task yet, taking provider and message id from its post. It returns how many it added.
   - `pending_tasks() -> tuple[Task, ...]` returns the unsent tasks, ordered by `queued_at`, then `item_id`.
   - `mark_task_sent(item_id: str, task_id: str) -> bool` reads `clock.now()` once. It sets `task_id` and `sent_at` only on a queued, unsent task, and returns whether it did. An id the schema refuses raises `sqlite3.IntegrityError`.
   - `task(item_id: str) -> Task | None`.
3. **`task_key(provider: str, message_id: str) -> str`** in a new `tasks_app.py` returns `f"{provider}:{message_id}"`.
4. **`task_payload(task: Task, approval: Approval, link: str, time_zone: str) -> dict[str, object]`** returns exactly `{"source": "email", "title": approval.title, "deadline": ..., "provider": task.provider, "message_id": task.message_id, "link": link}`.
   - `deadline` is `None` when `approval.due` is `None`.
   - Otherwise it is `{"date": "YYYY-MM-DD", "time": "HH:MM" or None, "time_zone": time_zone}`.
   - It takes nothing else from the email.
5. **`open_tasks_http() -> httpx.Client`** returns `httpx.Client(timeout=30.0, trust_env=False, follow_redirects=False)`. **`TasksUnavailable(Exception)`**: `TasksUnavailable(detail)` reads `f"tasks app unavailable ({detail})"`.
6. **`send_tasks(store: Store, settings: Settings, http: httpx.Client) -> PostReport`**:
   - With `settings.tasks_url == ""`, it raises `TasksUnavailable("not configured")` and does nothing else.
   - Otherwise it calls `store.queue_approved()`. Then, for each `pending_tasks()` in order, it builds `task_payload(task, store.approval(task.item_id), store.get(task.provider, task.message_id).record.link, settings.time_zone)`.
   - It POSTs that body as JSON to `settings.tasks_url + "/tasks"`, with the header `Idempotency-Key: task_key(task.provider, task.message_id)`.
   - A 200 or 201 whose JSON `id` is a string of 1 to 100 characters is `mark_task_sent(task.item_id, id)`.
   - Otherwise it stops, leaving that task and every later one queued: `"network"` for an `httpx.TransportError`, the status code as text for any other status, `"response"` for an unreadable or invalid id.
   - It returns `PostReport(posted, waiting, stopped)`, as `send_messages` does. With nothing pending, it sends nothing and returns `PostReport(0, 0, "")`.
7. **The round.** The signature becomes `run_round(store, settings, gmail_clients, model_http, discord_http, tasks_http, health)`.
   - After triage and before Discord posting, it runs `send_tasks` and reports the part `"tasks"` as `_status` does: `ok`, `waiting (<stopped>)`, or the text of `TasksUnavailable` or `KeychainError`.
   - Then it calls `alerts.track(store, "tasks", ...)` with `wait=alerts.TASKS_WAIT` (a new `timedelta(minutes=15)` in `alerts.py`), `raised=L.ALERT_TASKS`, `ping=False` and `resolved=L.ALERT_TASKS_FIXED`.
   - It tracks failing when the report stopped, and working when it posted at least one task with no stop. It does not track at all when it raised, or sent nothing.
8. **The service.** `run_service` gains `open_tasks_http: Callable[[], httpx.Client] = tasks_app.open_tasks_http`. It opens the client once, beside the others, passes it to every round, and closes it with the others. `MAILROOM_TASKS_URL` is not added to the settings the service requires.
9. **Progress entry** for `## Phase 2f: Stub tasks app (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Edited: migration 11 |
| `src/mailroom/discord_layout.py` | Edited: `ALERT_TASKS`, `ALERT_TASKS_FIXED` |
| `tests/fakes.py` | Edited: `FakeTasksApp` |
| `scripts/critical_modules.txt` | Edited: `store/tasks.py` and `tasks_app.py` added |
| `tests/unit/test_config_tasks.py` | The address unset by default, accepted on this Mac, refused anywhere else |
| `tests/unit/test_task_payload.py` | The key, and the payload for four decisions |
| `tests/integration/test_store_tasks.py` | Queued once per approval, combined included; not for drop, undecided or closed; sent keeps its id; nothing for an unknown or unqueued item; queue order; refused ids; a version 10 database migrates |
| `tests/integration/test_send_tasks.py` | One exact request under its key; nothing without an address; seven failures stay queued; a lost reply resent after clearing makes one task; a failure stops the round; drop and undecided never sent; the client's settings |
| `tests/integration/test_service_tasks.py` | The round sends once; 15 minutes down is alerted and the return announced; a short outage isn't; no address says so and never alerts; the service closes its tasks client |
| `tests/unit/test_store_package.py`, `tests/integration/test_store.py`, `test_store_sync.py`, `test_store_due.py`, `test_store_combined.py`, `test_service.py`, `test_service_more.py`, `test_service_alerts.py` | Edited as in Facts |
| `docs/verification/probe-02f.py` | The verifier's probe |

Given test count: **158** (49 new: 44 in the five new files, 5 new rows in `test_store_package.py`; the rest are in the edited files).

## Tests to write

The given tests cover every requirement's main cases. `store/tasks.py`, `tasks_app.py`, `store/__init__.py`, `config.py`, `alerts.py` and `service.py` are critical. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test. For example:
- a round whose `send_tasks` meets a `KeychainError`;
- a failing problem followed by a round with nothing to send, which neither alerts nor resolves.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/config.py` | `tasks_url`, `TASKS_URL_MESSAGE` |
| `src/mailroom/store/tasks.py` | create: `Task`, `TaskStore` |
| `src/mailroom/store/__init__.py` | mix in `TaskStore`, export `Task` |
| `src/mailroom/tasks_app.py` | create |
| `src/mailroom/alerts.py` | `TASKS_WAIT` |
| `src/mailroom/service.py` | the tasks step, its alert, the client |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- The real tasks app, its sign-in or a token in the Keychain, and thread-to-task linking (stage 3).
- Changing the Discord card when a task is sent, or a "sent" notice.
- Retrying within a round, backoff, or dropping a task the app refuses.
- Sending from the listener thread at the moment of the press.
- The evidence quote, confidence, summary or any other email text in the payload.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Nothing becomes a task without approval.** Only an `approvals` row with outcome `approve`, `change` or `nodeadline` is queued. A `drop`, an answer alone, or Not a task is never sent.
- **Sends are retry-safe.** The key is the provider and message id, never a new id or the item id. The body is rebuilt only from long-term data, so a retry sends the same one, and a failed send stays queued.
- **Email text stays local.** The request carries only what Requirement 4 lists. No error, status line or alert echoes a reply's body or an exception's text.
- **Network.** `tasks_app.py` connects only to `settings.tasks_url`, which must be on this Mac, through a client that ignores proxy settings and doesn't follow redirects.
- **Time through the module.** `clock.now()` is called through the module, only where Requirement 2 says, and in `alerts.track` as today.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 49 = 1010 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_config_tasks.py tests/unit/test_task_payload.py tests/integration/test_store_tasks.py tests/integration/test_send_tasks.py tests/integration/test_service_tasks.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_service.py tests/integration/test_service_more.py tests/integration/test_service_alerts.py --no-cov -q` | `158 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/tasks_app.py,src/mailroom/store/tasks.py,src/mailroom/store/__init__.py,src/mailroom/config.py,src/mailroom/alerts.py,src/mailroom/service.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python docs/verification/probe-02f.py` | last line `FAILURES 0` |
| `grep -c "^## Phase 2f: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 2f` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py scripts/critical_modules.txt tests/unit/test_config_tasks.py tests/unit/test_task_payload.py tests/integration/test_store_tasks.py tests/integration/test_send_tasks.py tests/integration/test_service_tasks.py tests/unit/test_store_package.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/integration/test_store_due.py tests/integration/test_store_combined.py tests/integration/test_service.py tests/integration/test_service_more.py tests/integration/test_service_alerts.py docs/verification/probe-02f.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'body_text|summary|subject|quote|confidence|extraction|sender' -- src/mailroom/tasks_app.py src/mailroom/store/tasks.py
git grep --untracked -n -E 'new_id|uuid|ids\.' -- src/mailroom/tasks_app.py src/mailroom/store/tasks.py
git grep --untracked -n -E '"https?://' -- src/mailroom/tasks_app.py
git grep --untracked -n -E 'follow_redirects=True|trust_env=True|verify=False' -- src
git grep --untracked -n -E 'response\.text|str\((error|exc|e)\)|\{(error|exc|e)(!r)?\}' -- src/mailroom/tasks_app.py
git grep --untracked -n -E 'tasks_app|send_tasks|queue_approved' -- src/mailroom/interactions.py src/mailroom/gateway.py
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/tasks_app.py src/mailroom/store src/mailroom/config.py src/mailroom/alerts.py src/mailroom/service.py
```
