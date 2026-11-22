# Mutation files for `phase_tools.py mutate`

`mutate` runs the guide's spot checks against a scratch stand-in during planning.
It applies one mutation at a time, runs the deciding test (and the probe when asked),
restores the file byte for byte, and reports `caught` or `MISSED` per row.

```zsh
.venv/bin/python .claude/skills/phase-architect/phase_tools.py mutate CLONE FILE.toml [--table]
```

- CLONE is a scratch clone from `clone ID --scratch DIR`. The tool refuses the
  repository itself.
- It removes the clone's `__pycache__` folders before every run and sets
  `PYTHONDONTWRITEBYTECODE=1`. Two same-size mutations written within one second
  otherwise run stale bytecode, which in 4h gave one false pass.
- When a row's deciding test still passes, it runs the `suite` files and names every
  test that does catch the mutation. Use one of those as the deciding test, or
  strengthen a test if none catches it.
- It reports a row whose `old` text is not found exactly once as `SKIPPED`, without
  running it.
- Exit codes: 0 means every row was caught, 1 means some were missed or skipped, 2
  means a bad file, the repository was passed as CLONE, or a restore failed.
- `--table` prints the guide's spot-check rows, using `prefixes` for short test ids.

Keep the file in scratch, next to the clone. It belongs to the stand-in, whose text
the coder's code will not match. Never commit it.

## Format

TOML, read with the standard-library `tomllib`. Strings with newlines use `"""`
or JSON-style `\n` escapes. `old` must match the stand-in exactly, including
indentation.

```toml
probe = "docs/verification/probe-04h.py"              # optional; used by rows with probe = true
suite = ["tests/integration/test_outlook_rotation.py"] # optional; searched when a row is missed

[prefixes]                                            # optional; short names in --table
OR = "tests/integration/test_outlook_rotation.py::"

[[mutation]]
id = "S7"                                             # unique; the guide's row number
file = "src/mailroom/outlook.py"                      # relative to the clone
where = "error"                                       # Function/boundary column
change = "Drop `from None`"                           # One-line mutation column
old = "            raise OutlookTokenUnsaved(self.account) from None"
new = "            raise OutlookTokenUnsaved(self.account)"
test = "tests/integration/test_outlook_rotation.py::test_a_new_token_the_keychain_refuses_is_reported_as_unsaved"
correct = "no cause/context"                          # Correct column
broken = "context kept"                               # Broken column
probe = true                                          # optional; the probe must fail too
```

Every row needs `id`, `file`, `where`, `change`, `old`, `new`, `test`, `correct` and
`broken`. With `probe = true`, a row counts as caught only if both the test and the
probe fail.

## In the workflow

1. Write the stand-in in the clone, and get the given tests passing on it.
2. Write one row per behavior the spec pins: each catch, each bound, each alert
   rule, each "never".
3. Run `mutate`. For each `MISSED` row, pick a deciding test from the suite list, or
   strengthen a given test and copy it back into the clone.
4. Run `mutate --table` and paste the rows into the guide's Spot checks. Replace the
   `correct` and `broken` cells with the distinct values the test sees, if they are
   still placeholders.
5. Mark the probe's rows `probe = true` to record which defects the probe catches in
   the spec's validation section.
