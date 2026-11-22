# Review: Phase 4l

- Verdict: FAIL
- Passed: 1577
- Findings: 1
- Approved deviations: None
- For the architect: The fake's _list in tests/fakes.py drops SPAM and TRASH mail before any fetch, so a Gmail test that reaches the fetch filter must put the labels on a message after a history round; the guide's Y14 note could say so.

## Findings

Tests to write: Gmail skips mail labelled both INBOX and SPAM | tests/integration/test_sync_adapters.py:71 | expected a test that fails when the SPAM check is removed from the Gmail fetch filter (src/mailroom/gmail_sync.py:61) | found test_gmail_skips_mail_labelled_both_inbox_and_spam delivers the message on a first run, where FakeGmail's list already omits SPAM and TRASH mail, so fetch is never reached; with the SPAM check deleted that test passes (1 passed) and the whole suite passes; the product code itself matches the spec

Parts that needed a repair: none

Built beyond the spec: none

## Baseline and scope (fresh: git inspection and byte comparison)

- Planning baseline 8c96004 (spec, guide, given tests, probe, docs/testing.md). Implementation is commit 879c414, working tree clean at review start apart from this report. G7 diff against HEAD: no output; `git diff 8c96004 HEAD --stat` lists only docs/progress.md, gmail_sync.py, mail_sync.py (new), outlook_sync.py, service.py and tests/integration/test_sync_adapters.py, all in the spec's Scope.
- service.py changes only the SyncResult import. No dependency, coverage exclusion, logging, broad catch, finally, or change to earlier tests, fakes or probes. Windows, link rules, inbox/spam/trash/folder rules and bookmark handling are unchanged; the bookmark is saved last, outside any finally.
- Progress entry: one "## Phase 4l:" entry, 1559 -> 1577 (given 12), no deviations.

## Gates (fresh)

- G1 check.py --first core: All checks passed; 1577 passed; Sections tooling 85/0 failed, core 1492/0 failed; no skips or warnings.
- G2 coverage mail_sync 66/10, gmail_sync 42/2, outlook_sync 41/4: TOTAL 100%, exit 0.
- G3 given files: 12 passed, three runs.
- G4 probe-04l: all lines ok, FAILURES 0. G4b probe-01n: FAILURES 0. G4c probe-04b: FAILURES 0.
- G5: 1. G7: no output. G8: clean tree.
- Q1 to Q5: no matches (exit 1 each); source review found no second clock read, no store call in an adapter, and run_round is called through the module.

## Spot checks (scratch copy, mailroom imported from the copy, original md5s unchanged)

- Y1 to Y13: the deciding test fails under the mutation, as required.
- Y14 (drop the SPAM check): the coder's INBOX plus SPAM test PASSES, and so does the full suite. This is the finding above; the other coder tests (profile order, expiry-only catch, false store.add) are meaningful and were not mutated further.

## Source review

- run_round reads clock.now() once, then the bookmark, then begin(), resumes or lists, skips stored ids before fetching, catches only ValueError for envelopes, and saves the bookmark after the last message. mail_sync.py names no provider; adapters catch only their own expiry error and MessageGone/ValueError on fetch.
