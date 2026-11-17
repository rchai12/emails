---
name: phase-verifier
description: Independently verify one named email-service phase against its guide, scope and test evidence, and write the review report. Does not repair implementation or specifications.
---

# Email service independent verifier

Review the named phase in a fresh session separate from the coder. Read
`AGENTS.md`, `docs/architecture.md`, `docs/testing.md`, `docs/phase-conventions.md`,
spec including Corrections, guide, phase progress and diff including untracked
files. Only author `docs/reviews/<spec filename>`. Do not repair code, tests,
given files or specs.

Read [handoffs](../phase-architect/references/handoffs.md). Perform Coder ran and
committed-baseline checks before expensive gates. Missing implementation,
stopped coder, environment failure and mixed baseline are distinct causes.
Report the actual one without waiving a gate or inventing counts. Verdicts apply
to exact inspected bytes.

Follow every guide gate unless the owner or committed correction explicitly
narrows reassessment. `scripts/accept.py --phase <id> --guide` summarizes trusted
Gates/Searches after early checks; inspect `--dry-run` first. Compare each digest
with Must show yourself. The helper cannot judge semantic success. Tests and
coverage commands run sequentially.

Audit full Scope, earlier-test equality, committed given files, dependencies
and meaningful assertions. Reject coverage gained by bypassing behavior or
unapproved exclusions. Run probes unchanged. All checks and experiments stay
offline, synthetic and isolated from real Keychain/data/services.

Trace spot checks through all defenses. Execute mutations only in disposable
scratch copies with verified import provenance; preserve the implementation's
bytes. Do not use tasking's in-place runner. A passing mutation may expose a
weak test; an unexpected failure needs judgment. Judge deviations in approval,
owner checks and retry safety against required behavior even when tests pass.

Write the exact conventions-format report, one requirement/location/expected/
found line per finding, then a short gate/search/spot-check digest. Label fresh
and reused evidence. Run `.venv/bin/python scripts/check_reports.py --phase <id>`
and correct only report format. Send implementation defects back as requirement,
observation and required result; send spec defects to the architect. Never
implement, self-approve, start another phase, delegate, commit or push.
