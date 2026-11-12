# Phase 1h: Discord posting

## Goal

Post a checkpoint 1 message on Discord for every email triage decided to notify you about. Each message is an embed card: the sender, subject, summary and proposed task, all inside code blocks so nothing in an email can format, link or mention. It carries the six answer buttons and an "Open email" link. Each email is queued once in a new `posts` table and posted with a duplicate-proof `nonce`. A failed send stops the round and is retried next time, so no email is lost or posted twice. Button presses are not handled yet: 1i receives them, 1j adds the commands, 1k runs the loop.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 407, the tests Phase 1g left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/unit/test_checkpoint.py --ignore=tests/unit/test_config_discord.py --ignore=tests/integration/test_store_posts.py --ignore=tests/integration/test_discord_post.py` must show `407 passed`. The ignored files import names you create, or test a setting you add. `test_store.py` and `test_store_sync.py` already pass with the given migration 5.

## Facts

From Discord's API reference (docs.discord.com/developers: Message, Components, Rate Limits, Reference):

- **The call.** `POST https://discord.com/api/v10/channels/<channel id>/messages`, with `Authorization: Bot <token>` and a User-Agent `DiscordBot ($url, $versionNumber)`. A request without a valid User-Agent may be blocked. Ids (snowflakes) are strings in JSON. A 200 returns the message, with its `id` and `channel_id`.
- **No duplicates.** `nonce` is at most 25 characters. With `enforce_nonce: true`, a nonce already used by the bot "in the past few minutes" returns the existing message instead of making a new one. The reference gives no exact window.
- **No pings.** `allowed_mentions: {"parse": []}` turns off every mention; by default a message parses all of them.
- **Embed limits.** Title 256, description 4096, at most 25 fields (name 256, value 1024), footer 2048, and 6000 characters across all embeds. A breach is a 400.
- **Buttons.** At most 5 action rows (`type` 1) of at most 5 buttons (`type` 2).
  - Styles: 1 primary, 2 secondary, 3 success, 4 danger, 5 link.
  - A label is at most 80 characters.
  - A non-link button needs a `custom_id` of 1 to 100 characters, unique in the message, and no `url`.
  - A link button needs a `url` of at most 512 and no `custom_id`, and sends no interaction.
- **Rate limits.** A 429 has JSON `retry_after` (seconds, a float) and `global`.
- **Ids.** `ids.new_id()` is `uuid4().hex`, 32 characters, so the nonce is its first 25.
- **The fake.** `tests.fakes.FakeDiscord` checks all of the above, makes message ids from `1300000000000000001` up, honours `enforce_nonce`, and takes scripted `failures`: an exception, a response, or `"lost-reply"` (the message is made, then `ReadTimeout`).

## Owner's decisions

- **Split.** 1h posts; 1i handles button presses; 1j adds `/trust`, `/untrust` and `/trusted`; 1k is the poll loop.
- **Plain REST with httpx** for every send, faked from Discord's documented shapes. Only receiving presses needs a Gateway listener, chosen in 1i. No new dependency here.
- **Embed card.** A colored card, with the email's text in fields and the buttons below.

## Architect's decisions

- **Email text only in code blocks.** The sender, subject, summary, title and spam reason each sit alone inside a code block, where Discord renders no markdown, links or mentions. Every backtick in them becomes `ˋ`, so the text can't close the block. The embed's title and footer are fixed text. The body is never posted; that is 1i's Show full text, as an ephemeral reply.
- **The layout is given** in `src/mailroom/discord_layout.py`: button ids `mr:<action>:<item id>`, labels, styles, colors, field names and fixed texts. 1i reads the button ids back.
- **A `posts` table** (given migration 5), not the planned `items` table. It holds only what posting needs: the item id, the email's key, when it was queued, and the Discord message id once posted. It holds no email text, so it is kept. 1i adds its answers in its own table rather than changing this one.
- **Retry-safe in two layers.** The store marks an item posted only after a 200 with an id. If the reply is lost, the next try sends the same nonce, and Discord returns the first message.
- **A failure stops the round.** Any network error, non-200 status or reply without an id ends this call, leaving the item and the ones after it queued for the next call. Nothing is dropped. No sleeping on `retry_after`: polls are minutes apart.
- **Grey for no summary.** An email the model couldn't read, or whose summary was cleared before it could be posted, gets a grey card with a fixed sentence instead of a summary. Red marks suspected spam.
- **A link too long for a button** (over 512) is left out, rather than failing the send.
- **The User-Agent** is `DiscordBot (mailroom, <version>)`; there is no public project address (see "Verify before building").
- **Critical modules**: `checkpoint.py` (what email text Discord shows, and how) and `discord_post.py` (each email posted once, never lost, the token never shown).

