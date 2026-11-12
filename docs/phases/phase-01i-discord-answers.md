# Phase 1i: Discord answers

## Goal

Make the checkpoint 1 buttons work, given a press as Discord delivers it. `handle_interaction` checks that the press is yours and in the service's channel, then acts on it.
- **Show full text** and **Trust sender** answer privately.
- **Yes**, **Not a task** and **Mute sender** record your answer and update the card in place.
- **Edit title** opens a one-field form, and the submitted title is checked and recorded.

Each email takes only your first answer. Every reply goes over plain REST. Receiving presses from Discord's Gateway is 1j, together with the commands; 1k runs the loop. Checkpoint 2 (the deadline) is stage 2: a "Yes" is recorded and waits for it.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 441, the tests Phase 1h left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_checkpoint_answered.py --ignore=tests/unit/test_config_owner.py --ignore=tests/integration/test_store_answers.py --ignore=tests/integration/test_interactions.py` must show `441 passed`. The ignored files import names you create, or test a setting you add. `test_store.py` and `test_store_sync.py` already pass with the given migration 6.

## Facts

From Discord's reference (docs.discord.com/developers: Receiving and Responding, Components):

- **A press** is an interaction:
  - `id`, `token` and `type`: 3 for a button, 5 for a form submission, 2 for a slash command
  - `channel_id`
  - the presser in `member.user.id` (in a server) or `user.id` (in a DM)
  - `data`: a button's `custom_id`, or a form's `custom_id` and its `components`

  It comes over the Gateway, the bot's own authenticated connection, so there is no signature to check.
- **The reply.** `POST https://discord.com/api/v10/interactions/<id>/<token>/callback`, with the usual User-Agent. The token in the path authorizes it, so no bot token is sent. It answers 204.
  - The first reply must be sent within 3 seconds, or the token is invalidated. The token then lasts 15 minutes.
  - An interaction takes one reply; a second answers 400 (code 40060).
- **Reply types.**
  - 4: a new message
  - 6: acknowledge, change nothing (presses and submissions only)
  - 7: update the message the button is on (presses and submissions only)
  - 9: a form (not for a submission)

  Flag 64 makes a message visible only to the presser.
- **Forms.** `custom_id` 1 to 100 characters and `title` at most 45. Inside are 1 to 5 Labels (`type` 18, `label` at most 45), each holding a Text Input (`type` 4: `custom_id`, `style` 1 for one line, `min_length` and `max_length` within 0 to 4000, `required`, an optional prefilled `value`). A submission returns the same nesting with the typed `value`; a Text Input inside an Action Row is the deprecated form.
- **The fake.** `tests.fakes.FakeDiscord` now builds presses (`press`) and submissions (`submit`) from `owner_id` in its channel. Its callback route checks the User-Agent, the interaction and token, one reply each, the allowed types, message limits (only flag 64) and form limits, and records each accepted reply in `callbacks`.

## Owner's decisions

- **Handling first, the Gateway next.** 1i handles a press given as Discord delivers it; 1j connects to the Gateway and adds the commands.
- **The card is updated in place.** Once you answer, the card shows your answer, and only Show full text and Open email remain, so it can't be answered twice.
- **Answers are recorded; a sender score waits.** What a lower score changes is an open question for later.

## Architect's decisions

- **Ignored means acknowledged with no change.** A press from anyone but you, or from another channel, or a button id that isn't ours, gets reply type 6. Nothing is recorded and nothing changes; the presser sees nothing happen. Slash commands get no reply here (1j).
- **The answer is recorded before the reply**, so a failed reply loses no answer; the next press says it is already answered.
- **Yes needs a title.** Yes on a card without a proposed title (unreadable, expired, or no title) opens the form, prefilled with the subject.
- **Edit title records `edit`**, with your title, when the form comes back. The title must be 1 to 100 characters after trimming, with no line breaks or invisible characters (categories `Cc`, `Cf`, `Zl`, `Zp`), the same rule the extractor uses.
- **Show full text** sends the body in a code block, backticks replaced as on the card. It is cut at 1,900 characters with a note, so the reply stays under 2,000. After 24 hours it says the text has expired. Mentions are off.
- **Trust works on any card**, answered or not, and never answers it. Trust and Mute need a sender address.
- **An `answers` table** (given migration 6) keeps the item id, the answer, the approved title and when. The title is kept beyond 24 hours, as the design keeps a pending item's task title; every other answer has an empty title.
- **No new settings except the owner's id**, `MAILROOM_DISCORD_OWNER_ID`.
- **Critical modules**: `interactions.py` (who can answer, what is recorded, what text goes back to Discord).

