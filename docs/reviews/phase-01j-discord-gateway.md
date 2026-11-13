# Review: Phase 1j

- Verdict: PASS
- Passed: 540
- Findings: 0
- Approved deviations: None
- For the architect: probe-01j.py plans a server close of 4008, then treats that close_code as a client rate limit, so the probe prints FAILURES 1 although the client matched the model

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/gateway.py` and `tests/integration/test_gateway_more.py` exist, and `grep -c "^## Phase 1j: " docs/progress.md` prints `1`. The baseline files are committed.

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

`tests (core): passed` and `critical coverage: passed`. The `tests` step is `540 passed`, 0 failed, 0 skipped, and there is no warnings summary. That is the previous 490, the 35 given tests, and 15 extra tests. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          481 passed    0 failed    0 skipped
```

G3, run on the coverage data from that check before any later pytest: exit 0, `TOTAL 188 0 60 0 100%` (`gateway.py`).

G2: `35 passed in 0.16s`.

G4: `1`.

G5: `Reports OK.`

G6: `Version: 17.3` and `Requires:` empty.

G7: no output.

G8:

```
 M docs/progress.md
?? src/mailroom/gateway.py
?? tests/integration/test_gateway_more.py
```

G9: `pip list --format=freeze` matches the Phase 1i set plus `websockets==17.3` only.

### Searches

Q1 through Q10 printed nothing.

### Spot checks

Each deciding test failed with the Broken value. The edited module was then restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and `git diff HEAD` and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | first beat at `41.25` |
| S2 | `(10.3125, 1, None)` |
| S3 | `ValueError` unpacking 1 connection |
| S4 | `wss://gateway-us-east1-b.discord.gg/?v=10&encoding=json` |
| S5 | `DID NOT RAISE GatewayStopped` |
| S6 | last wait `60` |
| S7 | `True` |
| S8 | `wss://gateway.discord.gg.evil.test/?v=10&encoding=json` |
| S9 | `isEnabledFor` `True` |
| S10 | `DiscordUnavailable` |

S5 stops at pytest's "did not raise" message, which is the guide's "no exception".

### Probe

`.venv/bin/python docs/verification/probe-01j.py` was run from the repository root and was not edited. The self-check prints `ok`. The next line is `FAIL trial 14: the fake closed 4008`, and the last line is `FAILURES 1`.

Trial 14's plans include a server close of 4008. The addresses, Identify-or-Resume choices, waits and stop code matched the model, and that connection had sent one frame. Replaying all 150 trials the same way found no case where the client differed from the model, and no unplanned 4002, 4007 or 4008. The printed failure is the probe reading a close it scheduled as a client rate limit.

The extra tests assert behavior. Addresses outside the given cases are accepted or refused as listed. No Hello within the time limit closes with 4000 and the next connection resumes. A `send` that finds the socket closed resumes, and a closed Identify connects again without a session. A frame that is not JSON, and an unknown op, are ignored. `stop()` already true opens nothing, after the token has been read. A `WebSocketException` while connecting waits 1 second and then identifies. The default stop runs until `gateway stopped (4004)`.
