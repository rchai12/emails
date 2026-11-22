"""A press or form on an email with incomplete stored rows gets a private notice, nothing more."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.interactions import handle_interaction
from mailroom.store import DB_FILENAME, Store
from tests.fakes import FakeDiscord
from tests.integration.test_interactions import ITEM, ephemeral, posted_store
from tests.support import fixed_ids

NOTICE = "Mailroom can't act on this email: its stored details are incomplete."
PRESSES = ("full", "trust", "yes", "edit", "notask", "mute", "link", "approve", "drop")
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


@pytest.fixture
def store(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    """The shared posted card, with an open clock so a test may read the time freely."""
    monkeypatch.setattr(clock, "now", lambda: NOW)
    fixed_ids(monkeypatch, ITEM)
    opened = posted_store()
    yield opened
    opened.close()


def remove(sql: str) -> None:
    """Delete rows with a second connection, as damage outside Mailroom would."""
    raw = sqlite3.connect(get_settings().data_dir / DB_FILENAME)
    try:
        raw.execute(sql)
        raw.commit()
    finally:
        raw.close()


def press(store: Store, settings: Settings, discord: FakeDiscord, event: dict) -> tuple[str, dict]:
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    before = len(discord.callbacks)
    outcome = handle_interaction(event, store, settings, http)
    (reply,) = discord.callbacks[before:]
    return outcome, reply[1]


def unchanged(store: Store) -> None:
    assert store.answer(ITEM) is None
    assert store.approval(ITEM) is None
    assert store.sender_status("billing@example.test") is None
    assert store.queue_approved() == 0
    assert store.queue_linked() == 0


@pytest.mark.parametrize("action", PRESSES)
def test_a_press_on_an_email_whose_message_row_is_gone_gets_the_notice(
    store: Store, settings: Settings, action: str
) -> None:
    remove("DELETE FROM messages")
    discord = FakeDiscord()
    outcome, reply = press(store, settings, discord, discord.press(f"mr:{action}:{ITEM}"))
    assert (outcome, reply) == ("incomplete", ephemeral(NOTICE))
    unchanged(store)


@pytest.mark.parametrize("action", PRESSES)
def test_a_press_on_an_email_whose_triage_row_is_gone_gets_the_notice(
    store: Store, settings: Settings, action: str
) -> None:
    remove("DELETE FROM triage")
    discord = FakeDiscord()
    outcome, reply = press(store, settings, discord, discord.press(f"mr:{action}:{ITEM}"))
    assert (outcome, reply) == ("incomplete", ephemeral(NOTICE))
    unchanged(store)


@pytest.mark.parametrize("form", ("title", "task"))
def test_a_form_on_an_incomplete_email_gets_the_notice_and_records_nothing(
    store: Store, settings: Settings, form: str
) -> None:
    store.record_answer(ITEM, "yes", "Pay the November bill")
    remove("DELETE FROM triage")
    discord = FakeDiscord()
    event = discord.submit(f"mr:{form}:{ITEM}", "Pay it", fields={"deadline": ""})
    assert press(store, settings, discord, event) == ("incomplete", ephemeral(NOTICE))
    assert store.answer(ITEM).title == "Pay the November bill"
    assert store.approval(ITEM) is None
    assert store.queue_approved() == 0


@pytest.mark.parametrize("action", ("link", "notask", "mute", "full"))
def test_a_follow_up_whose_task_approval_is_gone_gets_the_notice(
    store: Store, settings: Settings, action: str
) -> None:
    remove(f"UPDATE posts SET card = 'followup', follows = '{'f' * 32}'")
    discord = FakeDiscord()
    outcome, reply = press(store, settings, discord, discord.press(f"mr:{action}:{ITEM}"))
    assert (outcome, reply) == ("incomplete", ephemeral(NOTICE))
    unchanged(store)


def test_a_combined_card_whose_message_row_is_gone_approves_nothing(
    store: Store, settings: Settings
) -> None:
    remove("UPDATE posts SET card = 'combined'")
    remove("DELETE FROM messages")
    discord = FakeDiscord()
    for action in ("approve", "nodeadline", "change"):
        outcome, reply = press(store, settings, discord, discord.press(f"mr:{action}:{ITEM}"))
        assert (outcome, reply) == ("incomplete", ephemeral(NOTICE))
    unchanged(store)


def test_only_the_owner_gets_the_notice_and_others_are_still_ignored(
    store: Store, settings: Settings
) -> None:
    remove("DELETE FROM messages")
    discord = FakeDiscord()
    stranger = discord.press(f"mr:yes:{ITEM}", user_id="555555555555555555")
    assert press(store, settings, discord, stranger) == ("ignored", {"type": 6})
    owner = discord.press(f"mr:yes:{ITEM}")
    assert press(store, settings, discord, owner) == ("incomplete", ephemeral(NOTICE))
    unchanged(store)


def test_the_notice_names_nothing_from_the_email(store: Store, settings: Settings) -> None:
    remove("DELETE FROM triage")
    discord = FakeDiscord()
    _, reply = press(store, settings, discord, discord.press(f"mr:full:{ITEM}"))
    shown = reply["data"]["content"]
    for text in ("Your November bill", "billing@example.test", "$42.00", "m1", ITEM):
        assert text not in shown
