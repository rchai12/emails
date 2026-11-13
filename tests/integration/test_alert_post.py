import json
from collections.abc import Iterator

import httpx
import pytest

from mailroom.alerts import notice, post_alerts
from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable, PostReport
from mailroom.store import Store, open_store
from tests.fakes import FakeDiscord, FakeKeychain
from tests.support import fixed_ids

ALERT_1 = "1bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
ALERT_2 = "2bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


@pytest.fixture
def discord(fake_keychain: FakeKeychain) -> FakeDiscord:
    fake = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    return fake


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    fixed_ids(monkeypatch, ALERT_1, ALERT_2)
    with open_store(get_settings()) as opened:
        opened.queue_alert("gmail-auth:personal:raised", "Gmail sign-in needed.", True)
        notice(opened, "catch-up:personal:1", "Gmail personal caught up.")
        yield opened


def post(store: Store, settings: Settings, discord: FakeDiscord) -> PostReport:
    return post_alerts(
        store, settings, httpx.Client(transport=httpx.MockTransport(discord.handler))
    )


def test_alerts_are_posted_in_order_and_only_action_alerts_ping(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    assert post(store, settings, discord) == PostReport(posted=2, waiting=0, stopped="")
    first, second = (json.loads(request.content) for request in discord.requests)
    assert first == {
        "content": "<@444444444444444444> Gmail sign-in needed.",
        "allowed_mentions": {"users": ["444444444444444444"]},
        "nonce": ALERT_1[:25],
        "enforce_nonce": True,
    }
    assert second == {
        "content": "Gmail personal caught up.",
        "allowed_mentions": {"parse": []},
        "nonce": ALERT_2[:25],
        "enforce_nonce": True,
    }
    assert store.pending_alerts() == ()
    assert post(store, settings, discord) == PostReport(posted=0, waiting=0, stopped="")


@pytest.mark.parametrize(
    ("failure", "stopped"),
    [(httpx.Response(429, json={"retry_after": 1.0}), "429"), ("lost-reply", "network")],
    ids=["rate-limited", "lost-reply"],
)
def test_a_failed_alert_waits_for_the_next_round_and_is_never_doubled(
    store: Store, settings: Settings, discord: FakeDiscord, failure: object, stopped: str
) -> None:
    discord.failures.append(failure)
    assert post(store, settings, discord) == PostReport(posted=0, waiting=2, stopped=stopped)
    assert post(store, settings, discord) == PostReport(posted=2, waiting=0, stopped="")
    assert len(discord.messages) == 2


def test_nothing_to_post_reads_no_token(
    settings: Settings, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    with open_store(get_settings()) as empty:
        assert post(empty, settings, discord) == PostReport(posted=0, waiting=0, stopped="")
    assert (fake_keychain.calls, discord.requests) == ([], [])


def test_without_a_channel_or_owner_nothing_is_sent(store: Store, discord: FakeDiscord) -> None:
    with pytest.raises(DiscordUnavailable) as caught:
        post(store, get_settings(), discord)
    assert str(caught.value) == "discord unavailable (not configured)"
    assert discord.requests == []
