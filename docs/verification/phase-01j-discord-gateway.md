# Verification guide: Phase 1j (Discord Gateway)

Spec: `docs/phases/phase-01j-discord-gateway.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/gateway.py`
- `tests/integration/test_gateway_more.py`
- `grep -c "^## Phase 1j: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01j-discord-gateway.md pyproject.toml src/mailroom/gateway_protocol.py tests/fakes.py tests/integration/test_gateway.py tests/unit/test_gateway_open.py scripts/critical_modules.txt docs/verification/probe-01j.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 35.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 35 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_gateway.py tests/unit/test_gateway_open.py --no-cov -q` | `35 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/gateway.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1j: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1j` | `Reports OK.` |
| G6 | `.venv/bin/python -m pip show websockets` | `Version: 17.` and `Requires:` empty |
| G7 | `git diff HEAD --stat -- pyproject.toml src/mailroom/gateway_protocol.py tests/fakes.py tests/integration/test_gateway.py tests/unit/test_gateway_open.py scripts/critical_modules.txt docs/verification/probe-01j.py` | no output |
| G8 | `git status --short` | only the Scope paths |
| G9 | `.venv/bin/python -m pip list --format=freeze` | the packages before this phase plus `websockets==17.x` only |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `gateway.py` | Schedule the first heartbeat a full interval after Hello (no jitter) | `tests/integration/test_gateway.py::test_it_identifies_then_heartbeats_on_time_and_closes_when_stopped` | first beat at `10.3125` | first beat at `41.25` |
| S2 | `gateway.py` | Send every heartbeat with `d` null | `tests/integration/test_gateway.py::test_a_press_is_answered_and_other_events_are_ignored` | `(10.3125, 1, 3)` | `(10.3125, 1, None)` |
| S3 | `gateway.py` | Never treat a missing ACK as a dead connection | `tests/integration/test_gateway.py::test_a_lost_connection_resumes_after_a_second[no-ack]` | 2 connections | 1 connection (`ValueError` unpacking) |
| S4 | `gateway.py` | Treat close 1000 as resumable | `tests/integration/test_gateway.py::test_an_ended_session_identifies_again[closed-1000]` | second address `wss://gateway.discord.gg/?v=10&encoding=json` | `wss://gateway-us-east1-b.discord.gg/?v=10&encoding=json` |
| S5 | `gateway.py` | Leave 4004 out of the fatal set (resume instead) | `tests/integration/test_gateway.py::test_a_fatal_close_stops_with_its_code[4004]` | `GatewayStopped` | no exception |
| S6 | `gateway.py` | Never reset the backoff after READY | `tests/integration/test_gateway.py::test_failed_connections_back_off_and_a_session_resets_the_wait` | last wait `1` | last wait `60` |
| S7 | `gateway.py` | Check the host with `endswith("discord.gg")` | `tests/unit/test_gateway_open.py::test_only_discord_gateway_addresses_are_allowed[look-alike-name]` | `False` | `True` |
| S8 | `gateway.py` | Use `resume_gateway_url` without checking it | `tests/integration/test_gateway.py::test_a_resume_address_outside_discord_is_never_used` | second address the fixed one | `wss://gateway.discord.gg.evil.test/?v=10&encoding=json` |
| S9 | `gateway.py` | Pass `logger=logging.getLogger("websockets.client")` | `tests/unit/test_gateway_open.py::test_the_connection_is_direct_quiet_and_bounded` | `isEnabledFor` `False` | `True` |
| S10 | `gateway.py` | Let `DiscordUnavailable` from the handler propagate | `tests/integration/test_gateway.py::test_a_failed_reply_does_not_stop_the_listener` | runs to the end | `DiscordUnavailable` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01j.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks, beyond the given tests: 150 random chains of up to 7 troubles (refusals, drops with non-fatal codes, missing ACKs, Reconnect, Invalid Session either way, heartbeat requests, closes 1000 and 1001), sometimes ending in a fatal close, with random jitter and up to 11 presses mixed with other events. For each, the addresses, Identify-or-Resume choices, waits and the stop code must equal a model built from the plans alone; every delivered press gets one reply; heartbeats never lapse; the fake never closes for a bad frame, a wrong `seq` or too many sends; and the token never appears in an address.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | No other network library, no asyncio or threads | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|asyncio\|threading\|discord)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request' -- src` |
| Q2 | websockets only in the Gateway module | `git grep --untracked -n -E 'websockets' -- src ':!src/mailroom/gateway.py'` |
| Q3 | httpx only where a phase allowed it | `git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py' ':!src/mailroom/discord_post.py' ':!src/mailroom/interactions.py' ':!src/mailroom/gateway.py'` |
| Q4 | Gateway addresses only in the given constants | `git grep --untracked -n -E '[./]discord\.gg\|discord\.gg[/:]' -- src ':!src/mailroom/gateway_protocol.py'` |
| Q5 | No plain websocket, proxy, real sleeping or wall-clock time in the Gateway | `git grep --untracked -n -E 'ws://\|proxy=True\|time\.sleep\(\|time\.time\(\|time\.monotonic' -- src/mailroom/gateway.py` |
| Q6 | The Gateway module never logs or prints | `git grep --untracked -n -E 'logging\.(basicConfig\|getLogger\(\)\|debug\|info\|warning\|error\|exception\|critical)\|print\(' -- src/mailroom/gateway.py` |
| Q7 | No token, frame or reason text in an error | `git grep --untracked -n -E 'raise [A-Za-z]+\(f\|raise [A-Za-z]+\([a-z_.]*(token\|error\|frame\|payload\|text\|reason)' -- src/mailroom/gateway.py` |
| Q8 | No email text or token in logs elsewhere | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q9 | Time and ids only through `clock` and `ids` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|uuid\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q10 | Full coverage is earned, not excused | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/gateway.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Splitting the session into private helpers, or a small state class inside `gateway.py`.
- Computing the next heartbeat from the previous due time or from the send time, as long as the given times hold.
- Catching `ConnectionClosed` once around the whole session loop.
- Treating a Hello that is not op 10 as a dead connection (close with 4000, reconnect).
- The silent logger being a module-level instance or built per connection.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01j-discord-gateway.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1j`), then run `.venv/bin/python scripts/check_reports.py --phase 1j`; it must print `Reports OK.`
