# Ingestion

Each provider is read with read-only access, polled every 1 to 2 minutes, and turned into the [normalized record](architecture.md#normalized-record) by its own adapter. All three adapters implement the same interface.

## Gmail

- Gmail API with the read-only scope, over plain REST calls (httpx). Each account has a short name (such as `personal`); its OAuth client ID, client secret and refresh token are Keychain items `gmail.<account>.client-id`, `.client-secret` and `.refresh-token`.
- New mail is found by polling with a stored history ID, filtered to the inbox. A message added to the inbox later (for example one you move out of spam) counts as new.
- **Login.** `mailroom gmail-login <account>` opens Google's consent page and receives the answer on a one-request listener on 127.0.0.1 (PKCE, 5-minute limit). The first time, it asks for the OAuth client ID and secret (hidden input); `--new-client` replaces them. Only a token for exactly the read-only scope is stored, and nothing is stored unless the whole sign-in succeeds. It finishes by showing the account's address.
- **First run.** With no history ID yet, the service reads the last 3 days of the inbox, then starts the bookmark.
- **Still in the inbox.** A message is stored only if, when it is fetched, it is still in the inbox and not in spam or trash. Mail you archive or delete within the minute before a poll is skipped, and a deleted message never blocks the sync.
- **Link.** `https://mail.google.com/mail/?authuser=<address>#all/<message id>`, so the right account opens when several Google accounts are signed in. **Verify before building:** the link opens the exact message in a desktop browser and on the phone.
- **Verify before building:** Google refresh tokens for apps left in testing mode can expire after about a week, which would quietly stop ingestion. The read-only Gmail scope is one Google classes as restricted, so also check what publishing the app to production requires for a single personal user, and whether that avoids the full verification process.

## live.com

- Microsoft Graph with read-only mail access.
- New mail is found by polling with delta queries.
- Register the app for personal Microsoft accounts as well as work accounts.

## Yahoo

Yahoo has no modern mail API, so the adapter uses IMAP over TLS (`imap.mail.yahoo.com`, port 993) with an app password.

- **Read-only in code.** An app password gives full mailbox access, so read-only has to be enforced by the adapter:
  - open folders with `EXAMINE`, never `SELECT`
  - fetch with `BODY.PEEK[]` so messages are not marked as read
  - never issue `STORE`, `COPY`, `MOVE`, `EXPUNGE` or `APPEND`
- **New mail.** Store `UIDVALIDITY` and the last seen UID for each folder, and fetch UIDs above it on each poll. If `UIDVALIDITY` changes, rescan recent mail and rely on deduplication to skip what was already seen.
- **Message ID.** IMAP UIDs can change, so the record uses the `Message-ID` header. If it is missing, use a hash of sender, date and subject.
- **Thread ID.** IMAP has no threads, so the adapter derives one from the `References` and `In-Reply-To` headers.
- **Link.** Gmail and Outlook can link straight to the exact email. Yahoo can't, because its web addresses use an internal ID that IMAP doesn't expose, so a Yahoo link opens your Yahoo inbox and you find the email from the sender and subject. Show full text works the same as for the other providers (see [Approval flow](approval-flow.md#reading-the-full-email)).
- **Folders.** Inbox only. The Bulk (spam) folder is never read.
- **Verify before building:** confirm that the Yahoo account can still create app passwords (this requires two-step verification) and that IMAP access is enabled.

## Shared rules

- **No spam folders.** No adapter reads spam: Gmail's Spam label, Outlook's Junk Email folder or Yahoo's Bulk folder. Mail the provider has filtered as spam never reaches triage.
- **Deduplication.** Every record is keyed by provider and message ID, so a retry or repeated fetch never creates a second proposal.
- **Secrets.** OAuth tokens and the Yahoo app password are stored in the macOS Keychain or a vault, never in prompts or files an agent can read.
- **Failures.** A revoked or expired credential raises an alert instead of failing quietly.

## Catching up after an outage

Each adapter keeps a sync bookmark: Gmail's history ID, Graph's delta token, and Yahoo's `UIDVALIDITY` and last UID. These go stale if the service is offline too long. Gmail history IDs typically last about a week, and providers can invalidate them at any time.

When a bookmark is rejected (for example, Gmail returns 404, Graph returns 410 Gone, or Yahoo's `UIDVALIDITY` changes), the adapter:

1. Lists inbox mail received since the last successful poll (with an hour's overlap), going back at most 14 days.
2. Runs every email through dedup, so anything already seen is skipped.
3. Sends the rest through triage as usual. A large catch-up is batched into ranked digests like any busy hour.
4. Starts a fresh bookmark.
5. Posts one Discord message: which account resynced, how long it was offline, and how many new emails were found.

If the outage was longer than 14 days, the message says so, so you know to check the gap yourself.

## Retention

Email text is deleted 24 hours after the service fetches the email: the body, the local summary and the extractor output. A pending item stays in the pending list after that, with only its sender, subject, task title and deadline.

These are kept after the 24 hours, without any email text (see [Database](architecture.md#database)):

- **Dedup keys** (provider and message ID), so a later re-fetch, such as a catch-up after an outage, doesn't notify you twice about an old email.
- **Thread-to-task mapping**, so a follow-up in an approved thread links to the existing task.
- **Audit log entries**, which record state changes and message IDs only.
