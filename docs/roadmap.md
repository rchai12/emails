# Roadmap

## Build order and acceptance tests

Status (2026-11-22): Phases 0 to 3b and 4a to 4k are done and reviewed. The owner has verified the [codebase audit](codebase-audit.md); its remediation is planned below. **4l is specified and validated**, pending a committed planning baseline before implementation; 4m to 4t remain planned before Yahoo. Phase 3c's tasks-app implementation prerequisite now exists; its authenticated integration and cross-check remain to be specified.

Build one stage at a time, and move on only when its test passes. Stage N is Phase N, split into lettered sub-phases (`1a`, `1b`) when it is too big.

**Next build order:** 4e → 4f → 4g → 4h → 4i → 4j → 4k → 4l → 4m → 4n → 4o → 4p → 4q → 4r → 4s → 4t → 5 → 6 → 7. Phase 3c can be specified after 4n, once its cross-project contract and local deployment prerequisites are checked; it does not depend on Yahoo. Stage 7 also depends on a specified and implemented shared Discord service; it can be scheduled after 4t if that dependency is ready, independently of Yahoo. Until its cutover passes, the existing Gateway remains supported by 4e/4f. This puts listener and credential failures ahead of refactoring, and removes the provider copies before a third provider is built.

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
   - **3c** connecting your own tasks app, adopting the stub's contract and adding its sign-in. The Nov 13 deferral was until that app existed. Its intake API and localhost server now have PASS reviews ([tasking 2c](../../tasking/docs/reviews/phase-02c-http-routes.md), [tasking 2d](../../tasking/docs/reviews/phase-02d-serve.md)); this removes the implementation blocker, not the need for an email-service spec or a contract cross-check. Specify after 4n using the owning code and [handoff](handoffs/emails.md): bearer token from Keychain, source restricted to email, keyed task/link requests, and an explicit policy for permanent 401/409/422 refusals. Agent verification uses synthetic data and a fake/local test server; the owner configures and runs the real services. See the [3c contract and acceptance targets](#tasks-app-integration-phase-3c) below.
4. **live.com adapter** using the same pipeline.
   Test: identical emails give identical verdicts from Gmail and live.com.
   Sub-phases (later ones are planned when each is specified):
   - **4a** the Graph client: rotating tokens, inbox delta rounds and the raw message, read-only, against a fake Graph. Done.
   - **4b** Outlook sync: the delta bookmark, inbox only, dedup, first run (3 days), catch-up after an expired link. Done.
   - **4c** `mailroom outlook-login`: browser consent on a 127.0.0.1 listener that stores the refresh token. Done.
   - **4d** Outlook in the service: settings, each round, alerts, the card footer, and stage 4's test. Done; the corrected spec and implementation have a [PASS review](reviews/phase-04d-outlook-service.md).
   - **4e to 4t** the verified audit's reliability fixes and preparation for another provider/card. Sequenced below; 4e passed review. [4f spec](phases/phase-04f-listener-recovery.md) and [verification guide](verification/phase-04f-listener-recovery.md) are validated. Commit their given artifacts before the coder starts; later phase specs follow their predecessor reviews.
5. **Yahoo adapter** over IMAP using the same pipeline.
   Test: identical emails give identical verdicts from all three providers; a poll leaves every message unread and unchanged in Yahoo; a `UIDVALIDITY` change creates no duplicates.
   Start only after 4e to 4t pass. Reuse provider-neutral sync policy and account dispatch; Yahoo's IMAP/app-password behavior stays provider-specific and must not acquire an OAuth dependency. Add its fake in the provider-specific test module established by 4s. Split the client, sync and service/sign-in work into bounded specs before implementation.
6. **Hardening.**
   Test: an email containing instructions ("create 20 tasks") produces at most one junk proposal; an email forging a trusted sender's address is treated as untrusted; an obvious phishing email is flagged and ranked last; a rejected sync bookmark triggers a catch-up with no duplicates and one Discord message; a failed Discord send is retried until it goes through; a flood of emails arrives as ranked digests with none missing, an unanswered card gets one follow-up after 30 minutes and is then listed as pending, launchd restarts the service after it is killed, the email subagent reports on Discord when the service is unreachable, email text is gone after 24 hours while dedup keys remain, and a revoked token or app password raises an alert.
   Start with **6a**, relational integrity, and **6b**, the development report-tool boundary, below. Split the remaining hardening features and owner-run operational checks into later specs; earlier audit repairs do not imply that ranked digests, reminders, launchd packaging or service-monitoring tools already exist.


