# Phase 1j: Discord Gateway

## Goal

Receive button presses. `run_gateway` holds a websocket to Discord's Gateway: it identifies with the bot token, heartbeats on Discord's schedule, and hands each `INTERACTION_CREATE` to 1i's `handle_interaction`. It resumes after a drop, identifies again when the session has ended, and waits longer after each failed try. It stops with a fixed error on a close Discord says not to retry, such as a revoked token. It adds the `websockets` library and connects only to `*.discord.gg`. Commands are 1k; 1l runs everything as one service.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 490, the tests Phase 1i left passing.

Install first (requirement 1). Then Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_gateway.py --ignore=tests/unit/test_gateway_open.py` must show `490 passed`. The ignored files import `mailroom.gateway`, which you create.

## Facts

From Discord's reference (Gateway; Opcodes and Status Codes), and websockets 17.3 on this machine.

- **Payloads** are JSON text `{"op", "d", "s", "t"}`; `s` and `t` are set on Dispatches (op 0). The address is `wss://gateway.discord.gg/?v=10&encoding=json`.
- **The handshake.**
  - The server first sends Hello (op 10) with `heartbeat_interval` in milliseconds.
  - The client sends Identify (op 2: `token`, `intents`, `properties` with `os`, `browser`, `device`), or Resume (op 6: `token`, `session_id`, `seq`).
  - READY carries `session_id` and `resume_gateway_url`, which is where to resume, with the same version and encoding. A successful resume gets RESUMED.
  - Interactions are tied to no intent and always arrive, so intents can be 0.
- **Heartbeats.**
  - The first comes after `heartbeat_interval * jitter` (a random value from 0 to 1), then one every interval. Each is `{"op": 1, "d": <last s, or null>}`, and the server answers with an ACK (op 11).
  - If the server sends op 1, heartbeat at once.
  - No ACK before the next heartbeat means the connection is dead: close with any code but 1000 or 1001, then resume.
- **Other opcodes.** Reconnect (op 7) means resume. Invalid Session (op 9) with `d` false means identify again; with `d` true, resume.
- **Closes.**
  - 4004, 4010, 4011, 4012, 4013 and 4014 mean don't reconnect.
  - 1000 and 1001 end the session.
  - Any other code allows a resume.
- **Limits.** 120 sends per 60 seconds per connection, and 1000 Identifies a day.
- **websockets 17.3.**
  - `websockets.sync.client.connect(uri, *, user_agent_header, proxy=True, compression="deflate", open_timeout=10, ping_interval=20, max_size=1048576, logger=None, ...)` returns a `ClientConnection`.
  - `proxy=True` uses the system proxy.
  - `recv(timeout)` raises `TimeoutError`, or `ConnectionClosed` once closed. After a close, `close_code` holds the code. `send(str)` sends text, and `close(code)` closes.
  - Connecting can raise `OSError`, `TimeoutError` or a `websockets.exceptions.WebSocketException`. The package has no dependencies.
- **websockets logs frames.** When its logger is enabled for DEBUG, websockets logs every frame's text, so the Identify frame, with the token, would appear in any debug log. A logger whose `isEnabledFor` is always false keeps it silent.
- **The fake.** `tests.fakes.FakeGateway` runs connections in memory on a simulated clock (`now`, `sleep`, `done`). It behaves as above, with scripted `plans` per connection, and checks every frame the client sends (see its docstring).

## Owner's decisions

- **websockets**, the one new dependency, with the protocol written here and tested against a fake Gateway.
- **Split.** 1j connects and delivers presses; 1k adds `/trust`, `/untrust` and `/trusted`; 1l runs the service.
- **Stop and report** on a fatal close, such as a revoked token, with a fixed error naming the close code. Ordinary drops reconnect with backoff.

## Architect's decisions

- **One thread, no async.** The loop waits in `recv` at most 1 second at a time, so heartbeats go out on time and a stop is noticed quickly. 1l decides how it runs beside the poll loop.
- **Only `*.discord.gg`.** The fixed address, and a `resume_gateway_url` only if it is `wss` on a `.discord.gg` host with no port, user or path. An address outside that is never connected; the client identifies again at the fixed address instead.
- **Backoff** before every reconnect: 1, 2, 4, 8, 16, 32, then 60 seconds. It starts again at 1 after each READY or RESUMED.
- **A failed reply doesn't stop the listener.** `DiscordUnavailable` from the handler is swallowed (the answer is already recorded, as 1i chose). Any other error propagates for 1l to deal with.
- **Time, waiting and chance are injected**: `clock.now()` for the schedule, a `sleep` argument for backoff, an `rng` argument for jitter. Tests run on the fake's clock.
- **Quiet and direct.** No proxy, no compression, websockets' own pings off (Discord's heartbeat does that job), frames capped at 1 MiB, and a logger that can never log. The token goes only into Identify and Resume frames.
- **The protocol constants are given** in `src/mailroom/gateway_protocol.py`.
- **Critical modules**: `gateway.py` (the token, where it connects, and that presses are never lost silently).

