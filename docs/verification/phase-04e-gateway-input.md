# Verification guide: Phase 4e (Validate Gateway input)

Spec: `docs/phases/phase-04e-gateway-input.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh
session. All traffic is synthetic through fakes/MockTransport; never access real
Discord, mail, model, tasks, Keychain or the data folder.

## 1. Coder ran

Before gates, inspect status, tracked diff and untracked files. Require one
`## Phase 4e: ` progress entry and implementation changes in both gateway.py and
interactions.py. A stopped entry is not a completed implementation. Report a
missing coder or stop without treating every missing behavior as a new defect.

Require the final spec, this guide, both given test files and probe to be
committed. Record the full planning-baseline commit; verify their current bytes
match that commit. The earlier 06a5fba is the source predecessor, not the final
given-file baseline. A dirty planning tree must not be called a coder diff.
Do not waive this gate or commit files as verifier.

The only permitted implementation paths are the spec's Scope. Your report adds
only `docs/reviews/phase-04e-gateway-input.md`. A mixed baseline requires the
documented isolation/byte-comparison procedure before a valid Scope verdict.

## 2. Gates

Run sequentially from repository root. G2 reads G1's coverage before another test
run. Given count 83 includes 15 predecessor cases; minimum suite is 1230 + 68.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | All checks passed.; tests (core) passed; at least 1298 passed, 0 failed/skipped/xfailed, no warnings; all Sections rows have 0 failed |
| G2 | `.venv/bin/python -m coverage report --include=src/mailroom/gateway.py,src/mailroom/interactions.py --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_gateway_input.py tests/integration/test_gateway_more.py --no-cov -q` | 83 passed |
| G4 | `.venv/bin/python docs/verification/probe-04e.py` | check lines end ok; final FAILURES 0 |
| G5 | `grep -c '^## Phase 4e: ' docs/progress.md` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4e` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04e-gateway-input.md docs/verification/phase-04e-gateway-input.md tests/integration/test_gateway_input.py tests/integration/test_gateway_more.py docs/verification/probe-04e.py` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope, plus this review if already authored |

Also inspect the full diff for unlisted earlier-test changes, dependencies,
coverage exclusions, new network/logging behavior and weak assertions. No new
dependency is permitted; compare pyproject.toml and lock files with baseline.
The earlier-test rename is an architect-provided given edit, already committed,
not permission for the coder to alter that file again.

## Requirement checks

| Requirement | Deciding evidence |
|---|---|
| 1: decoding/frame shape | test_bad_session_frame_resumes_without_poisoning_state; coder boundary cases for deep JSON, huge integers and missing dispatch fields |
| 2: hello/early close | test_bad_hello_reconnects_before_identify; test_close_before_hello_uses_existing_close_policy; accepted fractional/UTF-8 and conversion-boundary coder tests |
| 3: state before dispatch | bad session frame cases with s=99; existing fatal/resume tests; coder tests for control s/t and malformed READY URLs |
| 4: callback envelope | test_unsafe_callback_address_never_sends; test_unaddressable_or_unknown_kind_is_ignored; test_opaque_token_is_escaped_as_one_callback_segment |
| 5: body before state | bad component/modal/slash tests using NoStore; test_malformed_member_cannot_fall_back_to_owner; probe corpus |
| 6: acknowledgement and continuation | exact callback dictionaries; test_valid_owner_press_after_bad_event_still_works; coder callback-failure continuation tests |
| 7: compatibility/privacy | existing Gateway, command and interaction suites; test_unexpected_handler_bug_is_not_swallowed; searches and source inspection |
| 8: progress | G5/G6 and factual entry contents |

## 3. Spot checks

Run only in disposable scratch copies of the current implementation/tests, with
the existing venv and `PYTHONPATH=src:.`. Confirm mailroom imports from the copy.
Never mutate the implementation under review. Start each row from original
bytes, run the deciding test with --no-cov, then discard just your own mutation.
Compare source bytes/status afterwards. These are behavioral mutations: locate
the equivalent guard if private helpers differ; do not prescribe helper names.

Every test below has prefix `tests/integration/test_gateway_input.py::` except
S8, whose prefix is `tests/integration/test_gateway_more.py::`.

