from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest

from mailroom.config import Settings, get_settings
from mailroom.discord_post import PostReport, open_discord_http
from mailroom.store import Store, open_store
from tests.fakes import FakeDiscord, FakeKeychain
from tests.integration.test_discord_post import ITEM_1, ITEM_2, RECORD, UNREAD, run
from tests.support import fixed_ids


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


def test_open_discord_http_ignores_proxy_settings_and_times_out() -> None:
    client = open_discord_http()
    assert client.timeout == httpx.Timeout(30.0)
    assert client.trust_env is False
    assert client.follow_redirects is False
    client.close()


def test_a_reply_that_is_not_json_stops_as_a_bad_response(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    discord.failures.append(httpx.Response(200, text="not json"))
    report = run(store, settings, discord)
    assert report == PostReport(posted=0, waiting=2, stopped="response")
    assert "not json" not in str(report)
    assert [post.item_id for post in store.pending_posts()] == [ITEM_1, ITEM_2]


def test_a_401_leaves_every_post_queued(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    discord.failures.append(httpx.Response(401, json={"message": "401: Unauthorized", "code": 0}))
    assert run(store, settings, discord) == PostReport(posted=0, waiting=2, stopped="401")
    assert [post.item_id for post in store.pending_posts()] == [ITEM_1, ITEM_2]
    assert len(discord.requests) == 1
