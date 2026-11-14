"""Follow-ups added to a task are sent to that task in the stub tasks app, once each."""

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.discord_post import PostReport
from mailroom.store import Store, open_store
from mailroom.tasks_app import send_tasks
from tests.fakes import FakeTasksApp
from tests.integration.test_store_posts import NOTIFY, RECORD
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
A, B = ("a" * 32, "b" * 32)
FOLLOW = replace(RECORD, message_id="m2", link="https://mail.google.com/mail/#all/m2")
LINK_BODY = {
    "source": "email",
    "provider": "gmail",
    "message_id": "m2",
    "link": "https://mail.google.com/mail/#all/m2",
}


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    fixed_ids(monkeypatch, A, B)
    return now


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, moment: list[datetime]) -> Settings:
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    monkeypatch.setenv("MAILROOM_TASKS_URL", FakeTasksApp.URL)
    return get_settings()


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    """m1 approved as a; m2 posted as a's follow-up (b), not answered yet."""
    with open_store(settings) as opened:
        opened.add(RECORD)
        opened.save_triage("gmail", "m1", NOTIFY)
        opened.queue_notified()
        opened.record_answer(A, "yes", "Pay the bill")
        opened.record_approval(A, "nodeadline", "Pay the bill", None)
        follow_up(opened)
        yield opened


def follow_up(store: Store) -> None:
    store.add(FOLLOW)
    store.save_triage("gmail", "m2", NOTIFY)
    store.queue_notified()
    store.choose_card(B, "followup", follows=A)


def send(store: Store, settings: Settings, fake: FakeTasksApp) -> PostReport:
    return send_tasks(store, settings, httpx.Client(transport=httpx.MockTransport(fake.handler)))


def test_a_follow_up_added_to_a_task_is_sent_to_it_once(store: Store, settings: Settings) -> None:
    fake = FakeTasksApp()
    store.record_answer(B, "link", "")
    assert send(store, settings, fake) == PostReport(posted=2, waiting=0, stopped="")
    request = fake.requests[1]
    assert (request.method, str(request.url)) == (
        "POST",
        "http://127.0.0.1:8765/tasks/task-1/links",
    )
    assert request.headers["idempotency-key"] == "gmail:m2"
    assert json.loads(request.content) == LINK_BODY
    assert store.link(B).sent_at == NOW
    assert send(store, settings, fake) == PostReport(posted=0, waiting=0, stopped="")
    assert len(fake.requests) == 2


def test_a_link_waits_while_its_task_cannot_be_sent(store: Store, settings: Settings) -> None:
    fake = FakeTasksApp()
    store.record_answer(B, "link", "")
    fake.failures.append(httpx.Response(503))
    assert send(store, settings, fake) == PostReport(posted=0, waiting=1, stopped="503")
    assert len(fake.requests) == 1
    assert send(store, settings, fake) == PostReport(posted=2, waiting=0, stopped="")
    assert list(fake.links) == ["gmail:m2"]


@pytest.mark.parametrize(
    ("failure", "stopped"),
    [
        (httpx.Response(503), "503"),
        (httpx.Response(404, json={"error": "unknown task"}), "404"),
        (httpx.ConnectError("refused"), "network"),
        ("lost-reply", "network"),
    ],
    ids=["503", "404", "network", "lost-reply"],
)
def test_a_failed_link_stays_queued_and_is_resent_under_its_key(
    store: Store, settings: Settings, failure: object, stopped: str
) -> None:
    fake = FakeTasksApp()
    store.record_answer(B, "link", "")
    fake.failures.extend([None, failure])
    assert send(store, settings, fake) == PostReport(posted=1, waiting=1, stopped=stopped)
    assert store.link(B).sent_at is None
    assert send(store, settings, fake) == PostReport(posted=1, waiting=0, stopped="")
    assert list(fake.links) == ["gmail:m2"]
    first, second = fake.requests[1:]
    assert json.loads(first.content) == json.loads(second.content) == LINK_BODY


@pytest.mark.parametrize("task_id", ["..", "a/b", "a.b", "task 1"])
def test_a_task_id_that_cannot_name_a_path_is_not_accepted(
    store: Store, settings: Settings, task_id: str
) -> None:
    fake = FakeTasksApp()
    store.record_answer(B, "link", "")
    fake.failures.append(httpx.Response(201, json={"id": task_id}))
    assert send(store, settings, fake) == PostReport(posted=0, waiting=1, stopped="response")
    assert store.task(A).task_id is None
    assert len(fake.requests) == 1


def test_a_follow_up_days_after_the_task_is_still_linked(
    settings: Settings, moment: list[datetime]
) -> None:
    fake = FakeTasksApp()
    with open_store(settings) as store:
        store.add(RECORD)
        store.save_triage("gmail", "m1", NOTIFY)
        store.queue_notified()
        store.record_answer(A, "yes", "Pay the bill")
        store.record_approval(A, "nodeadline", "Pay the bill", None)
        assert send(store, settings, fake) == PostReport(posted=1, waiting=0, stopped="")
        moment[0] = NOW + timedelta(days=3)
        store.clear_expired_text()
        follow_up(store)
        store.record_answer(B, "link", "")
        assert send(store, settings, fake) == PostReport(posted=1, waiting=0, stopped="")
        assert fake.links == {"gmail:m2": ("link-1", "task-1", LINK_BODY)}
        assert len(fake.tasks) == 1
