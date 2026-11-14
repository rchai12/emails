"""Presses on the follow-up card: Add to task closes it; New task goes on as checkpoint 1's Yes."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from mailroom import clock
from mailroom.checkpoint import answered_message, checkpoint2_message
from mailroom.config import Settings, get_settings
from mailroom.store import Approval, Store, open_store
from tests.fakes import FakeDiscord
from tests.integration.test_interactions import (
    ITEM,
    RECORD,
    VERDICT,
    answer,
    ephemeral,
    form,
    posted_store,
)
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
TARGET = "f" * 32
TASK = "Pay the October bill"
IGNORED = {"type": 6}
ALREADY = ephemeral("This email is already answered.")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    return get_settings()


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    fixed_ids(monkeypatch, TARGET, ITEM)
    return now


def followup_store() -> Store:
    """m0 approved as TARGET; m1, in the same thread, posted as ITEM's follow-up card."""
    store = open_store(get_settings())
    store.add(replace(RECORD, message_id="m0"))
    store.save_triage("gmail", "m0", VERDICT)
    store.add(RECORD)
    store.save_triage("gmail", "m1", VERDICT)
    store.queue_notified()
    store.record_answer(TARGET, "yes", TASK)
    store.record_approval(TARGET, "nodeadline", TASK, None)
    store.choose_card(ITEM, "followup", follows=TARGET)
    store.mark_posted(ITEM, "1300000000000000001")
    return store


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    with followup_store() as opened:
        yield opened


def press(store: Store, settings: Settings, action: str, user: str | None = None):
    discord = FakeDiscord()
    return answer(store, settings, discord, discord.press(f"mr:{action}:{ITEM}", user_id=user))


def test_add_to_task_records_the_link_and_closes_the_card(store: Store, settings: Settings) -> None:
    assert press(store, settings, "link") == (
        "answered",
        {"type": 7, "data": answered_message(RECORD, VERDICT, ITEM, "link", "", task_title=TASK)},
    )
    assert (store.answer(ITEM).answer, store.answer(ITEM).title) == ("link", "")
    assert store.approval(ITEM) is None


def test_new_task_goes_on_to_checkpoint_2(store: Store, settings: Settings) -> None:
    assert press(store, settings, "yes") == (
        "answered",
        {"type": 7, "data": checkpoint2_message(RECORD, VERDICT, ITEM, "Pay the November bill")},
    )
    assert press(store, settings, "nodeadline")[0] == "approved"
    assert store.approval(ITEM) == Approval(ITEM, "nodeadline", "Pay the November bill", None, NOW)


@pytest.mark.parametrize(
    ("action", "status"), [("notask", None), ("mute", "muted")], ids=["not-a-task", "mute"]
)
def test_not_a_task_and_mute_close_it_on_the_follow_up_card(
    store: Store, settings: Settings, action: str, status: str | None
) -> None:
    assert press(store, settings, action) == (
        "answered",
        {"type": 7, "data": answered_message(RECORD, VERDICT, ITEM, action, "", task_title=TASK)},
    )
    assert store.answer(ITEM).answer == action
    assert store.sender_status("billing@example.test") == status


@pytest.mark.parametrize("action", ["edit", "approve", "change", "nodeadline", "drop"])
def test_a_press_the_follow_up_card_does_not_have_is_ignored(
    store: Store, settings: Settings, action: str
) -> None:
    assert press(store, settings, action) == ("ignored", IGNORED)
    assert store.answer(ITEM) is None


@pytest.mark.parametrize("then", ["link", "yes", "notask", "mute"])
def test_after_add_to_task_every_answer_is_refused(
    store: Store, settings: Settings, then: str
) -> None:
    press(store, settings, "link")
    assert press(store, settings, then) == ("already", ALREADY)
    assert store.answer(ITEM).answer == "link"


def test_add_to_task_after_new_task_is_refused(store: Store, settings: Settings) -> None:
    press(store, settings, "yes")
    assert press(store, settings, "link") == ("already", ALREADY)
    assert store.answer(ITEM).answer == "yes"


def test_new_task_after_the_text_is_cleared_asks_for_the_title(
    moment: list[datetime], settings: Settings
) -> None:
    with followup_store() as store:
        moment[0] = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        store.clear_expired_text()
        assert press(store, settings, "yes") == ("form", form("Your November bill"))
        assert press(store, settings, "link")[0] == "answered"


def test_a_press_from_anyone_else_changes_nothing(store: Store, settings: Settings) -> None:
    assert press(store, settings, "link", user="555555555555555555") == ("ignored", IGNORED)
    assert store.answer(ITEM) is None


def test_add_to_task_on_another_card_is_ignored(
    moment: list[datetime], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store() as store:
        assert press(store, settings, "link") == ("ignored", IGNORED)
        store.choose_card(ITEM, "combined")
        assert press(store, settings, "link") == ("ignored", IGNORED)
        assert store.answer(ITEM) is None
