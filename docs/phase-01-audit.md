# Phase 1 audit

Read 13 Nov 2026 against commit `63999d5` (Phases 0 through 1m). Compared `src/mailroom` with [Purpose and scope](purpose-and-scope.md), [Architecture](architecture.md), [Security and privacy](security-and-privacy.md), [Decisions](decisions.md), the [Roadmap](roadmap.md), and [Open questions](open-questions.md).

The code that is built matches the threat model. Four issues should be settled before stage 2. Two documents describe later stages as properties of the service today.

## What holds

- Gmail's scope is `gmail.readonly`, and login refuses any other scope.
- The login listener binds to `127.0.0.1`, uses PKCE, and checks the OAuth state.
- SQL uses placeholders. The database file is mode `0o600` with `secure_delete` on, inside a `0o700` data folder. The rollback journal is the default, so no write-ahead log keeps old text.
- Checkpoint cards and Show full text turn mentions off and put email text in a code block. An alert pings only the owner.
- The Gateway logger is silenced, so the bot token is not written.
- Body text is cleared 24 hours after fetch.

## Handle before stage 2

### One store class owns every table

`src/mailroom/store.py` is 644 lines, about 15% of the 4,374-line package. Messages, sync, senders, triage, posts, answers, problems, and alerts are methods on one class. Stages 2 to 5 add deadlines, tasks, Outlook, and Yahoo to the same file.

### The Discord send loop is copied

`post_pending` in `src/mailroom/discord_post.py` and `post_alerts` in `src/mailroom/alerts.py` repeat the token read, the channel URL, the stop rules, and `_message_id`. `run_round` in `src/mailroom/service.py` repeats the same ok, waiting, and error status for posting and for alerts.

### Two connections write with a read, then an insert

`mailroom run` opens one store on the main thread and another on the listener thread, both on the same file. `Store.open_problem` and `Store.queue_alert` select a key and then insert. A second insert of the same key raises `IntegrityError`. Phase 1l treats any unexpected error as fatal, so the process exits. The keys used today do not overlap, so this has not fired.

### Gmail message ids are not stored per account

`messages` is keyed by provider and message id (`src/mailroom/schema.py`). Gmail ids are unique inside one mailbox. `MAILROOM_GMAIL_ACCOUNTS` already accepts several names. [Decisions](decisions.md) still says one account per provider, and Phase 1l assumed two Gmail accounts never share an id. A second Gmail account can collide with the first.

## Documents ahead of the code

[Architecture](architecture.md) lists `threads`, `audit_log`, and sender scores in the schema table. The sentence above that table says each table arrives with the phase that needs it. Schema version 7 has `messages`, `sync_state`, `senders` (address and status only), `triage`, `posts`, `answers`, `problems`, and `alerts`. [Open questions](open-questions.md) still has the sender score undecided.

[Security and privacy](security-and-privacy.md) states digests, sender scores, and an audit log as properties of the service. Digests and the audit log are stage 6 on the roadmap. Scores are undecided.

The [Roadmap](roadmap.md) status line still says Phases 0 to 1l are done and Phase 1m's result is pending. Phase 1m passed and is in `63999d5`.

Retention and backup disagree. Cleared text is overwritten in the live file. The architecture page also says the database is backed up with the Mac, so Time Machine keeps earlier copies, bodies included, past 24 hours.

## Scheduled, and not a defect

Outlook, Yahoo, the tasks app, the MCP server, digests, launchd, and the audit log are stages 2 to 6. Leaving them out of stage 1 matches the build order.

The Discord bot token can post in whatever channels the Discord permission allows. The code limits its calls to the configured channel. The channel permission is a Discord setting, which the security doc already names.

## Package size

| File | Lines | Role |
| --- | --- | --- |
| `store.py` | 644 | every table |
| `reports.py` | 391 | review checker, not the running service |
| `mime.py` | 309 | parser |
| `gmail.py` | 305 | Gmail client |
| `gateway.py` | 280 | Discord Gateway |
| `extractor.py` | 245 | local model |
| `interactions.py` | 226 | button presses |
| `service.py` | 224 | poll loop |

28 modules, 4,374 lines. Counts are `wc -l src/mailroom/*.py` on 13 Nov 2026.
