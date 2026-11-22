# Test helpers that given tests trip on

Read this before writing given tests or a probe. Each point here cost a validation
round in an earlier phase. Check the source when a detail matters: `tests/fakes.py`,
`tests/support.py`, `tests/conftest.py`, and the shared helpers named below.

## Seams and isolation

- `tests/conftest.py` blocks every socket that is not 127.0.0.1 or a Unix socket.
  It installs a failing keyring unless a test asks for `fake_keychain`. It removes
  every `MAILROOM_` variable and puts home and data under `tmp_path`.
- `fixed_times(monkeypatch, *iso)` gives one moment per `clock.now()` call and
  raises `StopIteration` when they run out, so count every read. For open-ended
  rounds use a list cell: `now = [NOW]` and `lambda: now[0]`.
- `fixed_ids(monkeypatch, *values)` works the same way for `ids.new_id()`.
- A new given file must import before the feature exists. Look up new names when a
  test runs (`mailroom.store.is_busy(error)` inside a helper), not with
  `from module import new_name`.

## Fakes

- **FakeKeychain** keys `secrets` by `("mailroom", name)`, and `writes` records
  successful sets. Setting `error` fails reads and writes alike. To fail only
  writes, subclass it and override `set_password` to raise
  `keyring.errors.KeyringError`; `keychain.set_secret` turns that into
  `KeychainUnavailable` (see `SaveFails` in `test_outlook_rotation.py`). It never
  deletes.
- **FakeGraph**: only the latest refresh token works. Every refresh issues
  `access-N` and rotates to `refresh-token-{N+1}`, and any other token gets 400
  `invalid_grant`. `token_failures` answers the token endpoint and `failures`
  answers Graph calls, each before any check. A token request is logged in
  `requests` even when it is answered from `token_failures`. Every Graph call needs
  `Prefer: IdType="ImmutableId"`.
- **FakeGmail**: refreshes return no new refresh token, so Gmail never writes to the
  Keychain.
- **FakeDiscord**: each entry of `messages` keeps only `id`, `channel_id`, `type`,
  `content`, `embeds`, `components`, `nonce` and `timestamp`. `allowed_mentions`
  and `enforce_nonce` are checked but not kept, so assert a ping by its
  `<@owner> ` content prefix. A repeated nonce with `enforce_nonce` returns the
  first message. `failures` entries may be `"lost-reply"`: the message is made,
  then `ReadTimeout` is raised. Interaction replies go to `callbacks` as
  `(interaction id, body)`. `press`, `submit` and `command` build Gateway events
  from the owner unless told otherwise.
- **FakeOllama** answers each call from `replies` in order. A round that triages
  mail with no reply queued fails triage, so append `GOOD` (from `test_service.py`)
  per message you expect triaged.

## Service rounds

- `Health.report` prints a line only when that part's state changes. A second
  round with the same failure prints nothing, so `both_round(...)[0]` raises
  `IndexError`. Assert the first round's line, or filter `world.lines` across rounds.
- `World` (`test_service.py`) seeds Gmail and the Discord token. `BothWorld`
  (`test_service_outlook.py`) adds `outlook.live.*` and a FakeGraph. Both build a
  new mail client every round. To keep one client across rounds, as `run_service`
  does, override `outlook()` to cache it (see `HeldWorld` in
  `test_service_rotation.py`). `BothWorld(keychain, ())` gives Outlook only.
- `alerts.track(store, problem, failing, wait=..., raised=..., ping=..., resolved=...)`
  raises its alert once per episode, and posts `resolved` only when the episode had
  alerted. Two resolutions in one round are queued in call order. A probe oracle
  should compare them as a set within a round, not by sorted text.
- Tracked problems in `service.py`: `gmail-auth:<account>`, `outlook-auth:<account>`,
  `outlook-token:<account>`, `model`, `tasks`, `listener` and `gateway`. Notices
  (posted once, never tracked): `catch-up:...` and `store:<since>:resolved`. The
  texts are in `discord_layout.py`.

## Store and locks

- `test_store_rollback.py` has `unlocked()` (can another connection take the write
  lock now) and `notified(store, *ids)`.
- `test_store_busy.py` has `Holder`, a raw second connection with `write_lock`,
  `read_lock` and `release`. It is opened with `check_same_thread=False`, so a timer
  thread can release it.
- `test_interactions.py` has `posted_store()`, `ephemeral(text)`, `RECORD`,
  `VERDICT` and `ITEM`.

## Validation traps

- A test that only checks layout text passes on predecessor code. Drop it, or tie
  it to behavior.
- Run mutations with `phase_tools.py mutate`, never by hand, so stale bytecode can't
  hide a mutation (see [mutations](mutations.md)).
- A grep search over all of `src/mailroom` for a name like `{token}` matches
  unrelated code, such as Discord's `Bot {token}` headers. Scope searches to the
  phase's files, and run them on predecessor code first.
