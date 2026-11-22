# Decisions

An email becomes a task only after your approval on Discord, and the service holds the least access that still works.

| Decision | Choice | Reason | Rejected |
| --- | --- | --- | --- |
| Service boundary | Separate service from the tasks app | Own credentials, untrusted input, polling runtime | Module inside the tasks app |
| Providers in v1 | Gmail, live.com and yahoo.com | All three accounts are in active use | Deferring Yahoo |
| Mail scope | Read-only: OAuth scopes for Gmail and Microsoft Graph, enforced in code for Yahoo | Ingestion never needs send rights; limits token-theft damage | Full mailbox scope |
| Yahoo access | IMAP with an app password | Yahoo has no modern mail API | Waiting for an API |
| Detecting new mail | Polling every 1 to 2 minutes | Works from a home machine with no public endpoint | Push webhooks or Pub/Sub |
| Triage order | Rules first, local model second | Most mail needs no model call | Model on every message |
| Who sees email text | Local model only | Raw email is personal data | Hosted model |
| Extractor design | No tools, strict JSON, validated in code | Injection can at worst produce a junk proposal | Tool-using agent reading mail |
| Task creation | Never automatic; two Discord approvals, or one combined approval for a clearly dated email | You decide what becomes a task | Auto-create for trusted senders (deferred) |
| Extractor model | Local model of 27B parameters or more, such as Qwen 3.6 or 3.8 | Fits on the Mac Studio and keeps email text local | Small models; hosted models |
| Flagging | The Discord notification is the flag | Read-only access can't label mail | Labels in the mailbox (needs write access) |
| Retention | Email text deleted after 24 hours | Keeps as little personal data as possible | Keeping bodies indefinitely |
| Backups | The data folder is excluded from Time Machine | Backups would otherwise keep email text past 24 hours | Backing it up and accepting the gap |
| State storage | One local SQLite database, no vector search in v1 | Every lookup is exact; embeddings would leak email text past 24 hours | A database server; a vector store |
| Database access | Standard library `sqlite3`, plain SQL, numbered migrations | No dependency; every query visible and testable | SQLAlchemy and Alembic |
| HTTP client | httpx for every outside REST call (Gmail, Graph, the local model, Discord, the tasks app) | One small library; plain REST calls; tests fake it with no network | Google's client library; the standard library |
| Accounts | Several per provider (at least two Gmail accounts); every secret and bookmark keyed by an account name, and every stored message and thread id written `<account>/<provider id>` | Two mailboxes can never collide, with one change at sync and none downstream | One account per provider; an `account` column in every table's key |
| Mailbox on the card | The card footer names the account (`Gmail personal`) | You know which inbox it came to | Provider only |
| Mail gone before fetch | Skipped: only mail still in the inbox (not spam or trash) when fetched is stored | You've already dealt with it; a deleted message can't block the sync | Triaging anything that was ever in the inbox |
| Gmail link | `authuser=<address>` picks the account | Opens the right mailbox with several Google accounts signed in | `u/0`, the first signed-in account |
| Gmail login | A one-request listener on 127.0.0.1 receives Google's answer, with PKCE | What Google expects for desktop apps; no pasting | Pasting the redirect address |
| OAuth client keys | The login asks for them (hidden) when missing and stores them | No manual Keychain step | Adding them with `security` by hand |
| First run | Read the last 3 days of the inbox | Recent mail may still need action; older mail you've already seen | Start from now; 14 days |
| Parsing | Each adapter fetches the raw RFC 822 message; one shared parser builds the record | One code path gives identical records for identical emails | Mapping each provider's JSON separately |
| HTML email | Standard library `html.parser`, link addresses kept as plain text | No dependency parsing untrusted input; the model and you see where links point | An HTML-to-text package |
| Dropped mail | Only senders you muted, matched by exact address | Nothing is dropped that you never chose | A built-in newsletter list; muting whole domains |
| Which authentication header | The first one, and only from the provider's own server | Senders can add their own fake headers lower down | Reading every header |
| Model server | Ollama on the Mac, its own API, `format` set to the schema | Common Mac setup; the reply is held to the schema | An OpenAI-compatible server |
| Relative deadlines | The model resolves them from the sent date and your time zone; code checks every value | Handles any wording; code still decides what counts | A date parser in code |
| Unreadable model reply | Rejected by field name and still sent to you, marked as unread by the model | No task is missed | Holding it silently; retrying |
| Notify threshold | Skip only a sure non-task: not actionable, not urgent, no deadline, high confidence (or medium on bulk mail); always notify trusted senders and unreadable replies | Misses as little as possible while quieting confident newsletters | Notifying everything not muted; notifying only actionable mail |
| Unreadable email's rank | As if nothing is known: not urgent, no deadline, low confidence, above suspected spam | The model's failure says nothing about importance | Near the top of a digest |
| Bulk-mail headers | Lower the score, never drop | Bills and work mail often carry `List-Unsubscribe` | Dropping on the header alone |
| Triage tuning | Miss as few tasks as possible | A "Not a task" tap is cheap; a missed task is not | Tuning for fewer notifications |
| Spam and phishing | The model suggests with a reason; you decide | Catches crafted "urgent" mail without ever hiding real mail | Auto-filing as spam |
| Trusted senders | Exact address and passing sender authentication | A forged "From" address gains nothing | Trusting by address alone |
| Agent access | Only a dedicated email subagent uses the MCP tools | Keeps email content out of other agents' context | Master agent calling the tools directly |
| Discord transport | Plain REST calls with httpx for every send; a Gateway listener only to receive presses | Same client and fakes as every other outside call; no library in between | discord.py for everything |
| Discord message | An embed card, with the email's text inside code blocks and backticks replaced | Nothing in an email can format, link or mention; the card is easy to scan | Plain text lines |
| Answered card | Updated in place: your answer shown, answer buttons removed | Can't be answered twice; the channel shows what's done | A private confirmation under an unchanged card |
| Presses from others | Acknowledged with no change | Nothing happens for anyone but you, and they see nothing | A refusal message |
| Gateway library | `websockets`, with the Gateway protocol written in the service | One small dependency-free library; the protocol is tested against a fake Gateway | discord.py |
| Gateway failures | Ordinary drops resume with backoff (1 s up to 60 s); fatal closes such as a revoked token stop with the close code | No silent retry loop on a bad token; you're told instead | Retrying every close forever |
| Commands | `/trust`, `/untrust`, `/trusted`, `/unmute`, `/muted`, in your server only, hidden from non-admins, registered by a setup command | Muting can be undone and seen; nothing registers behind your back | Global commands; registering at every start |
| Service layout | One process: polling in the main thread, the Gateway listener in a background thread with its own database connection | One launchd service to install and watch | Two processes |
| Part failures | Each account's sync, triage and posting fail on their own and are retried next round; a status line marks a change | One bad account or a down model never stops the rest | Exiting and letting launchd restart |
| Alerts | Gmail sign-in needed, listener stopped, model unreachable 15 minutes, catch-up summary; one message when each starts and one when it's fixed; action alerts mention you | You hear about what needs you without a stream of repeats | Alerting on every failed round; never pinging |
| Discord content | Short local summary, a link (exact email for Gmail and Outlook, inbox for Yahoo) and a Show full text button | Discord stores what is posted, so the body is never posted in the channel | Full body in the message |
| Full text on request | Private reply only you can see, sent when you tap Show full text | Lets you read the whole email without leaving Discord or keeping it in channel history | A local web page (needs a private connection from your phone); posting it in the channel |
| Handoff | The email service runs every checkpoint and sends the tasks app API only fully approved tasks | Simpler, and fits combined approval; the tasks app never asks you twice | The tasks app running the deadline checkpoint; direct writes to tasks or calendar |
| Stub tasks app (until stage 3) | Approved tasks queued, then POSTed to a tasks app address on this Mac with `Idempotency-Key: <provider>:<message id>`, tested against a fake | Retry safety is built and tested before the real API is known | Only an outbox table, nothing sent |
| Task payload | Title, deadline, provider, message ID and link; no evidence quote or confidence | No email text leaves the machine, and every field is kept, so a retry sends the same body | Sending the quote and confidence while still stored |
| Tasks app failures | Tasks stay queued and are retried every round; one alert after 15 minutes of failed sends, one when sends work again | You learn when approved tasks aren't arriving | Status line only |
| The real tasks app | Your own tasks app, built as its own project, adopting the stub's contract; connected in Phase 3c once it exists | Its API is ours to define, and no third-party write scope is added | Apple Reminders, Google Tasks, Microsoft To Do |
| Follow-ups | A new email in a thread with an approved item asks first: Add to task, New task or Not a task | Nothing in the tasks app changes without your press | Linking automatically; a notice only |
| Microsoft accounts | Personal accounts only (`consumers` tenant), `Mail.Read` | Covers live.com with the least access; no work tenant's policies apply | `common` (personal and work) |
| Outlook verification | The first Authentication-Results header, with no server name and a `compauth` result; Gmail's DMARC and SPF/DKIM rule | Microsoft adds its header above anything a sender wrote, as Gmail does; identical emails get identical verdicts | Never verifying Outlook mail |
| Microsoft sign-in | Browser consent with PKCE on a 127.0.0.1 listener, as for Gmail | Reuses the tested Gmail login; no code to type | Device code flow |
| Busy hours | No cap; above 20 notifications an hour, batch into digests every 15 minutes, ranked most to least important | Missing an important email is a bigger risk than a flood | An hourly cap that holds emails back |
| Restarts | launchd LaunchAgent, plus the email subagent reporting on Discord when it can't reach the service | Built into macOS and restarts within seconds | The orchestrator AI restarting the process (slow to notice, needs process control) |

