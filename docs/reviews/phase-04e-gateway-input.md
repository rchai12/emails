# Review: Phase 4e

- Verdict: PASS
- Passed: 1337
- Findings: 0
- Approved deviations: Kind 2 with no name key stays ignored with no callback; a present non-string name gets the private reply (owner-approved in the spec's Corrections).
- For the architect: The coder's commit af0971c also contains the spec Corrections and the architect history entry; the implementation itself is committed against baseline 5404a48.

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Baseline and scope (reused: git inspection; fresh: byte comparison)

- Planning baseline 5404a48 (final spec, guide, given tests, probe). Implementation is commit af0971c; working tree clean at review start. Given test files, spec body, guide and probe are byte-identical between 5404a48 and HEAD (diff empty); only the spec's dated Corrections section was added after 5404a48.
- af0971c changed: gateway.py, interactions.py, the two new boundary test files, docs/progress.md (Scope), plus `.claude/skills/phase-architect/history.md` and the spec Corrections (architect material, not coder-written product files).
- No change to pyproject.toml, lock files, tests/sections.toml, test_gateway_more.py or any earlier test after 5404a48. No new dependency, coverage exclusion, logging, network or broad catch.

## Gates (fresh)

- G1 `check.py --first core`: All checks passed; 1337 passed; Sections tooling 77/0 failed, core 1260/0 failed; no skips or warnings.
- G2 coverage gateway.py 234 stmts / 82 branches, interactions.py 347 / 164: TOTAL 100%, exit 0.
- G3 given files: 83 passed.
- G4 probe: oracle self-check ok; shape isolation ok; FAILURES 0.
- G5: 1. G7: no output. G8: clean tree.
- Q1 and Q2: no matches (exit 1 each).

## Spot checks (scratch copy, mailroom imported from the copy, original bytes unchanged)

- S1, S2, S4, S5, S6, S7, S8: the deciding test fails under the mutation, as required.
- S3 as written (seq set inside `_frame` before the READY check) passes for `ready-null`, because this implementation rejects a non-object `d` earlier in `_decode`, so that path never reaches `_frame`. Equivalent mutations were caught: setting seq before decode fails `ready-null`, and setting seq before the READY check in `_frame` fails `ready-id`. This is a guard-location difference, not a weak test.

## Source review

- Decode: ValueError (JSON, UTF-8, huge int) and RecursionError refused; exact int/str/dict types, bool excluded; non-dispatch s/t must be null.
- Hello: op, object d, exact int/float, positive and schedulable via timedelta (NaN, infinity, overflow, sub-microsecond refused); closes 4000 before identify; ConnectionClosed before hello goes through the existing close policy.
- State is updated only after READY and sequence validation; the handler is not wrapped in a broad catch (only DiscordUnavailable, as before).
- Interactions: envelope and body shape checked before any store access; the token is percent-encoded as one segment; the exact `{"type": 6}` and constant type-4 private replies are used; a malformed member never falls back to the top-level user.
