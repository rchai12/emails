# Purpose and Scope

## Purpose

The email service watches Gmail, live.com and yahoo.com, finds messages that need action, and sends them to the tasks app only after you approve them on Discord. It never creates tasks itself (the tasks app does), writes to the calendar or sends mail.

## In scope for v1

- Read-only ingestion from Gmail, live.com and yahoo.com
- Triage: rules first, then a local model that extracts action items
- Discord approvals: "is this a task?" and "confirm the deadline", or one combined step for clearly dated emails
- Sending fully approved tasks to the tasks app

## Out of scope for v1

- Sending or drafting replies
- Attachments
- Creating tasks without approval
- Labeling or flagging messages inside the mailboxes

See [Roadmap](roadmap.md#deferred-items) for the full list of deferred items.
