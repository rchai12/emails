# Verification guide: Phase 4l (Extract provider-neutral sync policy)

Spec: `docs/phases/phase-04l-shared-sync-round.md`. Follow AGENTS.md and
docs/phase-conventions.md. Use the independent phase-verifier role in a fresh session.
Everything is synthetic: FakeGmail, FakeGraph and a scripted adapter, on temporary
database files. Never access real mail, Google, Microsoft, the Keychain or the data
folder.

## 1. Coder ran

Before the gates, inspect status, the tracked diff and untracked files. Require one
`## Phase 4l: ` progress entry and implementation changes in `src/mailroom/mail_sync.py`
(new), `gmail_sync.py`, `outlook_sync.py` and `service.py`. A stopped entry is not a
completed implementation. If the coder did not run or stopped, report that. Do not
treat every missing behavior as a new defect.

Require these to be committed: the spec, this guide, the two new given test files, the
probe and the `docs/testing.md` line that lists `mail_sync.py`. Record the full
planning-baseline commit and verify that their bytes match it (G7). Do not call a dirty
planning tree a coder diff. Do not waive this gate, and do not commit.

The only permitted implementation paths are the spec's Scope. Your report adds only
`docs/reviews/phase-04l-shared-sync-round.md`.

## 2. Gates

Run them in order from the repository root. G2 reads G1's coverage data before any
other test run. 12 given cases are new, so the minimum suite is 1559 + 12.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | `All checks passed.`; tests (core) passed with at least 1571 passed, 0 failed, skipped or xfailed, and no warnings; every Sections row has 0 failed |
| G2 | `.venv/bin/python -m coverage report --include='src/mailroom/mail_sync.py,src/mailroom/gmail_sync.py,src/mailroom/outlook_sync.py' --fail-under=100` | exit 0; TOTAL 100% |
| G3 | `.venv/bin/python -m pytest tests/integration/test_mail_sync.py tests/integration/test_sync_parity.py --no-cov -q` | 12 passed |
| G4 | `.venv/bin/python docs/verification/probe-04l.py` | check lines end ok; final FAILURES 0 |
| G4b | `.venv/bin/python docs/verification/probe-01n.py` | final FAILURES 0 |
| G4c | `.venv/bin/python docs/verification/probe-04b.py` | final FAILURES 0 |
| G5 | `grep -c '^## Phase 4l: ' docs/progress.md` | 1 |
| G6 | `.venv/bin/python scripts/check_reports.py --phase 4l` | Reports OK. |
| G7 | `git diff HEAD --stat -- docs/phases/phase-04l-shared-sync-round.md docs/verification/phase-04l-shared-sync-round.md tests/integration/test_mail_sync.py tests/integration/test_sync_parity.py docs/verification/probe-04l.py docs/testing.md` | no output |
| G8 | `git status --short --untracked-files=all` | only spec Scope paths, plus this review if already written |

Run G3 two more times. Every run must show 12 passed. The tests replace the clock and
use no threads or real waiting, so any failure is a finding.

`probe-01c.py` ended FAILURES 2 on predecessor code too, because its oracle predates
account-qualified ids. It is not a gate. Do not report its result as a defect of this
phase.

Inspect the full diff for these:

- unlisted changes to earlier tests, fakes or probes;
- dependencies;
- coverage exclusions;
- new logging or output;
- a changed window, link rule, inbox, spam, trash or folder rule, or bookmark;
- a provider named anywhere in `mail_sync.py`, comments and docstrings included;
- a second `SyncResult` class or a copied window constant;
- the bookmark saved in a `finally` or before the last message;
- a broad `except`, or a provider error other than the expiry error turned into `None`;
- a change to `service.py` beyond the import;
- weak assertions in the coder's tests, and whether they pin Gmail's `INBOX` plus `SPAM`
  skip.

## Requirement checks

Test prefixes: MS is `tests/integration/test_mail_sync.py::` and SP is
`tests/integration/test_sync_parity.py::`.

| Requirement | Deciding evidence |
|---|---|
| 1: `mailroom/mail_sync.py` | MS test_the_shared_names_live_in_mail_sync; MS test_a_first_round_reads_three_days_and_keeps_the_bookmark; MS test_a_later_round_resumes_from_the_bookmark_under_the_adapters_name; MS test_an_expired_bookmark_catches_up_with_an_hour_overlap_and_14_days_at_most (3 ids); MS test_a_stored_message_is_not_fetched_again_and_skips_are_left_out; MS test_an_interrupted_round_keeps_the_bookmark_and_what_it_stored; MS test_accounts_of_one_provider_keep_their_own_bookmarks_and_ids; probe shared-round line; Q2, Q5 |
| 2: `gmail_sync.py` | SP test_one_timeline_gives_the_same_rounds_through_the_shared_round[gmail]; `tests/integration/test_gmail_sync*.py` unchanged; the coder's `INBOX` plus `SPAM` test; G4b; Q1, Q4 |
| 3: `outlook_sync.py` | MS test_outlook_sync_loads_no_gmail_module; SP test_one_timeline_gives_the_same_rounds_through_the_shared_round[outlook]; `tests/integration/test_outlook_sync*.py` unchanged; G4c; Q1, Q3 |
| 4: `service.py` | MS test_the_shared_names_live_in_mail_sync (`service.SyncResult`); `tests/integration/test_service*.py` and `test_alerts_more.py` unchanged; Q4; source review |
| 5: compatibility | full suite; G4b, G4c; probe both-providers line; source review of the call order and adapter rules |
| 6: critical module | G7 (the `docs/testing.md` line is in the planning commit) |
| 7: progress | G5/G6 and the entry's factual contents |

