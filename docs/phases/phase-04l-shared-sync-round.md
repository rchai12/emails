# Phase 4l: Extract provider-neutral sync policy

## Goal

A new module, `mailroom/mail_sync.py`, names no provider. It owns:

- `SyncResult`;
- the first-run and catch-up windows;
- one sync round for any provider.

A round is: read the bookmark, then do a first run, a resume or a catch-up. It skips a
message that is already stored before fetching it, and stores each message once. It saves
the bookmark only after the round completes.

`gmail_sync` and `outlook_sync` become small adapters that keep only their own rules:

- Gmail: history as the bookmark, and inbox mail outside spam and trash.
- Outlook: the delta link as the bookmark, the inbox folder, and the web link check.

Outlook stops importing from `gmail_sync`. This closes the sync-copy part of audit
finding 4.

Sections: `core`. The full check also runs `tooling`.

Follow `docs/phase-conventions.md`. N is **1559**, from the passing Phase 4k review
(`d6a77fc`). The coder's clean start is the planning and given-file commit made after
this document.

Start: `.venv/bin/python -m pytest --no-cov -q --ignore=tests/integration/test_mail_sync.py --ignore=tests/integration/test_sync_parity.py`
must show `1559 passed`. Nothing needs a missing-module stub. The two new given files
import only names that exist today. They reach `mailroom.mail_sync` through
`importlib.import_module` when a test runs.

## Corrections

- **2026-11-22, after the first review (FAIL, `8582566`).** The review found one
  defect, in the coder's tests; the product code matches this spec.
  `test_gmail_skips_mail_labelled_both_inbox_and_spam` delivers its message on a
  first run. `FakeGmail`'s inbox list already leaves out mail labelled `SPAM` or
  `TRASH`, so that message is never fetched and the test passes with the `SPAM` check
  removed from the Gmail fetch filter. This spec's "Tests to write" line did not say
  the test must reach the fetch filter; it now does.
  - Requirement: a test in `tests/integration/test_sync_adapters.py` shows that Gmail
    skips a message labelled both `INBOX` and `SPAM` **after fetching it**.
  - Observation: only a history resume or catch-up reaches `fetch` with such a
    message. FakeGmail's history keeps a message added with `INBOX` among its labels.
  - Required result: the test asserts the message was fetched and not stored. It fails
    when `or "SPAM" in labels` is removed from `src/mailroom/gmail_sync.py` and passes
    on the committed code. Replace the first-run test or keep it, whichever you
    choose; record which in the progress entry.
  - Nothing else changes. Product code, given files, probes and other tests stay as
    they are. The suite stays at least 1577 passed (1578 if the first-run test is kept).
  - Progress: update the Phase 4l entry with
    `.venv/bin/python scripts/progress.py --replace`, keeping its other fields. Add a
    Follow-ups item: `Correction 2026-11-22: Gmail INBOX+SPAM test now reaches fetch`.
  - Skip Start (its 1559 count is the pre-implementation baseline). Rerun every
    Acceptance command. The G7 row's baseline is the commit that adds this correction.

## Facts

- `gmail_sync.py` defines `FIRST_RUN` (3 days), `CATCH_UP_LIMIT` (14 days),
  `CATCH_UP_OVERLAP` (1 hour), `LINK`, `SyncResult` and `sync_gmail`, plus the private
  `_choose` and `_store_message`.
- `outlook_sync.py` imports `CATCH_UP_LIMIT`, `CATCH_UP_OVERLAP`, `FIRST_RUN` and
  `SyncResult` from `gmail_sync`. So an Outlook round loads `mailroom.gmail_sync` and
  `mailroom.gmail`. `service.py` also imports `SyncResult` from `gmail_sync`.
