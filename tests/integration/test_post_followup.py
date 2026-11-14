"""Posting: an email in a thread with an approved item gets the follow-up card."""

import json
from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest

from mailroom import clock
from mailroom.checkpoint import checkpoint_message, followup_message
from mailroom.config import Settings, get_settings
from mailroom.discord_post import post_pending
from mailroom.store import Store, Verdict, open_store
from tests.fakes import FakeDiscord, FakeKeychain
from tests.integration.test_post_combined import DATED, NOW
from tests.integration.test_triage import RECORD
from tests.support import fixed_ids

A, B, C = ("a" * 32, "b" * 32, "c" * 32)
UNDATED = replace(DATED, dated=False)
FOLLOW = replace(RECORD, message_id="m2", link="https://mail.google.com/mail/#all/m2")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(clock, "now", lambda: NOW[0])
    fixed_ids(monkeypatch, A, B, C)
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    return get_settings()


@pytest.fixture
def discord(fake_keychain: FakeKeychain) -> FakeDiscord:
    fake = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    return fake


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    with open_store(settings) as opened:
        yield opened


def run(store: Store, settings: Settings, discord: FakeDiscord) -> None:
    post_pending(store, settings, httpx.Client(transport=httpx.MockTransport(discord.handler)))


def first_posted(store: Store, settings: Settings, discord: FakeDiscord, decide: str) -> None:
    """m1 posted as item a, then answered: 'approve', 'drop', or 'yes' (no decision yet)."""
    store.add(RECORD)
    store.save_triage("gmail", "m1", UNDATED)
    run(store, settings, discord)
    store.record_answer(A, "yes", "Pay the October bill")
    if decide == "approve":
        store.record_approval(A, "nodeadline", "Pay the October bill", None)
    elif decide == "drop":
        store.record_approval(A, "drop", "", None)


def last_sent(discord: FakeDiscord) -> dict:
    return json.loads(discord.requests[-1].content)


@pytest.mark.parametrize("verdict", [UNDATED, DATED], ids=["undated", "clearly-dated"])
def test_a_reply_in_an_approved_thread_is_posted_as_a_follow_up(
    store: Store, settings: Settings, discord: FakeDiscord, verdict: Verdict
) -> None:
    first_posted(store, settings, discord, "approve")
    store.add(FOLLOW)
    store.save_triage("gmail", "m2", verdict)
    run(store, settings, discord)
    assert last_sent(discord) == followup_message(FOLLOW, verdict, B, "Pay the October bill")
    post = store.post("gmail", "m2")
    assert (post.card, post.follows) == ("followup", A)


@pytest.mark.parametrize("decide", ["drop", "yes"], ids=["dropped", "undecided"])
def test_a_reply_in_a_thread_without_an_approved_task_is_checkpoint_1(
    store: Store, settings: Settings, discord: FakeDiscord, decide: str
) -> None:
    first_posted(store, settings, discord, decide)
    store.add(FOLLOW)
    store.save_triage("gmail", "m2", UNDATED)
    run(store, settings, discord)
    assert last_sent(discord) == checkpoint_message(FOLLOW, UNDATED, B)
    assert (store.post("gmail", "m2").card, store.post("gmail", "m2").follows) == ("first", None)


def test_an_email_in_another_thread_is_not_a_follow_up(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    first_posted(store, settings, discord, "approve")
    other = replace(FOLLOW, thread_id="t2")
    store.add(other)
    store.save_triage("gmail", "m2", UNDATED)
    run(store, settings, discord)
    assert last_sent(discord) == checkpoint_message(other, UNDATED, B)


def test_a_retry_keeps_its_target_after_a_later_approval_in_the_thread(
    store: Store, settings: Settings, discord: FakeDiscord
) -> None:
    first_posted(store, settings, discord, "approve")
    earlier = replace(FOLLOW, message_id="m3", link="https://mail.google.com/mail/#all/m3")
    store.add(earlier)
    store.save_triage("gmail", "m3", UNDATED)
    run(store, settings, discord)
    store.add(FOLLOW)
    store.save_triage("gmail", "m2", UNDATED)
    discord.failures.append("lost-reply")
    run(store, settings, discord)
    store.record_answer(B, "yes", "Pay the November bill")
    store.record_approval(B, "nodeadline", "Pay the November bill", None)
    run(store, settings, discord)
    bodies = [json.loads(request.content) for request in discord.requests]
    sent = [body for body in bodies if body.get("nonce") == C[:25]]
    assert sent == [followup_message(FOLLOW, UNDATED, C, "Pay the October bill")] * 2
    assert store.post("gmail", "m2").follows == A
    assert len(discord.messages) == 3
