# Review: Phase 2d

- Verdict: PASS
- Passed: 901
- Findings: 0
- Approved deviations: None
- For the architect: S6's removed unanswered guard raises KeyError 'nodeadline' from the checkpoint 1 mute reply; the guide's broken value is ('already', ...)

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: `src/mailroom/store/approvals.py` exists, and `grep -c "^## Phase 2d: " docs/progress.md` prints `1`. The baseline given files are committed. `git status --short` lists `docs/progress.md`, `src/mailroom/checkpoint.py`, `src/mailroom/interactions.py`, `src/mailroom/store/__init__.py`, `src/mailroom/store/approvals.py`, `tests/integration/test_interactions_second_more.py`, and `tests/unit/test_checkpoint_second_more.py`.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `901 passed` in 4.19s, 0 failed, 0 skipped. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          842 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (382 statements, 144 branches). G2: `172 passed`. G4: `1`. G5: `Reports OK.` G6 is empty. G7 is empty. G8 lists only the seven Scope paths. G9 freeze matches the Phase 2c list, 35 packages, including `websockets==17.3`. Q1 through Q7 print nothing.

The probe prints `oracle self-check: ok`, `every press and form follows the model and Discord accepts each reply: ok`, and `FAILURES 0`.

S1 through S5 and S8 through S12 each failed with the Broken value. S7 failed with the deadline `Thursday 2026-11-12`, which is `date(2026, 11, 12)`. S6 failed with `KeyError: 'nodeadline'`: an unanswered `nodeadline` press falls into the checkpoint 1 mute reply, which looks up that action in the checkpoint 1 answer text. That is a different failure from `('already', ...)`, so it is a note. After every edit the module was restored from the copy outside the repository, `src/mailroom/__pycache__` and `src/mailroom/store/__pycache__` were removed, and `git diff HEAD` and `git status --short` matched the snapshot.

`Approval` is a frozen dataclass exported from `mailroom.store`, and `Store` subclasses `ApprovalStore` last. `record_approval` inserts from a Yes or Edit answer inside one write, with `ON CONFLICT DO NOTHING`. A Yes or an accepted title replaces the card with checkpoint 2. Approve, No deadline, Not a task, and a readable task form record one decision and show the closed card. Approve is omitted when nothing is proposed, and the Evidence field stays, with `EVIDENCE_EXPIRED`, after the extraction is gone. The two extra tests assert a long link leaving only Show full text, and a decision another writer already stored being refused.
