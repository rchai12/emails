# Review: Phase 2e

- Verdict: PASS
- Passed: 961
- Findings: 0
- Approved deviations: None
- For the architect: S7's removed no-extraction guard raises IntegrityError for an empty title; the guide's broken value is AttributeError

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `from mailroom.checkpoint import combined_message` and `from mailroom.deadlines import deadline_passed` exit 0, and `grep -c "^## Phase 2e: " docs/progress.md` prints `1`. The baseline given files are committed. `git status --short` lists the seven production and progress paths plus `tests/integration/test_interactions_combined_more.py` and `tests/integration/test_store_combined_more.py`.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `961 passed` in 4.67s, 0 failed, 0 skipped. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          902 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (695 statements, 252 branches). G2: `131 passed`. G4: `1`. G5: `Reports OK.` G6 is empty. G7 is empty. G8 lists only the nine Scope paths. G9 freeze matches the Phase 2d list, 35 packages, including `websockets==17.3`. Q1 through Q7 print nothing.

The probe prints `oracle self-check: ok`, `each post keeps the card chosen at its first send, once: ok`, `presses on the combined card follow the model: ok`, and `FAILURES 0`.

S1 through S6, S8, and S9 each failed with the Broken value. S3's second send was the checkpoint 1 card. S9's card was missing `nonce` and `enforce_nonce`. S7 failed with `sqlite3.IntegrityError: CHECK constraint failed: (answer IN ('yes', 'edit')) = (title != '')`. The handler treats a missing extraction as an empty title through `_proposed`, so removing that guard records an empty title and the schema refuses it. That is a different failure from `AttributeError`, so it is a note. After every edit the module was restored from the copy outside the repository, `src/mailroom/__pycache__` and `src/mailroom/store/__pycache__` were removed, and `git diff HEAD` and `git status --short` matched the snapshot.

`deadline_passed` is the public form of the 2b past check, and `clearly_dated` uses it. `choose_card` sets `posts.card` only while it is `NULL`. `post_pending` stores that choice before the send and rebuilds the stored card. `record_combined` writes the answer and the approval in one write, and rolls both back when the schema refuses the approval. A combined press records both through that method, and a missing title opens the task form. The two extra tests assert an unknown item has no card to choose, and a decision another writer already stored is refused.