## Examples in plain words

- The service connects, identifies, and heartbeats every 41 seconds or so; you press Not a task, and within a moment the card updates.
- Wi-Fi drops for a minute: the service waits 1, 2, 4… seconds between tries, then resumes the same session, and presses made meanwhile still arrive.
- You reset the bot's token in Discord's developer portal: the service stops with "gateway stopped (4004)" instead of retrying all day.

## Verify before building

With a test bot in your private server:
- Identify with intents 0 still delivers `INTERACTION_CREATE` for button presses.
- The connection holds for an hour on the Mac, and a resume after turning Wi-Fi off and on works.

## Requirements

1. **Install.** `pyproject.toml` (given) adds `websockets>=17.3,<18`. Run `.venv/bin/python -m pip install -e '.[dev]'`; this needs the network to reach PyPI, and nothing else in this phase does. websockets 17.3 may already be installed. Install nothing else.

2. **`src/mailroom/gateway.py`: the address check.**
   - `GATEWAY_URL_MESSAGE = "refused a Gateway address outside discord.gg"`.
   - `gateway_url_allowed(url: str) -> bool` is `True` only when `urllib.parse.urlsplit(url)` meets all of these:
     - scheme `wss`
     - a lower-cased hostname ending in `P.HOST_SUFFIX` (`P` is `gateway_protocol`, `L` is `discord_layout`)
     - no port, user name or password
     - a path of `""` or `"/"`
     - a query of `""` or `v=10&encoding=json`
     - no fragment

     A `ValueError` while reading it gives `False`.

3. **`open_gateway(url: str) -> ClientConnection`.**
   - An address `gateway_url_allowed` refuses raises `ValueError(GATEWAY_URL_MESSAGE)` before anything else.
   - Otherwise it returns `websockets.sync.client.connect(url, ...)`, called through the module (`import websockets.sync.client`), with exactly:
     - `user_agent_header` = `L.USER_AGENT` with `mailroom.__version__`
     - `proxy=None`, `compression=None`, `ping_interval=None`
     - `open_timeout=P.OPEN_TIMEOUT_SECONDS`, `max_size=P.MAX_FRAME_BYTES`
     - `logger`: a `logging.LoggerAdapter` whose `isEnabledFor` always returns `False`

4. **`GatewayStopped(Exception)`**, built as `GatewayStopped(code)`, with text `gateway stopped (<code>)` and raised `from None`.

5. **`run_gateway(store: Store, settings: Settings, http: httpx.Client, *, connect=open_gateway, sleep=time.sleep, rng=random.SystemRandom(), stop=lambda: False) -> None`: setup and reconnecting.**
   1. An empty `discord_owner_id` or `discord_channel_id` raises `DiscordUnavailable("not configured")`. Then the token is read once with `keychain.get_secret(L.TOKEN_NAME)`, and its errors propagate. Both happen before any connection.
   2. It repeats until `stop()` is true:
      - Before every connection but the first, `sleep(P.BACKOFF_SECONDS[min(tries, 6)])` and add 1 to `tries`. `tries` goes back to 0 at each READY and RESUMED.
      - Connect with `connect(<resume address>)` when it holds a session and a resume address, else `connect(P.GATEWAY_URL)`.
      - An `OSError`, `TimeoutError` or `websockets.exceptions.WebSocketException` while connecting goes round again.
   3. When `stop()` is true during a session, it closes with `1000` and returns.

6. **A session.**
   1. **Hello.** Wait up to `P.OPEN_TIMEOUT_SECONDS` for Hello, and take `heartbeat_interval`. Without it, close with `P.RESUME_CLOSE` and reconnect.
   2. **Open.** With a session, send `{"op": 6, "d": {"token", "session_id", "seq"}}`. Otherwise forget any `seq`, and send `{"op": 2, "d": {"token": <token>, "intents": P.INTENTS, "properties": P.PROPERTIES}}`.
   3. **Schedule.** The first heartbeat is due `heartbeat_interval * rng.random()` milliseconds after Hello arrived (by `clock.now()`), and each later one an interval after the one before it.
   4. **Loop.** Check `stop()`. At or after the due time:
      - If the last heartbeat has had no ACK, close with `P.RESUME_CLOSE` and resume.
      - Otherwise send `{"op": 1, "d": <seq>}` and wait for an ACK.

      Then `recv(timeout=min(<seconds until due>, P.POLL_SECONDS))`, where a `TimeoutError` just loops. Every frame with a non-null `s` sets `seq`.
   5. **By opcode:**
      - **Dispatch** (op 0):
        - `READY` stores `session_id` and the resume address: `resume_gateway_url.rstrip("/") + "/" + P.QUERY` when `gateway_url_allowed` accepts it, else none. It resets `tries`.
        - `RESUMED` resets `tries`.
        - `INTERACTION_CREATE` calls `handle_interaction(d, store, settings, http)`; a `DiscordUnavailable` it raises is swallowed.
        - Every other event is ignored.
      - **Heartbeat** (op 1): send a heartbeat at once, without moving the schedule.
      - **ACK** (op 11): the heartbeat is acknowledged.
      - **Reconnect** (op 7): close with `P.RESUME_CLOSE`, and resume.
      - **Invalid Session** (op 9): close with `P.RESUME_CLOSE`. Resume when `d` is true; otherwise forget the session.
   6. **Closed.** `ConnectionClosed` from `recv` or `send` reads `close_code`:
      - a code in `P.FATAL_CLOSES` raises `GatewayStopped(code)`
      - a code in `P.SESSION_ENDING_CLOSES` forgets the session
      - anything else resumes

