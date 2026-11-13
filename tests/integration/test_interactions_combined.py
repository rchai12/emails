"""Presses on the combined card: one decision records Yes and checkpoint 2 together."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from mailroom import clock
from mailroom.checkpoint import answered_message, approved_message
from mailroom.config import Settings, get_settings
from mailroom.store import Approval, Due, Store
from tests.fakes import FakeDiscord
from tests.integration.test_interactions import (
    ITEM,
    RECORD,
    VERDICT,
    answer,
    ephemeral,
    posted_store,
)
from tests.integration.test_interactions_second import task_form
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)  # 04:00 on Tuesday November 10 in New York
DUE = Due(date=date(2026, 11, 20), time=time(17, 0))
DATED = replace(VERDICT, dated=True, due=DUE)
TITLE = "Pay the November bill"
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
    fixed_ids(monkeypatch, ITEM)
    return now


def combined_store() -> Store:
    store = posted_store(verdict=DATED)
    store.choose_card(ITEM, "combined")
    return store


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    with combined_store() as opened:
        yield opened


def press(store: Store, settings: Settings, action: str, user: str | None = None):
    discord = FakeDiscord()
    return answer(store, settings, discord, discord.press(f"mr:{action}:{ITEM}", user_id=user))


def submit(store: Store, settings: Settings, title: str, deadline: str, action: str = "task"):
    discord = FakeDiscord()
    event = discord.submit(f"mr:{action}:{ITEM}", title, fields={"deadline": deadline})
    return answer(store, settings, discord, event)


@pytest.mark.parametrize(
    ("action", "approval", "first"),
    [
        ("approve", Approval(ITEM, "approve", TITLE, DUE, NOW), "yes"),
        ("nodeadline", Approval(ITEM, "nodeadline", TITLE, None, NOW), "yes"),
    ],
    ids=["approve", "no-deadline"],
)
def test_one_press_records_yes_and_the_decision(
    store: Store, settings: Settings, action: str, approval: Approval, first: str
) -> None:
    assert press(store, settings, action) == (
        "approved",
        {"type": 7, "data": approved_message(RECORD, DATED, ITEM, approval)},
    )
    assert (store.answer(ITEM).answer, store.answer(ITEM).title) == (first, TITLE)
    assert store.approval(ITEM) == approval


def test_edit_opens_the_task_form_with_the_proposal(store: Store, settings: Settings) -> None:
    assert press(store, settings, "change") == ("form", task_form(TITLE, "2026-11-20 5:00 pm"))
    assert store.answer(ITEM) is None


def test_a_submitted_task_records_your_title_and_deadline(store: Store, settings: Settings) -> None:
    approval = Approval(ITEM, "change", "Pay online", Due(date(2026, 11, 13), None), NOW)
    assert submit(store, settings, "Pay online", "Friday") == (
        "approved",
        {"type": 7, "data": approved_message(RECORD, DATED, ITEM, approval)},
    )
    assert (store.answer(ITEM).answer, store.answer(ITEM).title) == ("edit", "Pay online")
    assert store.approval(ITEM) == approval


@pytest.mark.parametrize(
    ("title", "text", "outcome", "reply"),
    [
        (
            "Pay online",
            "11/20",
            "bad-deadline",
            "Couldn't read that deadline. Try 'Nov 20 at 5 pm', 'Friday' or '2026-11-20'.",
        ),
        ("Pay\nnow", "Friday", "bad-title", "A title needs 1 to 100 characters on one line."),
    ],
    ids=["bad-deadline", "bad-title"],
)
def test_a_task_form_code_cannot_accept_records_nothing(
    store: Store, settings: Settings, title: str, text: str, outcome: str, reply: str
) -> None:
    assert submit(store, settings, title, text) == (outcome, ephemeral(reply))
    assert (store.answer(ITEM), store.approval(ITEM)) == (None, None)


@pytest.mark.parametrize(
    ("action", "status"), [("notask", None), ("mute", "muted")], ids=["not-a-task", "mute"]
)
def test_not_a_task_and_mute_close_it_as_at_checkpoint_1(
    store: Store, settings: Settings, action: str, status: str | None
) -> None:
    assert press(store, settings, action) == (
        "answered",
        {"type": 7, "data": answered_message(RECORD, DATED, ITEM, action, "")},
    )
    assert store.answer(ITEM).answer == action
    assert store.approval(ITEM) is None
    assert store.sender_status("billing@example.test") == status


@pytest.mark.parametrize("action", ["yes", "edit", "drop"])
def test_a_press_the_combined_card_does_not_have_is_ignored(
    store: Store, settings: Settings, action: str
) -> None:
    assert press(store, settings, action) == ("ignored", IGNORED)
    assert (store.answer(ITEM), store.approval(ITEM)) == (None, None)


def test_a_title_form_on_a_combined_card_is_ignored(store: Store, settings: Settings) -> None:
    assert submit(store, settings, "Pay online", "", action="title") == ("ignored", IGNORED)
    assert store.answer(ITEM) is None


@pytest.mark.parametrize("first", ["approve", "notask"])
@pytest.mark.parametrize("then", ["approve", "change", "nodeadline", "notask", "mute"])
def test_after_a_decision_every_answer_is_refused(
    store: Store, settings: Settings, first: str, then: str
) -> None:
    press(store, settings, first)
    assert press(store, settings, then) == ("already", ALREADY)


def test_a_task_form_after_a_decision_is_refused(store: Store, settings: Settings) -> None:
    press(store, settings, "nodeadline")
    assert submit(store, settings, "Pay online", "Friday") == ("already", ALREADY)
    assert store.approval(ITEM).outcome == "nodeadline"


@pytest.mark.parametrize("action", ["approve", "nodeadline"])
def test_approve_after_the_text_is_cleared_asks_for_the_title(
    moment: list[datetime], settings: Settings, action: str
) -> None:
    with combined_store() as store:
        moment[0] = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        store.clear_expired_text()
        assert press(store, settings, action) == (
            "form",
            task_form("Your November bill", "2026-11-20 5:00 pm"),
        )
        assert store.answer(ITEM) is None


@pytest.mark.parametrize("action", ["approve", "change", "nodeadline", "notask"])
def test_a_press_from_anyone_else_changes_nothing(
    store: Store, settings: Settings, action: str
) -> None:
    assert press(store, settings, action, user="555555555555555555") == ("ignored", IGNORED)
    assert (store.answer(ITEM), store.approval(ITEM)) == (None, None)


def test_a_checkpoint_1_card_keeps_working_as_before(
    moment: list[datetime], settings: Settings
) -> None:
    with posted_store(verdict=DATED) as store:
        assert press(store, settings, "approve") == ("ignored", IGNORED)
        assert press(store, settings, "yes")[0] == "answered"
        assert store.approval(ITEM) is None