## Examples in plain words

- You tap Yes on the bill's card: the card now says "Your answer: Yes, it's a task · Pay the November bill", with only Show full text and Open email left.
- Someone else in the server taps Mute sender: nothing happens, and the sender is not muted.
- You tap Not a task, then Mute sender on the same card from an old screen: the second tap privately says "This email is already answered."
- You tap Edit title and submit "  Pay online  ": the title "Pay online" is recorded and shown.
- You tap Show full text two days later: a private note says the text was deleted after 24 hours.

## Verify before building

With a test bot in your private server, once 1j connects:
- An interaction callback with no Authorization header is accepted.
- A form built with a Label holding a Text Input shows and submits on the phone app.

## Requirements

1. **Migration 6** (given) creates `answers`:
   - columns `item_id` (primary key), `answer` (`yes`, `edit`, `notask` or `mute`), `title` and `answered_at`
   - `title` is non-empty exactly for `yes` and `edit`

2. **`store.py`.**
   - `Answer`, a `@dataclass(frozen=True)`: `item_id: str`, `answer: Literal["yes", "edit", "notask", "mute"]`, `title: str`, `answered_at: datetime`.
   - `Store.post_by_item(item_id: str) -> Post | None`.
   - `Store.record_answer(item_id: str, answer: str, title: str) -> bool` reads `clock.now()` exactly once per call. It inserts only when a post with that `item_id` exists and no answer does, and returns `True` when it inserted. An answer the table refuses raises `sqlite3.IntegrityError`. It commits.
   - `Store.answer(item_id: str) -> Answer | None`.

3. **`config.py`: `discord_owner_id: str = ""`** (`MAILROOM_DISCORD_OWNER_ID`). A non-empty value must match `[0-9]{17,20}`, else `get_settings` raises `ConfigError` with `DISCORD_OWNER_MESSAGE = "MAILROOM_DISCORD_OWNER_ID must be a Discord user id (17 to 20 digits)"`, never the value.

4. **`checkpoint.py`: `answered_message(record: Record, verdict: Verdict, item_id: str, answer: str, title: str) -> dict[str, object]`** returns exactly `embeds`, `components` and `allowed_mentions` (call the layout `L`).
   - **The embed** is the one `checkpoint_message` builds, with one more field last: `{"name": L.ANSWER_NAME, "value": ...}`. The value is `L.ANSWER_TEXT[answer]`, followed for `yes` and `edit` by `"\n"` and the block of `title`.
   - **`components`** is one row: the Show full text button exactly as on the card, then the link button under the same rule.
   - **`allowed_mentions`** is `{"parse": []}`.

