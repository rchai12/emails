# Phase 1k: Discord commands

## Goal

Add five slash commands for managing senders from Discord: `/trust <address>`, `/untrust <address>` and `/trusted`, as designed, plus `/unmute <address>` and `/muted`, so a muted sender can be seen and let back in. `mailroom discord-commands` registers them once, in your server only, hidden from members without admin rights. The Gateway (1j) already delivers their uses, and `handle_interaction` now answers them privately. Only you can use them, in the service's channel. 1l runs everything as one service.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 540, the tests Phase 1j left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_commands.py --ignore=tests/integration/test_register_commands.py --ignore=tests/unit/test_config_guild.py` must show `540 passed`. The ignored files import names you create, or test behaviour you add.

## Facts

From Discord's reference (Application Commands; Application; Receiving and Responding):

- **Registering.** `PUT /applications/<application id>/guilds/<guild id>/commands` replaces all of a server's commands with the list sent, and returns 200 with them. `GET /applications/@me` returns the bot's application, with its `id`. Both use the bot's `Authorization`. Discord allows 200 command creates per day per server.
- **A slash command** has:
  - `type` 1
  - a lower-case `name` of 1 to 32
  - a `description` of 1 to 100
  - up to 25 `options` (a string option is `type` 3, with `name`, `description`, `required`, `min_length` and `max_length`)
  - `default_member_permissions`; `"0"` hides it from everyone but admins
- **A use** is interaction `type` 2, with `data.name` and `data.options`, a list of `{"name", "type", "value"}`. It takes reply type 4, 5 or 9, not 6 or 7.
- **The fake.** `FakeDiscord` now answers `GET /applications/@me` and the command `PUT`, checking both against the rules above. `command(name, address)` builds a use.

## Owner's decisions

- **Five commands**: the designed three, plus `/unmute` and `/muted`. There is no `/mute`; the button does that.
- **Your server only**, hidden from members without admin rights, and every use still checked against your user id.
- **A setup command** registers them; the service never registers on its own.

## Architect's decisions

- **The command list is given** in `discord_layout.COMMANDS`, with the reply texts.
- **Replies are private** (flag 64), with mentions off and addresses in code blocks, backticks replaced, like every other reply.
- **Someone else, or another channel,** gets the private `NOT_YOURS_TEXT`. A command can't be acknowledged silently the way a button can. A command name that isn't ours gets no reply, as in 1i.
- **Addresses** follow the store's rule: lower-cased, one `@`, no spaces, at most 254 characters. Trust replaces a mute, since a sender has one status. `/untrust` and `/unmute` remove only their own status.
- **Long lists** show as many addresses, in order, as fit in 1,800 characters, then "...and N more.", keeping the reply under Discord's 2,000.
- **The handler is split**: `commands.handle_command` decides the reply text, and `interactions.handle_interaction` checks who sent it and sends the reply.
- **Settings**: `MAILROOM_DISCORD_GUILD_ID`, your server's id.
- **Critical modules**: `commands.py` (who is trusted or muted, and what goes back to Discord).

## Examples in plain words

- You type `/trust Sam@Example.TEST`: a private reply says "Added to your trusted senders: sam@example.test".
- You type `/unmute news@example.test` for a sender you muted: their mail reaches triage again.
- `/untrust` on someone who was muted, not trusted: "Not on your trusted senders", and they stay muted.
- Someone else in the server finds `/muted`: a private "Only the owner can use this here."; they see no list.

## Verify before building

In your private server: after `mailroom discord-commands`, the five commands appear for you at once, are hidden from a member without admin rights, and each answers privately.

## Requirements

1. **`config.py`: `discord_guild_id: str = ""`** (`MAILROOM_DISCORD_GUILD_ID`). A non-empty value must match `[0-9]{17,20}`, else `get_settings` raises `ConfigError` with `DISCORD_GUILD_MESSAGE = "MAILROOM_DISCORD_GUILD_ID must be a Discord server id (17 to 20 digits)"`, never the value.

