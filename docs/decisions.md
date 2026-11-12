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
| State storage | One local SQLite database, no vector search in v1 | Every lookup is exact; embeddings would leak email text past 24 hours | A database server; a vector store |
| Database access | Standard library `sqlite3`, plain SQL, numbered migrations | No dependency; every query visible and testable | SQLAlchemy and Alembic |
| HTTP client | httpx for every outside call (Gmail, Graph, the local model, the tasks app) | One small library; plain REST calls; tests fake it with no network | Google's client library; the standard library |
| Accounts | One per provider in v1, every secret and bookmark keyed by an account name | A second account later is configuration, not code | A single fixed account |
| Mail gone before fetch | Skipped: only mail still in the inbox (not spam or trash) when fetched is stored | You've already dealt with it; a deleted message can't block the sync | Triaging anything that was ever in the inbox |
| Gmail link | `authuser=<address>` picks the account | Opens the right mailbox with several Google accounts signed in | `u/0`, the first signed-in account |
| Gmail login | A one-request listener on 127.0.0.1 receives Google's answer, with PKCE | What Google expects for desktop apps; no pasting | Pasting the redirect address |
| OAuth client keys | The login asks for them (hidden) when missing and stores them | No manual Keychain step | Adding them with `security` by hand |
| First run | Read the last 3 days of the inbox | Recent mail may still need action; older mail you've already seen | Start from now; 14 days |
| Parsing | Each adapter fetches the raw RFC 822 message; one shared parser builds the record | One code path gives identical records for identical emails | Mapping each provider's JSON separately |
| HTML email | Standard library `html.parser`, link addresses kept as plain text | No dependency parsing untrusted input; the model and you see where links point | An HTML-to-text package |
| Bulk-mail headers | Lower the score, never drop | Bills and work mail often carry `List-Unsubscribe` | Dropping on the header alone |
| Triage tuning | Miss as few tasks as possible | A "Not a task" tap is cheap; a missed task is not | Tuning for fewer notifications |
| Spam and phishing | The model suggests with a reason; you decide | Catches crafted "urgent" mail without ever hiding real mail | Auto-filing as spam |
| Trusted senders | Exact address and passing sender authentication | A forged "From" address gains nothing | Trusting by address alone |
| Agent access | Only a dedicated email subagent uses the MCP tools | Keeps email content out of other agents' context | Master agent calling the tools directly |
| Discord content | Short local summary, a link (exact email for Gmail and Outlook, inbox for Yahoo) and a Show full text button | Discord stores what is posted, so the body is never posted in the channel | Full body in the message |
| Full text on request | Private reply only you can see, sent when you tap Show full text | Lets you read the whole email without leaving Discord or keeping it in channel history | A local web page (needs a private connection from your phone); posting it in the channel |
| Handoff | The email service runs every checkpoint and sends the tasks app API only fully approved tasks | Simpler, and fits combined approval; the tasks app never asks you twice | The tasks app running the deadline checkpoint; direct writes to tasks or calendar |
| Busy hours | No cap; above 20 notifications an hour, batch into digests every 15 minutes, ranked most to least important | Missing an important email is a bigger risk than a flood | An hourly cap that holds emails back |
| Restarts | launchd LaunchAgent, plus the email subagent reporting on Discord when it can't reach the service | Built into macOS and restarts within seconds | The orchestrator AI restarting the process (slow to notice, needs process control) |
