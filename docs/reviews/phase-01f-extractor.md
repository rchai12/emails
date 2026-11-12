# Review: Phase 1f

- Verdict: PASS
- Passed: 352
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/extractor.py` and `tests/integration/test_extractor_more.py` exist, and `grep -c "^## Phase 1f: " docs/progress.md` prints `1`. The baseline files are committed.

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

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `352 passed`, 0 failed, 0 skipped, and there is no warnings summary. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          293 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 230 0 62 0 100%` (`extractor.py` 154, `extractor_prompt.py` 15, `config.py` 61).

G2: `29 passed in 0.07s`.

G4: `1`.

G5: `Reports OK.`

G6: no output.

G7:

```
 M docs/progress.md
 M src/mailroom/config.py
?? src/mailroom/extractor.py
?? tests/integration/test_extractor_more.py
?? tests/unit/test_config_extractor_more.py
```

G8: `pip list --format=freeze` matches the Phase 1e set. No package is new.

### Searches

Q1 through Q10 printed nothing.

### Spot checks

Each deciding test failed with the Broken value. The edited module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | `Sent: Tuesday 2026-11-10 07:59` |
| S2 | `<EMAIL >hi` |
| S3 | `assert False` on the exact-limit ending |
| S4 | `ModelUnavailable` `(400)` |
| S5 | an `Extraction` |
| S6 | an `Extraction` |
| S7 | an `Extraction` |
| S8 | an `Extraction` |
| S9 | an `Extraction` |
| S10 | an `Extraction` |
| S11 | an `Extraction`, `deadline=None` |
| S12 | an `Extraction` |
| S13 | `ModelUnavailable` `(network)` |
| S14 | `DID NOT RAISE ConfigError` |
| S15 | `MAILROOM_DATA_DIR must be an absolute path` |

S3's `endswith` assertion prints `assert False` when the exact-limit body no longer ends without the cut note. S14 stops at pytest's "did not raise" message.

### Probe

`.venv/bin/python docs/verification/probe-01f.py` was run from the repository root and was not edited. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The extra tests assert behavior. A 200 that is not JSON, has no message, or is a list is `Rejected("response")`, and a JSON list in `content` is `Rejected("content")`. `[::1]`, `[::1]` with a port, and `localhost` are accepted; a user name and `https` are refused without echoing the user name. `open_model_http()` has a 120 second timeout, `trust_env` false, and `follow_redirects` false. An empty time zone makes the model unavailable before a request. A deadline may omit the time, `24:00` and a time without a deadline are rejected, a non-actionable email may have an empty title, a reason requires suspicion, and an unknown confidence or a non-text date is rejected.