2. **`src/mailroom/commands.py`: `register_commands(settings: Settings, http: httpx.Client) -> int`** (call the layout `L`).
   1. An empty `discord_guild_id` raises `DiscordUnavailable("not configured")` before anything else. Then the token is read with `keychain.get_secret(L.TOKEN_NAME)`, and its errors propagate.
   2. Both requests carry `Authorization: Bot <token>` and `User-Agent: L.USER_AGENT`, with the version filled in.
   3. `GET f"{L.API_URL}/applications/@me"` must answer 200 with a string `id`.
   4. Then `PUT f"{L.API_URL}/applications/{id}/guilds/{discord_guild_id}/commands"` with `json=list(L.COMMANDS)` must answer 200 with a JSON list. Return its length.
   5. Failures raise `DiscordUnavailable`, all `from None`, with:
      - `"network"` for an `httpx.TransportError`
      - the status as text for a status other than 200
      - `"response"` for a body of the wrong shape

3. **`handle_command(event: dict[str, object], store: Store) -> tuple[str, str]`** returns (outcome, reply text) for one of our commands, called only after the checks in requirement 4. `block` is the card's (backticks replaced). The address is the string `value` of the option named `L.ADDRESS_OPTION`, lower-cased.
   - **An address command** (`trust`, `untrust`, `unmute`) whose option is missing, isn't a string, or isn't one the store accepts (it raises `ValueError`) gives `("bad-address", L.BAD_ADDRESS_TEXT)`, with nothing changed.
   - **`trust`**: `set_sender_status(address, "trusted")`. Gives `("trusted", L.TRUSTED_REPLY + "\n" + block(address))`.
   - **`untrust`**:
     - when the address is trusted, `set_sender_status(address, None)`, giving `("untrusted", L.UNTRUSTED_REPLY + ...)`
     - otherwise `("unchanged", L.NOT_TRUSTED_REPLY + ...)`
   - **`unmute`**: the same, with `"muted"`, `L.UNMUTED_REPLY`, `L.NOT_MUTED_REPLY` and `"unmuted"`.
   - **`trusted` and `muted`**: `store.senders(<kind>)`.
     - None gives `("listed", L.NONE_TRUSTED)` or `L.NONE_MUTED`.
     - Otherwise take the longest leading run whose addresses joined by `"\n"` are at most `L.LIST_LIMIT` characters. The text is `f"{L.TRUSTED_LIST or L.MUTED_LIST}\n" + block(<the run>)`, followed by `"\n" + L.MORE_TEXT.format(count=<the rest>)` when any are left out. The outcome is `"listed"`.

4. **`interactions.handle_interaction` routes type 2.** After the existing settings check:
   1. When `data.name` is not one of `L.COMMANDS`' names, return `"ignored"`, with no request.
   2. A user other than `discord_owner_id`, or a `channel_id` other than `discord_channel_id`, gets a private `L.NOT_YOURS_TEXT`. Return `"refused"`, with nothing changed.
   3. Otherwise send `handle_command`'s text as a private reply (1i's form: type 4, flag 64, mentions off), and return its outcome.

   Presses and submissions are unchanged.

5. **`cli.py`: `mailroom discord-commands`.**
   - It calls `commands.register_commands(get_settings(), http)` with `http` from `discord_post.open_discord_http()`, called through the module and closed afterwards.
   - It prints `L.REGISTERED_TEXT` with the count.
   - On a `DiscordUnavailable`, `KeychainError` or `ConfigError`, it prints the error's text to stderr and exits 1.

6. **Critical modules.** `scripts/critical_modules.txt` (given) lists `commands.py`.