7. **Shared Discord service integration.** Planned from the [tasks-app handoff](handoffs/emails.md), dependent on that service's own finalized contract and implementation. One service owns the bot token and Gateway; the email service becomes its client. This does not authorize designing that service's protocol here or removing the current listener before cutover.
   Test: the same cards, button ids, commands, forms, keyed posts/updates and owner checks work through a fake shared service; Show full text remains owner-only and ephemeral; every press is acknowledged within Discord's 3-second window; retries do not duplicate delivery. The email process no longer opens its own Gateway or reads the bot token after cutover.
   Planned sub-phases, each requiring a spec and guide:
   - **7a: Contract and client seam.** Read the owning service's code/spec first, map the email service's required operations and authentication, and add a synthetic contract fake/client. Define exactly what leaves the machine and how owner identity is authenticated. Block handoff if keyed posts, in-place updates, ephemeral replies, forms, slash commands or timely acknowledgements are unsupported; do not invent substitutes.
   - **7b: Outbound cards, replies and alerts.** Route posts, edits, forms, ephemeral full-text replies and alerts through that client, preserving literal layouts, mention suppression, idempotency keys and failed-send queues. No body text may enter a normal post, log, task payload or error; full text travels only for the owner's explicit Show full text request.
   - **7c: Inbound actions and single-bot cutover.** Route presses and slash commands through the authenticated shared-service input path, preserving the email owner's user/channel checks and every persisted custom id. Test unauthorized/spoofed/repeated/late actions and shared-service outages. Retire the local Gateway and direct bot-token use only once inbound/outbound parity and recovery pass; deployment instructions must prevent two bot owners running at once.

## Integration handoff requirements

Source: [Tasks app: what the email service needs to know](handoffs/emails.md), written November 14, 2026. Its opening implementation status predates tasking's completed intake API; use the current reviews linked in stage 3 for readiness. The following requirements are planned, not implemented by adding them here.

### Tasks app integration (Phase 3c)

- **Authentication and address:** read the email client's bearer token only through mailroom.keychain and send Authorization on both task and link requests. It grants only source `email`; missing/wrong tokens return 401. Configure the owner's `MAILROOM_TASKS_URL` as `http://127.0.0.1:8767`. The old fake's port 8765 is not the deployment address and need not change merely to match it. Add fake 401/source-refusal cases without reading a real token.
- **Existing contract:** retain `POST /tasks`, `POST /tasks/<id>/links`, payload fields and `Idempotency-Key`. Pin 201 for creation, 200 for identical repeats, 409 for the same key with a different body, 400 for a missing key, 422 for invalid input and 404 for a link to an unknown task. Task ids remain ASCII letters, digits, hyphen and underscore. Approval in the email service is final: the tasks app creates the approved task without a second approval; a follow-up link never creates another task.
- **Deadline ownership:** keep date-only `time: null` and the IANA `time_zone` in the payload. The tasks app applies its 17:00 default in that zone and stores a fixed UTC instant plus the zone; mailroom must not fill in 17:00 itself. Cross-contract tests include date-only and explicit-time deadlines across daylight-saving boundaries.
- **Data boundary:** only the finally approved plain-text title (at most 100 characters), confirmed deadline, provider, message id and link go to task creation. Links carry only provider, message id and link. No body, summary or evidence quote is added; downstream titles remain untrusted data, including when displayed in Discord code blocks.
- **Refusal policy to settle in the spec:** distinguish permanent 401/409/422 failures from transient transport/service failures. Specify alert timing, queue state, retry eligibility and recovery after token correction or a conflicting/invalid payload; do not silently inherit the current every-round retry plus 15-minute alert as the resolution. Preserve pending work and idempotency; no automatic task approval or dropping a refused item.
- **Acceptance:** run the mailroom tasks_app contract cases against the actual docket HTTP implementation in an isolated test harness with synthetic records, temporary storage and fake Keychain. Cover task/link authorization, source restriction, all status codes, identical/conflicting retries, null times, minimal payloads and refusal recovery. No live running service or real account is contacted by an agent. The owner separately provisions the shared client credential, configures port 8767 and runs deployment checks.

### Google sign-in setup (owner-run readiness check)

Attach this to the existing Gmail login/deployment checklist and carry it through 4k's OAuth extraction; it is not a new scope or a reason to redo completed Phase 1d. The handoff records that an External app in Testing can receive refresh tokens expiring after seven days, that switching the consent screen to In production requires signing in again, and that unused-token expiry and per-client/account token limits also matter (six months and 100 in that dated source). Before real rollout, the owner verifies current official Google rules, restricted gmail.readonly scope requirements and suitability for this personal deployment, then configures consent and signs in again as required. These dated numbers are not hardcoded into refresh/retry policy or treated as permanent provider guarantees. Agent acceptance stays on fake expiry/revocation cases; no real Google consent or Keychain access.

