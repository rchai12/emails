"""A queued task or link with incomplete stored rows is kept unsent and reported, never guessed."""

import itertools
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest

from mailroom import clock, ids
from mailroom.config import Settings, get_settings
from mailroom.store import DB_FILENAME, Store, open_store
from mailroom.tasks_app import send_tasks
from tests.fakes import FakeTasksApp
from tests.integration.test_store_posts import NOTIFY, RECORD

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
ALERT = "Mailroom kept item {item} unsent: its stored details are incomplete."


def remove(sql: str) -> None:
    """Delete rows with a second connection, as damage outside Mailroom would."""
    raw = sqlite3.connect(get_settings().data_dir / DB_FILENAME)
    try:
        raw.execute(sql)
        raw.commit()
    finally:
        raw.close()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    counter = itertools.count(1)
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):02d}" + "a" * 30)
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    monkeypatch.setenv("MAILROOM_TASKS_URL", FakeTasksApp.URL)
    return get_settings()


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    """m1 and m2 approved as tasks, each in its own thread."""
    with open_store(settings) as opened:
        for number in (1, 2):
            message_id = f"m{number}"
            link = f"https://mail.google.com/mail/#all/{message_id}"
            opened.add(replace(RECORD, message_id=message_id, thread_id=f"t{number}", link=link))
            opened.save_triage("gmail", message_id, NOTIFY)
        opened.queue_notified()
        for message_id in ("m1", "m2"):
            approve(opened, message_id)
        yield opened


def approve(store: Store, message_id: str) -> str:
    found = store.post("gmail", message_id).item_id
    store.record_answer(found, "yes", "Pay the bill")
    store.record_approval(found, "nodeadline", "Pay the bill", None)
    return found


def item(store: Store, message_id: str) -> str:
    return store.post("gmail", message_id).item_id


def send(store: Store, settings: Settings, fake: FakeTasksApp):
    return send_tasks(store, settings, httpx.Client(transport=httpx.MockTransport(fake.handler)))


def alerts(store: Store) -> list[tuple[str, str, bool]]:
    return [(alert.key, alert.text, alert.ping) for alert in store.pending_alerts()]


def sent_ids(fake: FakeTasksApp) -> list[str]:
    return [json.loads(request.content)["message_id"] for request in fake.requests]


def test_a_task_whose_approval_is_gone_is_never_sent(store: Store, settings: Settings) -> None:
    first = item(store, "m1")
    store.queue_approved()
    remove(f"DELETE FROM approvals WHERE item_id = '{first}'")
    fake = FakeTasksApp()
    report = send(store, settings, fake)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (1, 0, "", 1)
    assert sent_ids(fake) == ["m2"]
    assert store.task(first).task_id is None
    assert alerts(store) == [(f"incomplete:{first}", ALERT.format(item=first), False)]
    report = send(store, settings, fake)
    assert (report.posted, report.skipped) == (0, 1)
    assert sent_ids(fake) == ["m2"]
    assert len(alerts(store)) == 1


def test_a_task_whose_message_row_is_gone_is_kept_and_the_next_is_sent(
    store: Store, settings: Settings
) -> None:
    first = item(store, "m1")
    store.queue_approved()
    remove("DELETE FROM messages WHERE message_id = 'm1'")
    fake = FakeTasksApp()
    report = send(store, settings, fake)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (1, 0, "", 1)
    assert sent_ids(fake) == ["m2"]
    assert [task.item_id for task in store.pending_tasks()] == [first]
    assert alerts(store) == [(f"incomplete:{first}", ALERT.format(item=first), False)]


def test_a_link_whose_message_row_is_gone_is_kept(store: Store, settings: Settings) -> None:
    fake = FakeTasksApp()
    send(store, settings, fake)
    store.add(replace(RECORD, message_id="m3", thread_id="t1", link="https://mail.test/m3"))
    store.save_triage("gmail", "m3", NOTIFY)
    store.queue_notified()
    third = item(store, "m3")
    store.choose_card(third, "followup", follows=item(store, "m1"))
    store.record_answer(third, "link", "")
    remove("DELETE FROM messages WHERE message_id = 'm3'")
    report = send(store, settings, fake)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (0, 0, "", 1)
    assert fake.links == {}
    assert store.link(third).sent_at is None
    assert alerts(store) == [(f"incomplete:{third}", ALERT.format(item=third), False)]


def test_complete_tasks_are_sent_once_and_skip_nothing(store: Store, settings: Settings) -> None:
    fake = FakeTasksApp()
    report = send(store, settings, fake)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (2, 0, "", 0)
    report = send(store, settings, fake)
    assert (report.posted, report.skipped) == (0, 0)
    assert sent_ids(fake) == ["m1", "m2"]
    assert alerts(store) == []


def test_a_failed_task_send_after_a_kept_task_still_counts_it(
    store: Store, settings: Settings
) -> None:
    store.queue_approved()
    remove("DELETE FROM messages WHERE message_id = 'm1'")
    fake = FakeTasksApp()
    fake.failures.append(httpx.Response(503))
    report = send(store, settings, fake)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (0, 1, "503", 1)
    assert len(store.pending_tasks()) == 2
