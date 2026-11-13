"""Checkpoint 2: after Yes or a submitted title, the same card asks to confirm the deadline."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from mailroom import clock
from mailroom.checkpoint import approved_message, checkpoint2_message
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
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)  # 04:00 on Tuesday November 10 in New York
DUE = Due(date=date(2026, 11, 20), time=time(17, 0))
PROPOSED = replace(VERDICT, due=DUE)
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


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    with posted_store(verdict=PROPOSED) as opened:
        yield opened


def press(store: Store, settings: Settings, action: str) -> tuple[str, dict | None]:
    discord = FakeDiscord()
    return answer(store, settings, discord, discord.press(f"mr:{action}:{ITEM}"))


def submit(store: Store, settings: Settings, title: str, deadline: str) -> tuple[str, dict | None]:
    discord = FakeDiscord()
    event = discord.submit(f"mr:task:{ITEM}", title, fields={"deadline": deadline})
    return answer(store, settings, discord, event)


def task_form(title: str, deadline: str | None) -> dict:
    title_input = {
        "type": 4,
        "custom_id": "title",
        "style": 1,
        "min_length": 1,
        "max_length": 100,
        "required": True,
        "value": title,
    }
    deadline_input = {
        "type": 4,
        "custom_id": "deadline",
        "style": 1,
        "min_length": 0,
        "max_length": 100,
        "required": False,
    }
    if deadline is not None:
        deadline_input["value"] = deadline
    return {
        "type": 9,
        "data": {
            "custom_id": f"mr:task:{ITEM}",
            "title": "Edit task",
            "components": [
                {"type": 18, "label": "Task title", "component": title_input},
                {"type": 18, "label": "Deadline (empty for none)", "component": deadline_input},
            ],
        },
    }


def test_yes_turns_the_card_into_checkpoint_2(store: Store, settings: Settings) -> None:
    assert press(store, settings, "yes") == (
        "answered",
        {"type": 7, "data": checkpoint2_message(RECORD, PROPOSED, ITEM, TITLE)},
    )


@pytest.mark.parametrize(
    ("action", "approval", "outcome"),
    [
        ("approve", Approval(ITEM, "approve", TITLE, DUE, NOW), "approved"),
        ("nodeadline", Approval(ITEM, "nodeadline", TITLE, None, NOW), "approved"),
        ("drop", Approval(ITEM, "drop", "", None, NOW), "dropped"),
    ],
    ids=["approve", "no-deadline", "not-a-task"],
)
def test_a_checkpoint_2_answer_is_recorded_and_shown(
    store: Store, settings: Settings, action: str, approval: Approval, outcome: str
) -> None:
    press(store, settings, "yes")
    assert press(store, settings, action) == (
        outcome,
        {"type": 7, "data": approved_message(RECORD, PROPOSED, ITEM, approval)},
    )
    assert store.approval(ITEM) == approval


def test_approve_without_a_proposed_deadline_is_ignored(
    moment: list[datetime], settings: Settings
) -> None:
    with posted_store(verdict=VERDICT) as store:
        press(store, settings, "yes")
        assert press(store, settings, "approve") == ("ignored", IGNORED)
        assert store.approval(ITEM) is None


@pytest.mark.parametrize("action", ["approve", "change", "nodeadline", "drop"])
def test_a_checkpoint_2_press_before_yes_is_ignored(
    store: Store, settings: Settings, action: str
) -> None:
    assert press(store, settings, action) == ("ignored", IGNORED)
    assert (store.answer(ITEM), store.approval(ITEM)) == (None, None)


@pytest.mark.parametrize("action", ["approve", "change", "nodeadline", "drop", "yes", "notask"])
def test_after_a_checkpoint_2_answer_every_answer_is_refused(
    store: Store, settings: Settings, action: str
) -> None:
    press(store, settings, "yes")
    press(store, settings, "nodeadline")
    assert press(store, settings, action) == ("already", ALREADY)
    assert store.approval(ITEM).outcome == "nodeadline"


@pytest.mark.parametrize("action", ["yes", "edit"])
def test_a_stale_checkpoint_1_card_shows_checkpoint_2_again(
    store: Store, settings: Settings, action: str
) -> None:
    press(store, settings, "yes")
    assert press(store, settings, action) == (
        "again",
        {"type": 7, "data": checkpoint2_message(RECORD, PROPOSED, ITEM, TITLE)},
    )


def test_not_a_task_on_a_stale_checkpoint_1_card_is_refused(
    store: Store, settings: Settings
) -> None:
    press(store, settings, "yes")
    assert press(store, settings, "notask") == ("already", ALREADY)
    assert store.answer(ITEM).answer == "yes"


@pytest.mark.parametrize(
    ("due", "prefill"),
    [
        (DUE, "2026-11-20 5:00 pm"),
        (Due(date=date(2026, 11, 20), time=time(0, 30)), "2026-11-20 12:30 am"),
        (Due(date=date(2026, 11, 20), time=time(12, 0)), "2026-11-20 12:00 pm"),
        (Due(date=date(2026, 11, 20), time=None), "2026-11-20"),
        (None, None),
    ],
    ids=["afternoon", "after-midnight", "noon", "date-only", "none"],
)
def test_edit_opens_the_task_form_filled_in(
    moment: list[datetime], settings: Settings, due: Due | None, prefill: str | None
) -> None:
    with posted_store(verdict=replace(VERDICT, due=due)) as store:
        discord = FakeDiscord()
        answer(store, settings, discord, discord.submit(f"mr:title:{ITEM}", "Pay online"))
        assert press(store, settings, "change") == ("form", task_form("Pay online", prefill))


@pytest.mark.parametrize(
    ("now", "text", "due"),
    [
        (NOW, "", None),
        (NOW, "Nov 21 at 9 am", Due(date=date(2026, 11, 21), time=time(9, 0))),
        (NOW, "Friday", Due(date=date(2026, 11, 13), time=None)),
        (NOW, "2026-11-20 5:00 pm", DUE),
        (NOW, "  tomorrow  ", Due(date=date(2026, 11, 11), time=None)),
        (
            datetime(2026, 11, 11, 3, 0, tzinfo=UTC),
            "tomorrow",
            Due(date=date(2026, 11, 11), time=None),
        ),
    ],
    ids=["empty", "date-and-time", "weekday", "prefilled", "spaces", "local-today"],
)
def test_a_submitted_task_is_approved_with_the_deadline_read_by_code(
    store: Store,
    settings: Settings,
    moment: list[datetime],
    now: datetime,
    text: str,
    due: Due | None,
) -> None:
    press(store, settings, "yes")
    moment[0] = now
    approval = Approval(ITEM, "change", "Pay online", due, now)
    assert submit(store, settings, "  Pay online ", text) == (
        "approved",
        {"type": 7, "data": approved_message(RECORD, PROPOSED, ITEM, approval)},
    )
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
        (
            "Pay online",
            "next Friday",
            "bad-deadline",
            "Couldn't read that deadline. Try 'Nov 20 at 5 pm', 'Friday' or '2026-11-20'.",
        ),
        ("Pay\nnow", "Friday", "bad-title", "A title needs 1 to 100 characters on one line."),
    ],
    ids=["numeric-date", "next-weekday", "bad-title"],
)
def test_a_task_form_code_cannot_accept_is_refused_privately(
    store: Store, settings: Settings, title: str, text: str, outcome: str, reply: str
) -> None:
    press(store, settings, "yes")
    assert submit(store, settings, title, text) == (outcome, ephemeral(reply))
    assert store.approval(ITEM) is None


def test_a_task_form_before_yes_or_after_an_answer_changes_nothing(
    store: Store, settings: Settings
) -> None:
    assert submit(store, settings, "Pay online", "Friday") == ("ignored", IGNORED)
    press(store, settings, "yes")
    press(store, settings, "drop")
    assert submit(store, settings, "Pay online", "Friday") == ("already", ALREADY)
    assert store.approval(ITEM).outcome == "drop"


@pytest.mark.parametrize("action", ["approve", "change", "nodeadline", "drop"])
def test_a_checkpoint_2_press_from_anyone_else_changes_nothing(
    store: Store, settings: Settings, action: str
) -> None:
    press(store, settings, "yes")
    discord = FakeDiscord()
    event = discord.press(f"mr:{action}:{ITEM}", user_id="555555555555555555")
    assert answer(store, settings, discord, event) == ("ignored", IGNORED)
    assert store.approval(ITEM) is None