5. **`src/mailroom/interactions.py`: `handle_interaction(event: dict[str, object], store: Store, settings: Settings, http: httpx.Client) -> str`**, which returns what it did as one word (below).
   1. An empty `discord_owner_id` or `discord_channel_id` raises `DiscordUnavailable("not configured")` (from `discord_post`) before any request.
   2. An `event["type"]` other than 3 or 5 returns `"ignored"`, with no request.
   3. Reply `{"type": L.DEFERRED_UPDATE}` and return `"ignored"` when any of these holds:
      - the presser (`member.user.id`, else `user.id`) is not `discord_owner_id`
      - `channel_id` is not `discord_channel_id`
      - `data.custom_id` does not split on `:` into exactly `L.PREFIX`, an action and an item id
      - the action is not one of the card's six (for type 3), or not `L.FORM_ACTION` (for type 5)
      - `store.post_by_item` finds no post
   4. The record, verdict and whether the text is cleared come from `store.get` and `store.triage` for that post.
   5. **Presses (type 3)**, by action:
      - `full`: a private reply (requirement 6) of the body. Returns `"full"`.
      - `trust`:
        - with no sender, a private `L.NO_SENDER_TEXT`, returning `"no-sender"`
        - otherwise `store.set_sender_status(sender, "trusted")` and a private `L.TRUSTED_REPLY + "\n" + block(sender)`, returning `"trusted"`
      - `yes`, `edit`, `notask`, `mute`, once `store.answer(item_id)` already exists: a private `L.ALREADY_TEXT`, with nothing recorded. Returns `"already"`.
      - `mute` with no sender: a private `L.NO_SENDER_TEXT`. Returns `"no-sender"`.
      - `edit`, or `yes` when the extraction has no title: the form (requirement 7). Returns `"form"`.
      - `yes`: `record_answer(item_id, "yes", <the extraction's title>)`.
      - `notask`: `record_answer(item_id, "notask", "")`.
      - `mute`: `set_sender_status(sender, "muted")`, then `record_answer(item_id, "mute", "")`.
      - After `yes`, `notask` or `mute` is recorded, reply `{"type": L.UPDATE_MESSAGE, "data": answered_message(...)}`. Returns `"answered"`.
   6. **Form submissions (type 5).**
      - Already answered: the private `L.ALREADY_TEXT`, returning `"already"`.
      - Otherwise take the `value` of the Text Input with `custom_id` `L.FORM_INPUT_ID`, from a Label in `data.components`, and `strip()` it.
      - If it is missing, empty, over `L.FORM_TITLE_LIMIT`, or holds a character of category `Cc`, `Cf`, `Zl` or `Zp`: a private `L.BAD_TITLE_TEXT`, returning `"bad-title"`.
      - Otherwise `record_answer(item_id, "edit", title)`, then the update reply, returning `"answered"`.
   7. **Replies** are `http.post(f"{L.API_URL}/interactions/{event id}/{event token}/callback", json=..., headers={"User-Agent": ...})`, with no Authorization. Exactly one per type 3 or 5 event. A `httpx.TransportError` raises `DiscordUnavailable("network")`, and any status but 204 raises `DiscordUnavailable(<status>)`, both `from None`. A recorded answer stays recorded.

6. **A private reply** is `{"type": L.CHANNEL_MESSAGE, "data": {"content": <text>, "flags": L.EPHEMERAL, "allowed_mentions": {"parse": []}}}`. For Show full text, the text is:
   - `L.FULL_EXPIRED` once the message's `text_cleared_at` is set
   - `L.FULL_EMPTY` for an empty body
   - otherwise `block(body[:L.FULL_LIMIT])`, followed by `"\n" + L.FULL_CUT_NOTE` when the body is longer than `L.FULL_LIMIT`

   `block` is the card's (backticks replaced).

7. **The form** is `{"type": L.MODAL, "data": {"custom_id": f"{L.PREFIX}:{L.FORM_ACTION}:{item_id}", "title": L.FORM_TITLE, "components": [{"type": 18, "label": L.FORM_LABEL, "component": {"type": 4, "custom_id": L.FORM_INPUT_ID, "style": 1, "min_length": 1, "max_length": L.FORM_TITLE_LIMIT, "required": True, "value": <prefill>}}]}}`. The prefill is the extraction's title when non-empty, else the subject's first 100 characters. `"value"` is left out when the prefill is empty.

8. **Critical modules.** `scripts/critical_modules.txt` (given) lists `interactions.py`.

