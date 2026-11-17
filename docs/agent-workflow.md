# AI development workflow

Adapted from the current finances and tasking workflows on November 17, 2026.
This governs development roles, separate from the runtime email subagent in
[Architecture](architecture.md#agents). It introduces no mail-service behavior.

## Three separate roles

| Role | Canonical skill | Produces |
| --- | --- | --- |
| Architect | [phase-architect](../.agents/skills/phase-architect/SKILL.md) | Validated spec, given artifacts, guide and handoff |
| Coder | [phase-coder](../.agents/skills/phase-coder/SKILL.md) | One implementation, acceptance evidence and progress entry |
| Independent verifier | [phase-verifier](../.agents/skills/phase-verifier/SKILL.md) | Review of the exact implementation and scope |

Use a fresh session for each role. The coder reads the given tests in full but
does not read the verification guide or write a review. The verifier changes
only the review report. The architect handles specification errors; the coder
handles implementation errors. No role starts the next phase or another agent
without an assignment. There is no combined role.

The canonical skills live in `.agents/skills/` for Codex. Claude's matching
`.claude/skills/` entry points load those same files. Keep workflow rules in
the canonical skills and shared [phase conventions](phase-conventions.md).

## Tools available here

Run from the repository root with the existing project interpreter. All tools
operate on repository code, synthetic fixtures and temporary evidence only.

| Command after `.venv/bin/python` | Purpose |
| --- | --- |
| `.claude/skills/phase-architect/phase_status.py` | Tree, commits, unreviewed specs, latest progress/review and public names |
| `.claude/skills/phase-architect/phase_tools.py context <module ...>` | Source signatures, fields and constants without importing the application |
| `.claude/skills/phase-architect/phase_tools.py --help` | Existing clone, given-test failcheck, template, promotion and search tools |
| `scripts/check.py --first tooling --quiet` | Section-first full gates; summary and Sections on screen, full output in fresh temporary logs |
| `scripts/check.py --section tooling --quiet` | Focused tests without coverage; never substitutes for final acceptance |
| `scripts/accept.py --phase <id> --dry-run` | List spec acceptance/search commands without running them |
| `scripts/accept.py --phase <id>` | Execute trusted spec commands sequentially and retain full logs with exit codes |
| `scripts/accept.py --phase <id> --guide` | Execute guide Gates/Searches after the verifier's early checks |
| `scripts/progress.py --help` | Append a validated entry, or explicitly replace that phase on a correction |
| `scripts/check_reports.py [--phase <id>]` | Validate existing progress/review formats |

`check.py --quiet` preserves the normal gates, section counts, failure exit and
final `All checks passed.` line. `--log-dir` selects an evidence folder. Keep
tests and coverage reports sequential because they share `.coverage`.

`accept.py` executes shell code from the selected trusted Markdown document;
inspect `--dry-run` first. It stops on command errors, treats `git grep` exit 1
as no match, and uses shell pipefail. Its exit 0 means commands completed:
**the assigned agent must compare every output to Must show**, including counts,
scope, silent searches and probe results. It does not write progress, run early
Coder ran checks, execute spot-check prose or decide a verdict. Older guides
with different headings must be run directly. Use the spec's literal commands
when the helper cannot parse them; never alter a phase contract to fit a helper.

For example, after obtaining actual counts, write an entry with:

```zsh
.venv/bin/python scripts/progress.py --phase <id> --title '<spec title>' \
  --date YYYY-MM-DD --tests-before <N> --tests-after <passed> \
  --given <given count> --names '<public names or None>' --changed <path count>
```

Add repeated `--deviation` and `--follow-up` fields when needed. `--replace`
requires an existing entry for that phase; other phases stay unchanged. The
architect's history and the correction section retain failed-run history.
Non-phase workflow maintenance is documented here rather than as a fictitious
phase in `docs/progress.md`.

## Handoff

Use [the baseline and correction procedure](../.agents/skills/phase-architect/references/handoffs.md).
Given files and final planning documents must be committed before the coder
starts clean. Preserve unrelated work. If review needs isolation, compare the
exact scoped bytes and confirm imports come from the isolated source. Never
delete an existing scratch clone. Run verifier mutations only in disposable
copies; do not install tasking's in-place mutation runner here.

Use these prompts with a concrete id, document path and checkout:

> Architect: Use $phase-architect to specify Phase <id> in this checkout. Complete
> its spec, given files, verification guide, validation and handoff. Do not
> implement or launch the coder.

> Coder: Use $phase-coder to implement only Phase <id> from
> docs/phases/<filename>. Run every acceptance command and write progress.

> Verifier (another fresh session): Use $phase-verifier to review Phase <id>
> against docs/phases/<filename> and docs/verification/<filename>. Review the
> exact diff, including untracked files; write only docs/reviews/<filename>.

In Claude, use `/phase-architect`, `/phase-coder <id>` and `/phase-verifier <id>`.
All roles retain AGENTS.md's read order, offline fakes, synthetic data, no real
Keychain/data access, read-only mail, owner approval and privacy requirements.
These skills require no runtime connection to sibling projects.

## Workflow maintenance evidence: November 17, 2026

After Phase 4d's 1,212 tests, this workflow-only change added 18 tooling tests.
The verified starting suite for the next phase is **1,230 tests**: 77 tooling
and 1,153 core. Reconcile later phase progress against this maintenance evidence
rather than treating the older phase count as the current baseline.

`.venv/bin/python scripts/check.py --first tooling --quiet` ended with
`All checks passed.`; lint, format, all tests and critical coverage passed.
The sandbox-only first run failed to bind fake localhost callback servers; the
permitted rerun passed without contacting real services. Report validation printed
`Reports OK.`. Both current Phase 4d documents were parsed with `accept.py --dry-run`;
no historical phase acceptance or verdict was claimed for this workflow change.
Progress CLI smoke checks accepted a valid synthetic entry and refused a
duplicate without changing bytes. Six skill entry points' metadata and links
were checked directly; the bundled YAML validator needs PyYAML, absent from the
existing environment, so no package was installed to run it.

The clone-deletion and silent search-error fixes each have a regression test
observed failing before the fix. Mailroom production code, phase artifacts and
existing progress entries were not changed. Pre-existing audit and handoff work
was preserved, including the audit link already added to the docs index.
