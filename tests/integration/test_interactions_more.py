from dataclasses import replace

import httpx
import pytest

from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable
from tests.fakes import FakeDiscord
from tests.integration.test_interactions import (
    ITEM,
    RECORD,
    VERDICT,
    answer,
    ephemeral,
    posted_store,
)
from tests.support import fixed_ids


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


def test_a_direct_message_uses_the_user_id(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store() as store:
        discord = FakeDiscord()
        event = discord.press(f"mr:notask:{ITEM}")
        event["user"] = event["member"]["user"]
        del event["member"]
        outcome, reply = answer(store, settings, discord, event)
        stored = store.answer(ITEM)
    assert outcome == "answered"
    assert reply is not None
    assert reply["type"] == 7
    assert stored is not None
    assert stored.answer == "notask"


def test_a_submission_without_the_title_field_is_refused(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store() as store:
        discord = FakeDiscord()
        event = discord.submit(f"mr:title:{ITEM}", "Pay online")
        event["data"]["components"] = [
            {"type": 18, "component": {"type": 4, "custom_id": "note", "value": "Pay online"}}
        ]
        outcome, reply = answer(store, settings, discord, event)
        assert store.answer(ITEM) is None
    assert (outcome, reply) == (
        "bad-title",
        ephemeral("A title needs 1 to 100 characters on one line."),
    )


def test_a_lost_connection_keeps_the_answer(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store() as store:
        discord = FakeDiscord()
        discord.failures.append(httpx.ConnectError("refused"))
        with pytest.raises(DiscordUnavailable) as caught:
            answer(store, settings, discord, discord.press(f"mr:notask:{ITEM}"))
        stored = store.answer(ITEM)
    assert str(caught.value) == "discord unavailable (network)"
    assert caught.value.__suppress_context__
    assert "refused" not in str(caught.value)
    assert stored is not None
    assert stored.answer == "notask"


def test_show_full_text_of_an_empty_body_says_there_is_none(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store(replace(RECORD, body_text="")) as store:
        discord = FakeDiscord()
        outcome, reply = answer(store, settings, discord, discord.press(f"mr:full:{ITEM}"))
    assert (outcome, reply) == ("full", ephemeral("(no text)"))


def test_a_form_with_nothing_to_prefill_omits_the_value(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    verdict = replace(VERDICT, extraction=replace(VERDICT.extraction, title=""))
    with posted_store(replace(RECORD, subject=""), verdict) as store:
        discord = FakeDiscord()
        outcome, reply = answer(store, settings, discord, discord.press(f"mr:yes:{ITEM}"))
        assert store.answer(ITEM) is None
    assert outcome == "form"
    field = reply["data"]["components"][0]["component"]
    assert field["custom_id"] == "title"
    assert "value" not in field


def test_an_empty_channel_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    fixed_ids(monkeypatch, ITEM)
    with posted_store() as store:
        discord = FakeDiscord()
        with pytest.raises(DiscordUnavailable) as caught:
            answer(store, get_settings(), discord, discord.press(f"mr:yes:{ITEM}"))
    assert str(caught.value) == "discord unavailable (not configured)"
    assert discord.requests == []


def test_a_submission_with_no_fields_is_refused(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store() as store:
        discord = FakeDiscord()
        event = discord.submit(f"mr:title:{ITEM}", "Pay online")
        event["data"]["components"] = []
        outcome, reply = answer(store, settings, discord, event)
        assert store.answer(ITEM) is None
    assert (outcome, reply) == (
        "bad-title",
        ephemeral("A title needs 1 to 100 characters on one line."),
    )


def test_a_submission_after_an_answer_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store() as store:
        discord = FakeDiscord()
        answer(store, settings, discord, discord.press(f"mr:notask:{ITEM}"))
        outcome, reply = answer(store, settings, discord, discord.submit(f"mr:title:{ITEM}", "Pay"))
        stored = store.answer(ITEM)
    assert (outcome, reply) == ("already", ephemeral("This email is already answered."))
    assert stored is not None
    assert stored.answer == "notask"


def test_a_submission_for_another_action_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store() as store:
        discord = FakeDiscord()
        outcome, reply = answer(
            store, settings, discord, discord.submit(f"mr:yes:{ITEM}", "Pay online")
        )
        assert store.answer(ITEM) is None
    assert (outcome, reply) == ("ignored", {"type": 6})