| # | Function/boundary | One-line mutation | Deciding test suffix | Correct | Broken |
|---|---|---|---|---|---|
| S1 | hello validation | Accept any integer opcode instead of requiring 10 | test_bad_hello_reconnects_before_identify[wrong-op] | first connection sends nothing and closes 4000 | identify sent on first connection |
| S2 | active frame decoder | Remove the non-object refusal | test_bad_session_frame_resumes_without_poisoning_state[null] | reconnect/resume with seq 1 | attribute/type error on decoded null |
| S3 | READY validation order | Insert state.seq = payload.get("s") before validating the decoded READY shape | test_bad_session_frame_resumes_without_poisoning_state[ready-null] | resume seq 1 | resume seq 99 |
| S4 | callback addressing | Coerce an integer token to string rather than rejecting it | test_unsafe_callback_address_never_sends[token-12] | ignored before store/HTTP | store access assertion |
| S5 | modal body validation | Bypass the components container guard | test_malformed_modal_container_acknowledges[None] | one type-6 callback, no state access | store access assertion or shape error |
| S6 | malformed slash acknowledgement | Replace callback type 4 with 6 | test_malformed_slash_options_get_private_constant_reply[123] | private constant type-4 reply | callback dictionary has type 6 |
| S7 | Gateway interaction dispatch | Broaden DiscordUnavailable catch to Exception | test_unexpected_handler_bug_is_not_swallowed | HandlerFault propagates | expected exception is absent |
| S8 | unknown opcode handling | Reconnect instead of ignoring an unknown well-shaped opcode | test_an_unknown_op_is_ignored | one connection, normal heartbeat transcript | first connection closes/reconnects |

Resolve exact collected parameter ids before executing S4/S5/S6; use G3's
collection if the runner displays escaped punctuation. A missing test is not a
successful mutation check. These mutations were traced against the given inputs
at planning time; execution against the coder's eventual implementation is the
verifier's work. A different failure needs diagnosis; a passing mutation can
mean a weak test rather than a product defect. Report that distinction.

## 4. Probe

`.venv/bin/python docs/verification/probe-04e.py --oracle-only` checks the corpus
alone: 96 forced invalid-body cases, all three supported interaction kinds, with
seeded variation. The normal probe calls the real handler with a forbidden store
and mock HTTP transport. It asserts safe exact replies/no input echo, counts
failures without printing payloads, and always reaches FAILURES N for application
failures. It isolates HOME/MAILROOM settings in a temporary directory.

This adds combinations across malformed identity/data/channel shapes beyond the
given individual examples. It is not another implementation of the validator.
An oracle assertion failure belongs to the architect, not to a product finding.
Wire reconnect, fatal-close and state-order behavior is decided by the tests,
not by this probe. Never edit the probe to make it pass.

## 5. Searches

Each prints nothing; grep exit 1 is no match, exit above 1 is an execution error.

| # | Rule | Command |
|---|---|---|
| Q1 | Time/id seams | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.(clock\|ids) import' -- src/mailroom/gateway.py src/mailroom/interactions.py` |
| Q2 | No new output, broad catch or coverage bypass | `git grep --untracked -n -E 'print\(\|logger\.\|warnings\.warn\|except Exception\|except BaseException\|pragma: no cover\|noqa' -- src/mailroom/gateway.py src/mailroom/interactions.py` |

In Markdown table cells, escaped pipes represent ordinary alternation pipes in
the actual command. Source review also checks str/int coercion of malformed
fields, state updates before validation and unintended business-state access.

## 6. Reasonable variations

- Private validators/parsers in either Scope module, with shared local helpers,
  provided both public entry points remain guarded and no new module is added.
- Different narrowly scoped JSON/Unicode/conversion exception handling that
  refuses malformed input without catching handler/store failures.
- Returning a private sentinel or None from a decoder before existing reconnect
  logic; this is not a change to the public run_gateway return contract.
- An internal constant for the exact malformed-command sentence; no layout
  module edit is required. Extra Discord fields stay accepted.

The owner-selected reconnect and safe-acknowledgement policies are requirements,
not variations. No service supervisor, SQLite recovery or missing-row repair is
approved as part of 4e.

## 7. Verdict

Write `docs/reviews/phase-04e-gateway-input.md`, starting `# Review: Phase 4e`,
using the exact conventions-format head and findings. Include gate/Sections,
coverage, search and mutation digests. Classify defects as requirement, observed
result and required result; do not repair code or tests. Run G6 after writing it.

## Handoff prompts

Only after the final planning documents and given files are committed and the
coder checkout is clean:

> Use $phase-coder to implement only Phase 4e from
> docs/phases/phase-04e-gateway-input.md in this checkout. Read the required
> project docs and every given test. Run Start and all Acceptance commands;
> append progress. Do not read the verification guide or write a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4e against
> docs/phases/phase-04e-gateway-input.md and
> docs/verification/phase-04e-gateway-input.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probe, searches and
> scratch-only spot checks; write only docs/reviews/phase-04e-gateway-input.md.