## 3. Spot checks

Run spot checks only in disposable scratch copies of the current implementation and
tests:

- Use the existing venv and `PYTHONPATH=src:.`. Confirm that `mailroom.__file__` is
  inside the copy.
- Set `PYTHONDONTWRITEBYTECODE=1` and remove the copy's `__pycache__` folders first.
  Otherwise, two same-size mutations written within one second can run stale bytecode.
- Never mutate the implementation under review.
- Start each row from the original bytes and run the deciding test with `--no-cov`.
  Then discard only your mutation and compare bytes.
- If the coder's private code differs, locate the equivalent line. Do not prescribe
  helper or adapter class names.

| # | Function/boundary | One-line mutation | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| Y1 | FIRST_RUN | Read two days on a first run | MS test_a_first_round_reads_three_days_and_keeps_the_bookmark | start 2026-11-10T09:00 | start 2026-11-11T09:00 |
| Y2 | catch-up window | Drop the hour of overlap | MS test_an_expired_bookmark_catches_up_with_an_hour_overlap_and_14_days_at_most[2-days] | start 2026-11-13T08:00 | start 2026-11-13T09:00 |
| Y3 | catch-up window | Ignore the 14-day limit | MS test_an_expired_bookmark_catches_up_with_an_hour_overlap_and_14_days_at_most[20-days] | start 2026-11-19T09:00 | start 2026-11-13T08:00 |
| Y4 | gap | Count exactly 14 days away as a gap | MS test_an_expired_bookmark_catches_up_with_an_hour_overlap_and_14_days_at_most[14-days] | gap False | gap True |
| Y5 | catch-up result | Leave out when the account went offline | MS test_an_expired_bookmark_catches_up_with_an_hour_overlap_and_14_days_at_most[2-days] | offline_since NOW | None |
| Y6 | resumed kind | Name every resumed round delta | MS test_a_later_round_resumes_from_the_bookmark_under_the_adapters_name | history | delta |
| Y7 | run_round | Save the bookmark before storing the messages | MS test_an_interrupted_round_keeps_the_bookmark_and_what_it_stored | bookmark unchanged | bookmark moved |
| Y8 | storing step | Fetch a message that is already stored | MS test_a_stored_message_is_not_fetched_again_and_skips_are_left_out | no fetch y1 | fetch y1 |
| Y9 | storing step | Let an unusable envelope stop the round (catch `TypeError` in place of `ValueError`) | MS test_a_stored_message_is_not_fetched_again_and_skips_are_left_out | y3 to y5 skipped | ValueError |
| Y10 | run_round | Skip the adapter's begin | MS test_a_first_round_reads_three_days_and_keeps_the_bookmark | begin first | no begin |
| Y11 | outlook_sync imports | Take SyncResult from gmail_sync again | MS test_outlook_sync_loads_no_gmail_module | [] | ['mailroom.gmail', 'mailroom.gmail_sync'] |
| Y12 | Gmail fetch | Keep inbox mail in the trash | tests/integration/test_gmail_sync.py::test_mail_that_left_the_inbox_before_fetch_is_skipped[trash] | skipped | stored |
| Y13 | Outlook fetch | Keep mail outside the inbox folder | tests/integration/test_outlook_sync.py::test_mail_moved_out_of_the_inbox_before_its_fetch_is_skipped | skipped | stored |
| Y14 | Gmail fetch | Keep inbox mail labelled spam (drop the `SPAM` check) | the coder's `INBOX` plus `SPAM` test | skipped | stored |

These mutations were run against a throwaway scratch stand-in at planning time, not
against the coder's code. If a row fails in a different way, diagnose it. If a mutation
passes, the test may be weak rather than the product defective. Report the difference
either way. Y14 had no given or existing test at planning time. If the coder's tests do
not catch it, report the missing test as a finding against "Tests to write".

## 4. Probe

`.venv/bin/python docs/verification/probe-04l.py` runs offline. A seeded random
generator fixes every choice. The probe checks these:

- **Isolation.** A fresh interpreter imports `mailroom.mail_sync` and
  `mailroom.outlook_sync` and loads no `mailroom.gmail*` module.
- **No provider imports.** `mail_sync.py`'s own import statements name no provider
  module. The probe reads them with `ast`.
- **Shared objects.** The three windows keep their values. They and `SyncResult` on
  `gmail_sync`, and `SyncResult` on `outlook_sync` and `service`, are mail_sync's
  objects.
