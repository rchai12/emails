"""Each round sends approved tasks before posting; a tasks app down for 15 minutes is alerted."""

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.service import run_service
from mailroom.store import Store, open_store
from tests.fakes import FakeKeychain, FakeTasksApp
from tests.integration.test_service import GOOD, NOW, Rounds, World, deliver

DOWN = (
    "Approved tasks have not reached the tasks app for 15 minutes. They stay queued and are "
    "retried every round."
)
BACK = "The tasks app works again. Queued tasks are being sent."


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


def approved(world: World, store: Store, settings: Settings) -> str:
    """One email delivered, triaged and posted, then approved as the listener would record it."""
    deliver(world.gmail["personal"], 1)
    world.model.replies.append(GOOD)
    world.round(store, settings)
    item = store.post("gmail", "personal/m1").item_id
    store.record_answer(item, "yes", "Send Sam the report")
    store.record_approval(item, "nodeadline", "Send Sam the report", None)
    return item


def posted(world: World) -> list[str]:
    return [message["content"] for message in world.discord.messages if message["content"]]


def test_the_next_round_sends_an_approved_task_once(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    item = approved(world, store, settings)
    assert world.round(store, settings) == []
    assert list(world.tasks.tasks) == ["gmail:personal/m1"]
    assert store.task(item).task_id == "task-1"
    world.round(store, settings)
    assert len(world.tasks.requests) == 1


def test_a_tasks_app_down_for_15_minutes_is_alerted_and_its_return_announced(
    store: Store, settings: Settings, fake_keychain: FakeKeychain, moment: list[datetime]
) -> None:
    world = World(fake_keychain, ("personal",))
    item = approved(world, store, settings)
    world.tasks.failures.extend([httpx.ConnectError("refused"), httpx.Response(503)])
    assert world.round(store, settings) == ["tasks: waiting (network)"]
    moment[0] = NOW + timedelta(minutes=15)
    assert world.round(store, settings) == ["tasks: waiting (503)"]
    assert posted(world) == [DOWN]
    moment[0] = NOW + timedelta(minutes=16)
    assert world.round(store, settings) == ["tasks: ok"]
    assert posted(world) == [DOWN, BACK]
    assert store.task(item).task_id == "task-1"


def test_a_short_outage_is_not_alerted(
    store: Store, settings: Settings, fake_keychain: FakeKeychain, moment: list[datetime]
) -> None:
    world = World(fake_keychain, ("personal",))
    approved(world, store, settings)
    world.tasks.failures.append(httpx.Response(503))
    world.round(store, settings)
    moment[0] = NOW + timedelta(minutes=14)
    assert world.round(store, settings) == ["tasks: ok"]
    moment[0] = NOW + timedelta(minutes=30)
    world.round(store, settings)
    assert posted(world) == []


def test_without_a_tasks_app_address_the_round_says_so_and_never_alerts(
    monkeypatch: pytest.MonkeyPatch,
    store: Store,
    fake_keychain: FakeKeychain,
    moment: list[datetime],
) -> None:
    monkeypatch.delenv("MAILROOM_TASKS_URL")
    settings = get_settings()
    world = World(fake_keychain, ("personal",))
    approved(world, store, settings)
    assert "tasks: tasks app unavailable (not configured)" in world.lines
    moment[0] = NOW + timedelta(minutes=30)
    world.round(store, settings)
    assert posted(world) == []
    assert world.tasks.requests == []


def test_the_service_opens_one_tasks_client_and_closes_it(
    settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = World(fake_keychain, ("personal",))
    opened: list[httpx.Client] = []

    def open_tasks_http() -> httpx.Client:
        http = world.tasks_http()
        opened.append(http)
        return http

    def gateway(store: Store, gateway_settings: Settings, http: httpx.Client, *, stop) -> None:
        while not stop():
            threading.Event().wait(0.001)

    run_service(
        settings,
        say=world.lines.append,
        stop=Rounds(2),
        open_gmail=world.client,
        open_model_http=world.model_http,
        open_discord_http=world.discord_http,
        open_tasks_http=open_tasks_http,
        gateway=gateway,
    )
    assert len(opened) == 1
    assert opened[0].is_closed
    assert "tasks: ok" in world.lines