## Examples in plain words

- An email the model read: a blurple card with From, Subject, Summary and Proposed task, and the footer "Gmail · Verified sender".
- A subject like ``Use `code` and [click](https://evil.test)`` shows exactly as typed, with ˋ for each backtick, inside a code block. Nothing is bold and nothing is a link.
- The model couldn't read it: a grey card saying "The model couldn't read this email (timeout)."
- Discord answers 429 for the first of two queued emails: neither is posted now, both are posted next round.
- The reply to a post is lost: the next round sends it again, and Discord returns the same message, so you see one card.

## Verify before building

In your private server, with a test bot:
- A message posted with the User-Agent `DiscordBot (mailroom, 0.1.0)` is accepted.
- A URL or `@everyone` inside an embed field's code block is not clickable and pings nobody, on the desktop and phone apps.
- A second post with the same nonce and `enforce_nonce` returns the first message.

## Requirements

1. **Migration 5** (given) creates `posts`:
   - columns `item_id` (primary key), `provider`, `message_id`, `queued_at`, `discord_message_id`, `posted_at`
   - `UNIQUE (provider, message_id)`
   - `discord_message_id` and `posted_at` set together

2. **`store.py`: `Post`**, a `@dataclass(frozen=True)`: `item_id: str`, `provider: str`, `message_id: str`, `queued_at: datetime`, `discord_message_id: str | None`, `posted_at: datetime | None`.

3. **`Store.queue_notified() -> int`.**
   - Reads `clock.now()` exactly once per call.
   - Gives every `triage` row with `notify = 1` and no `posts` row a new post, with `item_id=ids.new_id()` (one call per new post) and `queued_at` = that time.
   - Posts are made in order of `decided_at`, then provider, then message id.
   - Returns how many it made, and commits.

4. **`Store.pending_posts() -> tuple[Post, ...]`** gives the posts not yet posted, in the order they were queued.

   **`Store.post(provider: str, message_id: str) -> Post | None`** reads one back.

5. **`Store.mark_posted(item_id: str, discord_message_id: str) -> bool`.** Reads `clock.now()` exactly once. It sets both columns only on a post not yet posted, and returns `True` when it did. It commits.

6. **`config.py`: `discord_channel_id: str = ""`** (`MAILROOM_DISCORD_CHANNEL_ID`). A non-empty value must match `[0-9]{17,20}`, else `get_settings` raises `ConfigError` with `DISCORD_CHANNEL_MESSAGE = "MAILROOM_DISCORD_CHANNEL_ID must be a Discord channel id (17 to 20 digits)"`, never the value.

7. **`src/mailroom/checkpoint.py`: `checkpoint_message(record: Record, verdict: Verdict, item_id: str) -> dict[str, object]`**, built only from `discord_layout` (call it `L`). It returns exactly `embeds` (one embed), `components`, `allowed_mentions`, `nonce` and `enforce_nonce`.
   - **Blocks.** `block(text)` is ```` "```\n" + text.replace(L.BACKTICK, L.BACKTICK_STAND_IN) + "\n```" ````.
   - **The embed** has `title` `L.TITLE`, `color`, `fields` and `footer` `{"text": ...}`, and nothing else.
   - **Color.** `L.COLOR_SUSPECTED` when the extraction is suspicious. Otherwise `L.COLOR_UNREAD` when `verdict.extraction is None`. Otherwise `L.COLOR_NORMAL`.
   - **Fields,** each `{"name": ..., "value": ...}`, in this order:
     1. `L.FROM_NAME`: the block of `"<sender_name> <<address>>"`, or of the address alone when `sender_name` is empty. The address is `record.sender`, or `L.NO_ADDRESS` when empty.
     2. `L.SUBJECT_NAME`: the block of the subject, or of `L.NO_SUBJECT` when it is empty.
     3. `L.SUMMARY_NAME`:
        - the block of the summary
        - for a rejected verdict, the plain text `L.UNREAD_TEXT` with `{reason}` filled in
        - for any other verdict with no extraction, `L.EXPIRED_TEXT`
     4. `L.TASK_NAME`: the block of the title, only with an extraction whose title is non-empty.
     5. `L.WARNING_NAME`: the block of the suspicion reason, only when suspicious.
   - **Footer.** Joined by `L.FOOTER_JOIN`:
     - `L.PROVIDER_NAMES[record.provider]`
     - then `L.TRUSTED_TEXT` if trusted, else `L.VERIFIED_TEXT` if verified, else `L.UNVERIFIED_TEXT`
     - then `L.BULK_TEXT` if bulk
   - **Components.**
     - Row one has the buttons of `L.FIRST_ROW`; row two has those of `L.SECOND_ROW`, then the link button.
     - Each answer button is `{"type": 2, "style": <style>, "label": <label>, "custom_id": f"{L.PREFIX}:{action}:{item_id}"}`.
     - The link button is `{"type": 2, "style": L.LINK_STYLE, "label": L.OPEN_LABEL, "url": record.link}`, present only when `len(record.link) <= L.LINK_LIMIT`.
     - Each row is `{"type": 1, "components": [...]}`.
   - `allowed_mentions` is `{"parse": []}`, `nonce` is `item_id[:L.NONCE_LENGTH]`, and `enforce_nonce` is `True`.

8. **`src/mailroom/discord_post.py`.**
   - `TIMEOUT_SECONDS = 30.0`.
   - `DiscordUnavailable(Exception)`, built as `DiscordUnavailable(detail)` with text `discord unavailable (<detail>)` and raised `from None`.
   - `PostReport`, a `@dataclass(frozen=True)`: `posted: int`, `waiting: int`, `stopped: str`.
   - `open_discord_http() -> httpx.Client` returns `httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)`.

9. **`post_pending(store: Store, settings: Settings, http: httpx.Client) -> PostReport`.**
   1. An empty `settings.discord_channel_id` raises `DiscordUnavailable("not configured")` before anything else.
   2. `store.queue_notified()`, then `store.pending_posts()`. With none pending, return `PostReport(0, 0, "")` without reading the Keychain.
   3. Read the token once with `keychain.get_secret(L.TOKEN_NAME)`. Its errors propagate.
   4. For each pending post, in order:
      - Build `checkpoint_message(record, verdict, post.item_id)` from `store.get` and `store.triage`.
      - Send it with `http.post(f"{L.API_URL}/channels/{channel}/messages", json=..., headers=...)`. The headers are `Authorization: Bot <token>` and `User-Agent: L.USER_AGENT` with `mailroom.__version__` filled in.
      - On a 200 whose JSON has a string `id`, call `store.mark_posted(post.item_id, id)`.
      - Otherwise stop and return `PostReport(<posted so far>, <this and every later pending post>, <stopped>)`, where `stopped` is `"network"` for any `httpx.TransportError`, the status number as text for a non-200, and `"response"` for a 200 without a string `id`.
   5. Return `PostReport(<posted>, 0, "")`.

   It never sleeps, retries within a call, edits or deletes a message, or puts the token in an error.

10. **Critical modules.** `scripts/critical_modules.txt` (given) lists `checkpoint.py` and `discord_post.py`.

11. **Progress entry** for `## Phase 1h: Discord posting (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/schema.py` | Adds migration 5, the `posts` table |
| `src/mailroom/discord_layout.py` | The message's fixed text, colors, buttons, ids and limits |
| `tests/fakes.py` | Adds `FakeDiscord` |
| `tests/integration/test_store.py`, `tests/integration/test_store_sync.py` | Schema version asserts now expect 5 |
| `tests/unit/test_checkpoint.py` | 11 tests (requirement 7) |
| `tests/unit/test_config_discord.py` | 5 tests (requirement 6) |
| `tests/integration/test_store_posts.py` | 4 tests (requirements 2 to 5) |
| `tests/integration/test_discord_post.py` | 10 tests (requirements 8 and 9) |
| `scripts/critical_modules.txt` | Adds `checkpoint.py` and `discord_post.py` |
| `docs/verification/probe-01h.py` | The verifier's probe |

Given test count: **30** in the four new files.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_discord_post_more.py` and `tests/integration/test_store_posts_more.py` (and `tests/unit/test_checkpoint_more.py` if needed), never by changing a given test, for at least:
- `open_discord_http()`'s timeout, `trust_env` and `follow_redirects`
- a 200 whose body is not JSON (`stopped="response"`)
- a 401 (`stopped="401"`) leaving every post queued
- `pending_posts()` on an empty database, and `post()` for an unknown key

## Scope

| Path | Change |
|---|---|
| `src/mailroom/store.py` | add `Post`, `queue_notified`, `pending_posts`, `post`, `mark_posted` |
| `src/mailroom/config.py` | add `discord_channel_id` and `DISCORD_CHANNEL_MESSAGE` |
| `src/mailroom/checkpoint.py` | create |
| `src/mailroom/discord_post.py` | create |
| `tests/integration/test_discord_post_more.py` | create |
| `tests/integration/test_store_posts_more.py` | create |
| `tests/unit/test_checkpoint_more.py` | create, only if coverage needs it |
| `docs/progress.md` | append your entry |

## Out of scope

- **Receiving.** Button presses, the Gateway, interactions, the owner's user id, Show full text, Edit title (1i), and slash commands (1j).
- **Changing messages.** Editing, deleting or replying to a posted message; marking it answered.
- **Busy hours and follow-ups.** Digests, the 20-an-hour count, the 30-minute follow-up.
- **Other changes.** Sleeping on `retry_after`, retries within a call, a CLI command, a poll loop, logging, a Discord library, any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Email text leaves the machine only as the design allows**: the sender, subject, summary, title and spam reason, in code blocks. Never the body or the authentication results.
- **Email-derived strings are untrusted**: inside code blocks, with backticks replaced, no mentions parsed, and never in the embed's title or footer.
- **Sends are retry-safe**: keyed by the item's nonce, recorded only after Discord's 200, and a failed send stays queued.
- **Secrets come only from the Keychain** (`discord.bot-token`), read only when there is something to post, and never put in an error, a log or a report.
- **Network**: only `https://discord.com/api/v10`, through the injected client. Tests reach it only through `FakeDiscord`; never post to a real Discord.
- **Time and ids through the modules**: `clock.now()` and `ids.new_id()`, never imported by name.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 30 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/unit/test_checkpoint.py tests/unit/test_config_discord.py tests/integration/test_store_posts.py tests/integration/test_discord_post.py --no-cov -q` | `30 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/checkpoint.py,src/mailroom/discord_post.py,src/mailroom/store.py,src/mailroom/config.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1h: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1h` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_checkpoint.py tests/unit/test_config_discord.py tests/integration/test_store_posts.py tests/integration/test_discord_post.py scripts/critical_modules.txt docs/verification/probe-01h.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|websockets|discord)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request|(import|from) urllib([^.A-Za-z_]|$)' -- src
git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py' ':!src/mailroom/discord_post.py'
git grep --untracked -n -E 'discord\.com|discordapp' -- src ':!src/mailroom/discord_layout.py'
git grep --untracked -n -E '\.(patch|put|delete)\(|"(PATCH|PUT|DELETE)"|webhooks|/interactions|gateway' -- src/mailroom/discord_post.py src/mailroom/checkpoint.py
git grep --untracked -n -E 'body_text|authentication_results' -- src/mailroom/checkpoint.py src/mailroom/discord_post.py
git grep --untracked -n -E 'sleep\(|while |retry_after' -- src/mailroom/discord_post.py
git grep --untracked -n -E 'raise [A-Za-z]+\(f|raise [A-Za-z]+\([a-z_]*(token|error|response)' -- src/mailroom/discord_post.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/checkpoint.py src/mailroom/discord_post.py src/mailroom/store.py src/mailroom/config.py
```
