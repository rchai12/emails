# Review: Phase 4k

- Verdict: PASS
- Passed: 1559
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Baseline and scope (fresh)

- Planning baseline da786ac (spec, guide, two given test files, probe, docs/testing.md line). Implementation is commit 56f81bb; working tree clean at review start.
- 56f81bb changed only oauth.py (new), gmail_login.py, outlook_login.py, cli.py, tests/integration/test_oauth_flow.py and docs/progress.md. The spec, guide, given tests, probe and docs/testing.md are byte-identical to da786ac (G7 empty). No change to pyproject.toml, tests/sections.toml, any earlier test, fake or probe.

## Gates (fresh)

- G1 `check.py --first core`: All checks passed; 1559 passed (core 1474 + tooling 85, 0 failed); no skips or warnings.
- G2 coverage oauth.py 96 stmts / 18 branches, gmail_login.py 42 / 6, outlook_login.py 39 / 6: TOTAL 100%, exit 0.
- G3 given files: 25 passed, and 25 passed in each of 2 further runs (3 in all).
- G4 probe-04k: every check line ok (fresh-interpreter import, shared names, token-reply and exchange contracts over 1500 seeded replies each, provider-neutral callback, every login command closes its client); FAILURES 0. probe-01d and probe-04c: FAILURES 0.
- G5: 1. G8: clean tree.
- Q1 to Q5: no matches (exit 1 each).

## Spot checks (scratch copy, bytecode writing off, mailroom imported from the copy, original bytes unchanged)

- O1 to O9 and C1 to C3: the deciding test file fails under each mutation, as required. C3 (close only after success, two edits) fails 3 command cases.

## Source review

- oauth.py names no provider (comments and docstrings included), imports only the standard library, httpx and `mailroom.clock`, and defines the single `LoginError`. `Callback` requires `provider`; the timeout and cancel errors use it and are raised `from None`.
- `token_reply` posts the given URL and form once and raises constant-text `LoginError`s from None for network, non-200, non-JSON or non-object bodies, a missing, non-text or empty refresh token, and a missing or non-text scope. It never includes reply text, a code or a token. Gmail now refuses an empty refresh token through it, as the owner decided.
- gmail_login re-exports the moved names as oauth's own objects (with `__all__`) and keeps a thin `Callback` subclass defaulting to gmail; the Gmail scope rule, consent URL, form fields and Keychain handling are unchanged. outlook_login imports nothing from gmail_login or gmail; its scope rule and form fields are unchanged.
- cli: each command opens the client with `with <module>.new_http() as http:` inside the existing `try`, looking `new_http` up on the module at run time, passes it to `login`, and catches `oauth.LoginError`. Output and exit codes are unchanged; `login()` does not close the client it is lent.
