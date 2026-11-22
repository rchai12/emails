"""A poll round goes on past an incomplete card: the others post, and the owner gets one notice."""

import sqlite3
from collections.abc import Iterator

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.store import DB_FILENAME, Store, open_store
from tests.fakes import FakeKeychain, FakeTasksApp
from tests.integration.test_service import GOOD, NOW, World, deliver

ALERT = "Mailroom kept item {item} unsent: its stored details are incomplete."


def remove(sql: str) -> None:
    raw = sqlite3.connect(get_settings().data_dir / DB_FILENAME)
    try:
        raw.execute(sql)
        raw.commit()
    finally:
        raw.close()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    for name, value in (
        ("MAILROOM_GMAIL_ACCOUNTS", "personal"),
        ("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b"),
        ("MAILROOM_TIME_ZONE", "America/New_York"),
        ("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111"),
        ("MAILROOM_DISCORD_OWNER_ID", "444444444444444444"),
        ("MAILROOM_TASKS_URL", FakeTasksApp.URL),
    ):
        monkeypatch.setenv(name, value)
    return get_settings()


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    with open_store(settings) as opened:
        yield opened


def test_a_round_posts_past_an_incomplete_card_and_says_so(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    deliver(world.gmail["personal"], 1)
    deliver(world.gmail["personal"], 2)
    world.model.replies.extend([GOOD, GOOD])
    world.discord.failures.append(httpx.Response(503))
    world.round(store, settings)
    (kept,) = [post.item_id for post in store.pending_posts() if post.message_id.endswith("m1")]
    remove("DELETE FROM messages WHERE message_id = 'personal/m1'")
    lines = world.round(store, settings)
    assert "discord posting: ok (1 incomplete)" in lines
    assert [post.item_id for post in store.pending_posts()] == [kept]
    contents = [message["content"] for message in world.discord.messages]
    assert contents.count(ALERT.format(item=kept)) == 1
    world.round(store, settings)
    contents = [message["content"] for message in world.discord.messages]
    assert contents.count(ALERT.format(item=kept)) == 1
    assert [post.item_id for post in store.pending_posts()] == [kept]
