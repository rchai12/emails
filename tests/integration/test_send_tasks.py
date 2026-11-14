"""Sending approved tasks to the stub tasks app: keyed, once each, and kept queued on a failure."""

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.discord_post import PostReport
from mailroom.store import Due, Store, open_store
from mailroom.tasks_app import TasksUnavailable, open_tasks_http, send_tasks
from tests.fakes import FakeTasksApp
from tests.integration.test_store_posts import NOTIFY, RECORD
from tests.support import fixed_ids

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
DUE = Due(date=date(2026, 11, 20), time=time(17, 0))
BODY = {
    "source": "email",
    "title": "Pay the bill",
    "deadline": {"date": "2026-11-20", "time": "17:00", "time_zone": "America/New_York"},
    "provider": "gmail",
    "message_id": "m1",
    "link": "https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
}


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    fixed_ids(monkeypatch, "a" * 32, "b" * 32)
    return now


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, moment: list[datetime]) -> Settings:
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    monkeypatch.setenv("MAILROOM_TASKS_URL", FakeTasksApp.URL)
    return get_settings()


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    with open_store(settings) as opened:
        for message_id in ("m1", "m2"):
            opened.add(replace(RECORD, message_id=message_id))
            opened.save_triage("gmail", message_id, NOTIFY)
        opened.queue_notified()
        yield opened


def approve(store: Store, message_id: str, outcome: str = "approve") -> str:
    item = store.post("gmail", message_id).item_id
    store.record_answer(item, "yes", "Pay the bill")
    title = "" if outcome == "drop" else "Pay the bill"
    store.record_approval(item, outcome, title, DUE if outcome == "approve" else None)
    return item


def send(store: Store, settings: Settings, fake: FakeTasksApp) -> PostReport:
    return send_tasks(store, settings, httpx.Client(transport=httpx.MockTransport(fake.handler)))


def test_an_approved_task_is_sent_once_under_its_key(store: Store, settings: Settings) -> None:
    fake = FakeTasksApp()
    item = approve(store, "m1")
    assert send(store, settings, fake) == PostReport(posted=1, waiting=0, stopped="")
    (request,) = fake.requests
    assert (request.method, str(request.url)) == ("POST", "http://127.0.0.1:8765/tasks")
    assert request.headers["idempotency-key"] == "gmail:m1"
    assert json.loads(request.content) == BODY
    assert (store.task(item).task_id, store.task(item).sent_at) == ("task-1", NOW)
    assert send(store, settings, fake) == PostReport(posted=0, waiting=0, stopped="")
    assert len(fake.requests) == 1


def test_without_a_tasks_app_address_nothing_is_sent(
    monkeypatch: pytest.MonkeyPatch, store: Store
) -> None:
    monkeypatch.delenv("MAILROOM_TASKS_URL")
    fake = FakeTasksApp()
    approve(store, "m1")
    with pytest.raises(TasksUnavailable) as caught:
        send(store, get_settings(), fake)
    assert str(caught.value) == "tasks app unavailable (not configured)"
    assert fake.requests == []


@pytest.mark.parametrize(
    ("failure", "stopped"),
    [
        (httpx.Response(503, text="busy"), "503"),
        (httpx.Response(409, json={"error": "key reused"}), "409"),
        (httpx.ConnectError("refused"), "network"),
        (httpx.Response(201, text="created"), "response"),
        (httpx.Response(201, json={"id": 7}), "response"),
        (httpx.Response(201, json={"id": ""}), "response"),
        (httpx.Response(201, json={"id": "t" * 101}), "response"),
    ],
    ids=["503", "409", "network", "not-json", "id-not-text", "id-empty", "id-too-long"],
)
def test_a_failed_send_keeps_the_task_queued_for_the_next_round(
    store: Store, settings: Settings, failure: object, stopped: str
) -> None:
    fake = FakeTasksApp()
    item = approve(store, "m1")
    fake.failures.append(failure)
    assert send(store, settings, fake) == PostReport(posted=0, waiting=1, stopped=stopped)
    assert store.task(item).task_id is None
    assert send(store, settings, fake) == PostReport(posted=1, waiting=0, stopped="")
    assert store.task(item).task_id == "task-1"


def test_a_lost_reply_is_resent_under_the_same_key_after_the_text_is_cleared(
    store: Store, settings: Settings, moment: list[datetime]
) -> None:
    fake = FakeTasksApp()
    item = approve(store, "m1")
    fake.failures.append("lost-reply")
    assert send(store, settings, fake) == PostReport(posted=0, waiting=1, stopped="network")
    moment[0] = NOW + timedelta(days=2)
    store.clear_expired_text()
    assert send(store, settings, fake) == PostReport(posted=1, waiting=0, stopped="")
    first, second = fake.requests
    assert first.headers["idempotency-key"] == second.headers["idempotency-key"] == "gmail:m1"
    assert json.loads(first.content) == json.loads(second.content) == BODY
    assert list(fake.tasks) == ["gmail:m1"]
    assert store.task(item).task_id == "task-1"


def test_a_failure_stops_the_round_and_leaves_the_rest_queued(
    store: Store, settings: Settings
) -> None:
    fake = FakeTasksApp()
    first = approve(store, "m1")
    second = approve(store, "m2", "nodeadline")
    fake.failures.extend([None, httpx.Response(503)])
    assert send(store, settings, fake) == PostReport(posted=1, waiting=1, stopped="503")
    assert [task.item_id for task in store.pending_tasks()] == [second]
    assert store.task(first).task_id == "task-1"
    assert json.loads(fake.requests[1].content)["deadline"] is None


def test_a_dropped_or_undecided_item_is_never_sent(store: Store, settings: Settings) -> None:
    fake = FakeTasksApp()
    approve(store, "m1", "drop")
    store.record_answer(store.post("gmail", "m2").item_id, "yes", "Pay the bill")
    assert send(store, settings, fake) == PostReport(posted=0, waiting=0, stopped="")
    assert fake.requests == []


def test_the_tasks_client_ignores_proxies_and_redirects() -> None:
    http = open_tasks_http()
    try:
        assert (http.trust_env, http.follow_redirects) == (False, False)
        assert http.timeout == httpx.Timeout(30.0)
    finally:
        http.close()