### Handoff coverage

| Handoff item | Roadmap home |
| --- | --- |
| Final email approval; existing task/link contract and status codes | 3c contract and cross-project acceptance |
| Bearer token, email-only source, 401 fake and port 8767 | 3c authentication and deployment |
| Null-time deadlines, IANA zones and fixed instants | 3c deadline ownership and DST contract tests |
| Follow-up links, minimal payloads and untrusted titles | 3c data boundary and repeat tests |
| Permanent refusal handling | Explicit 3c spec decision and recovery tests |
| One shared bot/Gateway, posts/updates, ephemeral replies, forms, commands, 3-second acknowledgement | 7a–7c, blocked on the owning service contract/implementation |
| Google consent mode, re-login and refresh-token lifetime/limits | Owner-run Gmail readiness check; preserved through 4k |

## Audit remediation sequence

**Accepted input:** the owner confirmed on November 17, 2026 that all findings in [the audit](codebase-audit.md) are verified. The audit was written against `879de3b`; the subsequent workflow commit `06a5fba` adds development tooling, not mail-service fixes. Do not repeat the audit or mark a finding closed because it now has a roadmap row.

Except for the linked Phase 4e, 4f, 4g, 4h, 4i, 4j, 4k and 4l specs/guides, these are ordered planning scopes and acceptance targets, **not coder-ready specs**. Each needs its own exact Scope, given files, failing-first tests for fixes, verification guide and offline probe before handoff. Apply the phase size limits when drafting; split an oversized unbuilt row rather than delivering a large reference implementation. Existing public imports, persisted values, messages and Discord custom ids remain contracts unless a spec explicitly lists their migration.