## Phase 4e input recovery (2026-11-17)

The owner selected both recommended options in the architect's multiple-choice
questions: malformed Gateway frames reconnect through the existing resume/backoff
path; malformed interaction bodies with valid callback addressing are safely
acknowledged and ignored without state changes. Unknown interaction kinds or
unaddressable callbacks are ignored without HTTP, as specified in Phase 4e.

## Phase 4f listener recovery (2026-11-21)

The owner selected the recommended option in each of the architect's three
multiple-choice questions. A listener that fails for a recoverable reason restarts
quietly, and the owner is pinged only after it has kept failing for 15 minutes,
then told once it is answering again (rather than a ping on every failure, or
none). It restarts forever, waiting 1, 2, 4, 8, 16, 32 and then 60 seconds, and
the wait resets once a listener survives a full poll round (rather than giving up
after 10). A missing bot token stays terminal, while an unavailable Keychain is
retried (rather than treating both as terminal).

## Phase 4g SQLite contention (2026-11-21)

The owner selected the recommended option in each of the architect's three
multiple-choice questions. A press or command that meets a locked database gets a
private "Mailroom is busy right now. Press again in a moment." reply, and the card
is left as it is (rather than no answer, or a wait long enough to miss Discord's
3 seconds). A poll round that meets the lock is skipped with a status line and
retried next round, and the owner is pinged only after 15 minutes of continuous
locking, then told once it is free (rather than a ping at once, or never). The
listener's store waits 1.5 seconds for a lock and the poll loop's 10 seconds
(rather than one shared wait). Because a locked database cannot store an alert, that
ping is posted directly with one nonce per episode, while the "free again" notice
uses the alert queue. WAL is not adopted.

