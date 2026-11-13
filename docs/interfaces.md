# Interfaces

The email service talks to the rest of the system through one outbound call and a few read-only tools.

## Outbound: approved task to the tasks app

Sent only after your final approval: checkpoint 2, or the combined step for a clearly dated email. The tasks app receives a task you have already approved, so it doesn't ask you again. It never contains email text.

The provider and message ID act as an idempotency key: if the service retries a send, the tasks app recognizes the key and doesn't create a second task.

| Field | Notes |
| --- | --- |
| source | Always `email` |
| title | As extracted, or as you edited it |
| deadline | Optional; already confirmed by you |
| deadline evidence | The short quote the deadline came from |
| confidence | From the extractor |
| provider | `gmail`, `outlook` or `yahoo` |
| message ID | The stored message ID, `<account>/<provider id>` |
| link | Link to the exact message for Gmail and Outlook; link to the Yahoo inbox for Yahoo |

## MCP tools for the email subagent (read-only)

Only the dedicated email subagent uses these tools; the master agent and other app subagents do not (see [Architecture](architecture.md#agents)).

| Tool | Returns |
| --- | --- |
| `list_pending_emails` | Metadata and local summaries of messages awaiting your decision |
| `get_email_summary(id)` | The local summary and the triage verdict for one message |
| `get_triage_stats` | Counts by outcome, whether batching is active, last poll time for each account |

No tool returns a message body, and none writes anything. After 24 hours the summaries are deleted too, so these tools return only metadata for older items. Approvals happen on Discord, handled by the service, not by the agent.
