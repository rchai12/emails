from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from mailroom.config import get_settings
from mailroom.record import Record
from mailroom.store import Post, Store, Verdict, open_store
from tests.support import fixed_ids, fixed_times

RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=None,
    body_text="Your bill is due.",
    list_unsubscribe=False,
    authentication_results=(),
)
NOTIFY = Verdict(
    outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="timeout"
)
QUIET = Verdict(outcome="dropped", trusted=False, verified=False, bulk=False, notify=False)


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def decided(store: Store, *verdicts: tuple[str, Verdict]) -> None:
    for message_id, verdict in verdicts:
        store.add(replace(RECORD, message_id=message_id))
        store.save_triage("gmail", message_id, verdict)


def test_every_notified_verdict_is_queued_once_in_the_order_decided(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_times(
        monkeypatch,
        *[f"2026-11-10T08:00:0{second}+00:00" for second in range(6)],
        "2026-11-10T08:01:00+00:00",
        "2026-11-10T08:02:00+00:00",
    )
    fixed_ids(monkeypatch, "item-b", "item-a")
    decided(store, ("b", NOTIFY), ("muted", QUIET), ("a", NOTIFY))
    assert store.queue_notified() == 2
    assert store.queue_notified() == 0
    assert store.pending_posts() == (
        Post(
            item_id="item-b",
            provider="gmail",
            message_id="b",
            queued_at=datetime(2026, 11, 10, 8, 1, tzinfo=UTC),
            discord_message_id=None,
            posted_at=None,
        ),
        Post(
            item_id="item-a",
            provider="gmail",
            message_id="a",
            queued_at=datetime(2026, 11, 10, 8, 1, tzinfo=UTC),
            discord_message_id=None,
            posted_at=None,
        ),
    )
    assert store.post("gmail", "muted") is None


def test_a_posted_item_records_its_discord_message_once(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:00:01+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-10T08:02:00+00:00",
        "2026-11-10T08:03:00+00:00",
        "2026-11-10T08:04:00+00:00",
    )
    fixed_ids(monkeypatch, "item-1")
    decided(store, ("m1", NOTIFY))
    store.queue_notified()
    assert store.mark_posted("item-1", "1300000000000000001") is True
    assert store.mark_posted("item-1", "1300000000000000002") is False
    assert store.mark_posted("item-9", "1300000000000000003") is False
    assert store.pending_posts() == ()
    assert store.post("gmail", "m1") == Post(
        item_id="item-1",
        provider="gmail",
        message_id="m1",
        queued_at=datetime(2026, 11, 10, 8, 1, tzinfo=UTC),
        discord_message_id="1300000000000000001",
        posted_at=datetime(2026, 11, 10, 8, 2, tzinfo=UTC),
    )


def test_a_verdict_decided_after_queueing_waits_for_the_next_queue(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:00:01+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-10T08:01:01+00:00",
        "2026-11-10T08:01:02+00:00",
        "2026-11-10T08:02:00+00:00",
    )
    fixed_ids(monkeypatch, "item-1", "item-2")
    decided(store, ("m1", NOTIFY))
    assert store.queue_notified() == 1
    decided(store, ("m2", NOTIFY))
    assert [post.item_id for post in store.pending_posts()] == ["item-1"]
    assert store.queue_notified() == 1
    assert [post.item_id for post in store.pending_posts()] == ["item-1", "item-2"]


def test_queued_posts_survive_reopening_and_text_clearing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:00:01+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-11T09:00:00+00:00",
    )
    fixed_ids(monkeypatch, "item-1")
    with open_store(get_settings()) as store:
        decided(store, ("m1", NOTIFY))
        store.queue_notified()
    with open_store(get_settings()) as store:
        assert store.clear_expired_text() == 1
        assert [post.item_id for post in store.pending_posts()] == ["item-1"]
