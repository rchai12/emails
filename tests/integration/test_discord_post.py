import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest

from mailroom.checkpoint import checkpoint_message
from mailroom.config import Settings, get_settings
from mailroom.discord_post import (
    DiscordUnavailable,
    PostReport,
    post_pending,
)
from mailroom.keychain import SecretMissing
from mailroom.record import Record
from mailroom.store import Store, Verdict, open_store
from tests.fakes import FakeDiscord, FakeKeychain
from tests.support import fixed_ids

RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
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
ITEM_1 = "1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ITEM_2 = "2aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
URL = "https://discord.com/api/v10/channels/111111111111111111/messages"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    return get_settings()


@pytest.fixture
def discord(fake_keychain: FakeKeychain) -> FakeDiscord:
    fake = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    return fake


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    fixed_ids(monkeypatch, ITEM_1, ITEM_2)
    with open_store(get_settings()) as opened:
        for message_id in ("m1", "m2"):
            opened.add(replace(RECORD, message_id=message_id))
            opened.save_triage("gmail", message_id, UNREAD)
        yield opened


def run(store: Store, settings: Settings, discord: FakeDiscord) -> PostReport:
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    return post_pending(store, settings, http)


def test_each_notified_email_is_posted_once_and_recorded(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    assert run(store, settings, discord) == PostReport(posted=2, waiting=0, stopped="")
    first, second = discord.requests
    assert (first.method, str(first.url)) == ("POST", URL)
    assert first.headers["authorization"] == "Bot discord-token-test"
    assert first.headers["user-agent"] == "DiscordBot (mailroom, 0.1.0)"
    assert json.loads(first.content) == checkpoint_message(RECORD, UNREAD, ITEM_1)
    assert json.loads(second.content) == checkpoint_message(
        replace(RECORD, message_id="m2"), UNREAD, ITEM_2
    )
    posted = store.post("gmail", "m1")
    assert posted is not None
    assert posted.discord_message_id == "1300000000000000001"
    assert run(store, settings, discord) == PostReport(posted=0, waiting=0, stopped="")
    assert len(discord.requests) == 2


@pytest.mark.parametrize(
    ("failure", "stopped"),
    [
        (
            httpx.Response(
                429,
                json={
                    "message": "You are being rate limited.",
                    "retry_after": 1.5,
                    "global": False,
                },
            ),
            "429",
        ),
        (httpx.Response(500, text="oops"), "500"),
        (httpx.ConnectError("refused"), "network"),
        (httpx.Response(200, json={"channel_id": "111111111111111111"}), "response"),
    ],
    ids=["rate-limited", "server-error", "network", "no-message-id"],
)
def test_a_failed_send_stops_the_round_and_is_retried_next_time(
    store: Store, settings: Settings, discord: FakeDiscord, failure: object, stopped: str
) -> None:
    discord.failures.append(failure)
    assert run(store, settings, discord) == PostReport(posted=0, waiting=2, stopped=stopped)
    assert [post.item_id for post in store.pending_posts()] == [ITEM_1, ITEM_2]
    assert run(store, settings, discord) == PostReport(posted=2, waiting=0, stopped="")


def test_a_failure_after_one_post_keeps_the_first(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    discord.failures.extend([None, httpx.Response(503, text="busy")])
    assert run(store, settings, discord) == PostReport(posted=1, waiting=1, stopped="503")
    assert [post.item_id for post in store.pending_posts()] == [ITEM_2]


def test_a_lost_reply_never_makes_a_second_message(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    discord.failures.append("lost-reply")
    assert run(store, settings, discord) == PostReport(posted=0, waiting=2, stopped="network")
    assert run(store, settings, discord) == PostReport(posted=2, waiting=0, stopped="")
    assert len(discord.messages) == 2
    posted = store.post("gmail", "m1")
    assert posted is not None
    assert posted.discord_message_id == "1300000000000000001"


def test_without_a_channel_nothing_is_read_or_sent(
    store: Store, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    with pytest.raises(DiscordUnavailable) as caught:
        run(store, get_settings(), discord)
    assert str(caught.value) == "discord unavailable (not configured)"
    assert caught.value.__suppress_context__
    assert (fake_keychain.calls, discord.requests, store.pending_posts()) == ([], [], ())


def test_nothing_to_post_reads_no_token(
    settings: Settings, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    with open_store(get_settings()) as empty:
        assert run(empty, settings, discord) == PostReport(posted=0, waiting=0, stopped="")
    assert (fake_keychain.calls, discord.requests) == ([], [])


def test_a_missing_token_sends_nothing(
    store: Store, settings: Settings, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    fake_keychain.secrets.clear()
    with pytest.raises(SecretMissing):
        run(store, settings, discord)
    assert discord.requests == []
    assert len(store.pending_posts()) == 2
