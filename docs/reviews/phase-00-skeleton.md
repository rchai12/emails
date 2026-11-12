# Review: Phase 0

- Verdict: FAIL
- Passed: 96
- Findings: 1
- Approved deviations: A leading ~ is expanded with Path.expanduser(), which also expands ~user.
- For the architect: Commit the spec and given files (G6 cannot see edits to untracked given files); the package passed the behavioral gates, and G7 fails only because that baseline is still uncommitted.

## Findings

G7 | docs/progress.md:12 | expected git status --short to list only the six new src/mailroom modules, docs/progress.md, and any tests/unit/test_*_more.py | found 17 paths, including 5 modified tracked files and untracked given files

Parts that needed a repair: none

Built beyond the spec: none

## Detail

Coder ran: the six `src/mailroom` modules exist, `.venv/bin/python` and `.venv/bin/mailroom` exist, and `grep -c "^## Phase 0: " docs/progress.md` prints `1`.

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

`tests (core): passed`. The `tests` step is `96 passed`, 0 failed, 0 skipped, and there is no warnings summary. Sections:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core           37 passed    0 failed    0 skipped
```

The earlier `tests (core)` section table is `core 37 passed, 0 failed, 0 skipped`.

G2, run immediately after G1: exit 0, `TOTAL 65 0 6 0 100%`.

G3: `96 passed in 0.14s`.

G4: `mailroom 0.1.0`.

G5: `Reports OK.`

G6: no output. These paths are untracked, so `git diff HEAD` cannot show an edit inside a given file. The collected counts match the spec: clock/ids 5, config 10, keychain 19, cli 3, report tests 59.

G7: `git status --short` prints 17 paths:

```
 M .claude/skills/phase-architect/SKILL.md
 M .claude/skills/phase-architect/history.md
 M .gitignore
 M docs/architecture.md
 M docs/roadmap.md
?? .claude/skills/phase-architect/phase_status.py
?? AGENTS.md
?? CLAUDE.md
?? docs/phase-conventions.md
?? docs/phases/
?? docs/progress.md
?? docs/testing.md
?? docs/verification/
?? pyproject.toml
?? scripts/
?? src/
?? tests/
```

`docs/progress.md` records the same count. The progress entry's `Changed files: 17` matches that list. No `tests/unit/test_*_more.py`.

G8: `pip list --format=freeze` contains `mailroom` 0.1.0, the `pyproject.toml` dependencies and their dependencies, and `pip`. No package sits outside that set. `setuptools` is not installed in the environment.

### Searches

Q1 through Q7 each printed nothing.

### Spot checks

Each deciding test failed, then the module was restored from the copy outside the repository, `src/mailroom/__pycache__` was removed, and the checksums, `git diff HEAD`, and `git status --short` matched the pre-check copies.

| # | Result |
|---|---|
| S1 | failed `assert 493 == 448` (0o755 left in place, 0o700 required) |
| S2 | failed `DID NOT RAISE ConfigError` (no exception). The failure text stops at that message. |
| S3 | failed with both paths equal to `.../data` |
| S4 | failed with the real home. The Broken column names that result. |
| S5 | failed `__suppress_context__` is `False` |
| S6 | failed `calls == [('mailroom', 'Gmail')]` |
| S7 | failed `DID NOT RAISE SecretMissing`. The failure text stops at that message. |
| S8 | failed with `KeyringError` propagating |
| S9 | failed with `SecretMissing` |
| S10 | failed `'0.1.0\n'` |
| S11 | failed `tzinfo` is `None` |

S2 and S7 are notes: the failure text is pytest's "did not raise" message, which is the broken outcome the column names.

### Probe

`/tmp/probe-00.py` was run from the repository root and then deleted. Every check line ends in `ok`. The probe's last line is `FAILURES 0`.
