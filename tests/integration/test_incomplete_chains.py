"""Phase 4i: incomplete-chain behavior the given tests leave unpinned."""

from dataclasses import replace

import httpx
import pytest

from mailroom.config import Settings, get_settings
from mailroom.interactions import handle_interaction
from mailroom.store import Store
from tests.fakes import FakeDiscord, FakeTasksApp
from tests.integration.test_send_incomplete import (
    ALERT,
    NOTIFY,
    RECORD,
    alerts,
    item,
    remove,
    send,
    sent_ids,
)
from tests.integration.test_send_incomplete import settings as settings
from tests.integration.test_send_incomplete import store as store


def test_a_kept_task_and_a_network_failure_on_the_next_keep_both_queued(
    store: Store, settings: Settings
) -> None:
    first = item(store, "m1")
    store.queue_approved()
    remove("DELETE FROM messages WHERE message_id = 'm1'")
    fake = FakeTasksApp()
    fake.failures.append(httpx.ConnectError("synthetic"))
    report = send(store, settings, fake)
    assert (report.posted, report.waiting, report.stopped, report.skipped) == (0, 1, "network", 1)
    assert len(store.pending_tasks()) == 2
    assert alerts(store) == [(f"incomplete:{first}", ALERT.format(item=first), False)]


def test_a_link_whose_message_row_returns_is_sent_once(store: Store, settings: Settings) -> None:
    fake = FakeTasksApp()
    send(store, settings, fake)
    third_record = replace(RECORD, message_id="m3", thread_id="t1", link="https://mail.test/m3")
    store.add(third_record)
    store.save_triage("gmail", "m3", NOTIFY)
    store.queue_notified()
    third = item(store, "m3")
    store.choose_card(third, "followup", follows=item(store, "m1"))
    store.record_answer(third, "link", "")
    remove("DELETE FROM messages WHERE message_id = 'm3'")
    assert send(store, settings, fake).skipped == 1
    store.add(third_record)
    assert send(store, settings, fake).skipped == 0
    assert send(store, settings, fake).posted == 0
    assert len(fake.links) == 1
    assert store.link(third).sent_at is not None
    assert len(alerts(store)) == 1
    assert sent_ids(fake) == ["m1", "m2", "m3"]


def test_a_slash_command_still_works_while_an_email_is_incomplete(
    store: Store, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    remove("DELETE FROM messages WHERE message_id = 'm1'")
    discord = FakeDiscord()
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    outcome = handle_interaction(discord.command("trusted"), store, get_settings(), http)
    assert outcome not in ("ignored", "incomplete")
    assert discord.callbacks[0][1]["type"] == 4
