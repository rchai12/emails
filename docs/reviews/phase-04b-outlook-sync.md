# Review: Phase 4b

- Verdict: PASS
- Passed: 1160
- Findings: 0
- Approved deviations: None
- For the architect: The given sync file collects 17 tests, so G2 prints 17 passed, and probe trial 4 leaves AAMk8 unstored after it moves into the inbox once the link has already expired and its received time is outside the catch-up window.

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

`git status --short` lists the four Scope paths: `docs/progress.md`, `src/mailroom/gmail_sync.py`, `src/mailroom/outlook_sync.py`, and `tests/integration/test_outlook_sync_more.py`. `git diff HEAD -- src/mailroom/gmail_sync.py` adds only `"delta"` to `SyncResult.kind`. `grep -c "^## Phase 4b: " docs/progress.md` prints `1`. The baseline given files are committed.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `1160 passed` in 6.17s, 0 failed, 0 skipped. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core         1101 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G2 prints `17 passed` for `tests/integration/test_outlook_sync.py`. The file has ten plain tests, two failed-round cases, and five odd-link cases. The spec's given count of 18 counts one more than the file contains. The suite total is 1160 because `tests/integration/test_outlook_sync_more.py` adds one test that asserts a declined `store.add` leaves `stored` empty, keeps the record the wrapper already wrote, and still saves the bookmark.

G3, taken from the check.py coverage data before any later pytest, exit 0 with `TOTAL 100%` (outlook_sync.py 51 statements and 10 branches, gmail_sync.py 56 statements and 8 branches).

G4 and the probe: `oracle self-check: ok`; `sync stores what reaches the inbox, once, and never loses it: FAIL trial 4: AAMk8= is in the inbox but not stored`; last line `FAILURES 1`. Replaying seed 42 shows AAMk8 born in junk at `2026-11-17T09:21:00Z` on round 7, the link expiring on round 11 while that round's sync fails and the bookmark stays put, then a move into the inbox on round 12. The catch-up lists by received time, so the old message is outside the window, and the new delta link starts after that move. The probe excuses a moved-in message only when `expire_deltas` runs and the message is already in `moved_in`. This move happens after that call. The code matches the spec's catch-up limit.

G5 prints `1`. G6 prints `Reports OK.` G7 and G8 print nothing. G9 lists the four Scope paths. G10 `.venv/bin/python -m pip list --format=freeze` is the same 35 packages as before this phase. Q1 through Q6 print nothing.

S1 through S7 each failed with the Broken value, then `outlook_sync.py` was copied back. `cmp` matched the saved copy, `git diff HEAD` matched the snapshot, and `git status --short` matched the snapshot.
