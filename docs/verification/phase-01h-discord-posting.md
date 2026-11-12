# Verification guide: Phase 1h (Discord posting)

Spec: `docs/phases/phase-01h-discord-posting.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/checkpoint.py`
- `src/mailroom/discord_post.py`
- `tests/integration/test_discord_post_more.py`
- `tests/integration/test_store_posts_more.py`
- `grep -c "^## Phase 1h: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01h-discord-posting.md src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_checkpoint.py tests/unit/test_config_discord.py tests/integration/test_store_posts.py tests/integration/test_discord_post.py scripts/critical_modules.txt docs/verification/probe-01h.py` fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: 30.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; `critical coverage: passed`; at least N + 30 passed, 0 failed, 0 skipped |
| G2 | `.venv/bin/python -m pytest tests/unit/test_checkpoint.py tests/unit/test_config_discord.py tests/integration/test_store_posts.py tests/integration/test_discord_post.py --no-cov -q` | `30 passed` |
| G3 | `.venv/bin/python -m coverage report --include=src/mailroom/checkpoint.py,src/mailroom/discord_post.py,src/mailroom/store.py,src/mailroom/config.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| G4 | `grep -c "^## Phase 1h: " docs/progress.md` | `1` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 1h` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- src/mailroom/schema.py src/mailroom/discord_layout.py tests/fakes.py tests/integration/test_store.py tests/integration/test_store_sync.py tests/unit/test_checkpoint.py tests/unit/test_config_discord.py tests/integration/test_store_posts.py tests/integration/test_discord_post.py scripts/critical_modules.txt docs/verification/probe-01h.py` | no output |
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
| S1 | `checkpoint.py` | Stop replacing backticks in blocks | `tests/unit/test_checkpoint.py::test_email_text_stays_inside_code_blocks_and_cannot_close_them` | Subject `Use ˋcodeˋ ...` | Subject ``Use `code` ...`` |
| S2 | `checkpoint.py` | Keep the link button only when `len(link) < 512` | `tests/unit/test_checkpoint.py::test_a_link_too_long_for_a_button_is_left_out` | row two ends with `Open email` | row two has 2 buttons |
| S3 | `checkpoint.py` | Leave out `allowed_mentions` | `tests/unit/test_checkpoint.py::test_the_whole_message_for_an_extracted_email` | `{"parse": []}` | key missing |
| S4 | `discord_post.py` | On a non-200, go on to the next post instead of stopping | `tests/integration/test_discord_post.py::test_a_failed_send_stops_the_round_and_is_retried_next_time[rate-limited]` | `posted=0, waiting=2` | `posted=1` |
| S5 | `discord_post.py` | Read the token before checking for pending posts | `tests/integration/test_discord_post.py::test_nothing_to_post_reads_no_token` | calls `[]` | `[('mailroom', 'discord.bot-token')]` |
| S6 | `store.py` | In `queue_notified`, ignore `notify` | `tests/integration/test_store_posts.py::test_every_notified_verdict_is_queued_once_in_the_order_decided` | `2` | `StopIteration` (a third id is asked for) |
| S7 | `store.py` | In `mark_posted`, update a post already posted | `tests/integration/test_store_posts.py::test_a_posted_item_records_its_discord_message_once` | `False` | `True` |
| S8 | `config.py` | Check the channel with `\d` instead of `[0-9]` | `tests/unit/test_config_discord.py::test_a_channel_that_is_not_an_id_is_refused_without_echoing_it[wide-digits]` | `ConfigError` | no exception |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-01h.py` from the repository root. It is a given file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the data folder and touches no network or Keychain.

It checks, beyond the given tests: 3,000 random messages with hostile text (markdown, backticks, mentions, links, fields at their limits, long links) are all accepted by `FakeDiscord`'s checks, show each email-derived string only as the whole inside of a code block with no backtick, keep the title and footer fixed, and carry six button ids that lead back to the item. Then 40 trials of 12 rounds post random batches through random failures (lost replies, 429s, 502s, network errors); every notified email ends with exactly one Discord message, recorded against the right message id, and none is left queued.

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | Only httpx for the network, no websocket or Discord library | `git grep --untracked -n -E '(import\|from) (socket\|ssl\|imaplib\|smtplib\|requests\|aiohttp\|websockets\|discord)([^A-Za-z_]\|$)\|(import\|from) http([^.A-Za-z_]\|$)\|http\.client\|urllib\.request\|(import\|from) urllib([^.A-Za-z_]\|$)' -- src` |
| Q2 | httpx only where a phase allowed it | `git grep --untracked -n -E 'httpx' -- src ':!src/mailroom/gmail.py' ':!src/mailroom/gmail_login.py' ':!src/mailroom/extractor.py' ':!src/mailroom/triage.py' ':!src/mailroom/discord_post.py'` |
| Q3 | Discord's address only in the given layout | `git grep --untracked -n -E 'discord\.com\|discordapp' -- src ':!src/mailroom/discord_layout.py'` |
| Q4 | Posting never edits, deletes, or uses webhooks, interactions or the Gateway | `git grep --untracked -n -E '\.(patch\|put\|delete)\(\|"(PATCH\|PUT\|DELETE)"\|webhooks\|/interactions\|gateway' -- src/mailroom/discord_post.py src/mailroom/checkpoint.py` |
| Q5 | The body and authentication results never go to Discord | `git grep --untracked -n -E 'body_text\|authentication_results' -- src/mailroom/checkpoint.py src/mailroom/discord_post.py` |
| Q6 | No sleeping or retry loop | `git grep --untracked -n -E 'sleep\(\|while \|retry_after' -- src/mailroom/discord_post.py` |
| Q7 | No token or exception text in an error | `git grep --untracked -n -E 'raise [A-Za-z]+\(f\|raise [A-Za-z]+\([a-z_]*(token\|error\|response)' -- src/mailroom/discord_post.py` |
| Q8 | No email text or token in logs | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py'` |
| Q9 | Time and ids only through `clock` and `ids` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid\|from mailroom\.(clock\|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q10 | Full coverage is earned, not excused | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/checkpoint.py src/mailroom/discord_post.py src/mailroom/store.py src/mailroom/config.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- Building blocks and buttons with private helpers, or from loops over `L.FIRST_ROW` and `L.SECOND_ROW`.
- `queue_notified` as one `INSERT ... SELECT` per row or a loop, as long as ids come from `ids.new_id()` in the stated order.
- Reading each post's record and verdict inside the loop or all at once.
- Catching `httpx.TransportError` around the `post` call only, or around the JSON read too.
- `stopped` built from `response.status_code` with `str()`.
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/phase-01h-discord-posting.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1h`), then run `.venv/bin/python scripts/check_reports.py --phase 1h`; it must print `Reports OK.`
