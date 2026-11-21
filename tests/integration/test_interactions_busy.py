"""A press or command that meets a locked database is asked, privately, to press again.

Another connection holds the file's write lock, as the poll loop's store or another program
would. Reads still work under it; the press's first write waits the listener's lock wait and
gives up. Pressing again after the lock is gone finishes the answer once.
"""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock
from mailroom.checkpoint import answered_message
from mailroom.config import Settings, get_settings
from mailroom.interactions import handle_interaction
from mailroom.store import Store
from tests.fakes import FakeDiscord
from tests.integration.test_interactions import ITEM, RECORD, VERDICT, ephemeral, posted_store
from tests.integration.test_store_busy import Holder
from tests.integration.test_store_rollback import unlocked
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
BUSY = ephemeral("Mailroom is busy right now. Press again in a moment.")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Iterator[Store]:
    fixed_ids(monkeypatch, ITEM)
    monkeypatch.setattr(clock, "now", lambda: NOW)
    opened = posted_store()
    opened.set_lock_wait(0.05)
    yield opened
    opened.close()


@pytest.fixture
def holder(store: Store) -> Iterator[Holder]:
    held = Holder()
    yield held
    held.connection.close()


def answer(store: Store, settings: Settings, discord: FakeDiscord, event: dict):
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    before = len(discord.callbacks)
    outcome = handle_interaction(event, store, settings, http)
    replies = discord.callbacks[before:]
    assert len(replies) <= 1
    return outcome, replies[0][1] if replies else None


def real_error() -> sqlite3.OperationalError:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("SELECT x FROM missing")
    except sqlite3.OperationalError as error:
        return error
    finally:
        connection.close()
    raise AssertionError("no error")


@pytest.mark.parametrize("action", ["mute", "notask", "yes"])
def test_a_press_that_meets_a_locked_file_is_asked_to_press_again(
    store: Store, settings: Settings, holder: Holder, action: str
) -> None:
    discord = FakeDiscord()
    holder.write_lock()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:{action}:{ITEM}"))
    holder.release()
    assert (outcome, reply) == ("busy", BUSY)
    assert store.answer(ITEM) is None
    assert store.sender_status("billing@example.test") is None
    assert unlocked()


def test_pressing_again_after_the_lock_clears_answers_once(
    store: Store, settings: Settings, holder: Holder
) -> None:
    discord = FakeDiscord()
    holder.write_lock()
    assert answer(store, settings, discord, discord.press(f"mr:mute:{ITEM}"))[0] == "busy"
    holder.release()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:mute:{ITEM}"))
    assert (outcome, reply) == (
        "answered",
        {"type": 7, "data": answered_message(RECORD, VERDICT, ITEM, "mute", "")},
    )
    stored = store.answer(ITEM)
    assert stored is not None
    assert (stored.answer, stored.title) == ("mute", "")
    assert store.sender_status("billing@example.test") == "muted"
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:notask:{ITEM}"))
    assert (outcome, reply) == ("already", ephemeral("This email is already answered."))


def test_a_mute_whose_second_write_meets_the_lock_finishes_when_pressed_again(
    store: Store, settings: Settings, holder: Holder, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_answer = store.record_answer
    locked: list[bool] = []

    def lock_first(item_id: str, answer_text: str, title: str) -> bool:
        if not locked:
            locked.append(True)
            holder.write_lock()
        return record_answer(item_id, answer_text, title)

    monkeypatch.setattr(store, "record_answer", lock_first)
    discord = FakeDiscord()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:mute:{ITEM}"))
    assert (outcome, reply) == ("busy", BUSY)
    assert store.sender_status("billing@example.test") == "muted"
    assert store.answer(ITEM) is None
    holder.release()
    assert unlocked()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:mute:{ITEM}"))
    assert outcome == "answered"
    stored = store.answer(ITEM)
    assert stored is not None
    assert stored.answer == "mute"
    assert store.sender_status("billing@example.test") == "muted"


def test_a_command_that_meets_a_locked_file_is_asked_to_press_again(
    store: Store, settings: Settings, holder: Holder
) -> None:
    discord = FakeDiscord()
    holder.write_lock()
    outcome, reply = answer(store, settings, discord, discord.command("trust", "sam@example.test"))
    holder.release()
    assert (outcome, reply) == ("busy", BUSY)
    assert store.sender_status("sam@example.test") is None
    assert unlocked()


def test_a_submitted_title_that_meets_a_locked_file_is_asked_to_press_again(
    store: Store, settings: Settings, holder: Holder
) -> None:
    discord = FakeDiscord()
    holder.write_lock()
    outcome, reply = answer(
        store, settings, discord, discord.submit(f"mr:title:{ITEM}", "Pay the bill")
    )
    holder.release()
    assert (outcome, reply) == ("busy", BUSY)
    assert store.answer(ITEM) is None


def test_a_press_from_someone_else_is_still_ignored_while_the_file_is_locked(
    store: Store, settings: Settings, holder: Holder
) -> None:
    discord = FakeDiscord()
    holder.write_lock()
    event = discord.press(f"mr:mute:{ITEM}", user_id="555555555555555555")
    outcome, reply = answer(store, settings, discord, event)
    holder.release()
    assert (outcome, reply) == ("ignored", {"type": 6})


@pytest.mark.parametrize("method", ["set_sender_status", "post_by_item"])
def test_a_database_error_that_is_not_a_lock_wait_is_not_hidden(
    store: Store, settings: Settings, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    error = real_error()

    def broken(*args: object) -> None:
        raise error

    monkeypatch.setattr(store, method, broken)
    discord = FakeDiscord()
    with pytest.raises(sqlite3.OperationalError) as caught:
        answer(store, settings, discord, discord.press(f"mr:mute:{ITEM}"))
    assert caught.value is error
    assert discord.callbacks == []
