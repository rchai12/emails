# Triage

Fixed rules drop only mail that is clearly not for you, a local model extracts action items from what is left, and ordinary code decides whether to notify you. Triage is tuned to miss as few tasks as possible: a "Not a task" tap costs you a second, while a missed task costs much more.

## Pipeline

1. **Sender check.** Code reads the provider's authentication results (SPF, DKIM and DMARC). A sender counts as [trusted](approval-flow.md#trusted-senders) only if the address is on your trusted list and the email passes DMARC, or both SPF and DKIM for the sender's domain. Otherwise it's treated as untrusted, so a forged "From" address gains nothing. Only the provider's own header counts (the first one, from `mx.google.com` for Gmail), because anyone can put such a header in the mail they send.
2. **Rules.** Only your muted senders are dropped with no model call; there is no built-in newsletter list, so Mute sender is how a newsletter stops. Mail from a trusted sender is never dropped. Bulk-mail signs such as a `List-Unsubscribe` header lower the email's score instead of dropping it, because banks, bills, schools and work systems often send with that header.
3. **Extractor.** A local model of 27B parameters or more (such as Qwen 3.6 or 3.8), run by Ollama on the Mac with no tools, reads the message and returns strict JSON (the prompt, schema and sampling are fixed in `mailroom.extractor_prompt`):
   - a short summary for the Discord message
   - urgent
   - actionable
   - task title (plain text, at most 100 characters)
   - the deadline as a date (and time, if stated) that the model works out from the sent date and your time zone, and whether the email states it explicitly
   - a short quote from the email as evidence for the deadline
   - suspected spam or phishing: yes or no, with a one-line reason
   - confidence
4. **Validation.** Code checks the JSON against the schema and rejects anything malformed or too long, naming the field. A rejected email is still sent to you, marked as one the model couldn't read, so no task is missed.
5. **Decision.** Thresholds in code, not the model, decide whether to send a Discord notification (only a sure non-task is skipped: not actionable, not urgent, no deadline, with high confidence, or medium confidence on bulk mail; trusted senders and unreadable replies are always notified), and whether the email is clearly dated enough for [combined approval](approval-flow.md#combined-approval-for-clearly-dated-emails). Thresholds start low, so borderline emails reach you rather than being dropped. There is no notification cap; in busy hours notifications are [batched into ranked digests](approval-flow.md#busy-hours-batching) instead.

## Spam and phishing suggestions

The extractor can suggest that an email looks like spam or phishing, for example a fake "urgent" invoice or a request to confirm a password. It only suggests; nothing is ever filed as spam automatically.

- The notification shows a warning label with the model's one-line reason, as plain text.
- A suspected email never gets combined approval, and it is ranked last in a digest.
- You decide with the usual buttons: Not a task, or Mute sender to drop future mail from that sender.
- The suggestion alone never changes a sender's score; only your answers do.

## Details

- A follow-up in a thread you already approved gets the [follow-up card](approval-flow.md#follow-ups), which asks whether to add it to the existing task instead of creating a new one. The thread is matched through stored approvals and thread ids, which are kept after email text is deleted.
- Repeated "Not a task" answers for a sender lower that sender's score automatically.
- Relative dates such as "by Friday" are resolved against the email's sent date and your time zone, and the evidence quote is shown with the deadline.
- Email text goes only to the local model.
- Triage behaves the same for every provider: identical emails must give identical verdicts whether they came from Gmail, live.com or Yahoo.
