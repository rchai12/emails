# Email Service Docs

Started Nov 9, 2026 · @Richard · split into separate docs Nov 11, 2026

The email service watches Gmail, live.com and yahoo.com, finds messages that need action, and sends them to the tasks app only after you approve them on Discord. It never creates tasks itself (the tasks app does), writes to the calendar or sends mail.

## Documents

| Doc | What it covers |
| --- | --- |
| [Purpose and scope](purpose-and-scope.md) | What the service is for, and what v1 includes and leaves out |
| [Decisions](decisions.md) | Every major decision, with the reason and the option rejected |
| [Architecture](architecture.md) | Components, data flow and the normalized message record |
| [Ingestion](ingestion.md) | How mail is read from Gmail, live.com and Yahoo |
| [Triage](triage.md) | Rules, the local extractor, validation and the notify decision |
| [Approval flow](approval-flow.md) | The two Discord checkpoints and what happens at each |
| [Security and privacy](security-and-privacy.md) | Threat model, least access, secrets and the audit log |
| [Interfaces](interfaces.md) | The approved task sent to the tasks app and the read-only MCP tools |
| [Roadmap](roadmap.md) | Build order, acceptance tests and deferred items |
| [Open questions](open-questions.md) | Decisions still to make before building |
| [Phase 1 audit](phase-01-audit.md) | Alignment, file size, duplication, and residual risk after Phases 0 to 1m |

The original single document is kept in [archive/](archive/Email%20Service%20Feature%20Decisions.md) for reference. These docs replace it.
