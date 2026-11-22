"""A pending card whose stored rows are incomplete is kept unsent and reported; the rest post."""

import itertools
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock, ids
from mailroom.checkpoint import checkpoint_message
from mailroom.config import Settings, get_settings
from mailroom.discord_post import post_pending
from mailroom.record import Record
from mailroom.store import DB_FILENAME, Store, Verdict, open_store
from tests.fakes import FakeDiscord, FakeKeychain

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
ALERT = "Mailroom kept item {item} unsent: its stored details are incomplete."
RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 21, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=None,
    body_text="Your bill is due.",
    list_unsubscribe=False,
    authentication_results=(),
)
UNREAD = Verdict(
    outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="timeout"
)


def remove(sql: str) -> None:
    """Delete rows with a second connection, as damage outside Mailroom would."""
    raw = sqlite3.connect(get_settings().data_dir / DB_FILENAME)
    try:
        raw.execute(sql)
        raw.commit()
    finally:
        raw.close()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    counter = itertools.count(1)
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):02d}" + "a" * 30)
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


@pytest.fixture
def discord(fake_keychain: FakeKeychain) -> FakeDiscord:
    fake = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    return fake


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    """Three notified emails, m1 to m3, in separate threads, queued as items 1 to 3."""
    with open_store(settings) as opened:
        for number in (1, 2, 3):
            opened.add(replace(RECORD, message_id=f"m{number}", thread_id=f"t{number}"))
            opened.save_triage("gmail", f"m{number}", UNREAD)
        opened.queue_notified()
        yield opened


def item(store: Store, message_id: str) -> str:
    return store.post("gmail", message_id).item_id


def run(store: Store, settings: Settings, discord: FakeDiscord):
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    return post_pending(store, settings, http)


def alerts(store: Store) -> list[tuple[str, str, bool]]:
    return [(alert.key, alert.text, alert.ping) for alert in store.pending_alerts()]


@pytest.mark.parametrize("table", ("messages", "triage"))
def test_an_incomplete_card_is_kept_and_the_others_still_post(
    store: Store, settings: Settings, discord: FakeDiscord, table: str
) -> None:
    first = item(store, "m1")
    remove(f"DELETE FROM {table} WHERE message_id = 'm1'")
    report = run(store, settings, discord)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (2, 0, "", 1)
    assert [json.loads(request.content)["nonce"] for request in discord.requests] == [
        item(store, "m2")[:25],
        item(store, "m3")[:25],
    ]
    assert [post.item_id for post in store.pending_posts()] == [first]
    assert store.post_by_item(first).discord_message_id is None
    assert alerts(store) == [(f"incomplete:{first}", ALERT.format(item=first), False)]


def test_the_notice_is_queued_once_and_the_card_stays_kept(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    first = item(store, "m1")
    remove("DELETE FROM triage WHERE message_id = 'm1'")
    run(store, settings, discord)
    for _ in range(2):
        report = run(store, settings, discord)
        assert (report.posted, report.waiting, report.stopped, report.skipped) == (0, 0, "", 1)
    assert len(discord.requests) == 2
    assert len(alerts(store)) == 1
    assert [post.item_id for post in store.pending_posts()] == [first]


def test_a_follow_up_card_whose_task_approval_is_gone_is_kept(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    first = item(store, "m1")
    remove(f"UPDATE posts SET card = 'followup', follows = '{'f' * 32}' WHERE message_id = 'm1'")
    report = run(store, settings, discord)
    assert (report.posted, report.skipped) == (2, 1)
    assert [post.item_id for post in store.pending_posts()] == [first]
    assert alerts(store) == [(f"incomplete:{first}", ALERT.format(item=first), False)]


def test_a_kept_card_posts_once_its_rows_are_back(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    first = item(store, "m1")
    remove("DELETE FROM triage WHERE message_id = 'm1'")
    run(store, settings, discord)
    store.save_triage("gmail", "m1", UNREAD)
    report = run(store, settings, discord)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (1, 0, "", 0)
    assert json.loads(discord.requests[-1].content) == checkpoint_message(RECORD, UNREAD, first)
    assert store.pending_posts() == ()


def test_complete_cards_post_exactly_once_and_skip_nothing(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    report = run(store, settings, discord)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (3, 0, "", 0)
    report = run(store, settings, discord)
    assert (report.posted, report.skipped) == (0, 0)
    assert len(discord.messages) == 3
    assert alerts(store) == []


def test_a_failed_send_after_a_kept_card_counts_only_the_unsent_rest(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    remove("DELETE FROM messages WHERE message_id = 'm1'")
    discord.failures.append(httpx.Response(503))
    report = run(store, settings, discord)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (0, 2, "503", 1)
    assert len(store.pending_posts()) == 3