7. **Critical modules.** `scripts/critical_modules.txt` (given) lists `gateway.py`.

8. **Progress entry** for `## Phase 1j: Discord Gateway (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `pyproject.toml` | Adds `websockets>=17.3,<18` |
| `src/mailroom/gateway_protocol.py` | The Gateway's address, opcodes, properties, close codes, backoff and limits |
| `tests/fakes.py` | Adds `FakeGateway` and `FakeGatewayConnection` |
| `tests/integration/test_gateway.py` | 23 tests (requirements 5 and 6) |
| `tests/unit/test_gateway_open.py` | 12 tests (requirements 2 and 3) |
| `scripts/critical_modules.txt` | Adds `gateway.py` |
| `docs/verification/probe-01j.py` | The verifier's probe |

Given test count: **35** in the two new files, from 15 test functions.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests in `tests/integration/test_gateway_more.py`, never by changing a given test, for at least:
- a connection with no Hello within the time limit (closed with 4000, then a resume)
- `ConnectionClosed` raised by a `send`
- a frame that is not JSON, and an op the client does not know (ignored)
- `stop()` already true at the start (no connection)
- a `WebSocketException` while connecting (backoff)

## Scope

| Path | Change |
|---|---|
| `src/mailroom/gateway.py` | create |
| `tests/integration/test_gateway_more.py` | create |
| `docs/progress.md` | append your entry |

## Out of scope

- **Commands.** Registering or handling `/trust`, `/untrust`, `/trusted` (1k).
- **Running it.** Threads, the poll loop, a CLI command, launchd (1l).
- **More Gateway.** Sharding, compression, zlib, ETF, presence updates, guild events, `GET /gateway/bot`, caching sessions across restarts.
- **Other changes.** Logging anything, a Discord library, asyncio, changing the interaction handler, any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Secrets** (`AGENTS.md`): the token is read from the Keychain once and appears only in Identify and Resume frames: never in an address, an error, a log or a report. websockets' logger must stay unable to log.
- **Network**: only `wss://*.discord.gg`, with no proxy. Tests reach it only through `FakeGateway`; never connect to the real Gateway.
- **Nothing is lost silently**: a press that fails to answer is still recorded (1i); a fatal close stops with its code for 1l to report.
- **No retry storms**: the backoff caps at 60 seconds, and heartbeats stay far below Discord's 120 sends a minute.
- **Time through the module**: `clock.now()`, never imported by name, and no `time.time()`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 35 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_gateway.py tests/unit/test_gateway_open.py --no-cov -q` | `35 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/gateway.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase 1j: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 1j` | `Reports OK.` |
| `.venv/bin/python -m pip show websockets` | `Version: 17.` and `Requires:` empty |
| `git diff HEAD --stat -- pyproject.toml src/mailroom/gateway_protocol.py tests/fakes.py tests/integration/test_gateway.py tests/unit/test_gateway_open.py scripts/critical_modules.txt docs/verification/probe-01j.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E '(import|from) (socket|ssl|imaplib|smtplib|requests|aiohttp|asyncio|threading|discord)([^A-Za-z_]|$)|(import|from) http([^.A-Za-z_]|$)|http\.client|urllib\.request' -- src
git grep --untracked -n -E 'websockets' -- src ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py' ':!src/mailroom/discord_post.py' ':!src/mailroom/interactions.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E '[./]discord\.gg|discord\.gg[/:]' -- src ':!src/mailroom/gateway_protocol.py'
git grep --untracked -n -E 'ws://|proxy=True|time\.sleep\(|time\.time\(|time\.monotonic' -- src/mailroom/gateway.py
git grep --untracked -n -E 'logging\.(basicConfig|getLogger\(\)|debug|info|warning|error|exception|critical)|print\(' -- src/mailroom/gateway.py
git grep --untracked -n -E 'raise [A-Za-z]+\(f|raise [A-Za-z]+\([a-z_.]*(token|error|frame|payload|text|reason)' -- src/mailroom/gateway.py
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|uuid|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/gateway.py
```
