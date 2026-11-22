"""Store readers map columns by name: a reordered projection returns the same records."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from types import ModuleType

import pytest

from mailroom import clock, ids
from mailroom.config import get_settings
from mailroom.record import Record
from mailroom.store import (
    Approval,
    Due,
    Link,
    Post,
    Store,
    StoredMessage,
    StoredTriage,
    StoreError,
    Task,
    approvals,
    messages,
    open_store,
    posts,
    tasks,
    triage,
)
from tests.integration.test_store_triage import EXTRACTED, REJECTED

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=25)
A, B, C, D, E = (f"{number:02d}" + "a" * 30 for number in range(1, 6))
DUE = Due(date=date(2026, 11, 20), time=time(17, 0))
DATE_ONLY = Due(date=date(2026, 11, 20), time=None)
DATED = replace(EXTRACTED, dated=True, due=DUE)
UNTIMED = replace(EXTRACTED, due=DATE_ONLY)
M1 = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 21, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=datetime(2026, 11, 21, 7, 59, tzinfo=UTC),
    body_text="Your bill of $42.00 is due on November 20 at 5 pm.",
    list_unsubscribe=True,
    authentication_results=("spf=pass", "dkim=pass"),
)
M2 = replace(M1, message_id="m2", sent_at=None, list_unsubscribe=False, authentication_results=())
POSTED = "900000000000000001"

PROJECTIONS: dict[str, tuple[ModuleType, str]] = {
    "posts": (posts, "POST_COLUMNS"),
    "tasks": (tasks, "TASK_COLUMNS"),
    "links": (tasks, "LINK_COLUMNS"),
    "approvals": (approvals, "APPROVAL_COLUMNS"),
    "messages": (messages, "MESSAGE_COLUMNS"),
    "triage": (triage, "TRIAGE_COLUMNS"),
}
ORDERS = ("as written", "reversed")


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    moment = [NOW]
    monkeypatch.setattr(clock, "now", lambda: moment[0])
    counter = itertools.count(1)
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):02d}" + "a" * 30)
    return moment


@pytest.fixture
def store(now: list[datetime]) -> Iterator[Store]:
    """m1 to m5 queued as items A to E. A is posted with an approved, sent task.

    B and C have approvals and unsent tasks. D and E are follow-up links to A and B.
    """
    with open_store(get_settings()) as opened:
        records = (M1, M2, replace(M2, message_id="m3", thread_id="t3"))
        records += tuple(replace(M2, message_id=f"m{n}", thread_id=f"t{n}") for n in (4, 5))
        verdicts = (DATED, UNTIMED, REJECTED, REJECTED, REJECTED)
        for record, verdict in zip(records, verdicts, strict=True):
            opened.add(record)
            opened.save_triage("gmail", record.message_id, verdict)
        opened.queue_notified()
        opened.mark_posted(A, POSTED)
        for item, answer, outcome, title, due in (
            (A, "yes", "approve", "Pay the November bill", DUE),
            (B, "edit", "change", "Pay it", DATE_ONLY),
            (C, "yes", "nodeadline", "File it", None),
        ):
            opened.record_answer(item, answer, title)
            opened.record_approval(item, outcome, title, due)
        opened.queue_approved()
        opened.mark_task_sent(A, "task-1")
        for item, target in ((D, A), (E, B)):
            opened.choose_card(item, "followup", target)
            opened.record_answer(item, "link", "")
        opened.queue_linked()
        yield opened


def arrange(monkeypatch: pytest.MonkeyPatch, projection: str, order: str) -> None:
    module, name = PROJECTIONS[projection]
    columns = getattr(module, name)
    if order == "reversed":
        columns = tuple(reversed(columns))
    monkeypatch.setattr(module, name, columns)


def post(item: str, message_id: str, **changes: object) -> Post:
    return replace(Post(item, "gmail", message_id, NOW, None, None), **changes)


@pytest.mark.parametrize("order", ORDERS)
def test_posts_read_back_as_literal_records(
    store: Store, monkeypatch: pytest.MonkeyPatch, order: str
) -> None:
    arrange(monkeypatch, "posts", order)
    assert store.pending_posts() == (
        post(B, "m2"),
        post(C, "m3"),
        post(D, "m4", card="followup", follows=A),
        post(E, "m5", card="followup", follows=B),
    )
    assert store.post("gmail", "m1") == post(A, "m1", discord_message_id=POSTED, posted_at=NOW)
    assert store.post_by_item(D) == post(D, "m4", card="followup", follows=A)
    assert store.post("gmail", "m9") is None
    assert store.post_by_item("f" * 32) is None


@pytest.mark.parametrize("order", ORDERS)
def test_tasks_read_back_as_literal_records(
    store: Store, monkeypatch: pytest.MonkeyPatch, order: str
) -> None:
    arrange(monkeypatch, "tasks", order)
    assert store.pending_tasks() == (
        Task(B, "gmail", "m2", NOW, None, None),
        Task(C, "gmail", "m3", NOW, None, None),
    )
    assert store.task(A) == Task(A, "gmail", "m1", NOW, "task-1", NOW)
    assert store.task(D) is None


@pytest.mark.parametrize("order", ORDERS)
def test_links_read_back_as_literal_records(
    store: Store, monkeypatch: pytest.MonkeyPatch, order: str
) -> None:
    arrange(monkeypatch, "links", order)
    assert store.pending_links() == (Link(D, "gmail", "m4", A, "task-1", NOW, None),)
    assert store.link(E) == Link(E, "gmail", "m5", B, None, NOW, None)
    store.mark_link_sent(D)
    assert store.link(D) == Link(D, "gmail", "m4", A, "task-1", NOW, NOW)
    assert store.link(A) is None


@pytest.mark.parametrize("order", ORDERS)
def test_approvals_read_back_as_literal_records(
    store: Store, monkeypatch: pytest.MonkeyPatch, order: str
) -> None:
    arrange(monkeypatch, "approvals", order)
    assert store.approval(A) == Approval(A, "approve", "Pay the November bill", DUE, NOW)
    assert store.approval(B) == Approval(B, "change", "Pay it", DATE_ONLY, NOW)
    assert store.approval(C) == Approval(C, "nodeadline", "File it", None, NOW)
    assert store.approved_in_thread("gmail", "t1") == store.approval(B)
    assert store.approved_in_thread("gmail", "t3") == store.approval(C)
    assert store.approval(D) is None
    assert store.approved_in_thread("gmail", "t4") is None


@pytest.mark.parametrize("order", ORDERS)
def test_messages_read_back_as_literal_records(
    store: Store, monkeypatch: pytest.MonkeyPatch, order: str
) -> None:
    arrange(monkeypatch, "messages", order)
    assert store.get("gmail", "m1") == StoredMessage(M1, NOW, None)
    assert store.get("gmail", "m2") == StoredMessage(M2, NOW, None)
    assert store.get("outlook", "m1") is None


@pytest.mark.parametrize("order", ORDERS)
def test_triage_reads_back_as_literal_records(
    store: Store, monkeypatch: pytest.MonkeyPatch, order: str
) -> None:
    arrange(monkeypatch, "triage", order)
    assert store.triage("gmail", "m1") == StoredTriage(DATED, NOW, None)
    assert store.triage("gmail", "m2") == StoredTriage(UNTIMED, NOW, None)
    assert store.triage("gmail", "m3") == StoredTriage(REJECTED, NOW, None)
    assert store.triage("gmail", "m9") is None


def test_cleared_text_reads_back_the_same_through_reversed_projections(
    store: Store, monkeypatch: pytest.MonkeyPatch, now: list[datetime]
) -> None:
    arrange(monkeypatch, "messages", "reversed")
    arrange(monkeypatch, "triage", "reversed")
    now[0] = LATER
    assert store.clear_expired_text() == 5
    cleared = replace(M1, body_text="", authentication_results=())
    assert store.get("gmail", "m1") == StoredMessage(cleared, NOW, LATER)
    assert store.triage("gmail", "m1") == StoredTriage(replace(DATED, extraction=None), NOW, LATER)
    assert store.triage("gmail", "m3") == StoredTriage(REJECTED, NOW, None)


READERS = [
    ("posts", "pending_posts", ()),
    ("posts", "post", ("gmail", "m1")),
    ("posts", "post_by_item", (A,)),
    ("tasks", "pending_tasks", ()),
    ("tasks", "task", (A,)),
    ("links", "pending_links", ()),
    ("links", "link", (D,)),
    ("approvals", "approval", (A,)),
    ("approvals", "approved_in_thread", ("gmail", "t1")),
    ("messages", "get", ("gmail", "m1")),
    ("triage", "triage", ("gmail", "m1")),
]


@pytest.mark.parametrize(
    ("projection", "reader", "args"), READERS, ids=[f"{p}-{r}" for p, r, _ in READERS]
)
def test_a_duplicate_column_in_a_projection_is_refused_by_name(
    store: Store,
    monkeypatch: pytest.MonkeyPatch,
    projection: str,
    reader: str,
    args: tuple[str, ...],
) -> None:
    module, name = PROJECTIONS[projection]
    columns = getattr(module, name)
    monkeypatch.setattr(module, name, (*columns, columns[1]))
    bare = columns[1].rsplit(".", 1)[-1]
    with pytest.raises(StoreError) as raised:
        getattr(store, reader)(*args)
    assert str(raised.value) == f"duplicate stored column: {bare}"
