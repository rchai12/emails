# Phase 4e: Validate Gateway input

## Goal

Malformed Gateway frames recover through the existing connection loop; malformed
interaction bodies cannot terminate the listener or reach business state. This
closes the input-shape portion of audit finding 1 and prepares finding 5's
dispatch boundary. Listener supervision belongs to 4f, not this phase.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is 1230, including the 18 workflow tests
added after Phase 4d's 1212. The source baseline is
`06a5fbaf5f87bcf22e738bcb0629990f01f6427d`; the finalized planning/given-file commit
made after this document supersedes it for the coder's clean start.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_gateway_input.py`
must show `1230 passed`. Nothing needs a missing-module stub. The new given file
already imports successfully and is excluded because its behavior is unbuilt.

## Facts

- Today's `_read_hello` indexes decoded JSON without shape validation; `_loop`
  catches only JSONDecodeError, then `_frame` calls `.get`. `_dispatch` indexes
  READY data and passes interaction data to an indexing handler. Existing client
  errors and missing database rows are different failures and remain out of scope.
- Discord documents hello opcode 10 with a millisecond interval, and resume using
  the saved session id, resume address and last dispatch sequence. See the
  [official Gateway reference](https://github.com/discord/discord-api-docs/blob/main/developers/events/gateway.mdx)
  and [event shapes](https://github.com/discord/discord-api-docs/blob/main/developers/events/gateway-events.mdx).
- [Official interaction responses](https://github.com/discord/discord-api-docs/blob/main/developers/interactions/receiving-and-responding.mdx)
  distinguish component/modal deferred updates from command replies. A malformed
  slash command must not receive a component-only acknowledgement.
- Offline standard-library spike: JSON null/list/scalar decode successfully but
  are not dictionaries; booleans also compare equal to integers. timedelta accepts
  zero/negative/bool values; NaN, infinity and very large intervals fail conversion.
  Validate the interval before scheduling, without copying library error text.
- The old `test_a_bad_frame_and_an_unknown_op_are_ignored` pins the former bad-JSON
  policy. Its given replacement retains only the valid unknown-op guard. No
  production code or other earlier test is provided/changed by the architect.
- At specification time, given collection is 83 cases: 68 new and 15 in the edited
  earlier file. Against predecessor code: 62 fail, 21 pass. Six new passing cases
  are guards (custom-id, user-id and channel cases; unknown/bool kinds; unexpected
  handler failure propagation), not evidence that the feature is already built.

## Owner's decisions

- **2026-11-17:** reconnect malformed Gateway frames through existing backoff and
  resume, rather than ignore them on the current connection.
- **2026-11-17:** safely acknowledge malformed interaction bodies when callback
  addressing is valid, then ignore them without state changes.

## Architect's decisions

- Preserve `run_gateway` and `handle_interaction` signatures and existing valid
  behavior. Private helpers inside the two Scope modules suffice; no dependency,
  schema migration, new module, retry loop or service lifecycle change.
- Shape checks allow extra Discord fields; this is not the model's closed schema.
  Validate only the boundaries below, preserving existing semantic refusals for
  bad titles, addresses, unknown actions and expired cards.
- Invalid callback addressing or an unknown/missing interaction kind cannot be
  safely acknowledged and is ignored with no HTTP call. Known kinds are 2, 3, 5.
- No new diagnostic logging or exception messages echo wire text or tokens.

## Requirements

1. **Decode and frame shape.** Reject invalid JSON/UTF-8, JSON decode recursion or
   integer-conversion limit failures, and non-object top levels. `op` is an exact
   nonnegative int, never bool/float/string. A dispatch (`op=0`) requires an exact
   nonnegative integer `s`, a nonempty string `t` and object `d`. Non-dispatch
   `s`/`t` may be absent or null, not populated. Unknown well-shaped opcodes and
   dispatch names remain ignored. Do not coerce malformed fields with str/int.
2. **Hello.** Before identify/resume, require opcode 10, object `d`, and numeric
   heartbeat_interval of exact int/float type (not bool), finite and positive.
   Its timedelta must be positive and representable, and schedulable relative to
   the received clock time; reject overflow or a value rounded to zero. Malformed
   hello closes with 4000 and reconnects with existing backoff, sending nothing
   on that connection. Keep the last valid resume state if one exists. A normal
   first hello and a valid fractional interval continue to work. Timeout behavior
   is unchanged. ConnectionClosed before hello uses the same fatal/session-ending/
   resumable close policy as after hello, rather than escaping as a raw close.
3. **Session validation before state.** A malformed active frame closes with 4000
   and returns to backoff/resume, preserving the last accepted session/sequence.
   Validate READY's nonempty string session_id and resume_gateway_url before
   changing state; a string URL outside the existing allowlist still clears resume
   capability without connecting there, as earlier tests require. INVALID_SESSION
   requires boolean `d`. Only accepted dispatches update sequence. Preserve
   heartbeats, ACKs, existing reconnect/session-reset behavior, fatal-code
   GatewayStopped and token privacy. Never classify an arbitrary handler/store
   exception as malformed JSON or silently swallow it; 4f owns supervision.
4. **Interaction envelope.** `handle_interaction` returns `ignored` with no store
   access and no HTTP request for non-objects, missing/unknown/non-integer kinds,
   or unsafe callback addressing. For known kinds, id is a nonempty ASCII decimal
   string at most 20 characters; token is a nonempty string. Treat it as opaque: percent-encode it as one
   UTF-8 path segment (quote with safe=""), never interpolate its delimiters into
   the callback URL or coerce a non-string token. Empty/non-string tokens are
   unaddressable. Preserve the fixed Discord API origin and callback suffix.
   Configuration's existing not-configured refusal still takes precedence.
5. **Interaction body before business state.** For known kinds with safe callback
   addressing, require object data, nonempty string channel_id and presser id.
   If member is present it must contain object user with that id; never fall back
   to a top-level user when member is malformed. Without member use top-level
   object user. Kinds 3/5 need string custom_id. Kind 2 needs string name; options
   may be absent/null or a list of objects, with name a string when present.
   Leave option value validation to the existing bad-address behavior. Kind 5
   needs a components list of objects, each with object component containing
   string custom_id/value. An empty components list or a missing title field
   remains the existing semantic bad-title refusal, not a new shape error.
   Do not read or write the store until shape checks have passed. Existing owner
   and channel checks remain mandatory before any action or email-derived reply.
6. **Safe acknowledgement.** A body failing requirement 5 returns `ignored`.
   For kind 3/5 send exactly `{"type": 6}`. For kind 2 send exactly
   `{"type": 4, "data": {"content": "This interaction is unavailable.", "flags": 64, "allowed_mentions": {"parse": []}}}`.
   One callback at most; no input is echoed and no card/task/sender state changes.
   Callback failure retains the existing DiscordUnavailable contract: direct
   callers see it, and Gateway dispatch catches it and continues. A following
   valid owner press works. Do not add re-acknowledgement or callback retries.
7. **Compatibility and privacy.** Keep existing valid component/modal/command
   replies, private full text, unknown-action behavior, direct-message identity,
   duplicate-press handling and least-access provider behavior. No broad Exception
   catcher around the dispatcher, real connections, Keychain reads in tests,
   telemetry, new logs or raw exception text. Time remains through clock.now.
8. **Progress entry** for `## Phase 4e: Validate Gateway input (YYYY-MM-DD)` at the
   end of docs/progress.md, including actual test counts and public names.

## Given files

Committed with the finalized spec before coding; never change them as the coder.

| File | What it is |
|---|---|
| `tests/integration/test_gateway_input.py` | 68 tests from 12 functions; malformed hello/session, early close, input isolation, safe callbacks, valid subsequent press and propagation guard |
| `tests/integration/test_gateway_more.py` | 15 tests from 8 functions; only the old mixed bad-JSON/unknown-op test is narrowed and renamed to test_an_unknown_op_is_ignored |
| `docs/verification/probe-04e.py` | Independent 96-case shape-isolation corpus with oracle-only mode |

Given test count: **83**. Net new cases: **68**, so minimum final suite is **1298**,
not N + 83 (15 cases already belong to N).

## Tests to write

Add behavior tests in the two named new files in Scope, not `_more` files.
Both touched production modules are already critical: every line and branch
must remain covered. Cover accepted UTF-8 bytes/fractional hello intervals,
sub-microsecond/overflow/deep JSON and huge-integer refusals, missing frame fields,
null/empty/wrong-type READY fields, populated non-dispatch s/t, invalid-session
flags, and no state poisoning. Cover missing nested body keys, nonstring option
names, safe DM identity, malformed slash data/name, unknown kinds, malformed
callback send failure directly and via Gateway, and later valid processing.
Use distinct injected exceptions to prove handler defects are not swallowed.
Preserve semantic bad-title and bad-address cases; do not weaken earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/gateway.py` | Validate incoming frames/hello and recover through existing connection loop |
| `src/mailroom/interactions.py` | Guard addressing/body shapes before state access; safe malformed callbacks |
| `tests/integration/test_gateway_input_boundaries.py` | New coder-written behavior/coverage tests only |
| `tests/integration/test_interaction_input_boundaries.py` | New coder-written behavior/coverage tests only |
| `docs/progress.md` | Append Phase 4e entry |

All new tests fall in core already; tests/sections.toml stays unchanged.

## Out of scope

- Listener restart/supervision, lock waits, missing database rows, token persistence,
  shared Discord service migration and interaction-module extraction (later phases).
- Changes to commands.py, service.py, gateway_protocol.py, layouts, schemas,
  fakes, given files, other earlier tests, dependencies or design documents.
- New public APIs, wire formats, button ids, acknowledgement retries, diagnostics
  containing payload text, or repair/coercion of malformed input.

## Rules that bite

All checks are synthetic/offline. HTTP uses MockTransport; Gateway uses the fake.
No real mail, model, Discord, task service, Keychain or data-folder access.
An ignored/refused payload cannot create a task, mutate a sender or reveal text.
Preserve keyed retry safety and 24-hour retention. Keep exact validation at the
input boundary; do not hide unrelated code defects behind exception handlers.

## Acceptance

Run from repository root, sequentially. The coverage row uses data from the
preceding check; the given-only run has --no-cov and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line All checks passed.; tests (core) passed; at least 1298 passed, 0 failed/skipped/xfailed, no warnings; every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include=src/mailroom/gateway.py,src/mailroom/interactions.py --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_gateway_input.py tests/integration/test_gateway_more.py --no-cov -q` | 83 passed |
| `.venv/bin/python docs/verification/probe-04e.py` | each successful check ends ok; final FAILURES 0 |
| `grep -c '^## Phase 4e: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4e` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04e-gateway-input.md docs/verification/phase-04e-gateway-input.md tests/integration/test_gateway_input.py tests/integration/test_gateway_more.py docs/verification/probe-04e.py` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may additionally write its named review |

### Searches

Each prints nothing (git grep exit 1 means no matches, exit above 1 is an error).
These supplement behavioral checks; they do not prove privacy by themselves.

```zsh
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src/mailroom/gateway.py src/mailroom/interactions.py
git grep --untracked -n -E 'print\(|logger\.|warnings\.warn|except Exception|except BaseException|pragma: no cover|noqa' -- src/mailroom/gateway.py src/mailroom/interactions.py
```

## Architect validation and handoff

No feature implementation was built. Given tests collect on predecessor imports;
62 failures are missing behavior/shape exceptions, with 21 documented guards
passing. Probe oracle-only passes; predecessor probe reaches FAILURES 1 across
the full 96-case corpus without aborting. Given files are linted/formatted and
the search patterns are checked on legitimate code and planted scratch violations.


Before coder use, commit the finalized planning docs and given artifacts,
including the owner decisions and roadmap/history updates, and require a clean
checkout. No commit is made by this planning assignment. Use a new verifier
session after implementation. Use the role prompts supplied with this planning handoff.