- The two `sync_*` functions are the same algorithm with different client calls:

  | Step | Gmail | Outlook |
  |---|---|---|
  | Order | `clock.now()`, then `store.sync_state`, then `client.profile()` | the same |
  | No bookmark | `"first"`: `list_inbox(now - FIRST_RUN)`, with the profile's history id as the bookmark | `"first"`: `first_delta(now - FIRST_RUN)` and its delta link |
  | Bookmark works | `"history"`: `history(bookmark)` | `"delta"`: `next_delta(bookmark)` |
  | Bookmark expired | `BookmarkExpired`: `"catch_up"` | `DeltaExpired`: `"catch_up"` |

  On a catch-up, both read from `max(synced_at - CATCH_UP_OVERLAP, now - CATCH_UP_LIMIT)`.
  `gap` is `now - synced_at > CATCH_UP_LIMIT` and `offline_since` is `synced_at`.
- Each message goes through these steps:
  1. Compute `stored_id(account, id)`.
  2. Skip the message, without fetching it, when the store already has it.
  3. Fetch it, and skip it on `MessageGone` or `ValueError`.
  4. Apply the provider's own filter:
     - Gmail: `INBOX` must be among the labels, with neither `SPAM` nor `TRASH`.
     - Outlook: the message must be in the inbox folder.
  5. Build the `Envelope`, and skip the message on `ValueError`.
  6. Run `store.add(parse_message(raw, envelope))`, and count the message only when it
     was added.

  The bookmark is saved, with `synced_at=now`, only after every message has been
  handled. Any other error propagates and leaves the bookmark as it was.
- The Gmail link is `LINK.format(address=quote(email_address, safe="@"), message_id=id)`.
  Outlook's `_web_link` keeps a `https://outlook.live.com/` link that is printable, has
  no space and is at most `LINK_LIMIT` long. Any other link becomes `INBOX_LINK`.
- `GmailClient` and `OutlookClient` read `clock.now()` for token expiry. So the order of
  clock reads and profile calls is part of today's behavior.
- `service._catch_up` uses only `result.kind == "catch_up"`, `offline_since`,
  `len(stored)` and `gap`. Alert keys and texts are not in scope.
- Existing tests pin the old import paths:
  - `test_gmail_sync.py` imports `CATCH_UP_LIMIT`, `CATCH_UP_OVERLAP`, `FIRST_RUN`,
    `SyncResult` and `sync_gmail` from `gmail_sync`.
  - `test_outlook_sync.py` imports `SyncResult` from `gmail_sync` and `INBOX_LINK` from
    `outlook_sync`.
  - `test_alerts_more.py` and `test_service_more.py` monkeypatch
    `gmail_sync.sync_gmail`.
  - The probes `probe-01n.py` and `probe-04b.py` import `sync_gmail` and `sync_outlook`.
- `probe-01c.py` already ends with `FAILURES 2` on predecessor code. Its oracle predates
  account-qualified ids. It is not an acceptance check for this phase.
- The store's `provider` CHECK already allows `yahoo`. The given tests use it for an
  invented adapter.
- Validated with a throwaway scratch stand-in only, never copied in:
  - All 145 sync, alert and service tests pass on it, the given ones included.
  - The given tests pass 6 of 6 runs.
  - `probe-01n.py` and `probe-04b.py` end with `FAILURES 0`.
  - On predecessor code, all 12 given cases fail.

## Owner's decisions

- **2026-11-22:** the module is `mailroom/mail_sync.py`. The other choices were
  `mailroom/sync.py`, which sits beside `store/sync.py`, and `mailroom/sync_policy.py`.
- **2026-11-22:** share the round and the storing steps. These steps are shared:
  - the first-run, resume or catch-up choice;
  - the store check before any fetch;
  - building the `Envelope` and `store.add`;
  - saving the bookmark only after a completed round.

  Adapters supply only listing, resuming and a fetch that applies their own filter and
  link.
- **2026-11-22:** an adapter's `resume` returns `None` when its bookmark expired. The
  adapter catches its own `BookmarkExpired` or `DeltaExpired`. Every other error
  propagates unchanged.
- **2026-11-22:** each provider has a small private adapter class, typed against a
  `Protocol` in `mail_sync`. `sync_gmail` and `sync_outlook` stay as thin public
  wrappers.

## Architect's decisions