9. **Progress entry** for `## Phase 1i: Discord answers (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Adds migration 6, the `answers` table |
| `src/mailroom/discord_layout.py` | Adds the reply types, answer texts, form and reply texts |
| `tests/fakes.py` | `FakeDiscord` gains presses, submissions and the callback route |
| `tests/integration/test_store.py`, `tests/integration/test_store_sync.py` | Schema version asserts now expect 6 |
| `tests/unit/test_checkpoint_answered.py` | 5 tests (requirement 4) |
| `tests/unit/test_config_owner.py` | 4 tests (requirement 3) |
| `tests/integration/test_store_answers.py` | 5 tests (requirement 2) |
| `tests/integration/test_interactions.py` | 26 tests (requirements 5 to 7) |
| `scripts/critical_modules.txt` | Adds `interactions.py` |
| `docs/verification/probe-01i.py` | The verifier's probe |

Given test count: **40** in the four new files, from 25 test functions.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_interactions_more.py` (and `tests/integration/test_store_answers_more.py` if needed), never by changing a given test, for at least:
- a press carrying `user.id` instead of `member` (a DM)
- a submission with no Text Input of `custom_id` `title` (`"bad-title"`)
- a reply that fails with a network error (`discord unavailable (network)`)
- Show full text for an empty body (`L.FULL_EMPTY`)
- the form for a card with no title and an empty subject (no `"value"`)

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store.py` | add `Answer`, `post_by_item`, `record_answer`, `answer` |
| `src/mailroom/config.py` | add `discord_owner_id` and `DISCORD_OWNER_MESSAGE` |
| `src/mailroom/checkpoint.py` | add `answered_message`, sharing the card's code |
| `src/mailroom/interactions.py` | create |
| `tests/integration/test_interactions_more.py` | create |
| `tests/integration/test_store_answers_more.py` | create, only if coverage needs it |
| `docs/progress.md` | append your entry |

## Out of scope

- **Receiving.** The Gateway connection, heartbeats, reconnecting, registering or handling slash commands (1j); the poll loop (1k).
- **Stage 2 and later.** Checkpoint 2, combined approval, sending tasks, sender scores, the 30-minute follow-up, digests.
- **Other changes.** Follow-up messages after the first reply, editing other messages, undoing an answer, untrusting or unmuting, logging, retries, a Discord library, any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Nothing happens for anyone but you** (`AGENTS.md`): every press and submission is checked against your Discord user id and the service's channel before anything is read or changed.
- **Email text reaches Discord only as the design allows**: the body only through Show full text's private reply, in a code block with backticks replaced and mentions off.
- **Your title is untrusted text too**: plain, one line, at most 100 characters.
- **Retry-safe**: one answer per email, the first; a repeated press changes nothing.
- **No secrets** are read or sent in this phase: replies need no bot token.
- **Time through the module**: `clock.now()`, never imported by name.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 40 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_checkpoint_answered.py tests/unit/test_config_owner.py tests/integration/test_store_answers.py tests/integration/test_interactions.py --no-cov -q` | `40 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/interactions.py,src/mailroom/checkpoint.py,src/mailroom/store.py,src/mailroom/config.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1i: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1i` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_checkpoint_answered.py tests/unit/test_config_owner.py tests/integration/test_store_answers.py tests/integration/test_interactions.py scripts/critical_modules.txt docs/verification/probe-01i.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|websockets|discord)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request|(import|from) urllib([^.A-Za-z_]|$)' -- src
git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py' ':!src/mailroom/discord_post.py' ':!src/mailroom/interactions.py'
git grep --untracked -n -E 'discord\.com|discordapp' -- src ':!src/mailroom/discord_layout.py'
git grep --untracked -n -E 'keychain|get_secret|[Aa]uthorization' -- src/mailroom/interactions.py
git grep --untracked -n -E '\.(patch|put|delete)\(|webhooks|/channels/|gateway' -- src/mailroom/interactions.py
git grep --untracked -n -E 'authentication_results|[^_]summary' -- src/mailroom/interactions.py
git grep --untracked -n -E 'sleep\(|while |retry' -- src/mailroom/interactions.py
git grep --untracked -n -E 'raise [A-Za-z]+\(f|raise [A-Za-z]+\([a-z_.]*(token|error|value|title|body|content|text|json)' -- src/mailroom/interactions.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store.py src/mailroom/config.py
```