7. **Progress entry** for `## Phase 1k: Discord commands (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `src/mailroom/discord_layout.py` | Adds `COMMANDS`, `ADDRESS_OPTION` and the command reply texts |
| `tests/fakes.py` | `FakeDiscord` gains the application and command routes and `command()`; replies to a command allow types 4, 5 and 9 only |
| `tests/integration/test_commands.py` | 21 tests (requirements 3 and 4); one already passes, pinning that a foreign command gets no reply |
| `tests/integration/test_register_commands.py` | 8 tests (requirements 2 and 5) |
| `tests/unit/test_config_guild.py` | 4 tests (requirement 1) |
| `scripts/critical_modules.txt` | Adds `commands.py` |
| `docs/verification/probe-01k.py` | The verifier's probe |

Given test count: **33** in the three new files, from 19 test functions.

`docs/verification/probe-01j.py` also changed: it no longer schedules server closes of 4008, which it read as a client fault (the 1j review's note). It is not this phase's file.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_commands_more.py`, never by changing a given test, for at least:
- `GET /applications/@me` answering without a string `id`, and the `PUT` answering something other than a list (`"response"`)
- an address option whose value isn't a string
- the CLI reporting a missing token (`secret not found: discord.bot-token`, exit 1)
- a command used by `user.id` instead of `member` (a DM)

## Scope

| Path | Change |
|---|---|
| `src/mailroom/config.py` | add `discord_guild_id` and `DISCORD_GUILD_MESSAGE` |
| `src/mailroom/commands.py` | create |
| `src/mailroom/interactions.py` | route type 2 as in requirement 4 |
| `src/mailroom/cli.py` | add `discord-commands` |
| `tests/integration/test_commands_more.py` | create |
| `docs/progress.md` | append your entry |

## Out of scope

- **Running it.** Registering at start, the poll loop, threads, launchd (1l).
- **More commands.** `/mute`, `/pending`, autocomplete, options other than the address, global commands, per-command permissions.
- **Other changes.** Changing the Gateway, the buttons or the cards; logging; a Discord library; any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Nothing happens for anyone but you** (`AGENTS.md`): every use is checked against your user id and the channel before anything is read or changed.
- **Typed text is untrusted**: an address is checked by the store's rule and shown only inside a code block with backticks replaced, with mentions off.
- **Secrets**: the token is read from the Keychain only by `register_commands`, and never printed; the CLI prints only fixed text and error messages that hold no secret.
- **Network**: only `https://discord.com/api/v10`, through the injected client. Tests reach it only through `FakeDiscord`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 32 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_commands.py tests/integration/test_register_commands.py tests/unit/test_config_guild.py --no-cov -q` | `33 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/commands.py,src/mailroom/interactions.py,src/mailroom/config.py,src/mailroom/cli.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1k: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1k` | `Reports OK.` |
| `git diff HEAD --stat -- src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_commands.py tests/integration/test_register_commands.py tests/unit/test_config_guild.py scripts/critical_modules.txt docs/verification/probe-01k.py docs/verification/probe-01j.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|asyncio|threading|discord)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request' -- src
git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py' ':!src/mailroom/discord_post.py' ':!src/mailroom/interactions.py' ':!src/mailroom/gateway.py' ':!src/mailroom/commands.py'
git grep --untracked -n -E 'discord\.com|discordapp' -- src ':!src/mailroom/discord_layout.py'
git grep --untracked -n -E '\.(delete|patch)\(|/channels/|/global|applications/[^@{]' -- src/mailroom/commands.py
git grep --untracked -n -E 'from mailroom\.discord_post import .*open_discord_http' -- src/mailroom/cli.py
git grep --untracked -n -E 'get_secret|set_secret' -- src/mailroom/interactions.py src/mailroom/cli.py
git grep --untracked -n -E 'raise [A-Za-z]+\(f|raise [A-Za-z]+\([a-z_.]*(token|error|value|address|text|json)' -- src/mailroom/commands.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|uuid|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/commands.py src/mailroom/interactions.py src/mailroom/config.py src/mailroom/cli.py
```