## Phase 4h rotated Outlook credentials (2026-11-21)

The owner selected the recommended option in each of the architect's four
multiple-choice questions. When Microsoft issues a new Outlook refresh token that the
Keychain refuses to save, the client keeps it in memory, and the account reads no mail
and reports the save failure until the token is saved (rather than reading on, or
dropping the account until sign-in). The owner is pinged at once (rather than after
15 minutes). The save is tried once per round for as long as the service runs, and a
restart loses the held token, which the alert states along with the
`mailroom outlook-login` fix (rather than giving up after an hour). The access token
from the unsaved refresh is never used. The token is never written anywhere but the
Keychain, and the alert is resolved only by a round that read mail.

## Phase 4i incomplete stored chains (2026-11-21)

The owner selected the recommended option in each of the architect's four
multiple-choice questions. Task and link sends get the same guard as card posting and
presses (rather than leaving them for a later phase). A poll round keeps an
incomplete card, task or link unsent and queued, sends the others, shows an
`ok (N incomplete)` status line, and posts one unpinged notice per item naming only
its item id (rather than a status line alone, or a ping). A press or form on an
incomplete email gets the private reply "Mailroom can't act on this email: its stored
details are incomplete." and records nothing (rather than a silent acknowledgement).
Show full text follows the same rule (rather than working whenever the message row
exists). Nothing is repaired or deleted; database constraints remain Phase 6a. A
missing answer row is the same state as an unanswered card, which is already refused
safely, so it needs no change.

