# Baselines, corrections and evidence

## Ready means executable

A phase-spec assignment includes spec, guide, given files, failing-test
validation, probe/search validation and handoff. Finish independent work before
asking for a missing decision; report concrete blockers instead of workarounds.
Check paths, test ids/counts, Scope, acceptance and guide agreement; no TODOs.

Record the full baseline commit. Check `git status --short --untracked-files=all`
and `git diff HEAD -- <spec> <guide> <given files>`. Tracking does not prove final
content is committed. Account for required untracked inputs too.
The coder's actual checkout must start clean with final spec/given files
committed, per `docs/phase-conventions.md`. A dirty main tree does not authorize
bypassing this gate. Prepare a fresh isolated clone from the intended committed
baseline when appropriate. Never stash, reset, delete or commit unrelated work.
Do not call copied uncommitted specs committed. Prepare a complete planning
result before requesting commit authorization, unless already authorized.

Link the existing venv, exclude that symlink in the clone's `.git/info/exclude`,
set `PYTHONPATH=src:.` per command and verify `mailroom.__file__` is in the clone.
Do not install packages or change tracked ignore rules for temporary setup.
For mixed implementation review, copy only explicit phase paths and authorized
report, including deletions, to a fresh clone. Record the whole path inventory;
inspect overlaps in shared files such as progress.md. Compare bytes before
review and before copying back a verdict. Isolation makes current scope
reviewable; it does not establish that the original coder started clean.

## Corrections and stops

Missing implementation is not a spec defect. A stopped coder, environment
problem and uncommitted baseline differ from functional failure. Verifiers
report causes without fixing code or waiving gates.
Send code defects as requirement, observation and required result, without
prescribing bodies. For spec defects, preserve coder work, write a dated
Corrections section, validate corrected expectations against existing behavior,
and identify correction revision and live rerun commands. Keep failed-run
history; do not rewrite it as first-pass success.

Avoid duplicate progress headings. A correction may update its phase entry via
`scripts/progress.py --replace`, recording the correction in Deviations or
Follow-ups and preserving all other entries. Architect history retains the
failed run and final outcome. A stop's first Follow-ups item is
`Stopped: <requirement/gate> | <observation> | <what permits completion>`.

## Evidence and review

Tests and coverage run sequentially because they share `.coverage`. Keep full
output, exit codes, revision, changed paths and byte comparisons in temporary
logs. Do not hide failed commands behind tail pipes. The acceptance helper runs
trusted commands and summarizes evidence; it cannot decide PASS, approve a
deviation or replace the guide's early checks.

Reuse evidence for a narrowed reassessment only when the owner or a committed
correction authorizes it, relevant source/tests/dependencies/configuration match,
and prior commands/output are available. Label fresh versus reused evidence.
Otherwise run every literal gate. Changed behavior invalidates relevant prior
evidence; a narrow run never counts as a new full-suite pass.

Mutations run only in disposable scratch copies with checked import provenance
and original-byte comparisons. Never mutate the implementation under review or
import tasking's in-place spot-check runner. Interpret unexpected failures; a
passing mutation may expose a test weakness rather than a product defect.
