# Review: Phase 1d

- Verdict: PASS
- Passed: 271
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/gmail_login.py` and `tests/integration/test_gmail_login_more.py` exist, and `grep -c "^## Phase 1d: " docs/progress.md` prints `1`. The baseline files are committed.

### Gates

G1 `.venv/bin/python scripts/check.py --first core` exit 0. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `271 passed`, 0 failed, 0 skipped, and there is no warnings summary. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          212 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 158 0 32 0 100%` (`gmail_login.py` 126, `keychain.py` 32).

G2: `29 passed in 0.34s`.

G4: `1`.

G5: `Reports OK.`

G6: no output.

G7:

```
 M docs/progress.md
 M src/mailroom/cli.py
 M src/mailroom/keychain.py
?? src/mailroom/gmail_login.py
?? tests/integration/test_gmail_login_more.py
```

G8: `pip list --format=freeze` matches the Phase 1c set. No package is new.

### Searches

Q1, Q2, Q3, Q5, Q6, Q8, Q9, Q10, and Q11 printed nothing. Q4 printed two lines: `src/mailroom/gmail.py:218` `self.http.post(` and `src/mailroom/gmail_login.py:132` `http.post(`. Q7 printed one line: `src/mailroom/keychain.py:42` `keyring.set_password(`.

### Spot checks

Each deciding test failed. The edited module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | `DID NOT RAISE ValueError` |
| S2 | `__suppress_context__` is `False` |
| S3 | challenge ends `dnLI8=` |
| S4 | no `('code_challenge_method', 'S256')` |
| S5 | regex assertion is `assert None` |
| S6 | stderr holds `127.0.0.1 - -` |
| S7 | returned `'code-9'` |
| S8 | returned `'code-9'` |
| S9 | `StopIteration` |
| S10 | about 3.0 s |
| S11 | `DID NOT RAISE LoginError` |
| S12 | `ConnectError` |
| S13 | client ID and secret written |
| S14 | `consent request: client_id` |
| S15 | the consent address is the last line |

S1 and S11 stop at pytest's "did not raise" message. S5's regex assertion prints `assert None` when the redirect is not `http://127.0.0.1:<port>`. S14 stops in the fake consent check: ignoring `new_client` sends the stored client id, `client-id-0`, and the fake expects `client-id-1`, so the writes assertion is not reached.

### Probe

`.venv/bin/python docs/verification/probe-01d.py` was run from the repository root and was not edited. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The three tests in `tests/integration/test_gmail_login_more.py` assert behavior. A `POST` to the callback is 501, the wait still returns the real code, and the secret is not in the page or the terminal. A token `scope` that is a list is `gmail login failed: personal (response)`. `new_http()` has a 30 second timeout, `trust_env` false, and `follow_redirects` false.