The last product phase passed 1,212 tests; the subsequent [workflow maintenance](agent-workflow.md#workflow-maintenance-evidence-november-17-2026) passed **1,230** (77 tooling, 1,153 core). Use that verified starting evidence when specifying 4e, then use each successor's actual results. Do not rerun the suite solely to rediscover N.

| Phase | Planned change | Deciding acceptance evidence | Audit findings |
| --- | --- | --- | --- |
| **4e: Validate Gateway input** | Guard hello/session frames and interaction payload shapes before indexing them. Malformed input causes a controlled reconnect/resume or a refused interaction, never a listener-killing decode/type/key error. Keep owner and channel checks ahead of any state-changing action. | Bad JSON, wrong container types, missing fields and invalid heartbeat intervals cannot terminate input processing or approve anything; a following valid frame/owner press still works. Preserve existing fatal-close, resume-host and token-privacy behavior. | 1; 5 (input boundary) |
| **4f: Supervise listener recovery** | Give the service an explicit distinction between a recoverable listener failure, a terminal Gateway outcome and requested shutdown. Restart only recoverable failures with bounded backoff, close each failed listener's resources, and keep polling independent. | A synthetic handler/store failure does not leave a live poll loop with permanently dead Discord input; a later valid press works. At most one listener runs; shutdown interrupts recovery; fatal closes are alerted and remain stopped rather than being restarted by the supervisor. Recovery/failure alerts remain keyed and secret-free. | 1; 2 (listener side) |
| **4g: Bound SQLite contention** | Set an explicit lock-wait policy for both connections and handle busy/locked outcomes at the poll/listener boundaries. Keep rollback journaling, secure deletion and atomic writes. Account for Discord's acknowledgement window instead of blindly increasing the wait. | Two synthetic connections contend, release and make progress; an exhausted wait leaves no partial decision/send mark or leaked transaction, and the service can handle later work. Non-lock OperationalError cases are distinguished; no arbitrary SQL replay, duplicate approval or WAL is introduced. | 2 |
| **4h: Preserve rotated Outlook credentials** | Handle failure to persist a newly rotated refresh token as an explicit credential-persistence failure. Do not silently continue using the superseded token; define bounded in-process recovery and an actionable account alert. | Fake Graph retires the old token while fake Keychain rejects the write: the new credential is not silently discarded/replaced by an old-token retry, no success is reported before the required persistence, and the owner gets a constant-text diagnostic. Recovery and process-restart limits are explicit; no disk fallback or token text in output. | 8 |
| **4i: Refuse incomplete stored chains safely** | Guard message, triage, answer/approval and follow-up target lookups in interaction handling and pending-card posting. Refuse an action whose prerequisite is missing; retain unsent work for diagnosis rather than marking it delivered. | Removing each related row in synthetic storage yields a bounded unavailable/refusal result, not AttributeError, an unauthorized task or a successful-send mark. Valid chains still post and approve exactly once; listener and poll paths continue after the inconsistent item. | 3 (read side) |
| **4j: Stabilize store readers and lifecycle** | Share the duplicate due reader, centralize repeated post projections and make column-to-field mapping explicit. Retain the Store facade while pinning one connection/migration lifecycle and preventing mixin constructors from creating a second one. | All public readers return the same literal records, including null dates/times; adding/reordering a projection cannot silently swap fields. Store initialization/migration happens once, writes remain atomic, and existing callers need no new store API. No wholesale repository redesign. | 6; audit's recommended shared due reader |
| **4k: Extract shared OAuth mechanics** | Move callback, PKCE and the common login error contract out of Gmail-owned modules. Keep provider-specific consent/scope/token exchange rules and close login HTTP clients on success, cancellation and error. | Both existing consent flows pass against fakes, importing neutral helpers; state, PKCE, timeout and least-scope checks remain pinned. Each CLI-created HTTP client closes on every path, with no real sign-in or Keychain access. | 4 (login coupling and resource lifetime) |
| **4l: Extract provider-neutral sync policy** | Give SyncResult and first-run/catch-up windows a neutral home, then share the first-run/bookmark/catch-up orchestration. Keep Gmail history and Graph delta/folder/link behavior in their adapters. | The same synthetic first run, expired bookmark, interrupted round and repeat produce identical stored ids, counts and alert inputs for both providers. Bookmark writes occur only after a completed round; earlier inbox/dedup and provider-specific fetch rules remain unchanged. No Outlook import of Gmail sync internals. | 4 (sync copies) |
| **4m: Share safe HTTP/token mechanics** | Extract only common token-cache, transport mapping and one-401-retry mechanics from Gmail/Graph clients. Preserve provider-specific refresh persistence, request allowlists, read-only operations and response parsing; carry forward 4h's failure policy. | Both provider suites exercise expiry, transport failure, one retry and refusal after the second 401. Graph tokens never follow an unapproved URL, rotated tokens stay safe, and Gmail's scope/token rules do not change. No new provider or generic unrestricted HTTP client. | 4 (client copies) |
| **4n: Remove copied provider wiring** | Replace the service's concrete-client branch and copied account/auth-alert paths with explicit provider registration. Share account-list/Discord-id validation, login-command plumbing and the common DMARC-or-SPF/DKIM predicate, while retaining provider-specific header selection. | Gmail/Outlook preserve poll order, isolated failures, existing alert keys/text and login command names. Shared validators retain each setting's error message. Identical authentication results agree, forged/misplaced headers still fail, and adding a provider does not require another copied service branch. | 4 (service, CLI, settings, sender auth); 7 (id validators) |
| **4o: Share safe text and card primitives** | Centralize Unicode/plain-title validation, expose the shared safe code-block renderer without a private checkpoint import, and give cards one embed/component envelope. Keep model-title and owner-title length/error differences explicit. | Unicode controls/separators, mentions, backticks and overlong values remain refused or rendered inert as each boundary requires. Literal shapes of all existing cards, buttons and allowed_mentions stay unchanged. | 5 (private rendering helper); 7 (text rules and card envelopes) |
| **4p: Separate interaction dispatch and first answers** | Extract owner/channel/shape/registered-action routing and the first-checkpoint handlers from the ordered interaction tree, retaining handle_interaction as the facade. Pin the complete custom-id registration alongside card builders. | Every emitted button/form id has a matching route; a missing registration fails a contract test. Unknown/expired/foreign-owner presses remain safely ignored/refused; Show full text remains owner-only and ephemeral, and first answers stay retry-safe. | 5 (large dispatcher and silently missing routes) |
| **4q: Separate deadline and follow-up decisions** | Extract second-checkpoint, combined-card and follow-up handlers; share the write-or-already-answered/update-card sequence and repeated title-form construction. Preserve 4i's incomplete-chain guards. | Each card path and form has literal response/state tests; repeated presses record one decision and send no second task/link. Existing persisted custom ids still work, owner/channel checks cannot be bypassed by a handler, and a failed update cannot manufacture a second approval. | 5 (decision/form copies and remaining interaction size) |
| **4r: Unify queued task/link delivery** | Share the task and follow-up send loop and factor common queue-reporting mechanics with Discord where their semantics actually agree. Keep destination-specific success codes, payloads, keyed sends and mark callbacks explicit. | Transport errors and 200/201/refusal responses produce consistent posted/waiting/stopped counts without dropping pending items. A retry after a send/mark interruption creates one external task/link, and only finally approved fields leave the service. Existing Discord retry behavior remains pinned. | 7 (send-loop copies) |
| **4s: Organize fakes and behavior tests** | Split tests/fakes.py along provider/model/Discord/tasks boundaries, preserving existing imports with a facade during migration. Fold small overflow tests into their module or behavior file; replace remaining `_more` names with meaningful names. Update sections and given/probe import references deliberately. | All existing cases still collect and pass; no assertions are dropped or weakened. Fakes still import nothing from mailroom and every test remains offline. Renames have an explicit old/new inventory so historical given-file checks are not silently reinterpreted. Yahoo gets a separate fake module. | 9 (fake monolith and test discoverability) |
| **4t: Exercise complete approval flows** | Add the missing tests/e2e layer for CLI and synthetic fetch-to-triage-to-card-to-approved-task/link behavior. Add focused clearly-dated boundary regressions before future card/date changes; leave the pure deadline parser together. | CLI entry points use CliRunner; a fake-only pipeline covers rejection, both approval paths, follow-up, restart/retry, text expiry and an unauthorized press. Exact/out-of-range/ambiguous date evidence cannot wrongly skip a checkpoint. All external systems and time/id seams are faked. | 9 (missing e2e layer); 5 (deadline-policy concentration) |

### Scheduled after Yahoo

These lower-urgency audit items stay scheduled in hardening rather than being silently dropped or mixed into the listener fixes.

| Phase | Planned change | Deciding acceptance evidence | Audit findings |
| --- | --- | --- | --- |
| **6a: Enforce relational integrity** | After 4i/4j, design an append-only migration for the enforceable message/post/answer/approval/task/link relationships and enable foreign-key enforcement on every connection. Specify handling of existing orphans before writing the migration; default to a clear refusal, never silently delete data. Preserve legitimate combined approvals and retention's text-clearing behavior. | Synthetic pre-migration rows survive correctly; invalid new references fail at the write, valid first/combined/follow-up paths still work, and a refused migration leaves the original database intact. Both connections enforce constraints; foreign_key_check is clean; secure_delete, rollback journaling and dedup history survive. Split table rebuilds into bounded specs if necessary. | 3 (schema side) |
| **6b: Separate development report tooling** | Move progress/review parsing and checking out of the mail runtime package into an explicit development-tool boundary, splitting the large module by responsibility. Migrate check_reports.py, progress.py, tests and coverage-path support together. Keep the checker fully measured rather than dropping its critical gate. | Historical valid/invalid reports retain their exact results, both command entry points work, and scripts/check.py still enforces every line/branch of the moved checker at its new paths. No runtime mail module acquires a tooling dependency; given tests/imports migrate explicitly. Split the move before drafting if it exceeds the phase size target. | 10; 9 (report test organization) |

### Finding coverage and preserved decisions

| Audit finding | Planned disposition |
| --- | --- |
| 1: listener dies while process stays up | 4e, 4f |
| 2: SQLite contention is fatal on one side | 4f, 4g |
| 3: related rows enforced only in application SQL | 4i now; 6a database constraints |
| 4: provider copies and Gmail-owned shared contracts | 4k, 4l, 4m, 4n |
| 5: interaction tree, repeated forms/decisions and deadline risk | 4e, 4o, 4p, 4q, 4t |
| 6: Store lifecycle/projections and duplicate due reader | 4j |
| 7: smaller shared text/send/card/settings copies | 4n, 4o, 4r |
| 8: rotated refresh-token persistence failure | 4h before token refactoring |
| 9: large fakes, `_more` files and absent e2e layer | 4s, 4t; report tests finish in 6b |
| 10: large development-only critical report checker | 6b |

Keep the audit's deliberate exceptions: MIME parsing must still return a record on malformed input; SQLite stays on the rollback journal; Yahoo remains an allowed provider before its adapter exists; persisted Discord ids are not renamed. No new phase weakens read-only mail, owner approval, keyed retries, local-only extraction or 24-hour text retention. All agent-run acceptance stays synthetic and offline; existing owner-run live acceptance remains separate.

## Deferred items

V1 stays narrow on purpose; each item below is a later decision, not a rejection.

- Sending or drafting replies (would be a separate, gated tool)
- Auto-creating tasks for trusted senders
- Attachment handling
- Labeling or flagging messages inside Gmail, Outlook or Yahoo (needs more than read-only access)
- Learning beyond sender scores, such as per-topic importance
- Fuzzy matching of related emails across threads with vector embeddings (embeddings would count as email text under the 24-hour retention rule)
