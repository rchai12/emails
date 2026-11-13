"""Coverage for alert edges the given tests leave closed."""

from collections.abc import Iterator
from datetime import timedelta

import httpx
import pytest

from mailroom import clock, gmail_sync
from mailroom.alerts import post_alerts
from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable, PostReport
from mailroom.gmail_sync import SyncResult
from mailroom.store import Store, open_store
from tests.fakes import FakeDiscord, FakeKeychain
from tests.integration.test_service_alerts import GOOD, NOW, World, deliver
from tests.support import fixed_ids

ALERT_ID = "abbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    monkeypatch.setenv("MAILROOM_GMAIL_ACCOUNTS", "personal")
    monkeypatch.setenv("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    return get_settings()


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def store(now: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    fixed_ids(monkeypatch, ALERT_ID)
    with open_store(get_settings()) as opened:
        opened.queue_alert("gmail-auth:personal:raised", "Gmail sign-in needed.", True)
        yield opened


def test_a_reply_without_an_id_stops_as_a_bad_response(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    discord = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
    discord.failures.append(httpx.Response(200, json={"ok": True}))
    report = post_alerts(
        store, settings, httpx.Client(transport=httpx.MockTransport(discord.handler))
    )
    assert report == PostReport(posted=0, waiting=1, stopped="response")
    assert len(store.pending_alerts()) == 1


def test_a_network_error_leaves_the_alert_waiting(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    discord = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
    discord.failures.append(httpx.ConnectError("refused"))
    report = post_alerts(
        store, settings, httpx.Client(transport=httpx.MockTransport(discord.handler))
    )
    assert report == PostReport(posted=0, waiting=1, stopped="network")
    assert len(store.pending_alerts()) == 1


def test_marking_an_unknown_or_posted_alert_changes_nothing(store: Store) -> None:
    assert store.mark_alert_posted("missing", "111") is False
    assert store.mark_alert_posted(ALERT_ID, "111") is True
    assert store.mark_alert_posted(ALERT_ID, "222") is False
    row = store._connection.execute(
        "SELECT discord_message_id FROM alerts WHERE alert_id = ?",
        (ALERT_ID,),
    ).fetchone()
    assert row == ("111",)
    assert store.pending_alerts() == ()


def test_a_catch_up_without_an_offline_time_posts_no_summary(
    settings: Settings, fake_keychain: FakeKeychain, now: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sync(client: object, found: Store) -> SyncResult:
        return SyncResult("personal", "catch_up", (), None, True)

    monkeypatch.setattr(gmail_sync, "sync_gmail", sync)
    world = World(fake_keychain)
    with open_store(settings) as opened:
        world.round(opened, settings)
        assert opened.pending_alerts() == ()
    assert world.posted() == []


def test_a_model_failure_after_one_email_leaves_the_problem_open(
    settings: Settings, fake_keychain: FakeKeychain, now: None
) -> None:
    world = World(fake_keychain)
    with open_store(settings) as opened:
        deliver(world.gmail, 1, NOW - timedelta(minutes=30))
        deliver(world.gmail, 2, NOW - timedelta(minutes=20))
        world.model.replies.append(httpx.ConnectError("refused"))
        world.round(opened, settings)
        opened_problem = opened.problem("model")
        assert opened_problem is not None
        assert opened_problem.alerted is False
        world.model.replies.extend([GOOD, httpx.ConnectError("refused")])
        world.round(opened, settings)
        assert opened.problem("model") == opened_problem
        assert "The local model is back. Waiting mail is being triaged." not in world.posted()


def test_a_queued_alert_without_a_bot_token_is_reported(
    settings: Settings, fake_keychain: FakeKeychain, now: None
) -> None:
    world = World(fake_keychain)
    del fake_keychain.secrets[("mailroom", "discord.bot-token")]
    world.keychain.secrets[("mailroom", "gmail.personal.refresh-token")] = "revoked"
    with open_store(settings) as opened:
        assert world.round(opened, settings)[-1] == (
            "discord alerts: secret not found: discord.bot-token"
        )
        assert len(opened.pending_alerts()) == 1


def test_without_an_owner_nothing_is_sent(
    store: Store, fake_keychain: FakeKeychain, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    discord = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = discord.token
    with pytest.raises(DiscordUnavailable) as caught:
        post_alerts(
            store,
            get_settings(),
            httpx.Client(transport=httpx.MockTransport(discord.handler)),
        )
    assert str(caught.value) == "discord unavailable (not configured)"
    assert discord.requests == []
    assert len(store.pending_alerts()) == 1
