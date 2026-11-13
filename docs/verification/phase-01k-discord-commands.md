# Verification guide: Phase 1k (Discord commands)

Spec: `docs/phases/phase-01k-discord-commands.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/commands.py`
- `tests/integration/test_commands_more.py`
- `grep -c "^## Phase 1k: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01k-discord-commands.md src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_commands.py tests/integration/test_register_commands.py tests/unit/test_config_guild.py scripts/critical_modules.txt docs/verification/probe-01k.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 33.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 32 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/integration/test_commands.py tests/integration/test_register_commands.py tests/unit/test_config_guild.py --no-cov -q` | `33 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/commands.py,src/mailroom/interactions.py,src/mailroom/config.py,src/mailroom/cli.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1k: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1k` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_commands.py tests/integration/test_register_commands.py tests/unit/test_config_guild.py scripts/critical_modules.txt docs/verification/probe-01k.py docs/verification/probe-01j.py` | no output |
| G7 | `git status --short` | only the Scope paths |
| G8 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `commands.py` | Reply with the address as typed, not lower-cased | `tests/integration/test_commands.py::test_trust_adds_the_exact_address_in_lower_case` | block holds `sam@example.test` | `Sam@Example.TEST` |
| S2 | `commands.py` | `/untrust` removes whatever status the address has | `tests/integration/test_commands.py::test_untrust_and_unmute_remove_only_their_own_status[untrust-not-trusted]` | `'unchanged'` | `'untrusted'` |
| S3 | `commands.py` | Fit lists in 2,000 characters instead of `L.LIST_LIMIT` | `tests/integration/test_commands.py::test_a_long_list_is_cut_with_a_count` | `...and 5 more.` | `...and 4 more.` |
| S4 | `interactions.py` | Skip the user check for commands | `tests/integration/test_commands.py::test_a_command_from_anyone_else_or_elsewhere_is_refused[another-user]` | `'refused'` | `'untrusted'` |
| S5 | `interactions.py` | Skip the channel check for commands | `tests/integration/test_commands.py::test_a_command_from_anyone_else_or_elsewhere_is_refused[another-channel]` | `'refused'` | `'untrusted'` |
| S6 | `commands.py` | Call `set_sender_status` without catching `ValueError` | `tests/integration/test_commands.py::test_an_address_that_is_not_one_is_refused[not-an-address-trust]` | `'bad-address'` | `ValueError` |
| S7 | `commands.py` | Raise `DiscordUnavailable(response.text)` for a non-200 | `tests/integration/test_register_commands.py::test_a_failure_names_only_the_status[unauthorized]` | `discord unavailable (401)` | the response's text in the message |
| S8 | `cli.py` | Import `open_discord_http` by name instead of through the module | `tests/integration/test_register_commands.py::test_the_setup_command_registers_and_reports` | exit `0` | exit `1` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01k.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks, beyond the given tests: 80 trials of up to 29 commands (all five, from the owner and others, in the channel and elsewhere, with mixed-case, backtick, accented, long and broken addresses, against lists of 0, 3 or 60 senders). The trusted and muted lists must end exactly as a model kept from the commands says; every outcome must match; every reply must be private, mentions off, under 2,000 characters and accepted by Discord; and each list reply must show the right leading run and count the rest.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | No other network library, no asyncio or threads | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|asyncio\|threading\|discord)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request' -- src` |
| Q2 | httpx only where a phase allowed it | `git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py' ':!src/mailroom/discord_post.py' ':!src/mailroom/interactions.py' ':!src/mailroom/gateway.py' ':!src/mailroom/commands.py'` |
| Q3 | Discord's address only in the given layout | `git grep --untracked -n -E 'discord\.com\|discordapp' -- src ':!src/mailroom/discord_layout.py'` |
| Q4 | Registration only replaces this server's commands; no deletes, global commands or channel posts | `git grep --untracked -n -E '\.(delete\|patch)\(\|/channels/\|/global\|applications/[^@{]' -- src/mailroom/commands.py` |
| Q5 | The CLI opens the client through the module, so tests can replace it | `git grep --untracked -n -E 'from mailroom\.discord_post import .*open_discord_http' -- src/mailroom/cli.py` |
| Q6 | No secret is read outside `register_commands` | `git grep --untracked -n -E 'get_secret\|set_secret' -- src/mailroom/interactions.py src/mailroom/cli.py` |
| Q7 | No token, address or response text in an error | `git grep --untracked -n -E 'raise [A-Za-z]+\(f\|raise [A-Za-z]+\([a-z_.]*(token\|error\|value\|address\|text\|json)' -- src/mailroom/commands.py` |
| Q8 | No email text, address or token in logs | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'` |
| Q9 | Time and ids only through `clock` and `ids` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q10 | Full coverage is earned, not excused | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/commands.py src/mailroom/interactions.py src/mailroom/config.py src/mailroom/cli.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- `block` shared from `checkpoint.py` or `interactions.py`, or a private copy in `commands.py` with the same rule.
- Validating an address by calling `store.sender_status` first, or by catching `ValueError` from `set_sender_status`.
- Building the command-name set from `L.COMMANDS` once at import.
- The CLI catching all three errors in one `except`.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01k-discord-commands.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1k`), then run `.venv/bin/python scripts/check_reports.py --phase 1k`; it must print `Reports OK.`
