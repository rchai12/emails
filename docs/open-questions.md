# Open Questions

- [ ] **Sender score.** Every "Not a task" answer is recorded (Phase 1i), but what a lower score changes is not decided yet. Decide once the service has been used for a while.
- [ ] **Backups and retention.** Email text is overwritten in the live database after 24 hours, but Time Machine keeps earlier copies of the data folder. Excluding the folder from backups keeps the promise; the cost is that after a restore the dedup keys and Gmail bookmarks are gone, so the first run rereads 3 days of inbox and notifies those emails again. Found by the [Phase 1 audit](phase-01-audit.md) (Nov 13, 2026).
- [ ] **More than one Gmail account.** Mail is keyed by provider and message id, not by account, so a second Gmail account's message with the same id as the first's would be silently skipped. Either limit Gmail to one account for now (matching [Decisions](decisions.md)), or add the account to the keys before real data builds up. Found by the [Phase 1 audit](phase-01-audit.md) (Nov 13, 2026).

## Resolved

- [x] **Restarts.** launchd keeps the service running, and the email subagent reports on Discord if it can't reach the service. See [Architecture](architecture.md#keeping-it-running) (Nov 11, 2026).
- [x] **Notification cap.** No cap. In busy hours notifications are batched into digests ranked from most to least important. See [Approval flow](approval-flow.md#busy-hours-batching) (Nov 11, 2026).
- [x] **Second checkpoint.** The email service runs every checkpoint and sends the tasks app only fully approved tasks (Nov 11, 2026).
- [x] **Trusted senders.** The list starts empty and you build it as you go, with a Trust sender button and Discord commands. See [Approval flow](approval-flow.md#trusted-senders) (Nov 11, 2026).
- [x] **Spam folders.** Never read, for any provider (Nov 11, 2026).
- [x] **Reading emails from Discord.** Every notification has a short summary and a Show full text button that sends the full text as a private reply. Every notification also has a link: to the exact email for Gmail and Outlook, and to the Yahoo inbox for Yahoo, which can't link to a single email (Nov 11, 2026).
- [x] **Flagging.** The Discord notification is the flag in v1; nothing is labeled in the mailboxes (Nov 11, 2026).
- [x] **Extractor model.** A local model of 27B parameters or more, such as Qwen 3.6 or 3.8. Accuracy is still tested on 30 real emails in [build stage 1](roadmap.md) (Nov 11, 2026).
- [x] **Follow-up timing.** One follow-up 30 minutes after an unanswered notification (Nov 11, 2026).
- [x] **Retention.** Email text (body and summary) is deleted 24 hours after it arrives. See [Ingestion](ingestion.md#retention) for what is kept (Nov 11, 2026).
- [x] **Combined approval.** A clearly dated email gets one combined approval step instead of two. See [Approval flow](approval-flow.md#combined-approval-for-clearly-dated-emails) (Nov 11, 2026).
- [x] **Orchestration.** A master agent hands email work to a dedicated email subagent, which is the only agent that uses this service's MCP tools. This keeps email content out of the context of agents working on other apps (Nov 11, 2026).
