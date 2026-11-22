# Verification guide: Phase 4m (Share safe HTTP and token mechanics)

Spec: `docs/phases/phase-04m-shared-token-http.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh session.
Everything is synthetic: FakeGmail, FakeGraph and scripted `httpx.MockTransport`
handlers. Never access real mail, Google, Microsoft, the Keychain or the data folder.

## 1. Coder ran

Before the gates, inspect status, the tracked diff and untracked files. Require one
`## Phase 4m: ` progress entry and implementation changes in
`src/mailroom/token_http.py` (new), `gmail.py`, `outlook.py` and
`scripts/critical_modules.txt`. A stopped entry is not a completed implementation. If
the coder did not run or stopped, report that. Do not treat every missing behavior as a
new defect.

Require these to be committed: the spec, this guide, the two new given test files, the
probe and the `docs/testing.md` line that lists `token_http.py`. Record the full
planning-baseline commit and verify that their bytes match it (G7). Do not call a dirty
planning tree a coder diff. Do not waive this gate, and do not commit.

The only permitted implementation paths are the spec's Scope. Your report adds only
`docs/reviews/phase-04m-shared-token-http.md`.

## 2. Gates

Run them in order from the repository root. G2 reads G1's coverage data before any
other test run. 61 given cases are new, so the minimum suite is 1577 + 61.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | `All checks passed.`; tests (core) passed with at least 1638 passed, 0 failed, skipped or xfailed, and no warnings; every Sections row has 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='src/mailroom/token_http.py,src/mailroom/gmail.py,src/mailroom/outlook.py' --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_token_http.py tests/integration/test_token_clients.py --no-cov -q` | 61 passed |
| G4 | `.venv/bin/python docs/verification/probe-04m.py` | check lines end ok; final FAILURES 0 |
| G4b | `.venv/bin/python docs/verification/probe-01b.py` | final FAILURES 0 |
| G4c | `.venv/bin/python docs/verification/probe-04a.py` | final FAILURES 0 |
| G4d | `.venv/bin/python docs/verification/probe-04h.py` | final FAILURES 0 |
| G5 | `grep -c '^## Phase 4m: ' docs/progress.md` | 1 |
| G5b | `grep -c '^token_http.py$' scripts/critical_modules.txt` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4m` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04m-shared-token-http.md docs/verification/phase-04m-shared-token-http.md tests/integration/test_token_http.py tests/integration/test_token_clients.py docs/verification/probe-04m.py docs/testing.md` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope paths, plus this review if already written |

Run G3 two more times. Every run must show 61 passed. The tests replace the clock and
use no threads or real waiting, so any failure is a finding.

`probe-01l.py` and `probe-01m.py` already end FAILURES 1 on predecessor code. They
are not gates. Do not report their results as defects of this phase.

Inspect the full diff for these:

- unlisted changes to earlier tests, fakes or probes;
- dependencies;
- coverage exclusions;
- new logging or output;
- a changed request, token form, header, scope, timeout, redirect or proxy setting;
- a provider named anywhere in `token_http.py`, comments and docstrings included;
- a second copy of the token cache, retry loop or transport mapping left in a client;
- a request sent with `self.http` directly from `gmail.py` or `outlook.py`;
- the URL check after `prepare`, a refresh or a request;
- the client's headers able to replace `Authorization`;
- a broad `except`, or an error raised without `from None`;
- a new error class that can reach the service;
- weak assertions in the coder's tests, and whether they pin the three "Tests to write"
  cases through requests and the fake Keychain rather than private fields.

## Requirement checks

Test prefixes: TH is `tests/integration/test_token_http.py::` and TC is
`tests/integration/test_token_clients.py::`.

| Requirement | Deciding evidence |
|---|---|
| 1: `mailroom/token_http.py` | every TH test; the coder's `Authorization` header test; probe lines 1, 2 and 3; Q2, Q4, Q5 |
| 2: `gmail.py` | TC test_gmail_builds_one_session_for_its_api_and_token_url; TC test_every_gmail_request_and_token_post_goes_through_the_session; `tests/integration/test_gmail*.py` unchanged; the coder's missing-secret test; G4b; Q1, Q3 |
| 3: `outlook.py` | TC test_outlook_builds_one_session_for_its_api_and_token_url; TC test_every_outlook_request_and_token_post_goes_through_the_session; `tests/integration/test_outlook*.py` unchanged; the coder's delta-link test; G4c, G4d; Q1, Q3 |
| 4: compatibility | full suite; G4b to G4d; probe line 4b; TC test_both_clients_keep_the_shared_margin; source review of headers, forms and `open_*` |
| 5: critical module | G5b; G2 |
| 6: progress | G5/G6 and the entry's factual contents |

## 3. Spot checks

Run spot checks only in disposable scratch copies of the current implementation and
tests:

- Use the existing venv and `PYTHONPATH=src:.`. Confirm that `mailroom.__file__` is
  inside the copy.
- Set `PYTHONDONTWRITEBYTECODE=1` and remove the copy's `__pycache__` folders first.
  Otherwise, two same-size mutations written within one second can run stale bytecode.
- Never mutate the implementation under review.
- Start each row from the original bytes and run the deciding test with `--no-cov`.
  Then discard only your mutation and compare bytes.
- If the coder's private code differs, locate the equivalent line. Do not prescribe
  private helper names.

| # | Function/boundary | One-line mutation | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| Y1 | TOKEN_MARGIN | No margin before expiry | TH test_the_margin_is_sixty_seconds | refresh at 3540 s | refresh at 3600 s |
| Y2 | ensure | Keep the token at its exact expiry | TH test_the_token_is_reused_until_its_margin_then_refreshed | refreshed | reused |
| Y3 | get | No retry after a 401 | TH test_a_rejected_token_is_refreshed_and_the_request_sent_once_more | second GET 200 | auth error |
| Y4 | get | Keep the rejected token | TH test_a_rejected_token_is_refreshed_and_the_request_sent_once_more | access-2 | access-1 again |
| Y5 | _allowed | Any host | TH test_a_url_outside_the_api_is_refused_before_any_request[other-host] | refused | sent |
| Y6 | _allowed | Allow dot segments | TH test_a_url_outside_the_api_is_refused_before_any_request[dot-dot] | refused | sent |
| Y7 | _allowed | Bare path prefix | TH test_a_url_outside_the_api_is_refused_before_any_request[path-prefix] | refused | sent |
| Y8 | _allowed | Any port | TH test_a_url_outside_the_api_is_refused_before_any_request[port] | refused | sent |
| Y9 | grant | Listed codes only on 400 | TH test_a_listed_refusal_is_the_auth_error[invalid_grant-401] | auth | unavailable 401 |
| Y10 | grant | Accept a bool lifetime | TH test_an_unusable_grant_is_unavailable_response[lifetime-bool] | unavailable response | grant |
| Y11 | ensure | A failed refresh keeps the old token | TH test_a_failed_refresh_leaves_no_token_for_the_next_request | POST then access-2 | access-1 reused |
| Y12 | ensure | Skip prepare | TH test_prepare_runs_before_every_token_check | prepared 1 | prepared 0 |
| Y13 | _send | Map only timeouts | TH test_a_transport_failure_on_a_request_is_unavailable_network | unavailable network | ConnectError |
| Y14 | OutlookClient.__init__ | No prepare hook (held token never saved) | tests/integration/test_outlook_rotation.py::test_the_next_call_tries_the_save_again_before_any_request | held token saved before the request | held token lost |
| Y15 | GmailClient.__init__ | Gmail also treats interaction_required as sign-in | TC test_gmail_builds_one_session_for_its_api_and_token_url | {invalid_grant} | two codes |
| Y16 | _get | Drop the Prefer header | tests/integration/test_outlook.py::test_the_profile_falls_back_to_the_sign_in_name_and_finds_the_inbox | ImmutableId ids | no Prefer |
| Y17 | _refresh | Drop the scope from the token form | tests/integration/test_outlook.py::test_a_token_is_asked_for_as_a_public_client_and_the_new_refresh_token_saved | scope sent | no scope |
| Y18 | Outlook delta link | Allow dot segments (as Y6) | the coder's delta-link test with a `..` segment | OutlookUnavailable (response), nothing sent | link followed |
| Y19 | get | Let a client header replace the bearer token (put `Authorization` before the client's headers) | the coder's `Authorization` header test | Bearer access-1 | the client's value |

These mutations were run against a throwaway scratch stand-in at planning time, not
against the coder's code. If a row fails in a different way, diagnose it. If a mutation
passes, the test may be weak rather than the product defective. Report the difference
either way.

- Y4 must drop both the token and its expiry on a 401. Clearing only one of them still
  forces a refresh, so that is not the mutation.
- Y11 removes the forgetting before `refresh`. Its test moves the clock back, so an
  old token would look valid again.
- Y18 and Y19 had no given or existing test at planning time. Y18 reuses Y6's mutation
  and asks whether the coder's Outlook delta-link test fails under it. Y19 was missed by
  the whole planning-time suite. If the coder's tests do not catch either one, report
  the missing test as a finding against "Tests to write".

## 4. Probe

`.venv/bin/python docs/verification/probe-04m.py` runs offline. A seeded random
generator fixes every choice. The probe checks these:

- **Neutral module.** A fresh interpreter imports `mailroom.token_http` and loads no
  `mailroom.gmail*` or `mailroom.outlook*` module. `token_http.py`'s own import
  statements name no mailroom module but `clock`; the probe reads them with `ast`.
  `gmail.TOKEN_MARGIN` and `outlook.TOKEN_MARGIN` are its 60-second object.
- **The session.** 200 seeded scripts of 12 requests each. Between requests the clock
  moves by 0 s to 2 h, including exactly the margin. Each token post is good (with a
  60 s, 120 s or 1 h lifetime), refused with a listed code on 400 or 401, refused with
  another code, a 503, unusable, or unreachable. Each API reply is 200, 401, 403, 500
  or unreachable. The probe's own oracle predicts every request with its bearer token,
  and every outcome. Every error must be raised `from None`.
- **Where a token may go.** 400 seeded URLs built from good and bad schemes, hosts
  (including a suffix trick and upper case), ports, user info, near-miss base paths, and
  plain or `%`-encoded dot segments. The probe decides each one itself. A refused URL
  must be `unavailable("response")` with nothing sent and no `prepare`.
- **Both real clients.** Each builds one session, and every GET and token post goes
  through it. 60 seeded call scripts per provider run against FakeGmail and FakeGraph,
  with clock moves, token invalidation, scripted token and API failures. Every call's
  outcome and token-post count must match one model of the session, for Gmail and for
  Outlook.

It does not check `prepare` or Outlook's held token, the `Prefer` header, the scope,
or Gmail's codes; the tests and probe-04h cover those. It reports names and counts,
never tokens or payloads, and always reaches `FAILURES N`. Never edit the probe. An
oracle disagreement that is not a product defect belongs to the architect.

## 5. Searches

Each search prints nothing. A grep exit of 1 means no match, and an exit above 1 is an
error.

| # | Rule | Command |
|---|---|---|
| Q1 | No token cache, retry, transport mapping or bearer header left in the clients | `git grep --untracked -n -E '_access_token\|_expiry\|range\(2\)\|TransportError\|TOKEN_MARGIN = timedelta\|clock\|def _send\|_invalid_grant\|_oauth_error\|Bearer' -- src/mailroom/gmail.py src/mailroom/outlook.py` |
| Q2 | `token_http.py` names no provider | `git grep --untracked -n -i -E 'gmail\|outlook\|google\|microsoft\|graph' -- src/mailroom/token_http.py` |
| Q3 | The clients send nothing except through the session | `git grep --untracked -n -E '\.http\.(get\|post)\(' -- src/mailroom/gmail.py src/mailroom/outlook.py` |
| Q4 | `token_http.py` imports no mailroom module but `clock` | `git grep --untracked -n -e 'import' --and -e 'mailroom' --and --not -e '^from mailroom import clock$' -- src/mailroom/token_http.py` |
| Q5 | No broad catches, `finally`, exclusions, logging, time shortcuts or `isinstance` lifetime | `git grep --untracked -n -E 'except (Exception\|BaseException)[ :]\|except:\|pragma: no cover\|noqa\|datetime\.now\|from mailroom\.(clock\|ids) import\|print\(\|logging\|finally:\|isinstance\(expires_in' -- src/mailroom/token_http.py src/mailroom/gmail.py src/mailroom/outlook.py` |

The escaped pipes in the table are ordinary alternation pipes. Q1 and Q3 are text-based,
so source review also checks for other spellings: a client reaching `httpx` through
another name, or a copied retry written as a `while` loop.

## 6. Reasonable variations

- Private helpers in `token_http.py` under any names, and `__slots__`.
- The URL check written with `PurePosixPath` or a loop over segments, as long as it
  decides every given and probe URL the same way.
- The default `prepare` as a module function, a lambda or `None` handled inside the
  session, as long as the public parameter is optional.
- Gmail's or Outlook's refresh as a method or a closure.
- `Grant.body` holding the reply object itself or a copy.
- Extra behavior tests in the coder's test file.

Not variations:

- a base class, a provider branch or a provider name in `token_http.py`;
- a session that raises its own error classes;
- the URL check after `prepare` or the refresh, or one that accepts a dot segment;
- `isinstance` for the lifetime;
- a client still holding its own access token or expiry;
- a change to any request, form, header, error text or `open_*` setting.

## 7. Verdict

Write `docs/reviews/phase-04m-shared-token-http.md`, starting `# Review: Phase 4m`, with
the exact conventions-format head and findings. Include:

- the gate and Sections output;
- coverage;
- the repeated G3 runs;
- the searches;
- the probe results;
- the spot-check results.

Classify each defect by its requirement, the observed result and the required result.
Do not repair code or tests. Run G6 after writing it.

## Handoff prompts

Only after the final planning documents and given files are committed and the coder's
checkout is clean:

> Use $phase-coder to implement only Phase 4m from
> docs/phases/phase-04m-shared-token-http.md in this checkout. Read the required project
> docs and every given test. Run Start and all Acceptance commands; append progress. Do
> not read the verification guide or write a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4m against
> docs/phases/phase-04m-shared-token-http.md and
> docs/verification/phase-04m-shared-token-http.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probes, searches and
> scratch-only spot checks; write only docs/reviews/phase-04m-shared-token-http.md.
