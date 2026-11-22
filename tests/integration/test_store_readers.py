"""Store lifecycle and reader behavior the given projection tests leave unpinned."""

import itertools
import random
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mailroom import clock, ids
from mailroom.config import get_settings
from mailroom.schema import MIGRATIONS
from mailroom.store import DB_FILENAME, Store, StoreError, approvals, open_store
from tests.integration.test_store_projections import M1, M2, PROJECTIONS
from tests.integration.test_store_triage import EXTRACTED

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)
ITEM = "01" + "a" * 30


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    counter = itertools.count(1)
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):02d}" + "a" * 30)


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        opened.add(M1)
        opened.save_triage("gmail", "m1", replace(EXTRACTED, notify=True))
        opened.queue_notified()
        yield opened


def count_opens(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counts = {"connect": 0, "scripts": 0}
    real = sqlite3.connect

    class Counting(sqlite3.Connection):
        def executescript(self, script: str) -> sqlite3.Cursor:
            counts["scripts"] += 1
            return super().executescript(script)

    def connect(path: str | Path, *args: object, **kwargs: object) -> sqlite3.Connection:
        counts["connect"] += 1
        return real(path, factory=Counting)

    monkeypatch.setattr(sqlite3, "connect", connect)
    return counts


def test_a_new_store_connects_once_and_runs_every_migration_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = count_opens(monkeypatch)
    with open_store(get_settings()):
        pass
    assert counts == {"connect": 1, "scripts": len(MIGRATIONS)}
    assert (get_settings().data_dir / DB_FILENAME).exists()


def test_a_reopened_store_connects_once_and_runs_no_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with open_store(get_settings()):
        pass
    counts = count_opens(monkeypatch)
    with open_store(get_settings()):
        pass
    assert counts == {"connect": 1, "scripts": 0}


@pytest.mark.parametrize("name", sorted(PROJECTIONS))
def test_a_duplicate_column_is_refused_even_when_no_row_matches(
    store: Store, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    module, constant = PROJECTIONS[name]
    columns = getattr(module, constant)
    monkeypatch.setattr(module, constant, (*columns, columns[0]))
    bare = columns[0].rsplit(".", 1)[-1]
    readers = {
        "posts": lambda: store.post("gmail", "none"),
        "tasks": lambda: store.task("f" * 32),
        "links": lambda: store.link("f" * 32),
        "approvals": lambda: store.approval("f" * 32),
        "messages": lambda: store.get("gmail", "none"),
        "triage": lambda: store.triage("gmail", "none"),
    }
    with pytest.raises(StoreError) as raised:
        readers[name]()
    assert str(raised.value) == f"duplicate stored column: {bare}"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_shuffled_projection_reads_the_same_records(
    store: Store, monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    store.add(M2)
    store.save_triage("gmail", "m2", replace(EXTRACTED, notify=True))
    store.queue_notified()
    store.record_answer(ITEM, "yes", "Pay it")
    store.record_approval(ITEM, "nodeadline", "Pay it", None)
    store.queue_approved()
    before = (
        store.pending_posts(),
        store.post("gmail", "m1"),
        store.pending_tasks(),
        store.approval(ITEM),
        store.approved_in_thread("gmail", "t1"),
        store.get("gmail", "m2"),
        store.triage("gmail", "m1"),
    )
    rng = random.Random(seed)
    for module, constant in PROJECTIONS.values():
        columns = list(getattr(module, constant))
        rng.shuffle(columns)
        monkeypatch.setattr(module, constant, tuple(columns))
    after = (
        store.pending_posts(),
        store.post("gmail", "m1"),
        store.pending_tasks(),
        store.approval(ITEM),
        store.approved_in_thread("gmail", "t1"),
        store.get("gmail", "m2"),
        store.triage("gmail", "m1"),
    )
    assert after == before


def test_a_failed_combined_record_writes_neither_answer_nor_approval(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "_INSERT", "INSERT INTO nowhere VALUES (1)")
    with pytest.raises(sqlite3.OperationalError):
        store.record_combined(ITEM, "approve", "Pay it", None)
    assert store.answer(ITEM) is None
    assert store.approval(ITEM) is None
