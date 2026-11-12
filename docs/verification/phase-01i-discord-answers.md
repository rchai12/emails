# Verification guide: Phase 1i (Discord answers)

Spec: `docs/phases/phase-01i-discord-answers.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/interactions.py`
- `tests/integration/test_interactions_more.py`
- `grep -c "^## Phase 1i: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01i-discord-answers.md src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_checkpoint_answered.py tests/unit/test_config_owner.py tests/integration/test_store_answers.py tests/integration/test_interactions.py scripts/critical_modules.txt docs/verification/probe-01i.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 40.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 40 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_checkpoint_answered.py tests/unit/test_config_owner.py tests/integration/test_store_answers.py tests/integration/test_interactions.py --no-cov -q` | `40 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/interactions.py,src/mailroom/checkpoint.py,src/mailroom/store.py,src/mailroom/config.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1i: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1i` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_checkpoint_answered.py tests/unit/test_config_owner.py tests/integration/test_store_answers.py tests/integration/test_interactions.py scripts/critical_modules.txt docs/verification/probe-01i.py` | no output |
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
| S1 | `interactions.py` | Skip the presser check | `tests/integration/test_interactions.py::test_a_press_from_anyone_else_or_elsewhere_changes_nothing[another-user]` | `'ignored'` | `'answered'` |
| S2 | `interactions.py` | Skip the channel check | `tests/integration/test_interactions.py::test_a_press_from_anyone_else_or_elsewhere_changes_nothing[another-channel]` | `'ignored'` | `'answered'` |
| S3 | `interactions.py` | Skip the already-answered check for presses | `tests/integration/test_interactions.py::test_a_second_answer_is_refused_privately` | `'already'` | `StopIteration` (the refused `record_answer` reads the clock a sixth time) |
| S4 | `interactions.py` | Show full text without replacing backticks | `tests/integration/test_interactions.py::test_show_full_text_is_a_private_code_block` | `ˋportalˋ` | `` `portal` `` |
| S5 | `interactions.py` | Cut the full text at 2000 instead of `L.FULL_LIMIT` | `tests/integration/test_interactions.py::test_a_long_email_is_cut_with_a_note` | 1,900 `a`s and the note | 1,901 `a`s, no note |
| S6 | `interactions.py` | Record the submitted title without `strip()` | `tests/integration/test_interactions.py::test_a_submitted_title_is_recorded_and_updates_the_card` | `'Pay the bill online'` | `'  Pay the bill online  '` |
| S7 | `interactions.py` | Drop `Cf` from the title's refused categories | `tests/integration/test_interactions.py::test_a_bad_title_is_refused_privately[zero-width]` | `'bad-title'` | `'answered'` |
| S8 | `interactions.py` | Reply before recording the answer | `tests/integration/test_interactions.py::test_a_failed_reply_keeps_the_answer_and_names_only_the_status` | answer `'notask'` | no answer (`None`) |
| S9 | `store.py` | `record_answer` with `INSERT OR REPLACE` | `tests/integration/test_store_answers.py::test_the_first_answer_is_kept` | second call `False` | `True` |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01i.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks, beyond the given tests: 60 trials of random sequences of up to 24 presses and submissions (the six actions and made-up ones, real and unknown item ids, the owner and a stranger, the channel and another one, good and bad titles, senders with and without an address, cards with and without a title). Each outcome must match a small model; only the owner's first answer is stored, with its title; every sender ends trusted, muted or untouched as the model says; Discord accepts every reply; and full text with backticks stays inside its block.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Only httpx for the network, no websocket or Discord library | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|websockets\|discord)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request\|(import\|from) urllib([^.A-Za-z_]\|$)' -- src` |
| Q2 | httpx only where a phase allowed it | `git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py' ':!src/mailroom/discord_post.py' ':!src/mailroom/interactions.py'` |
| Q3 | Discord's address only in the given layout | `git grep --untracked -n -E 'discord\.com\|discordapp' -- src ':!src/mailroom/discord_layout.py'` |
| Q4 | Replies need no secret; no token is read | `git grep --untracked -n -E 'keychain\|get_secret\|[Aa]uthorization' -- src/mailroom/interactions.py` |
| Q5 | Answering never edits other messages, posts to the channel or touches the Gateway | `git grep --untracked -n -E '\.(patch\|put\|delete)\(\|webhooks\|/channels/\|gateway' -- src/mailroom/interactions.py` |
| Q6 | No authentication results or summary sent from the handler | `git grep --untracked -n -E 'authentication_results\|[^_]summary' -- src/mailroom/interactions.py` |
| Q7 | No sleeping or retry loop | `git grep --untracked -n -E 'sleep\(\|while \|retry' -- src/mailroom/interactions.py` |
| Q8 | No email text, title or exception text in an error | `git grep --untracked -n -E 'raise [A-Za-z]+\(f\|raise [A-Za-z]+\([a-z_.]*(token\|error\|value\|title\|body\|content\|text\|json)' -- src/mailroom/interactions.py` |
| Q9 | No email text in logs | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py'` |
| Q10 | Time and ids only through `clock` and `ids` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q11 | Full coverage is earned, not excused | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/interactions.py src/mailroom/checkpoint.py src/mailroom/store.py src/mailroom/config.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Sharing the card's code between `checkpoint_message` and `answered_message` through a private helper.
- Checking the event's shape with `isinstance` at each step, or once up front.
- Reading the record and verdict before or after parsing the action, as long as an unknown item replies type 6.
- Answering a type 5 event whose action is not `title` with type 6.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01i-discord-answers.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1i`), then run `.venv/bin/python scripts/check_reports.py --phase 1i`; it must print `Reports OK.`
