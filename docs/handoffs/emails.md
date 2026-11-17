# Tasks app: what the email service needs to know

Written Nov 14, 2026 from the tasks app's design (`tasking/docs/`). For the email service's architect and owner. Nothing here changes the email service until its own phases are specified.

## Summary

The tasks app exists as a design: the Python package `docket` in the `tasking` project, with Phase 0 specified and nothing built yet. It adopts the email service's stub contract (Phase 2f and 3b) unchanged, and adds one thing: a sign-in token. The Discord bot code is planned to move out of the email service into a shared Discord service.

## Decisions that affect the email service

| Decision | What it means here |
| --- | --- |
| The email service's approval is final (Nov 14) | Matches the email service's "Handoff" decision: the tasks app creates the task at once and never asks you again |
| The stub contract is adopted unchanged | `POST /tasks` and `POST /tasks/<id>/links`, the same fields, the `Idempotency-Key` header, and the same answers as `FakeTasksApp`: 201, 200 on a repeat, 409 for a reused key with a different body, 400 for a missing key, 422 for an invalid body, 404 for a link to an unknown task. Task ids stay ASCII letters, digits, `-` and `_` |
| One addition: a bearer token | Every request needs `Authorization: Bearer <token>`, or the app answers **401**. The token is the email service's own, kept in the Keychain on both sides, and it only allows `source: "email"`. This is the "sign-in" Phase 3c was going to add |
| Address | `http://127.0.0.1:8767` (`finances` uses 8765, Conductor 8766). `FakeTasksApp.URL` uses 8765; that's harmless in tests, but the real `MAILROOM_TASKS_URL` is 8767 |
| Date-only deadlines | When `time` is `null`, the tasks app uses 17:00 in the given `time_zone`, and shows that no time was given. The email service keeps sending `time: null`; it shouldn't fill a time in itself |
| Deadlines are fixed instants | Stored as a UTC instant plus the IANA zone sent. `time_zone` must be an IANA name (for example `America/New_York`), which the email service's setting already is |
| Follow-up links | Stored on the task and shown with it. They never create a task |
| No email text | The tasks app stores only what the payload carries. It already has no quote, summary or body, as the email service decided on Nov 13 |
| Titles are untrusted | The tasks app treats titles as plain text of at most 100 characters and shows them in code blocks on Discord, the same rule the email service follows |

## Work this means for the email service

1. **Phase 3c** (deferred until the tasks app exists) is now well defined:
   - Read the client token from the Keychain and send it as a bearer token.
   - Point `MAILROOM_TASKS_URL` at port 8767.
   - Add 401 to `FakeTasksApp`.
   - The tasks app's stage 2 builds the real endpoint, and its acceptance test runs the email service's own `tasks_app` tests against it.
2. **Permanent refusals.** Today `send_tasks` stops the round on any answer other than 200 or 201 and retries next round, with the existing alert after 15 minutes. A 401, 409 or 422 won't fix itself on a retry. Phase 3c should decide whether those raise their own alert (a wrong token, a reused key) instead of retrying quietly behind the 15-minute alert.
3. **The shared Discord service** (new project, planned). The owner chose on Nov 14 that one service owns the bot token and the Gateway connection, so no app runs its own bot. That means a later email-service phase moves the Gateway listener (`gateway.py`) and the REST senders (`discord_post.py`, the alerts) onto that service, keeping every card, button id and owner check as they are. The shared service must support:
   - keyed posts and in-place updates
   - ephemeral replies (Show full text)
   - forms (Edit title, the deadline form)
   - slash commands (`/trust` and the rest)
   - answering within Discord's 3-second window

   Nothing changes until that service exists, and its contract will be specified there first.

## Facts checked that also apply here

- **Google sign-in lifetime.** Google's OAuth documentation says an External app in Testing gets refresh tokens that expire in 7 days. Setting the consent screen to In production avoids that; sign in again after the switch. Refresh tokens also stop working after six months unused, and each account keeps at most 100 per OAuth client. Gmail's login is affected the same way.
