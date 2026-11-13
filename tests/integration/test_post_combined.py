"""Posting: a clearly dated email gets the combined card unless its deadline has passed."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time

import httpx
import pytest

from mailroom import clock
from mailroom.checkpoint import checkpoint_message, combined_message
from mailroom.config import Settings, get_settings
from mailroom.discord_post import PostReport, post_pending
from mailroom.store import Due, Store, Verdict, open_store
from tests.fakes import FakeDiscord, FakeKeychain
from tests.integration.test_triage import EXTRACTION, RECORD
from tests.support import fixed_ids

ITEM = "d" * 32
NOW = [datetime(2026, 11, 10, 9, 0, tzinfo=UTC)]
PAST = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)  # 17:00 on November 20 in New York
DATED = Verdict(
    outcome="extracted",
    trusted=False,
    verified=True,
    bulk=False,
    notify=True,
    extraction=EXTRACTION,
    dated=True,
    due=Due(date=date(2026, 11, 20), time=time(17, 0)),
)

# Due 06:00 on November 10 in New York: passed by 12:00 UTC, three hours after the fetch.
EARLY = replace(DATED, due=Due(date=date(2026, 11, 10), time=time(6, 0)))


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    return get_settings()


@pytest.fixture
def discord(fake_keychain: FakeKeychain) -> FakeDiscord:
    fake = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    return fake


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW[0]]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    fixed_ids(monkeypatch, ITEM)
    return now


def stored(verdict: Verdict) -> Store:
    store = open_store(get_settings())
    store.add(RECORD)
    store.save_triage("gmail", "m1", verdict)
    return store


def run(store: Store, settings: Settings, discord: FakeDiscord) -> PostReport:
    return post_pending(
        store, settings, httpx.Client(transport=httpx.MockTransport(discord.handler))
    )


def sent(discord: FakeDiscord) -> list[dict]:
    return [json.loads(request.content) for request in discord.requests]


def test_a_clearly_dated_email_is_posted_as_the_combined_card(
    moment: list[datetime], settings: Settings, discord: FakeDiscord
) -> None:
    with stored(DATED) as store:
        assert run(store, settings, discord) == PostReport(posted=1, waiting=0, stopped="")
        assert sent(discord) == [combined_message(RECORD, DATED, ITEM)]
        assert store.post("gmail", "m1").card == "combined"


@pytest.mark.parametrize(
    ("verdict", "now", "shown"),
    [
        (EARLY, datetime(2026, 11, 10, 12, 0, tzinfo=UTC), EARLY),
        (replace(DATED, dated=False), NOW[0], replace(DATED, dated=False)),
        (DATED, datetime(2026, 11, 11, 10, 0, tzinfo=UTC), replace(DATED, extraction=None)),
    ],
    ids=["deadline-passed-before-posting", "not-dated", "text-cleared"],
)
def test_otherwise_it_is_posted_as_checkpoint_1(
    moment: list[datetime],
    settings: Settings,
    discord: FakeDiscord,
    verdict: Verdict,
    now: datetime,
    shown: Verdict,
) -> None:
    with stored(verdict) as store:
        moment[0] = now
        store.clear_expired_text()
        run(store, settings, discord)
        assert sent(discord) == [checkpoint_message(RECORD, shown, ITEM)]
        assert store.post("gmail", "m1").card == "first"


def test_a_retry_after_the_deadline_passed_keeps_the_card_first_chosen(
    moment: list[datetime], settings: Settings, discord: FakeDiscord
) -> None:
    with stored(DATED) as store:
        discord.failures.append("lost-reply")
        assert run(store, settings, discord) == PostReport(posted=0, waiting=1, stopped="network")
        moment[0] = PAST
        assert run(store, settings, discord) == PostReport(posted=1, waiting=0, stopped="")
        assert sent(discord) == [combined_message(RECORD, DATED, ITEM)] * 2
        assert len(discord.messages) == 1
        assert store.post("gmail", "m1").card == "combined"