- **Moved, not copied.** `FIRST_RUN`, `CATCH_UP_LIMIT`, `CATCH_UP_OVERLAP` and
  `SyncResult` exist once, in `mail_sync.py`. `gmail_sync` imports and lists them in
  `__all__`, so `gmail_sync.X is mail_sync.X`. `outlook_sync` and `service` import
  `SyncResult` from `mail_sync`.
- **`mail_sync.py` names no provider.** It imports only the standard library and
  `mailroom.clock`, `mailroom.mime`, `mailroom.record` and `mailroom.store`. No text in
  it names Gmail, Outlook, Google, Microsoft, Graph or Yahoo, docstrings and comments
  included. The kind names `"history"` and `"delta"` stay in `SyncResult`'s `Literal`,
  since existing results and tests use them. Each adapter says which one it uses.
- **The shared round builds the stored ids and the `Envelope`.** The adapter returns the
  provider's own message and thread ids. So an adapter can't store under a wrong id or
  provider.
- **The order of calls is kept.** The round reads `clock.now()`, then the bookmark, then
  calls the adapter's `begin()`, where Gmail and Outlook read their profile. Only then
  does it list or resume. Gmail's existing test pins profile before listing.
- **Wrappers look up `mail_sync.run_round` when they run**, so a test can wrap it.
- **`mail_sync.py` is a critical module.** This spec adds it to `docs/testing.md` beside
  `gmail_sync.py`, which keeps its entry.

## Requirements

