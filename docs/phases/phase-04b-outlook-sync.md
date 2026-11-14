# Phase 4b: Outlook sync

## Goal

Store a live.com inbox's new mail once each, as Phase 1c does for Gmail ([Ingestion](../ingestion.md#livecom)).

`sync_outlook(client, store)` runs one round:
- **First round:** with no bookmark, it reads the last 3 days of the inbox.
- **Later rounds:** it reads what was created since the stored delta link.
- **Expired link:** it catches up from the last round, with an hour's overlap and at most 14 days back.
- **Storing:** each listed message not yet stored is fetched, kept only if it is still in the inbox, and stored as an `outlook` record with the account-prefixed ids.
- **The bookmark:** the new delta link is saved only when the whole round succeeds.

Nothing calls it yet. `mailroom outlook-login` is 4c, and the service 4d.

Sections: `core`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is 1142, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_outlook_sync.py` must show `1142 passed`. The ignored file imports `mailroom.outlook_sync`, which you create.

## Corrections

- **2026-11-13, after the review (PASS).** The verifier found three faults in the given files; the code was right.
  - **The test count.** `test_outlook_sync.py` has 17 tests, not 18: I miscounted the functions.
  - **FakeGraph's expiry.** `expire_deltas()` also expired a link issued right after it when no mail had arrived in between, because a link names only how much of the log it has seen. The next round became an unneeded catch-up. `expire_deltas()` now adds a marker to the log, which no round lists, so later links count past it. The catch-up test's bookmark is therefore `d3`, not `d2`.
  - **The probe.** It excused an old message moved into the inbox only when the link expired after the move; now it also excuses a move while an expired link waits for its catch-up. It also counted any second download as a fault. 4a's `fetch` downloads the text along with the folder, so mail moved to junk before its fetch is legitimately downloaded again if it comes back. The rule is now "never downloaded once stored".
  On the committed `outlook_sync.py`, the given tests pass and the probe prints `FAILURES 0`. With the "already stored" check removed, the probe prints `FAIL`.

## Facts

Checked against the 4a client and the fake on this machine, and in Microsoft's documentation. Nothing here was checked against a real account.

- **The bookmark is the delta link,** stored whole in `sync_state.bookmark` (free text) under provider `outlook`. 4a's `next_delta` accepts only a Graph inbox delta link, so a corrupted bookmark fails the round by name.
- **Delta lists more than what's new.** A round lists every item created in the inbox since the link, including mail moved out again before the fetch and mail moved in from junk. Removals arrive too, and 4a drops them. So sync decides at fetch time: a message is kept only if its `folder_id` is the profile's `inbox_id`. That's the counterpart of Gmail's label check.
- **A catch-up lists by received time.** `first_delta(after)` filters on `receivedDateTime`. An old message moved into the inbox just before an expired link may fall outside the window, the same limit Gmail's catch-up has. The probe knows this case.
- **A message deleted after its listing** answers 404 on fetch (`MessageGone`). FakeGraph gains `delete(message_id)` for this (given).
- **The link comes from Graph.** A record needs an `https://` link of at most 2,000 characters, printable and without spaces. Graph's `webLink` is the provider's to shape, so a long or odd one must not cost the email. Sync falls back to the Outlook inbox link instead of dropping it.
- **Gmail's constants and result are shared.** `gmail_sync.py` already has `FIRST_RUN`, `CATCH_UP_LIMIT`, `CATCH_UP_OVERLAP` and `SyncResult`. Outlook sync reuses them, and `SyncResult.kind`'s `Literal` gains `"delta"` for a round from the bookmark.
- **Thread ids** are Graph's `conversationId`, stored as `<account>/<conversationId>`, so 3a's follow-ups work for Outlook threads unchanged.

## Owner's decisions

- From stage 1, for every provider: inbox only, never junk; a first run reads 3 days; a catch-up after a rejected bookmark reads from the last round with an hour's overlap, at most 14 days, and says when it was longer.
- From 4a: personal accounts only, read-only.

## Architect's decisions

- **Same shape as Gmail sync,** so 4d can treat both alike: one `clock.now()` per round, the profile first, the refs in order, and the bookmark saved last.
- **A failure stops the round.** Anything stored before it stays (dedup skips it next time), and the bookmark stays where it was. An auth, network or Keychain error is not caught here; 4d reports it.
- **A link that fails the checks becomes the inbox link,** `https://outlook.live.com/mail/0/inbox`. A `webLink` is used only when it starts with `https://outlook.live.com/`, so a look-alike host never reaches a card's Open email button.
- **A message whose envelope can't be built is skipped,** as for Gmail. An example is a `conversationId` with a space.

## Requirements

1. **`src/mailroom/outlook_sync.py`, names:** `INBOX_LINK = "https://outlook.live.com/mail/0/inbox"`, `WEB_LINK_PREFIX = "https://outlook.live.com/"`, and `sync_outlook(client: OutlookClient, store: Store) -> SyncResult`, with `SyncResult` from `gmail_sync`. `gmail_sync.SyncResult.kind` becomes `Literal["first", "history", "delta", "catch_up"]`; nothing else in `gmail_sync.py` changes.
2. **A round starts** by reading `clock.now()` once, then `store.sync_state("outlook", client.account)`, then `client.profile()`.
3. **Choosing what to read:**
   - **No state:** `client.first_delta(now - FIRST_RUN)`, kind `"first"`.
   - **A state:** `client.next_delta(state.bookmark)`, kind `"delta"`.
   - **`DeltaExpired`:** kind `"catch_up"`, with `after = max(state.synced_at - CATCH_UP_OVERLAP, now - CATCH_UP_LIMIT)`, `offline_since = state.synced_at` and `gap = now - state.synced_at > CATCH_UP_LIMIT`, then `client.first_delta(after)`.
   - Only a catch-up has an `offline_since`; the others have `None` and `gap=False`.