- **The shared round.** 60 seeded histories of 3 to 7 rounds each go through a scripted
  `yahoo` adapter. The histories include:
  - absences of a minute, five hours, two days and twenty days;
  - random expired bookmarks;
  - pages that repeat stored ids;
  - fetches that come back missing, with an unusable thread, time or link, or that fail.

  The probe's own oracle predicts every adapter call and its arguments, the
  `SyncResult`, and the bookmark. That includes no bookmark change after a failed round,
  and every kept message staying stored.
- **Both providers.** 12 seeded timelines go through FakeGmail and FakeGraph, wrapping
  `mail_sync.run_round`. The timelines have random steps, deliveries and expiries. Each
  round must match the oracle's kind, offline time, gap and exactly the messages
  delivered since the last round. Each round must also go through `run_round` once, and
  both providers must give the same rounds.

It does not check the adapters' inbox, spam, trash or folder rules, since it delivers
only inbox mail. It also never lands on exactly 14 days away. The tests cover both. It
reports names and counts, never payloads, and always reaches `FAILURES N`. Never edit
the probe. An oracle disagreement that is not a product defect belongs to the architect.

## 5. Searches

Each search prints nothing. A grep exit of 1 means no match, and an exit above 1 is an
error.

| # | Rule | Command |
|---|---|---|
| Q1 | No window, result type or round step left in the adapters | `git grep --untracked -n -E 'FIRST_RUN =\|CATCH_UP_[A-Z]+ =\|timedelta\(\|class SyncResult\|sync_state\(\|store\.(get\|add)\(\|parse_message\|stored_id\|Envelope\(\|clock\.' -- src/mailroom/gmail_sync.py src/mailroom/outlook_sync.py` |
| Q2 | `mail_sync.py` names no provider | `git grep --untracked -n -i -E 'gmail\|outlook\|google\|microsoft\|graph\|yahoo' -- src/mailroom/mail_sync.py` |
| Q3 | Outlook sync names nothing from Gmail | `git grep --untracked -n -E 'gmail' -- src/mailroom/outlook_sync.py` |
| Q4 | Nothing imports the shared names from `gmail_sync`, and `run_round` is looked up when called | `git grep --untracked -n -E 'from mailroom\.gmail_sync import\|gmail_sync\.(SyncResult\|FIRST_RUN\|CATCH_UP)\|import .*run_round\|^ +run_round,$' -- src/mailroom` |
| Q5 | No broad catches, `finally`, exclusions, logging or time and id shortcuts | `git grep --untracked -n -E 'except (Exception\|BaseException)[ :]\|pragma: no cover\|noqa\|datetime\.now\|from mailroom\.(clock\|ids) import\|print\(\|logging\|finally:' -- src/mailroom/mail_sync.py src/mailroom/gmail_sync.py src/mailroom/outlook_sync.py` |

The escaped pipes in the table are ordinary alternation pipes. Q1 and Q4 are text-based,
so source review also checks for other spellings: a second clock read, a store call
inside an adapter, or `run_round` bound at import under another name.

## 6. Reasonable variations

- Adapter classes with other private names, `__slots__`, or a profile stored in
  `begin()` under any attribute name.
- `Page` and `Fetched` with extra private helpers, as long as their public fields are the
  spec's.
- The round written as one function or with private helpers, and `stored` built in a
  loop or a comprehension.
- `resumed` as a class attribute or set in `__init__`.
- Extra behavior tests in the coder's test file.

Not variations:

- a provider adapter that reads the store, builds an `Envelope` or saves the bookmark;
- `run_round` taking a provider name or branching on one;
- the clock read twice, or the profile read before the bookmark;
- `resume` returning `None` for any error other than the provider's expiry error;
- a changed `SyncResult` field, kind name or value;
- changes in `service.py` beyond the import.

## 7. Verdict

Write `docs/reviews/phase-04l-shared-sync-round.md`, starting `# Review: Phase 4l`, with
the exact conventions-format head and findings. Include:

- the gate and Sections output;
- coverage;
- the repeated G3 runs;
- the searches;
- the probe results;
- the spot-check results.

Classify each defect by its requirement, the observed result and the required result.
Do not repair code or tests. Run G6 after writing it.

## Handoff prompts

Only after the final planning documents and given files are committed and the coder's
checkout is clean:

> Use $phase-coder to implement only Phase 4l from
> docs/phases/phase-04l-shared-sync-round.md in this checkout. Read the required project
> docs and every given test. Run Start and all Acceptance commands; append progress. Do
> not read the verification guide or write a review.

In another fresh session after the coder completes:

> Use $phase-verifier to review Phase 4l against
> docs/phases/phase-04l-shared-sync-round.md and
> docs/verification/phase-04l-shared-sync-round.md. Check the committed given-file
> baseline, exact diff and untracked files. Run all gates, probes, searches and
> scratch-only spot checks; write only docs/reviews/phase-04l-shared-sync-round.md.
