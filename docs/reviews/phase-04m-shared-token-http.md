# Review: Phase 4m

- Verdict: PASS
- Passed: 1644
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Baseline and scope (fresh: git inspection and byte comparison)

- Planning baseline 99d2248 (spec, guide, given tests, probe, docs/testing.md). Implementation is commit f533e4a; working tree clean at review start. G7 against HEAD: no output.
- `git diff 99d2248 HEAD --stat` lists only docs/progress.md, scripts/critical_modules.txt, gmail.py, outlook.py, token_http.py (new) and tests/integration/test_token_clients_more.py, all in the spec's Scope. No change to docs, fakes, earlier tests, probes, pyproject or dependencies.
- Progress entry: one "## Phase 4m:" entry, 1577 -> 1644 (given 61), no deviations. token_http.py is listed once in scripts/critical_modules.txt.

## Gates (fresh)

- G1 check.py --first core: All checks passed; 1644 passed (tooling 85, core 1559), 0 failed, no skips or warnings.
- G2 coverage token_http 90/18, gmail 161/28, outlook 212/54: TOTAL 100%, exit 0.
- G3 given files: 61 passed, three runs.
- G4 probe-04m: all five lines ok, FAILURES 0. G4b probe-01b, G4c probe-04a, G4d probe-04h: each FAILURES 0.
- G5: 1. G5b: 1. G7: no output. G8: clean tree.
- Q1 to Q5: no matches (exit 1 each).

## Spot checks (scratch copy, mailroom imported from the copy, original md5s unchanged)

- Y1 to Y17 and Y19: each mutation fails its deciding test (and others) as required.
- Y18 (dot segments allowed): the coder's test_an_outlook_link_that_climbs_out_of_the_api_is_refused_unsent fails (1 failed of 6).
- Y19 (client header replaces the bearer): fails both parametrized cases of the coder's header test. A case-sensitive-only filter (Y19b) fails the lowercase case, so the test pins case-insensitivity too.
- The coder's tests assert through requests and the fake Keychain; the missing-secret test checks no POST was made, then a POST and GET after the secret returns.

## Source review

- token_http.py imports only stdlib, httpx and `mailroom.clock`, and names no provider. The URL check runs first in `get`, before prepare, refresh or any request. Client headers are filtered case-insensitively so `Authorization` is always the session's bearer. Only httpx.TransportError and ValueError are caught; every raise is `from None`; `type(...) is` is used for the lifetime and token.
- ensure forgets the token before refresh, so a failed refresh leaves nothing. Outlook's rotation and held token stay in outlook.py via `prepare=_save_held`; the form fields, Prefer header, scope, timeout and redirect settings are unchanged. Clients send nothing through `self.http` directly.
