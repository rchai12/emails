# Roadmap

## Build order and acceptance tests

Status: Phases 0 to 3b done; 3c waits for the tasks app; 4a done; 4b is specified.

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
   - **1g** storing the triage result (cleared after 24 hours), the notify decision and ranking. Done.
   - **1h** posting checkpoint 1 messages to Discord, retry-safe. Done.
   - **1i** handling button presses: the owner check, Show full text, Trust, the answers and the Edit title form. Done.
   - **1j** the Gateway connection that delivers presses: heartbeats, resume, backoff, a stop on fatal closes. Done.
   - **1k** the `/trust`, `/untrust`, `/trusted`, `/unmute` and `/muted` commands, registered by `mailroom discord-commands`. Done.
   - **1l** `mailroom run`: the poll loop and the Gateway listener as one service, each part failing on its own. Done.
   - **1m** Discord alerts: a credential stopped working, the Gateway stopped, the model unreachable for a while, and the catch-up summary. Done.
   - **1n** fixes from the [Phase 1 audit](phase-01-audit.md), part 1: ids written `<account>/<provider id>` and the account on the card, and the data folder excluded from Time Machine. Done.
   - **1o** fixes from the audit, part 2: single-statement inserts for problems and alerts, and one shared Discord send helper for cards and alerts. Done.
2. **Deadline checkpoint and combined approval**, sending approved tasks to a stub tasks app.
   Test: relative dates resolve correctly, each shows its evidence quote, and only emails meeting every clearly-dated condition get combined approval.
   Sub-phases (later ones are planned when each is specified):
   - **2a** `store.py` split into a package with one module per area, `Store`'s API unchanged, and every write committed or rolled back as a whole. Done.
   - **2b** the clearly-dated rule in code: a deadline reader for the evidence quote and every condition for combined approval, as pure functions. Done.
   - **2c** triage decides and stores whether each email is clearly dated, with the proposed deadline kept past 24 hours (migration 8). Done.
   - **2d** the checkpoint 2 card in place after Yes or Edit title (Approve, Edit with a free-text deadline, No deadline, Not a task), and the decision recorded (migration 9). Done.
   - **2e** the combined card for clearly dated email, one step instead of two, chosen once at posting (migration 10). Done.
   - **2f** approved tasks queued and sent to a stub tasks app on this Mac, keyed by provider and message ID so a retry never duplicates, with an alert after 15 minutes of failures (migration 11). Done.
3. **Follow-ups, and the real tasks app.**
   Test: an approved email produces exactly one task, even when the send is retried; a follow-up in the same thread links to it instead of creating a duplicate, including when the follow-up arrives more than 24 hours later.
   Sub-phases (later ones are planned when each is specified):
   - **3a** the follow-up card for an email in a thread with an approved item (Add to task, New task, Not a task), chosen once at posting (migration 12). Done.
   - **3b** Add to task sends a link to the new email on the existing task to the stub tasks app, keyed so a retry never duplicates, once that task has its id (migration 13). Done.
   - **3c** connecting your own tasks app, adopting the stub's contract and adding its sign-in. Deferred until the tasks app exists (owner's decision, Nov 13, 2026); stage 4 goes first.
4. **live.com adapter** using the same pipeline.
   Test: identical emails give identical verdicts from Gmail and live.com.
   Sub-phases (later ones are planned when each is specified):
   - **4a** the Graph client: rotating tokens, inbox delta rounds and the raw message, read-only, against a fake Graph. Done.
   - **4b** Outlook sync: the delta bookmark, inbox only, dedup, first run (3 days), catch-up after an expired link.
   - **4c** `mailroom outlook-login`: browser consent on a 127.0.0.1 listener that stores the refresh token.
   - **4d** Outlook in the service: settings, each round, alerts, the card footer, and stage 4's test.
5. **Yahoo adapter** over IMAP using the same pipeline.
   Test: identical emails give identical verdicts from all three providers; a poll leaves every message unread and unchanged in Yahoo; a `UIDVALIDITY` change creates no duplicates.
6. **Hardening.**
   Test: an email containing instructions ("create 20 tasks") produces at most one junk proposal; an email forging a trusted sender's address is treated as untrusted; an obvious phishing email is flagged and ranked last; a rejected sync bookmark triggers a catch-up with no duplicates and one Discord message; a failed Discord send is retried until it goes through; a flood of emails arrives as ranked digests with none missing, an unanswered card gets one follow-up after 30 minutes and is then listed as pending, launchd restarts the service after it is killed, the email subagent reports on Discord when the service is unreachable, email text is gone after 24 hours while dedup keys remain, and a revoked token or app password raises an alert.

## Deferred items

V1 stays narrow on purpose; each item below is a later decision, not a rejection.

- Sending or drafting replies (would be a separate, gated tool)
- Auto-creating tasks for trusted senders
- Attachment handling
- Labeling or flagging messages inside Gmail, Outlook or Yahoo (needs more than read-only access)
- Learning beyond sender scores, such as per-topic importance
- Fuzzy matching of related emails across threads with vector embeddings (embeddings would count as email text under the 24-hour retention rule)
