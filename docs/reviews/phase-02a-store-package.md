# Review: Phase 2a

- Verdict: PASS
- Passed: 730
- Findings: 0
- Approved deviations: None
- For the architect: probe-02a.py seed 21 never fails queue_notified after a successful id, so partial stays 0 and the probe prints FAILURES 1

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: the eight package files exist, `src/mailroom/store.py` is gone, and `grep -c "^## Phase 2a: " docs/progress.md` prints `1`. The baseline given files are committed. `git status --short` lists `docs/progress.md`, the deleted `src/mailroom/store.py`, and the new `src/mailroom/store/` package.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `730 passed` in 3.36s, 0 failed, 0 skipped, no warnings. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          671 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (323 statements, 34 branches). G2: `45 passed`. G4: `gone`. G5 prints nothing. G6: `1`. G7: `Reports OK.` G8 is empty. G9 is empty. G10 lists only the Scope paths. G11 freeze matches the Phase 1o list, 35 packages, including `websockets==17.3`. Q1 through Q8 print nothing.

The probe prints `a failed call changes nothing and leaves the file unlocked: FAIL too few failures reached: {'injected': 208, 'refused': 456, 'partial': 0}` and `FAILURES 1`. Every failure it did raise left the tables unchanged and the file unlocked. `partial` stays 0 because, across 394 `queue_notified` calls, only one turn had two waiting rows, and on that turn `ids.new_id` was not the failing function. The halfway rollback the probe is trying to count is covered by `test_a_write_that_fails_halfway_keeps_none_of_its_rows`. The progress entry already records this.

Spot checks S1 through S8 each failed as designed, then the files were restored (`git diff HEAD` and `git status --short` matched the snapshots). S1 and S2 left one `Post`. S3 left the file locked (`unlocked()` was `False`). S4 did not raise. S5 defined `close` in `mailroom.store.messages`. S6 reported `Verdict.__module__` as `mailroom.store`. S7 added `connection`. S8 kept the extraction.

| Requirement | Where it is checked |
| --- | --- |
| 1 The package and the public names | `test_store_package.py`; G4 |
| 2 `StoreBase` | `test_each_method_lives_in_its_area[close]`, `test_each_name_is_defined_in_its_area_and_still_imported_from_the_store` |
| 3 Area classes and `Store` | `test_each_area_is_its_own_module`, `test_the_store_keeps_exactly_its_public_methods` |
| 4 `_write()` commits or rolls back | `test_a_write_that_fails_halfway_keeps_none_of_its_rows`, `test_a_good_write_is_committed_at_once`; Q1 |
| 5 Every write is one block | `test_store_rollback.py`; the 685 earlier tests |
| 6 Critical list, each file covered | G1 critical coverage; G3 |
| 7 Progress entry | G6, G7 |
