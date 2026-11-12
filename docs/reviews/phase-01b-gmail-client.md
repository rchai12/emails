# Review: Phase 1b

- Verdict: PASS
- Passed: 212
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/gmail.py` exists, and `grep -c "^## Phase 1b: " docs/progress.md` prints `1`. The baseline files are committed.

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

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `212 passed`, 0 failed, 0 skipped, and there is no warnings summary. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          153 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 189 0 38 0 100%`.

G2: `30 passed in 0.04s`.

G4: `1`.

G5: `Reports OK.`

G6: no output.

G7:

```
 M docs/progress.md
?? src/mailroom/gmail.py
?? tests/integration/test_gmail_more.py
```

G8: the packages added since Phase 1a are `httpx` 0.28.1 and its dependencies `anyio`, `certifi`, `h11`, `httpcore`, and `idna`. Requirement 1 requires that install. No other package is new.

### Searches

Q1, Q2, Q3, Q4, Q6, Q7, Q8, and Q9 printed nothing. Q5 printed one line: `src/mailroom/gmail.py:210` `self.http.post(`.

### Spot checks

Each deciding test failed with the Broken value. `gmail.py` was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | issued tokens `['access-1']` |
| S2 | issued tokens `['access-1']` |
| S3 | `GmailAuthError` |
| S4 | `DID NOT RAISE GmailAuthError` |
| S5 | refs `m1, m3, m4` |
| S6 | 5 refs, `m3` twice |
| S7 | refs `m1, m3` only |
| S8 | `GmailUnavailable` `(response)` |
| S9 | `GmailUnavailable` `(response)` after the id was requested |
| S10 | `__suppress_context__` is `False` |
| S11 | text contains `secret body` |
| S12 | `SecretMissing` |
| S13 | `GmailUnavailable` `(400)` |
| S14 | `sent` first |
| S15 | `trust_env` is `True` |

S4 stops at pytest's "did not raise" message. S9 fails as `GmailUnavailable` `(response)`, which is the result of sending the unsafe id.

### Probe

`.venv/bin/python docs/verification/probe-01b.py` was run from the repository root and was not edited. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The seven tests in `tests/integration/test_gmail_more.py` each assert an error text from the spec, including a 500 token answer, a token body without `access_token`, a `raw` value that is not base64url, and a history page without `historyId`.
