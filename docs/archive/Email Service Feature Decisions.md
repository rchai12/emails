# Email Service: Feature Decisions

Nov 9, 2026 · @Richard

## Purpose and scope

The email service watches Gmail and live.com, finds messages that need action, and sends proposals to the tasks app only after you approve them on Discord. It never creates tasks, writes to the calendar, or sends mail itself.

**In scope for v1**

- Read-only ingestion from Gmail and live.com
- Triage: rules first, then a local model that extracts action items
- Discord notifications for the first approval ("is this a task?")
- Submitting approved items to the tasks app as proposals

**Out of scope for v1**

- Sending or drafting replies
- Yahoo (no good API; see Ingestion)
- Attachments
- Creating tasks without approval

## Decisions at a glance

Every email becomes a proposal only after two human approvals, and the service holds the least access that still works.

| Decision | Choice | Reason | Rejected |
| --- | --- | --- | --- |
| Service boundary | Separate service from the tasks app | Own credentials, untrusted input, polling runtime | Module inside the tasks app |
| Mail scope | Read-only for Gmail and Microsoft Graph | Ingestion never needs send rights; limits token-theft damage | Full mailbox scope |
| Detecting new mail | Polling every 1 to 2 minutes | Works from a home machine with no public endpoint | Push webhooks or Pub/Sub |
| Triage order | Rules first, local model second | Most mail needs no model call | Model on every message |
| Who sees email text | Local model only | Raw email is personal data | Hosted model |
| Extractor design | No tools, strict JSON, validated in code | Injection can at worst produce a junk proposal | Tool-using agent reading mail |
| Task creation | Never automatic; two Discord approvals | You decide what becomes a task | Auto-create for trusted senders (deferred) |
| Discord content | Short local summary plus a link, no body | Discord stores what is posted | Full body in the message |
| Handoff | Proposal sent to the tasks app API | One approval path for every source | Direct writes to tasks or calendar |
| Yahoo | Deferred | No calendar or modern mail API; needs IMAP with an app password | Include in v1 |

## Ingestion

Gmail and live.com are read through their own APIs with read-only access, polled every 1 to 2 minutes, and normalized into one record shape so triage never knows which provider a message came from.

- **Gmail:** Gmail API, read-only scope, new mail found by polling with a stored history ID.
- **live.com:** Microsoft Graph, new mail found by polling with delta queries. Register the app for personal Microsoft accounts as well as work accounts.
- **Yahoo:** deferred. It would need IMAP with an app password behind the same adapter interface.
- **Normalized record:** provider, message ID, thread ID, sender, subject, received time, body text, link back to the message.
- **Deduplication:** every record is keyed by provider and message ID, so a retry or repeated fetch never creates a second proposal.
- **Tokens:** stored in the macOS Keychain or a vault, never in prompts or agent-readable files.

To verify before building: Google refresh tokens for apps left in testing mode can expire after about a week, which would silently stop ingestion. Check Google's current rules, and publish the app to production for yourself if needed.

## Triage pipeline

Deterministic rules drop most mail first, a local model extracts action items from what remains, and ordinary code decides whether to notify you.

1. **Rules.** Bulk-mail headers such as List-Unsubscribe, known newsletter senders, and your allow and block lists remove most messages with no model call.
2. **Extractor.** A local model with no tools reads the message and returns strict JSON: urgent, actionable, task title, explicit deadline, a short quote as evidence for the deadline, and confidence.
3. **Validation.** Code checks the JSON against the schema and rejects anything malformed.
4. **Decision.** Thresholds in code, not the model, decide whether to send a Discord notification. A per-hour notification cap stops a flood of crafted emails.

**Details**

- A follow-up in a thread you already approved links to the existing task instead of creating a new proposal.
- Repeated "not a task" answers for a sender lower that sender's score automatically.
- Relative dates such as "by Friday" are resolved against the email's sent date and your time zone, and the evidence quote is shown with the proposal.
- Email text goes only to the local model.

