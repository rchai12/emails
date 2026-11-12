# Roadmap

## Build order and acceptance tests

Status: Phases 0 to 1f done. Phase 1g specified (`docs/phases/phase-01g-triage-result.md`); result pending.

Build one stage at a time, and move on only when its test passes. Stage N is Phase N, split into lettered sub-phases (`1a`, `1b`) when it is too big.

0. **Skeleton**: the `mailroom` package, the check tooling, and the seams every later phase uses (clock, ids, settings with a private data folder, Keychain reads).
   Test: 96 given tests pass, critical modules fully covered, `mailroom version` prints `mailroom 0.1.0`. Done.
1. **Gmail ingestion, triage and the first-approval Discord message**, with no task creation.
   Test: 30 real emails, including bills and other mail with a `List-Unsubscribe` header, produce sensible verdicts with no actionable email missed; a re-fetch creates no duplicates; Show full text appears only to you and not in the channel history; a button press from another Discord user is ignored; the extractor runs at a usable speed while the Mac's other services are busy.
   Sub-phases:
   - **1a** the record, the raw-MIME parser and the SQLite store (dedup, 24-hour clearing). Done.
   - **1b** the Gmail client: token refresh and the four read calls, against a fake Gmail. Done.
   - **1c** Gmail sync: the bookmark, inbox only, dedup, first run (3 days), catch-up after an outage. Done.
   - **1d** the Gmail login command: one-time browser consent that stores the refresh token. Done.
   - **1e** sender authentication and the rules. Done.
   - **1f** the extractor: prompt, schema, validation, a fake model. Done.
   - **1g** storing the triage result (cleared after 24 hours), the notify decision and ranking. Specified.
   - **1h** Discord checkpoint 1.
   - **1i** the poll loop that joins them.
2. **Deadline checkpoint and combined approval**, sending approved tasks to a stub tasks app.
   Test: relative dates resolve correctly, each shows its evidence quote, and only emails meeting every clearly-dated condition get combined approval.
3. **Send approved tasks to the real tasks app.**
   Test: an approved email produces exactly one task, even when the send is retried; a follow-up in the same thread links to it instead of creating a duplicate, including when the follow-up arrives more than 24 hours later.
4. **live.com adapter** using the same pipeline.
   Test: identical emails give identical verdicts from Gmail and live.com.
5. **Yahoo adapter** over IMAP using the same pipeline.
   Test: identical emails give identical verdicts from all three providers; a poll leaves every message unread and unchanged in Yahoo; a `UIDVALIDITY` change creates no duplicates.
6. **Hardening.**
   Test: an email containing instructions ("create 20 tasks") produces at most one junk proposal; an email forging a trusted sender's address is treated as untrusted; an obvious phishing email is flagged and ranked last; a rejected sync bookmark triggers a catch-up with no duplicates and one Discord message; a failed Discord send is retried until it goes through; a flood of emails arrives as ranked digests with none missing, launchd restarts the service after it is killed, the email subagent reports on Discord when the service is unreachable, email text is gone after 24 hours while dedup keys remain, and a revoked token or app password raises an alert.

## Deferred items

V1 stays narrow on purpose; each item below is a later decision, not a rejection.

- Sending or drafting replies (would be a separate, gated tool)
- Auto-creating tasks for trusted senders
- Attachment handling
- Labeling or flagging messages inside Gmail, Outlook or Yahoo (needs more than read-only access)
- Learning beyond sender scores, such as per-topic importance
- Fuzzy matching of related emails across threads with vector embeddings (embeddings would count as email text under the 24-hour retention rule)
