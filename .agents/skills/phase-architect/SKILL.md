---
name: phase-architect
description: Design, split, revise, or review email-service phase specs and verification guides, with validated given tests, probes and coder/verifier handoffs. Does not implement phases.
---

# Email service phase architect

Produce a complete executable spec for a coder and a guide for a separate
verifier. A planning assignment includes validation and handoff; a draft is an
intermediate artifact. Do not implement the feature or launch other agents.

Read `AGENTS.md`, `docs/architecture.md`, `docs/testing.md`, then
`docs/phase-conventions.md`. Read relevant design sections, the roadmap row,
progress deviations, latest relevant review and actual code contracts before
drafting. Read [handoffs](references/handoffs.md) before declaring work ready or
handling a failed review. Read [test helpers](references/test-helpers.md) before
writing given tests or a probe. Paths below are relative to the repository root.

## Establish facts and scope

Run `.venv/bin/python .claude/skills/phase-architect/phase_status.py` before
asserting phase status. Take N from verified suite evidence: start with the
latest actual phase progress and reconcile its review and subsequent tooling-only
test additions in `docs/agent-workflow.md`. Do not rerun the suite just to count.
Inspect `git status --short --untracked-files=all`
before repository writes. Preserve unrelated work; do not make it a deviation.
Use the existing `phase_tools.py context <module ...>` for signatures before
bodies. Search earlier tests for names, values, messages, response shapes,
schema-version pins and patched names before changing a contract.

Design docs govern the spec. Ask only about unresolved product choices, with
short options and a recommendation when useful. Record dated owner decisions
separately from architect choices. Treat owner-verified audit findings as input,
while checking current contracts and relevant drift. Cross-project changes
require reading the owning code/docs and identifying the work needed there;
they do not authorize edits to another project.

Aim for about 10 requirements, 3–5 public units, at most 30 given test functions,
one migration and roughly 300 changed production lines. Split larger work into
lettered phases before tests. Count parameter cases separately for acceptance.
Fix names, signatures, schemas, validation order, messages and observable results.
Give contract tests for critical modules, migrations and exact user-facing shapes;
leave bodies, private helpers and named behavior tests to the coder. Map every
requirement to a test with its deciding input. List exact Scope and sections.

Check mail-specific boundaries: account-prefixed ids, read-only provider calls,
24-hour deletion of email-derived fields, owner checks, approval before tasks,
keyed retries, plain-text limits, constant errors and local-only extraction with
closed schemas and fixed sampling. Update both critical-module lists when a
phase adds a critical path. Do not add an unapproved dependency.

## Validate before publishing

Resolve real unknowns with small offline spikes on synthetic inputs before
tests: library behavior, exceptions, logging or time-zone edges. Facts requiring
real mail/accounts/services/Keychain become owner "Verify before building" items.
Never build a reference feature, derive expected values from new code, or run
the full suite/check.py during scratch planning. More than about 30 lines of
scratch source beyond given parts signals implementation drift. No Codex hook
enforces this boundary; enforce it yourself.

Reuse `.claude/skills/phase-architect/phase_tools.py`; all commands start with
`.venv/bin/python`. Inspect subcommand help before write operations:

| Command | Purpose |
| --- | --- |
| `clone ID --scratch DIR` | Fresh failNNx clone, existing venv, checked imports |
| `failcheck CLONE TEST...` | Given-test failures and distinct reasons |
| `new ...`, `guide SPEC --out FILE` | Email spec/guide skeletons |
| `searches SPEC --cwd CLONE [--plant FILE]` | Searches; plant violations only in scratch |
| `promote CLONE FILE... --ignore TEST...` | Copy explicit given paths and run Start |
| `mutate CLONE FILE.toml [--table]` | Stand-in mutations, deciding tests, probe; guide rows ([format](references/mutations.md)) |

Choose a fresh scratch parent if a clone exists. Use `PYTHONPATH=src:.` for every
clone command and verify `mailroom.__file__` is inside it. Copy uncommitted
planning inputs deliberately and record provenance. Given files are committed
with the spec, never embedded. Validate only given tests in scratch, no coverage.
Collect exact counts with `.venv/bin/python -m pytest <files> --collect-only
--no-cov -q`. Separate missing behavior from import mistakes or bad expectations.
Use names-only stubs where collection needs new names; label already passing
guards. Failure-injection exceptions must not catch stub `NotImplementedError`.
Inspect assertions beyond the first failure, which have not executed yet.

Use literal expected rows/messages, readable parameter ids, `fixed_times` and
`fixed_ids` from `tests/support.py`, with one moment per allowed clock read.
For "same as" behavior, run the existing function on equivalent synthetic input.
Vary one refusal field at a time. Try migrations with existing synthetic rows
and every constraint. Explicitly lint/format probes, since Ruff excludes docs;
repeat after promotion so clone stubs cannot mask import errors.

From Phase 1b the probe is a given `docs/verification/probe-NNx.py`. Keep its
oracle small and independent: privacy, retention, retries, bounds or state
invariants, not a second implementation. Self-check known cases, force required
transitions and assert reach counts. Isolate each trial, seed randomness, and
distinguish fake state before/after resets. Import new names inside checks and
reach `FAILURES N` on missing behavior without exposing private data. Success
lines end in `ok`, then `FAILURES 0`. Validate oracle alone and intended failures
on the predecessor. Scheduled faults must respect earlier guarantees.

Every spot-check row names the function, exact mutation, full given-test id,
deciding input and distinct correct/broken values. Trace all defenses, schema
constraints, later reads and fake clock limits. Strengthen tests that cannot see
the mutation. Run them with `mutate`, not by hand, and take the guide's rows from
`--table`. Execute only in disposable scratch copies. An unrelated error is
not the intended evidence; a passing mutation may mean a weak test.

## Complete the handoff

Use established spec/guide sections and report formats. Manually cross-check
paths, collected ids/counts, Start expectations, coverage includes, given-file
diff gates, requirement mappings and guide agreement. Local phase_tools lacks
tasking's lint, stubcheck and search catalog; do not claim they exist. Older
phases include edited given tests, so state given count and net new count.

Acceptance starts with `scripts/check.py --first <sections>` using the project
interpreter. Coverage follows that check on its data. Include exact given tests,
probe, searches, reports, committed given-file equality and Scope gates. Validate
searches on legitimate code and planted violations in scratch. Distinguish no
match (grep exit 1) from execution errors. Avoid unsupported word boundaries and
searches that flag allowed calls. Keep output compact while retaining exit codes.

Complete spec, guide, given files and affected design/roadmap updates together.
Record "specified; result pending" in `.claude/skills/phase-architect/history.md`.
Use [handoffs](references/handoffs.md) to establish a concrete committed baseline
before declaring implementation ready. Do not silently commit, push, edit memory
or launch the coder. Report checks, unresolved owner items and concrete prompts
from `docs/agent-workflow.md`. A spec defect gets a dated correction, never a
weaker contract written to accommodate incorrect code.
