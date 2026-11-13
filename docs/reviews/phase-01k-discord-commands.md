# Review: Phase 1k

- Verdict: PASS
- Passed: 580
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Detail

The reviewed code is `git diff 3ef3e19 HEAD` (through `87e301d`). The diff gates were run against HEAD. `git diff HEAD` of the given files, including `tests/integration/test_commands.py`, is empty. The helper change is inside that range and is the Corrections change: `use` counts only callbacks from the start of its own call.

`git diff --stat 3ef3e19 HEAD` is the six Scope paths, that helper change, the Corrections section, this review, and the two skill files as they stood in `87e301d`. `git status --short` also lists newer uncommitted edits to those two skill files. They are not in HEAD and were not judged.

G1 `.venv/bin/python scripts/check.py --first core` exit 0. The tests step is `580 passed` in 2.52s, 0 failed, 0 skipped, no warnings. Last lines:

```
Sections:
  tooling        59 passed    0 failed    0 skipped
  core          521 passed    0 failed    0 skipped
== critical coverage

Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

G3, run immediately after that, exit 0, `TOTAL` 100% (350 statements, 108 branches). G2: `33 passed`. G4: `1`. G8 freeze matches the Phase 1j list, including `websockets==17.3` and no new package. Q1 through Q10 print nothing. Probe: `oracle self-check: ok`, `commands follow the model and every reply fits: ok`, `FAILURES 0`.

Spot checks S1 through S8 each failed as designed, then the files were restored (`git diff HEAD` and `git status --short` matched the snapshots). S7's message held the response body. S8 exited 1.

Requirements: the guild id is `tests/unit/test_config_guild.py`; registration is `test_the_five_commands_replace_the_servers_commands`; addresses and lists are `test_trust_adds_the_exact_address_in_lower_case`, `test_untrust_and_unmute_remove_only_their_own_status`, and `test_a_long_list_is_cut_with_a_count`; a type 2 event with no name is `test_a_slash_command_is_left_for_later`; another user or channel is `test_a_command_from_anyone_else_or_elsewhere_is_refused`; the CLI is `test_the_setup_command_registers_and_reports`. The extra file asserts a non-string application id, a non-list command body, a non-string address, a missing token, and a DM that uses `user.id`.
