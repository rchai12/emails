# Review: Phase 1h

- Verdict: PASS
- Passed: 441
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/checkpoint.py`, `src/mailroom/discord_post.py`, `tests/integration/test_discord_post_more.py`, and `tests/integration/test_store_posts_more.py` exist, and `grep -c "^## Phase 1h: " docs/progress.md` prints `1`. The baseline files are committed. `tests/unit/test_checkpoint_more.py` was not added; coverage of the new code was already complete.

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

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `441 passed`, 0 failed, 0 skipped, and there is no warnings summary. That is the previous 407, the 30 given tests, and 4 extra tests. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          382 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 352 0 66 0 100%` (`checkpoint.py` 38, `discord_post.py` 53, `store.py` 190, `config.py` 71).

G2: `30 passed in 0.14s`.

G4: `1`.

G5: `Reports OK.`

G6: no output.

G7:

```
 M docs/progress.md
 M src/mailroom/config.py
 M src/mailroom/store.py
?? src/mailroom/checkpoint.py
?? src/mailroom/discord_post.py
?? tests/integration/test_discord_post_more.py
?? tests/integration/test_store_posts_more.py
```

G8: `pip list --format=freeze` matches the Phase 1g set. No package is new.

### Searches

Q1 through Q10 printed nothing.

### Spot checks

Each deciding test failed with the Broken value. The edited module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | Subject ``Use `code` ...`` |
| S2 | row two has 2 buttons |
| S3 | `allowed_mentions` missing |
| S4 | `posted=1` |
| S5 | `[('mailroom', 'discord.bot-token')]` |
| S6 | `StopIteration` |
| S7 | `True` |
| S8 | `DID NOT RAISE ConfigError` |

S8 stops at pytest's "did not raise" message, which is the guide's "no exception".

### Probe

`.venv/bin/python docs/verification/probe-01h.py` was run from the repository root and was not edited. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.

The extra tests assert behavior. `open_discord_http()` uses a 30 second timeout, ignores proxy settings, and does not follow redirects. A 200 whose body is not JSON stops the round as `response` and leaves both posts queued. A 401 stops as `401`, leaves both posts queued, and sends one request. An empty database has no pending posts, and `post()` for an unknown key is `None`.