4. **Each listed ref, in order:**
   - **Already stored:** skip it when `store.get("outlook", stored_id(account, ref.id))` exists, without fetching.
   - **Fetching:** `client.fetch(ref.id)`. `MessageGone` or `ValueError` skips it.
   - **Still in the inbox:** skip it when `message.folder_id != profile.inbox_id`.
   - **The link** is `message.web_link` if it starts with `WEB_LINK_PREFIX`, is at most `record.LINK_LIMIT` characters, is printable and has no space. Otherwise it is `INBOX_LINK`.
   - **The envelope** is `Envelope(provider="outlook", message_id=stored_id(account, ref.id), thread_id=stored_id(account, message.thread_id), received_at=message.received_at, link=link)`. A `ValueError` skips the message.
   - **Storing:** `store.add(parse_message(message.raw, envelope))`. When it returns true, the stored id joins the result's `stored`, in order.
5. **The round ends** with `store.save_sync_state("outlook", account, SyncState(bookmark=<the round's delta_link>, synced_at=now))`, then returns `SyncResult(account, kind, stored, offline_since, gap)`. Any exception before that leaves the sync state unchanged and propagates.
6. **Progress entry** for `## Phase 4b: Outlook sync (YYYY-MM-DD)` at the end of `docs/progress.md`.

## Verify before building

For the owner, with the real account, once 4c can sign in:
- Open a stored message's `webLink` on a desktop browser and on the phone. It should open the exact message; if not, the inbox link is used for all.
- Move a message from Junk Email into the inbox. It should arrive as created in the next round.
- After a long idle period, confirm an expired delta link answers 410 or `syncStateNotFound`, as documented.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
| `tests/fakes.py` | Edited: `FakeGraph.delete` |
| `scripts/critical_modules.txt` | Edited: `outlook_sync.py` added |
| `tests/integration/test_outlook_sync.py` | First run; the envelope; a later round from the bookmark; moved out before the fetch; moved in; listed again but not refetched; deleted before the fetch; a catch-up with overlap; a catch-up past 14 days; two failed rounds keep the bookmark; five odd links replaced; a thread that can't be stored |
| `docs/verification/probe-04b.py` | The verifier's probe |

Given test count: **18**, all new.

## Tests to write

The given tests cover every requirement's main cases. `outlook_sync.py` is critical. To reach full coverage, add behaviour tests in new `*_more.py` files, never by changing a given or earlier test.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/outlook_sync.py` | create |
| `src/mailroom/gmail_sync.py` | `SyncResult.kind` gains `"delta"` |
| `tests/**/test_*_more.py` | new files only, if coverage needs them |
| `docs/progress.md` | append your entry |

## Out of scope

- Settings, accounts in the service, status lines, alerts or the catch-up notice (4d).
- The login command (4c).
- Any change to `outlook.py`, or to Gmail sync beyond the `Literal`.
- Retrying within a round, a per-message failure list, or reading folders other than the inbox.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- **Mail access is read-only.** Only the 4a client's reads.
- **Inbox only.** Mail in junk, or moved there before the fetch, is never stored.
- **Dedup.** A record is keyed by provider and `<account>/<id>`, and one already stored is never fetched again.
- **Nothing lost on a failure.** The bookmark moves only after a whole round.
- **Email-derived text is untrusted.** A link not on `outlook.live.com` never reaches a card.
- **Time through the module:** `clock.now()` once per round.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; summary lists `tests (core): passed`; at least N + 18 = 1160 passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest tests/integration/test_outlook_sync.py --no-cov -q` | `18 passed` |
| `.venv/bin/python -m coverage report --include=src/mailroom/outlook_sync.py,src/mailroom/gmail_sync.py --fail-under=100`, right after `check.py` | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python docs/verification/probe-04b.py` | last line `FAILURES 0` |
| `grep -c "^## Phase 4b: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 4b` | `Reports OK.` |
| `git diff HEAD --stat -- tests/fakes.py scripts/critical_modules.txt tests/integration/test_outlook_sync.py docs/verification/probe-04b.py` | no output |
| `git diff HEAD --stat -- tests` | no output: no earlier test changed |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
git grep --untracked -n -E 'http\.|httpx\.|junkemail|mailFolders' -- src/mailroom/outlook_sync.py
git grep --untracked -n -E 'except (Exception|OutlookError|OutlookUnavailable|OutlookAuthError|KeychainError)' -- src/mailroom/outlook_sync.py
git grep --untracked -n -E 'finally:' -- src/mailroom/outlook_sync.py
git grep --untracked -n -E 'datetime\.now|datetime\.utcnow|date\.today|time\.time\(|from mailroom\.(clock|ids) import' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'
git grep --untracked -n -E 'print\(|logging|logger|warnings\.warn' -- src ':!src/mailroom/cli.py' ':!src/mailroom/gateway.py'
git grep --untracked -n -E 'pragma: no cover|noqa' -- src/mailroom/outlook_sync.py src/mailroom/gmail_sync.py
```
