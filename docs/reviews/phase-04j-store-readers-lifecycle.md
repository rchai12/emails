# Review: Phase 4j

- Verdict: PASS
- Passed: 1529
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Baseline and scope (fresh)

- Planning baseline 6057b24 (spec, guide, two given test files, probe). Implementation is commit f02db0c; working tree clean at review start.
- f02db0c changed only store/base.py, posts.py, tasks.py, approvals.py, messages.py, triage.py, tests/integration/test_store_readers.py and docs/progress.md. The spec, guide, given tests and probe are byte-identical to 6057b24 (G7 empty). No change to pyproject.toml, tests/sections.toml or any earlier test, and no method moved or public name added to `mailroom.store`.

## Gates (fresh)

- G1 `check.py --first core`: All checks passed; 1529 passed (full run also 1529); Sections tooling 85/0 failed, core 1444/0 failed; no skips or warnings.
- G2 coverage `src/mailroom/store/*`: TOTAL 100% (485 statements, 46 branches), exit 0.
- G3 given files: 29 passed, and 29 passed in each of 2 further runs (3 in all).
- G4 probe: oracle self-check ok; one connection and one migration per open ok; constructors refused at definition ok; 40 of 40 trials reached; reader invariants across 40 trials x 3 shuffles ok; FAILURES 0.
- G5: 1. G7: no output. G8: clean tree.
- Q1 to Q5: no matches (exit 1 each).

## Spot checks (scratch copy, bytecode writing off, mailroom imported from the copy, original bytes unchanged)

- S1 to S16: the deciding test file fails under each mutation, as required (the targeted cases fail, others pass).
- S17 (a second connection opened in `StoreBase.__init__`) is caught by the coder's `test_store_readers.py` lifecycle tests (2 failed), and by the probe (FAILURES 1). The missing-lifecycle-test condition in the guide does not apply.

## Source review

- The six constants match the spec's table, in order, as tuples; `messages._SELECT` is removed. Every one of the eleven readers passes the module constant to the shared `_select` when it runs (a global lookup, no default argument or import-time SQL). SQL tails and write statements are unchanged.
- `_select` names columns from `cursor.description` (bare names), refuses a repeated name with `StoreError("duplicate stored column: <name>")` before building any record, including for a read that finds no row, and carries no row value. Readers use column names only, with no positional fallback and no caught `KeyError`.
- One `due_columns` and `read_due` live in triage.py; approvals.py imports them and the private copies are gone.
- `StoreBase.__init_subclass__` refuses `__init__` in a class body at any depth with `TypeError("a store area must not define __init__: <name>")`; `StoreBase.__init__` is otherwise unchanged.
