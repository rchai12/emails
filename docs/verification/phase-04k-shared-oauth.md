# Verification guide: Phase 4k (Extract shared OAuth mechanics)

Spec: `docs/phases/phase-04k-shared-oauth.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh session.
Everything is synthetic, and every HTTP call goes to a fake. The callback listens only on
127.0.0.1. Never open a real consent page or access real mail, Google, Microsoft, the
Keychain or the data folder.

## 1. Coder ran

Before the gates, inspect status, the tracked diff and untracked files. Require one
`## Phase 4k: ` progress entry and implementation changes in `src/mailroom/oauth.py`
(new), `gmail_login.py`, `outlook_login.py` and `cli.py`. A stopped entry is not a
completed implementation. If the coder did not run or stopped, report that. Do not
treat every missing behavior as a new defect.

Require these to be committed: the spec, this guide, the two new given test files, the
probe and the `docs/testing.md` line that lists `oauth.py`. Record the full
planning-baseline commit and verify that their bytes match it (G7). Do not call a dirty
planning tree a coder diff. Do not waive this gate, and do not commit.

The only permitted implementation paths are the spec's Scope. Your report adds only
`docs/reviews/phase-04k-shared-oauth.md`.

## 2. Gates

Run them in order from the repository root. G2 reads G1's coverage data before any
other test run. 25 given cases are new, so the minimum suite is 1529 + 25.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | `All checks passed.`; tests (core) passed with at least 1554 passed, 0 failed, skipped or xfailed, and no warnings; every Sections row has 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='src/mailroom/oauth.py,src/mailroom/gmail_login.py,src/mailroom/outlook_login.py' --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_oauth.py tests/integration/test_login_close.py --no-cov -q` | 25 passed |
| G4 | `.venv/bin/python docs/verification/probe-04k.py` | check lines end ok; final FAILURES 0 |
| G4b | `.venv/bin/python docs/verification/probe-01d.py` | final FAILURES 0 |
| G4c | `.venv/bin/python docs/verification/probe-04c.py` | final FAILURES 0 |
| G5 | `grep -c '^## Phase 4k: ' docs/progress.md` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4k` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04k-shared-oauth.md docs/verification/phase-04k-shared-oauth.md tests/integration/test_oauth.py tests/integration/test_login_close.py docs/verification/probe-04k.py docs/testing.md` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope paths, plus this review if already written |

Run G3 two more times. Every run must show 25 passed. The callback tests use a real
local socket but no real waiting, because the clock is replaced. So any failure is a
finding.

Inspect the full diff for these:

- unlisted changes to earlier tests, fakes or probes;
- dependencies;
- coverage exclusions;
- new logging or output;
- a changed consent URL, scope, form field, Keychain name, prompt or `new_http` setting;
- a `LoginError` defined anywhere but `oauth.py`;
- a provider named anywhere in `oauth.py`, comments and docstrings included;
- `login()` closing the client it was lent;
- the reply's `error`, `error_description` or exception text in an error message;
- `new_http` bound at import in `cli.py`;
- weak assertions in the coder's tests, and whether they pin an unexpected exception
  closing the client.

## Requirement checks

Test prefixes: OA is `tests/integration/test_oauth.py::` and LC is
`tests/integration/test_login_close.py::`.

| Requirement | Deciding evidence |
|---|---|
| 1: `mailroom/oauth.py` | OA test_the_shared_pieces_live_in_oauth_and_gmail_login_keeps_its_names; OA test_the_neutral_callback_requires_and_names_its_provider; OA test_a_good_token_reply_gives_the_refresh_token_and_scope; OA test_a_bad_token_reply_is_one_constant_error (11 ids); probe token_reply and callback lines; Q2, Q5 |
| 2: `gmail_login.py` | OA test_the_gmail_callback_still_defaults_to_gmail; OA test_gmail_now_refuses_an_empty_refresh_token; `tests/integration/test_gmail_login*.py` unchanged; probe both-exchanges line; probe-01d; Q1 |
| 3: `outlook_login.py` | OA test_outlook_sign_in_loads_no_gmail_module; `tests/integration/test_outlook_login*.py` unchanged; probe no-gmail-module and both-exchanges lines; probe-04c; Q1, Q3 |
| 4: CLI closes its client | LC test_the_login_command_closes_its_client (8 ids); probe closes-its-client line; the coder's unexpected-exception test; Q4 |
| 5: compatibility | full suite; G4b, G4c; source review of consent URLs, form fields, scope rules and `new_http` |
| 6: critical module | G7 (the `docs/testing.md` line is in the planning commit) |
| 7: progress | G5/G6 and the entry's factual contents |

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
  helper names.

| # | Function/boundary | One-line mutation | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| O1 | Callback | Give the neutral callback a gmail default | OA test_the_neutral_callback_requires_and_names_its_provider | TypeError | a callback |
| O2 | Callback.wait | Name gmail in the timeout whatever the provider | OA test_the_neutral_callback_requires_and_names_its_provider | yahoo login timed out: live | gmail login timed out: live |
| O3 | token_reply | Accept an empty refresh token | OA test_a_bad_token_reply_is_one_constant_error[empty-token] | yahoo login failed: family (response) | ('', 'read') |
| O4 | token_reply | Accept a scope that is not text | OA test_a_bad_token_reply_is_one_constant_error[scope-not-text] | yahoo login failed: family (response) | ('refresh-1', ['read']) |
| O5 | token_reply | Treat only server errors as a failed status | OA test_a_bad_token_reply_is_one_constant_error[status-400] | yahoo login failed: family (400) | yahoo login failed: family (response) |
| O6 | token_reply | Keep the network error as the context | OA test_a_bad_token_reply_is_one_constant_error[refused] | context suppressed | context kept |
| O7 | outlook_login imports | Take the shared names from gmail_login again | OA test_outlook_sign_in_loads_no_gmail_module | [] | ['mailroom.gmail', 'mailroom.gmail_login'] |
| O8 | gmail exchange_code | Skip the gmail scope check | tests/integration/test_gmail_login.py::test_a_token_for_any_scope_but_read_only_is_refused | gmail login scope refused | a token |
| O9 | outlook exchange_code | Accept any grant that includes Mail.Read | tests/integration/test_outlook_login.py::test_any_other_grant_is_refused[send-too] | outlook login scope refused | a token |
| C1 | gmail_login_command | Pass the client without closing it | LC test_the_login_command_closes_its_client[gmail-signed in] | closed | open |
| C2 | outlook_login_command | Pass the client without closing it | LC test_the_login_command_closes_its_client[outlook-signed in] | closed | open |
| C3 | gmail_login_command | Close the client only after a successful sign-in (replace the `with` and add `http.close()` before the success line) | LC test_the_login_command_closes_its_client[gmail-cancelled] | closed | open |

These mutations were run against a throwaway scratch stand-in at planning time, not
against the coder's code. If a row fails in a different way, diagnose it. If a mutation
passes, the test may be weak rather than the product defective. Report the difference
either way. C3 takes two edits, and both the given tests and the probe caught it at
planning time.

## 4. Probe

`.venv/bin/python docs/verification/probe-04k.py` runs offline against the fakes. A
seeded random generator fixes every choice. The probe checks these:

- **Isolation.** A fresh interpreter imports `mailroom.oauth` and
  `mailroom.outlook_login` and loads no `mailroom.gmail*` or `mailroom.cli` module.
- **No provider imports.** `oauth.py`'s own import statements name no provider module.
  The probe reads them with `ast`.
- **Shared objects.** `LoginError`, `new_verifier` and `code_challenge` on both
  provider modules, and `outlook_login.Callback`, are oauth's objects.
  `gmail_login.Callback` subclasses `oauth.Callback`.
- **token_reply.** 1500 seeded replies go to `oauth.token_reply` under random provider
  and account names. The replies include:
  - network errors;
  - error statuses carrying a marker;
  - bodies that are not JSON or not objects;
  - fields that are missing, retyped or empty.

  The probe predicts each outcome from its own reading of the contract. An error must
  meet all of these:
  - it is exactly a `LoginError`;
  - its text is exactly the predicted one;
  - its context is suppressed;
  - it holds no marker, code or token.

  An accepted reply must return the reply's own pair.
- **Both exchanges.** 1500 seeded replies go to both `exchange_code` functions. The
  probe uses its own copy of each scope rule. A scope refusal and a reply failure must
  each have the exact text.
- **The callback.** The neutral callback names yahoo, fastmail and outlook in its
  timeout. Without a provider it raises `TypeError`. The Gmail callback still says
  gmail.
- **Closing.** Every outcome of each login command is run through a recording `login`:
  success, each reported error type and two unexpected errors. That `login` must be
  lent the one client `new_http` made, still open. That client must be closed
  afterwards. Reported errors must end the output with exit 1, and unexpected errors
  must propagate.

It does not check the coder's test file or `docs/testing.md`. It reports names and
counts, never payloads, and always reaches `FAILURES N`. Never edit the probe. An
oracle disagreement that is not a product defect belongs to the architect.

## 5. Searches

Each search prints nothing. A grep exit of 1 means no match, and an exit above 1 is an
error.

| # | Rule | Command |
|---|---|---|
| Q1 | No reply check, callback server, PKCE or error type left in the provider modules | `git grep --untracked -n -E 'http\.post\(\|\.json\(\)\|TransportError\|HTTPServer\|BaseHTTPRequestHandler\|hashlib\|base64\|class LoginError\|def (new_verifier\|code_challenge\|_handler)\(' -- src/mailroom/gmail_login.py src/mailroom/outlook_login.py` |
| Q2 | `oauth.py` names no provider | `git grep --untracked -n -i -E 'gmail\|outlook\|google\|microsoft\|yahoo' -- src/mailroom/oauth.py` |
| Q3 | Outlook sign-in names nothing from Gmail | `git grep --untracked -n -E 'gmail' -- src/mailroom/outlook_login.py` |
| Q4 | The CLI catches the shared error and does not pass an unowned client | `git grep --untracked -n -E '[a-z_]+_login\.LoginError\|^ +[a-z_]+_login\.new_http\(\),\|from mailroom\.[a-z_]+_login import' -- src/mailroom/cli.py` |
| Q5 | No broad catches, exclusions, logging or time and id shortcuts | `git grep --untracked -n -E 'except (Exception\|BaseException)[ :]\|pragma: no cover\|noqa\|datetime\.now\|from mailroom\.(clock\|ids) import\|print\(\|logging' -- src/mailroom/oauth.py src/mailroom/gmail_login.py src/mailroom/outlook_login.py` |

The escaped pipes in the table are ordinary alternation pipes. Q4 is text-based, so
source review also checks for other spellings: a client made before the `try`, or
closed only on one path, or a `new_http` lookup bound at import.

## 6. Reasonable variations

- `contextlib.closing` or try/finally in place of `with`, if every path closes.
- `gmail_login.Callback` written with `functools.partialmethod` or a plain `__init__`,
  as long as it subclasses `oauth.Callback` and defaults to gmail.
- `token_reply` reading the JSON in one or two `try` blocks, catching `ValueError`
  and `AttributeError`, or checking `isinstance(body, dict)` first.
- Private helpers inside `oauth.py`, a module docstring, and extra behavior tests in
  the coder's test file.
- `__all__` in `gmail_login` listing more than the re-exported names.

Not variations:

- a copy of `LoginError`, `Callback`, the pages or PKCE left in a provider module;
- a `provider` default on `oauth.Callback`;
- `token_reply` also applying a scope rule, or taking a provider-specific URL itself;
- `login()` closing its client;
- a changed error text, consent URL, form field or scope rule;
- the empty-token rule still differing between providers.

## 7. Verdict

Write `docs/reviews/phase-04k-shared-oauth.md`, starting `# Review: Phase 4k`, with the
exact conventions-format head and findings. Include:

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

> Use $phase-coder to implement only Phase 4k from docs/phases/phase-04k-shared-oauth.md
> in this checkout. Read the required project docs and every given test. Run Start and
> all Acceptance commands; append progress. Do not read the verification guide or write
> a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4k against docs/phases/phase-04k-shared-oauth.md
> and docs/verification/phase-04k-shared-oauth.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probes, searches and
> scratch-only spot checks; write only docs/reviews/phase-04k-shared-oauth.md.
