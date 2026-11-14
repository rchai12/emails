"""Stage 3's test: a follow-up in an approved thread is added to its task, not made a second one."""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.store import Store, open_store
from tests.fakes import FakeKeychain, FakeTasksApp
from tests.integration.test_service import GOOD, NOW, World, raw


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    return now


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, moment: list[datetime]) -> Settings:
    for name, value in (
        ("MAILROOM_GMAIL_ACCOUNTS", "personal"),
        ("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b"),
        ("MAILROOM_TIME_ZONE", "America/New_York"),
        ("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111"),
        ("MAILROOM_DISCORD_OWNER_ID", "444444444444444444"),
        ("MAILROOM_TASKS_URL", FakeTasksApp.URL),
    ):
        monkeypatch.setenv(name, value)
    return get_settings()


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    with open_store(settings) as opened:
        yield opened


def arrive(world: World, number: int, moment: datetime) -> None:
    world.gmail["personal"].add_message(
        f"m{number}",
        raw(number),
        thread_id="th1",
        internal_ms=round(moment.timestamp() * 1000),
    )
    world.model.replies.append(GOOD)


@pytest.mark.parametrize("later", [timedelta(hours=1), timedelta(days=3)], ids=["hour", "days"])
def test_a_follow_up_is_added_to_the_task_instead_of_making_another(
    store: Store,
    settings: Settings,
    fake_keychain: FakeKeychain,
    moment: list[datetime],
    later: timedelta,
) -> None:
    world = World(fake_keychain, ("personal",))
    arrive(world, 1, NOW)
    world.round(store, settings)
    first = store.post("gmail", "personal/m1").item_id
    store.record_answer(first, "yes", "Send Sam the report")
    store.record_approval(first, "nodeadline", "Send Sam the report", None)
    world.round(store, settings)
    assert list(world.tasks.tasks) == ["gmail:personal/m1"]
    moment[0] = NOW + later
    arrive(world, 2, moment[0])
    world.round(store, settings)
    follow = store.post("gmail", "personal/m2")
    assert (follow.card, follow.follows) == ("followup", first)
    store.record_answer(follow.item_id, "link", "")
    world.round(store, settings)
    world.round(store, settings)
    assert list(world.tasks.tasks) == ["gmail:personal/m1"]
    assert list(world.tasks.links) == ["gmail:personal/m2"]
    assert world.tasks.links["gmail:personal/m2"][1] == "task-1"