## Approval flow

An email reaches the tasks app only after two approvals from you, each on Discord.

&#91;embedded content: approval flow · 2 checkpoints\]

Shaded boxes are your decisions; everything else is automatic. At the first checkpoint the buttons are Yes, Edit title, Not a task and Mute sender. At the second they are Approve, Edit and No deadline. If you do not answer, the service sends one follow-up and then lists the item as pending; it never creates a task on a timeout.

## Security and privacy

A hostile email can at worst produce one junk proposal, because the code that reads it has no tools and no write access.

- **No tools for the reader.** The extractor outputs validated JSON only. Instructions inside an email are treated as text to describe, never as commands.
- **Least access.** Read-only mail scopes; the service holds no send, calendar or task-creation rights.
- **Local model only** for email text. A hosted orchestrator receives only an approved task title and time.
- **Discord content.** Messages carry sender, subject, a one-line local summary and a link, never the body, since Discord stores what is posted.
- **Rate limits.** A per-hour cap on notifications and per-sender trust scores, so unknown senders stay at proposal level until you approve.
- **Secrets.** OAuth tokens in the Keychain or a vault, revocable from your phone if the machine is lost.
- **Audit log.** Every state change records what triggered it and the original message ID.

## Interfaces

The email service talks to the rest of the system through one outbound call and a few read-only tools.

**Outbound: proposal to the tasks app**

Only after your first approval, the service submits a proposal with these fields: source (email), title, optional deadline, deadline evidence quote, confidence, provider and message ID, and a link to the message. It never sends email text.

**MCP tools for the orchestrator (read-only)**

| Tool | Returns |
| --- | --- |
| list\_pending\_emails | Metadata and local summaries of messages awaiting your decision |
| get\_email\_summary(id) | The local summary and the triage verdict for one message |
| get\_triage\_stats | Counts by outcome, notification cap status, last poll time per account |

No tool returns a message body to a hosted model, and none writes anything. Approvals happen on Discord, handled by the service, not by the agent.

## Non-goals and deferred items

V1 stays narrow on purpose; each item below is a later decision, not a rejection.

- Sending or drafting replies (would be a separate, gated tool)
- Auto-creating tasks for trusted senders
- Yahoo support through IMAP with an app password
- Attachment handling
- Labeling or flagging messages inside Gmail or Outlook (needs more than read-only access)
- Learning beyond sender scores, such as per-topic importance

## Open questions

Seven decisions are still yours to make before building.

- [ ] Flagging: read-only access cannot label messages in Gmail or Outlook. Is the Discord notification enough as the flag in v1?
- [ ] Which local model runs the extractor, and how accurate is it on 20 to 30 of your real emails?
- [ ] What is the starting trusted-sender list, and what notification cap per hour?
- [ ] How long to wait before the single follow-up on an unanswered proposal?
- [ ] How long are message records kept, and are bodies stored at all or only summaries?
- [ ] Should a clearly dated email be allowed to skip to one combined approval step?
- [ ] Where does the service run relative to the Mac Studio's other services, and who restarts it?

## Build order and acceptance tests

Build one stage at a time, and move on only when its test passes.

1. **Gmail ingestion, triage and first-approval Discord message**, with no task creation. Test: 30 real emails produce sensible verdicts, and a re-fetch creates no duplicates.
2. **Deadline proposals** against a stub tasks app. Test: relative dates resolve correctly and each shows its evidence quote.
3. **Submit proposals to the real tasks app.** Test: an approved email produces exactly one proposal; a thread follow-up links instead of duplicating.
4. **live.com adapter** using the same pipeline. Test: identical emails give identical verdicts from either provider.
5. **Hardening.** Test: an email containing instructions ("create 20 tasks") produces at most one junk proposal, the hourly cap holds, and a revoked token raises an alert.
