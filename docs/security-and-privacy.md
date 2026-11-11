# Security and Privacy

A hostile email can at worst produce one junk proposal, because the code that reads it has no tools and no write access.

- **No tools for the reader.** The extractor outputs validated JSON only. Instructions inside an email are treated as text to describe, never as commands.
- **Least access.** The service holds no send, calendar or task-creation rights.
  - Gmail and Microsoft Graph use read-only OAuth scopes.
  - Yahoo's app password cannot be limited to read-only, so the adapter enforces it in code (see [Ingestion](ingestion.md#yahoo)). This is the weakest point in the access model: a stolen Yahoo app password gives full mailbox access, so treat it as the most sensitive secret the service holds. If the Mac is lost or compromised, revoke the Yahoo app password first.
- **Local model only** for processing email text.
- **Agent isolation.** Only the dedicated email subagent reads this service's summaries. The master agent receives only an approved task title and time, so text planted in an email can't reach agents working on other apps.
- **Task titles.** Titles come from emails, so they're plain text, at most 100 characters, and the master agent treats them as data, never instructions.
- **Retention.** Email text is deleted after 24 hours. Only records without email text are kept longer: dedup keys, the thread-to-task mapping and the audit log.
- **Forged senders.** A sender counts as trusted only if the email passes the provider's authentication checks (DMARC, or SPF and DKIM). A forged "From" address is treated as untrusted. See [Triage](triage.md#pipeline).
- **Spam and phishing.** The extractor can flag an email as suspected spam or phishing, with a reason. You decide what to do; nothing is filed as spam automatically. Suspected emails are ranked last and never get combined approval.
- **Discord.** The bot lives in a private server. As extra protection:
  - every button press and command is checked against your Discord user ID, so no one else can approve anything, even if they join the server
  - the bot token is kept in the Keychain with the other secrets; anyone holding it could read the channel and post fake prompts
  - the bot has permissions only for its own channel
  - turn on two-factor authentication for your Discord account
- **Discord content.** Channel messages carry the sender, subject, a short local summary and a link, never the body, since Discord stores what is posted.
- **Full text on request.** Show full text sends the body as an ephemeral reply only you can see, which is not kept in the channel history. The text does pass through Discord's servers, so this is the one place email text leaves the machine, and only when you ask for it. It is shown as plain text in a code block so links in a hostile email are not clickable.
- **Floods.** There is no notification cap, so an important email is never held back. A flood of emails, crafted or not, is batched into ranked digests, so it can't flood your phone with pings. Your mail providers' spam filtering stops most of it before triage, and bulk mail that gets through is scored low.
- **Sender scores.** Per-sender scores drop with each "Not a task", and nothing from any sender becomes a task without your approval.
- **Secrets.** OAuth tokens and the Yahoo app password are kept in the Keychain or a vault, and can be revoked from your phone if the machine is lost: Google and Microsoft from their account security pages, Yahoo from its app password settings.
- **Audit log.** Every state change records what triggered it and the original message ID.
