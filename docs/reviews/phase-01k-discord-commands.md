# Review: Phase 1k

- Verdict: FAIL
- Passed: 518
- Findings: 2
- Approved deviations: None
- For the architect: test_commands.use counts every callback on one FakeDiscord, so the second command in the two list tests fails len(replies) <= 1 even though both replies match the expected text.

## Findings

4.1 | src/mailroom/interactions.py:80 | expected a type 2 event whose name is not a command returns ignored with no request | found KeyError on data name
7 | docs/progress.md:102 | expected one Phase 1k progress entry headed ## Phase 1k: Discord commands | found no Phase 1k heading

Parts that needed a repair: none

Built beyond the spec: none

## Detail

`src/mailroom/commands.py` and `tests/integration/test_commands_more.py` exist. `grep -c "^## Phase 1k: " docs/progress.md` prints `0`. `docs/progress.md` still ends at the Phase 1j entry, and `git status --short` does not list it. The guide says to stop with FAIL when that count is not 1.

G1 `.venv/bin/python scripts/check.py --first core` exit 1. It stopped at tests (core): 518 passed, 3 failed, 0 skipped. The tests step and critical coverage were not run. Rerun: `.venv/bin/python scripts/check.py --section core`.

`tests/integration/test_interactions.py::test_a_slash_command_is_left_for_later` builds a type 2 event from a button press, so `data` has no `name`. `_slash` reads `event["data"]["name"]` and raises `KeyError`. Requirement 4.1 requires `ignored` and no request when the name is not one of the commands.

`test_the_lists_are_sorted_in_code_blocks` and `test_empty_lists_say_so` fail on the second `use()` call. The two callback bodies are the trusted and muted replies those tests expect. The given helper counts every callback stored on that `FakeDiscord`, so the second command sees both. That is recorded for the architect, not as a finding.

Spot checks, the probe, coverage, and the later gates were not run. The core section already failed, and the progress entry is absent. `.venv/bin/python scripts/check_reports.py --phase 1k` names that missing entry on the review and on `docs/progress.md`, and does not print `Reports OK.`
