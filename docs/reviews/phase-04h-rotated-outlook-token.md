# Review: Phase 4h

- Verdict: PASS
- Passed: 1437
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Baseline and scope (fresh)

- Planning baseline 6fab968 (spec, guide, two given test files, layout edit, probe). Implementation is commit 2dfcfd9; working tree clean at review start.
- 2dfcfd9 changed only outlook.py, service.py, tests/integration/test_outlook_token_save.py and docs/progress.md. All given files, the spec and the guide are byte-identical to 6fab968 (G7 empty). No change to pyproject.toml, tests/sections.toml or any earlier test.

## Gates (fresh)

- G1 `check.py --first core`: All checks passed; 1437 passed; Sections tooling 77/0 failed, core 1360/0 failed; no skips or warnings.
- G2 coverage outlook.py 244 stmts / 68 branches, service.py 258 / 52: TOTAL 100%, exit 0.
- G3 given files: 18 passed, and 18 passed in each of 3 further runs (4 in all).
- G4 probe: oracle self-check ok; 40 of 40 trials reached; rotation invariants ok; FAILURES 0.
- G5: 1. G7: no output. G8: clean tree.
- Q1 to Q4: no matches (exit 1 each).

## Spot checks (scratch copy, bytecode writing off, mailroom imported from the copy, original bytes unchanged)

- S1 to S14: the deciding test fails under each mutation, as required. The unmutated copy passes the outlook rotation file (10 passed), and a sampled failure (S5) fails on the expected assertion rather than on a setup error.

## Source review

- `OutlookTokenUnsaved` is an `OutlookError` (not an `OutlookAuthError`), takes only the account, and is raised `from None`. The rotated token is held only in a private client attribute, is never formatted into any message, and the access token and expiry from the unsaved reply are cleared.
- Every Graph call goes through `_ensure_token`, which first tries the save once and clears the held token only after it succeeds; a failed try raises with no HTTP request. No loop, sleep, or disk, environment or database copy exists.
- Service: the unsaved branch precedes the generic branch, reports the constant text, and raises `outlook-token:<account>` with `wait=timedelta(0)` and `ping=True`. It is resolved only in the successful-sync branch; the sign-in and generic branches do not touch it.