1. **`mailroom/mail_sync.py`.** Create it with these public names:
   - `FIRST_RUN = timedelta(days=3)`, `CATCH_UP_LIMIT = timedelta(days=14)` and
     `CATCH_UP_OVERLAP = timedelta(hours=1)`.
   - `SyncResult`, a frozen dataclass with the fields in this order: `account: str`,
     `kind: Literal["first", "history", "delta", "catch_up"]`,
     `stored: tuple[str, ...]`, `offline_since: datetime | None` and `gap: bool`. This
     is unchanged.
   - `Page`, a frozen dataclass with `ids: tuple[str, ...]` (the provider's message
     ids, in order) and `bookmark: str`.
   - `Fetched`, a frozen dataclass with `raw: bytes`, `thread_id: str` (the
     provider's thread id), `received_at: datetime` and `link: str`.
   - `Source`, a `typing.Protocol` with the attributes `provider: str`,
     `account: str` and `resumed: Literal["history", "delta"]`, and these methods:
     - `begin() -> None`;
     - `start(after: datetime) -> Page`;
     - `resume(bookmark: str) -> Page | None`, where `None` means the bookmark expired;
     - `fetch(message_id: str) -> Fetched | None`, where `None` means skip.
   - `run_round(source: Source, store: Store) -> SyncResult`, in this order:
     1. Read `now = clock.now()` once.
     2. Read `store.sync_state(source.provider, source.account)`.
     3. Call `source.begin()`.
     4. With no bookmark, call `start(now - FIRST_RUN)`. The kind is `"first"`.
     5. Otherwise call `resume(bookmark)`. A page gives kind `source.resumed`. `None`
        gives `"catch_up"`, with:
        - `start(max(synced_at - CATCH_UP_OVERLAP, now - CATCH_UP_LIMIT))`;
        - `offline_since = synced_at`;
        - `gap = now - synced_at > CATCH_UP_LIMIT`.
     6. For each id in the page, in order:
        - when `store.get(provider, stored_id(account, id))` exists, skip the id
          without calling `fetch`;
        - when `fetch` returns `None`, skip it;
        - build `Envelope(provider, stored_id(account, id), stored_id(account,
          thread_id), received_at, link)`, and skip the id on `ValueError`;
        - keep the stored id when `store.add(parse_message(raw, envelope))` is true.
     7. After the last id, save `SyncState(bookmark=page.bookmark, synced_at=now)`.

     Any exception from the adapter or the store propagates, and the bookmark stays as
     it was. Messages already added stay stored.
2. **`gmail_sync.py`.**
   - Remove `_choose`, `_store_message`, `SyncResult` and the window definitions.
   - Import the moved names from `mail_sync`, as the Architect's decisions say.
   - Keep `LINK`.
   - `sync_gmail(client, store)` keeps its signature and returns
     `mail_sync.run_round(<adapter>, store)`. The adapter does the following:
     - Its `provider` is `"gmail"` and its `resumed` is `"history"`.
     - `begin()` reads `client.profile()`.
     - `start(after)` lists the inbox. Its bookmark is the profile's history id.
     - `resume(bookmark)` reads `history(bookmark)`. It returns `None` on
       `BookmarkExpired`.
     - `fetch(id)` returns `None` on `MessageGone` or `ValueError`. It also returns
       `None` unless `INBOX` is among the labels, with neither `SPAM` nor `TRASH`.
       Otherwise it returns the raw message, its thread id, its `internal_date`, and
       the `LINK` for the profile's address.
3. **`outlook_sync.py`.**
   - It imports nothing from `gmail_sync` or `gmail`.
   - It keeps `INBOX_LINK`, `WEB_LINK_PREFIX` and `_web_link`.
   - `sync_outlook(client, store)` returns `mail_sync.run_round(<adapter>, store)`. The
     adapter does the following:
     - Its `provider` is `"outlook"` and its `resumed` is `"delta"`.
     - `begin()` reads `client.profile()`.
     - `start(after)` is `first_delta(after)` with its delta link.
     - `resume(bookmark)` is `next_delta(bookmark)`. It returns `None` on
       `DeltaExpired`.
     - `fetch(id)` returns `None` on `MessageGone` or `ValueError`, or when the message
       is not in the profile's inbox folder. Otherwise it returns the raw message, its
       thread id, `received_at` and `_web_link(web_link)`.
   - In a fresh interpreter, `import mailroom.mail_sync, mailroom.outlook_sync` loads no
     `mailroom.gmail*` module.
4. **`service.py`** imports `SyncResult` from `mail_sync`. Nothing else in it changes.
5. **Compatibility.** Existing tests keep passing unchanged. These stay the same:
   - every stored record, id, link and bookmark;
   - the provider requests and their order;
   - the `SyncResult` values;
   - the catch-up alert inputs;
   - the errors that reach the service.
6. **Critical module.** Add `mail_sync.py` to the critical modules list in
   `docs/testing.md`. This is done in the planning commit; the coder does not edit it.
7. **Progress entry** for `## Phase 4l: Extract provider-neutral sync policy (YYYY-MM-DD)`
   at the end of `docs/progress.md`, with actual counts.

## Given files

Committed with the finalized spec before coding. The coder never changes them.

| File | What it is |
|---|---|
| `tests/integration/test_mail_sync.py` | 10 cases, using a scripted adapter for an invented `yahoo` account. They check that the windows and `SyncResult` are mail_sync's objects, re-exported by `gmail_sync` and used by `outlook_sync` and `service`, and that a fresh interpreter loading `mail_sync` and `outlook_sync` loads no gmail module. They cover a first round's exact calls, window, stored record and bookmark, and a resumed round under the adapter's own kind name. A catch-up after 2, 14 and 20 days checks its window, gap and offline time. Further cases cover a stored message that is not fetched again, a missing message and unusable thread, link and time values left out, an interrupted round that keeps the bookmark and what it stored, and two accounts that keep separate bookmarks |
| `tests/integration/test_sync_parity.py` | 2 cases. Gmail and Outlook go through one five-round timeline (first run, resume, expired bookmark after 2 days, nothing new, expired after 20 days) against their fakes. Each must give the same kinds, counts, offline times and gaps, and send every round through `mail_sync.run_round` |
| `docs/verification/probe-04l.py` | It loads `mail_sync` and `outlook_sync` in a fresh interpreter, and inspects `mail_sync.py`'s imports (no provider) and the shared names. It runs 60 seeded random histories of a scripted adapter, with random absences, expiries, repeats, skips and mid-round failures, against its own oracle of every call, result and bookmark. It runs 12 seeded random timelines through both real adapters, which must match its oracle and each other, every round through `run_round` |

Given test count: **12** new cases, so the minimum final suite is **1571**.

## Tests to write

Add behavior tests in `tests/integration/test_sync_adapters.py`, not a `_more` file.
`mail_sync.py` and `gmail_sync.py` are critical: cover every line and branch.
`outlook_sync.py` stays at 100% too. Add tests for behavior the given and existing tests
leave unpinned, at least:

- Gmail skips a message labelled both `INBOX` and `SPAM`. No existing test pins this;
  the spam case there has no `INBOX` label. The message must reach the fetch filter:
  FakeGmail's first-run list already leaves out spam and trash, so deliver it after a
  bookmark and let a history round fetch it (see Corrections).
- Each adapter's `resume` returns `None` on its own expiry error only. Another error from
  `history` or `next_delta`, such as a transport failure, propagates from `sync_gmail` or
  `sync_outlook` and leaves the bookmark unchanged.
- Each adapter reads its profile before its first listing or resume. The existing Gmail
  test pins only the first run.
- `store.add` returning false leaves the id out of `stored` for the scripted adapter, and
  the round still saves its bookmark.

Use synthetic data. Do not edit given or earlier tests.

## Scope

| Path | Change |
|---|---|
| `src/mailroom/mail_sync.py` | New: the windows, `SyncResult`, `Page`, `Fetched`, `Source` and `run_round` |
| `src/mailroom/gmail_sync.py` | Re-exports, the Gmail adapter and the thin `sync_gmail` |
| `src/mailroom/outlook_sync.py` | Imports from `mail_sync`, the Outlook adapter and the thin `sync_outlook` |
| `src/mailroom/service.py` | The `SyncResult` import only |
| `tests/integration/test_sync_adapters.py` | New coder-written behavior tests |
| `docs/progress.md` | Append the Phase 4l entry |

New tests fall in `core`, so `tests/sections.toml` stays unchanged.

## Out of scope

- A Yahoo or IMAP adapter. The given tests' `yahoo` source is a test double only.
- The provider clients (`gmail.py`, `outlook.py`), token handling and retries. Those are
  4m.
- The service's per-provider account functions, auth alerts, `_catch_up` alert keys and
  the `isinstance` dispatch. Those are 4n.
- Changes to the windows, the inbox, spam, trash or folder rules, link rules, dedup,
  schema or bookmark format.
- Changes to fakes, given files, earlier tests, earlier probes, dependencies or design
  documents. The `docs/testing.md` line comes with this spec.

## Rules that bite

All checks are synthetic and offline, against FakeGmail, FakeGraph and a scripted
adapter on temporary database files. Never touch real mail, Google, Microsoft, the
Keychain or the data folder.

- **Keep the call order.** Read the clock once and first, then the bookmark, then call
  `begin()`. The clients read the clock for token expiry. A round that calls the
  profile first, or reads the clock again, changes what existing tests see.
- **Skip before fetching.** The store check comes before `fetch`. A stored message must
  never be fetched again.
- **Save last.** Write the bookmark only after the last message. Never save it in a
  `finally`, and never catch an adapter error to save it.
- **`None` means expired only in `resume`.** Do not catch the provider's other errors,
  or a broad `Exception`, to return `None` or skip a message.
- **The shared names must be mail_sync's objects.** A second `SyncResult` class would
  make results unequal to the ones tests build.

## Acceptance

Run from the repository root, in order. The coverage row reads the data the check left;
the given-only run has `--no-cov` and does not overwrite it.

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first core` | The last line is `All checks passed.`. The tests (core) passed: at least 1571 passed; 0 failed, skipped or xfailed; no warnings. Every Sections row has 0 failed |
| `.venv/bin/python -m coverage report --include='src/mailroom/mail_sync.py,src/mailroom/gmail_sync.py,src/mailroom/outlook_sync.py' --fail-under=100` | exit 0; TOTAL 100% |
| `.venv/bin/python -m pytest tests/integration/test_mail_sync.py tests/integration/test_sync_parity.py --no-cov -q` | 12 passed |
| `.venv/bin/python docs/verification/probe-04l.py` | each check line ends ok; final FAILURES 0 |
| `.venv/bin/python docs/verification/probe-01n.py` | final FAILURES 0 |
| `.venv/bin/python docs/verification/probe-04b.py` | final FAILURES 0 |
| `grep -c '^## Phase 4l: ' docs/progress.md` | 1 |
| `.venv/bin/python scripts/check_reports.py --phase 4l` | Reports OK. |
| `git diff HEAD --stat -- docs/phases/phase-04l-shared-sync-round.md docs/verification/phase-04l-shared-sync-round.md tests/integration/test_mail_sync.py tests/integration/test_sync_parity.py docs/verification/probe-04l.py docs/testing.md` | no output |
| `git status --short --untracked-files=all` | only Scope paths; a verifier may also write its named review |

### Searches

Each prints nothing. A git grep exit of 1 means no matches, and an exit above 1 is an
error.

```zsh
git grep --untracked -n -E 'FIRST_RUN =|CATCH_UP_[A-Z]+ =|timedelta\(|class SyncResult|sync_state\(|store\.(get|add)\(|parse_message|stored_id|Envelope\(|clock\.' -- src/mailroom/gmail_sync.py src/mailroom/outlook_sync.py
git grep --untracked -n -i -E 'gmail|outlook|google|microsoft|graph|yahoo' -- src/mailroom/mail_sync.py
git grep --untracked -n -E 'gmail' -- src/mailroom/outlook_sync.py
git grep --untracked -n -E 'from mailroom\.gmail_sync import|gmail_sync\.(SyncResult|FIRST_RUN|CATCH_UP)|import .*run_round|^ +run_round,$' -- src/mailroom
git grep --untracked -n -E 'except (Exception|BaseException)[ :]|pragma: no cover|noqa|datetime\.now|from mailroom\.(clock|ids) import|print\(|logging|finally:' -- src/mailroom/mail_sync.py src/mailroom/gmail_sync.py src/mailroom/outlook_sync.py
```

## Architect validation and handoff

No feature implementation was built. The given tests collect on predecessor imports,
and all 12 new cases fail there.

A throwaway scratch stand-in (about 340 changed lines, 102 of them the new module,
deleted with the scratch clone) did the following. It is not a reference for the coder.

- It passed the given tests 6 of 6 runs.
- It passed all 145 sync, alert and service tests, the given ones included.
- It left `mail_sync.py`, `gmail_sync.py` and `outlook_sync.py` at 100% line and branch
  coverage.
- `probe-01n.py` and `probe-04b.py` ended FAILURES 0 on it.
- 13 of 13 mutations of it were caught by a given or existing test:
  - a two-day first run, a catch-up with no overlap or no 14-day limit, and a gap at
    exactly 14 days;
  - no offline time, and every resumed round named `delta`;
  - the bookmark saved before storing, and a stored message fetched again;
  - an unusable envelope stopping the round, and `begin` skipped;
  - `outlook_sync` importing from `gmail_sync` again;
  - Gmail keeping inbox mail in the trash, and Outlook keeping mail outside the inbox.

A 14th mutation, Gmail keeping mail labelled both `INBOX` and `SPAM`, was missed by every
existing test. The spec asks the coder's tests to pin it, and the guide makes it a spot
check.

The probe results:

- On predecessor code it ends FAILURES 5, since `mailroom.mail_sync` does not exist.
- On the stand-in it ends FAILURES 0.
- It catches 10 of the 13 mutations. It leaves to the tests the exact 14-day gap, which
  its random absences never hit, and both adapters' filter rules, since it delivers only
  inbox mail.

The searches print nothing on the stand-in, and each catches a planted line. On
predecessor code, searches 1, 3 and 4 print the old windows, round steps and imports.
Start shows 1559 passed. The given files are linted and formatted.

Before coder use, commit the finalized planning docs and given artifacts, including the
roadmap, history and `docs/testing.md` updates, and require a clean checkout.