## Phase 4j store readers and lifecycle (2026-11-22)

The owner selected the recommended option in each of the architect's four
multiple-choice questions. Each stored record type in scope gets one named column list
(a module constant such as `POST_COLUMNS`), every SELECT for it uses that list, and
rows are read by column name (rather than a shared unpacking helper that still reads
by position, or a test-only check of column order). Defining `__init__` in any store
area or in `Store` raises `TypeError` when the class is defined (rather than a test
that only inspects today's classes). The readers in scope are posts, tasks, links,
approvals, messages and triage; answers, alerts, problems, sync and senders stay
positional. A column name that appears twice in a reader's result raises `StoreError`
with "duplicate stored column: <name>" (rather than letting the later value win). The
architect placed one due reader and writer, `due_columns` and `read_due`, in
`store/triage.py`, where `Due` lives. The Store facade, method placement, schema and
write SQL are unchanged.

## Phase 4k shared OAuth mechanics (2026-11-22)

The owner chose the recommended option in each of the architect's four multiple-choice
questions:

- **Module.** The shared sign-in pieces live in `mailroom/oauth.py`, a module that names
  no provider. The other choices were a login package and keeping them in `gmail_login`.
- **Token reply.** The check is shared as `oauth.token_reply`, which gives one error
  contract. The other choice was sharing only the callback and PKCE. The checks cover:
  - network errors and statuses;
  - a body that is not JSON or not an object;
  - a refresh token that is missing, not text or empty;
  - a scope that is missing or not text.

  As a result, Gmail now refuses an empty refresh token, as Outlook already did. Scope
  rules stay with each provider.
- **Callback.** `oauth.Callback` requires its `provider` keyword. `gmail_login` keeps a
  thin subclass that defaults to `"gmail"`, so existing imports and calls still work.
  The other choice was keeping a gmail default in the neutral class.
- **Closing.** Each CLI login command opens its HTTP client in a `with` block and closes
  it on success, cancellation and every error. `login()` keeps borrowing the client it
  is given. The other choice was `login()` owning the client.

The architect listed `oauth.py` as a critical module in `docs/testing.md`.

## Phase 4l provider-neutral sync policy (2026-11-22)

The owner chose the recommended option in each of the architect's four multiple-choice
questions:

- **Module.** `SyncResult`, the first-run and catch-up windows, and the shared round
  live in `mailroom/mail_sync.py`, a module that names no provider. The other choices
  were `mailroom/sync.py`, which sits beside `store/sync.py`, and
  `mailroom/sync_policy.py`.
- **Shared part.** Both the round and the storing steps are shared. The other choices
  were sharing the round only, or only the names and windows. These steps are shared:
  - the choice between first run, resume and catch-up;
  - the store check before any fetch;
  - building the stored ids and `Envelope`, and `store.add`;
  - saving the bookmark only after a completed round.

  Each adapter keeps its listing, its resume, and a fetch that applies its own
  inbox/label/folder filter and link.
- **Expiry.** An adapter's `resume` returns `None` when its bookmark expired. It catches
  only its own `BookmarkExpired` or `DeltaExpired`. The other choices were a neutral
  exception, or an adapter naming its exception type.
- **Adapter.** Each provider has a small private class typed against
  `mail_sync.Source`. `sync_gmail` and `sync_outlook` stay as thin public wrappers. The
  other choice was keyword callables.

The architect kept the call order: one clock read, then the bookmark, then the
adapter's `begin()` profile read. The kind names `"history"` and `"delta"` stay in
`SyncResult`. `mail_sync.py` was listed as a critical module.
