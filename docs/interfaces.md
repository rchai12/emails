# Interfaces

The email service talks to the rest of the system through one outbound call and a few read-only tools.

## Outbound: approved task to the tasks app

Sent only after your final approval: checkpoint 2, or the combined step for a clearly dated email. The tasks app receives a task you have already approved, so it doesn't ask you again. It never contains email text.

The provider and message ID act as an idempotency key: if the service retries a send, the tasks app recognizes the key and doesn't create a second task.

Until stage 3 connects the real tasks app, the contract is the stub's (Phase 2f): `POST <MAILROOM_TASKS_URL>/tasks` with a JSON body and an `Idempotency-Key: <provider>:<message id>` header. The address must be on this Mac (`127.0.0.1`, `localhost` or `[::1]`). The app answers 201 with `{"id": ...}` for a new task, and 200 with the same id when the key is sent again. Stage 3 adapts this to the real app and adds its sign-in.

| Field | Notes |
| --- | --- |
| source | Always `email` |
| title | The title you approved |
| deadline | `null`, or `date` (YYYY-MM-DD), `time` (HH:MM or `null`) and `time_zone` (yours); already confirmed by you |
| provider | `gmail`, `outlook` or `yahoo` |
| message_id | The stored message ID, `<account>/<provider id>` |
| link | Link to the exact message for Gmail and Outlook; link to the Yahoo inbox for Yahoo |

The evidence quote and the extractor's confidence are not sent (owner's decision, Nov 13, 2026). The quote is email text, and both are cleared 24 hours after fetch. Every field above is kept long term, so a retry always sends the same body.

## MCP tools for the email subagent (read-only)

Only the dedicated email subagent uses these tools; the master agent and other app subagents do not (see [Architecture](architecture.md#agents)).

| Tool | Returns |
| --- | --- |
| `list_pending_emails` | Metadata and local summaries of messages awaiting your decision |
| `get_email_summary(id)` | The local summary and the triage verdict for one message |
| `get_triage_stats` | Counts by outcome, whether batching is active, last poll time for each account |

No tool returns a message body, and none writes anything. After 24 hours the summaries are deleted too, so these tools return only metadata for older items. Approvals happen on Discord, handled by the service, not by the agent.
