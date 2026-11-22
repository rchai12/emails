"""One sync round for any provider lives in `mailroom.mail_sync`, under no provider's name.

The tests drive it with a scripted adapter for an invented provider account.
"""

import importlib
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from mailroom import clock, gmail_sync, outlook_sync, service
from mailroom.config import get_settings
from mailroom.store import Store, SyncState, open_store

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
RECEIVED = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
LINK = "https://mail.example.test/message/{id}"


def mail_sync():
    return importlib.import_module("mailroom.mail_sync")


def raw(name: str) -> bytes:
    return (
        f"From: Sender <{name}@example.test>\r\n"
        f"Subject: Note {name}\r\n"
        "Date: Thu, 12 Nov 2026 07:59:00 +0000\r\n"
        f"\r\nBody {name}.\r\n"
    ).encode()


class Scripted:
    """A made-up provider: pages to hand out and messages to fetch, every call logged."""

    provider = "yahoo"
    resumed = "delta"

    def __init__(self, log: list[str], account: str = "family") -> None:
        self.account = account
        self.log = log
        self.listed: list[str] = []
        self.new: list[str] | None = []
        self.bookmark = 1
        self.missing: set[str] = set()
        self.broken: dict[str, dict[str, object]] = {}
        self.failing: set[str] = set()

    def _page(self, ids: list[str]):
        self.bookmark += 1
        return mail_sync().Page(tuple(ids), f"b{self.bookmark}")

    def begin(self) -> None:
        self.log.append("begin")

    def start(self, after: datetime):
        self.log.append(f"start {after.isoformat()}")
        return self._page(self.listed)

    def resume(self, bookmark: str):
        self.log.append(f"resume {bookmark}")
        if self.new is None:
            return None
        return self._page(self.new)

    def fetch(self, message_id: str):
        self.log.append(f"fetch {message_id}")
        if message_id in self.failing:
            raise RuntimeError("provider down")
        if message_id in self.missing:
            return None
        fields = {
            "raw": raw(message_id),
            "thread_id": f"t-{message_id}",
            "received_at": RECEIVED,
            "link": LINK.format(id=message_id),
        }
        fields.update(self.broken.get(message_id, {}))
        return mail_sync().Fetched(**fields)


@pytest.fixture
def moment() -> list[datetime]:
    return [NOW]


@pytest.fixture
def log(monkeypatch: pytest.MonkeyPatch, moment: list[datetime]) -> list[str]:
    """Every adapter call, in order."""
    monkeypatch.setattr(clock, "now", lambda: moment[0])
    return []


@pytest.fixture
def store(log: list[str]) -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        log.clear()
        yield opened


def at(log: list[str], moment: list[datetime], when: datetime) -> None:
    """Move the clock and start a fresh log for the next round."""
    moment[0] = when
    log.clear()


def run(source: Scripted, store: Store):
    return mail_sync().run_round(source, store)


def test_the_shared_names_live_in_mail_sync() -> None:
    shared = mail_sync()
    assert shared.FIRST_RUN == timedelta(days=3)
    assert shared.CATCH_UP_LIMIT == timedelta(days=14)
    assert shared.CATCH_UP_OVERLAP == timedelta(hours=1)
    for name in ("FIRST_RUN", "CATCH_UP_LIMIT", "CATCH_UP_OVERLAP", "SyncResult"):
        assert getattr(gmail_sync, name) is getattr(shared, name)
    assert outlook_sync.SyncResult is shared.SyncResult
    assert service.SyncResult is shared.SyncResult
    assert [field for field in shared.SyncResult.__dataclass_fields__] == [
        "account",
        "kind",
        "stored",
        "offline_since",
        "gap",
    ]


def test_outlook_sync_loads_no_gmail_module() -> None:
    script = (
        "import sys, mailroom.mail_sync, mailroom.outlook_sync;"
        "print(sorted(name for name in sys.modules if name.startswith('mailroom.gmail')))"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(path for path in sys.path if path)}
    found = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True, env=env
    )
    assert found.stdout.strip() == "[]"


def test_a_first_round_reads_three_days_and_keeps_the_bookmark(
    log: list[str], moment: list[datetime], store: Store
) -> None:
    source = Scripted(log)
    source.listed = ["y1", "y2"]
    result = run(source, store)
    assert result == mail_sync().SyncResult(
        "family", "first", ("family/y1", "family/y2"), None, False
    )
    assert log == [
        "begin",
        f"start {(NOW - timedelta(days=3)).isoformat()}",
        "fetch y1",
        "fetch y2",
    ]
    assert store.sync_state("yahoo", "family") == SyncState(bookmark="b2", synced_at=NOW)
    stored = store.get("yahoo", "family/y1").record
    assert (stored.provider, stored.thread_id, stored.link, stored.received_at) == (
        "yahoo",
        "family/t-y1",
        LINK.format(id="y1"),
        RECEIVED,
    )


def test_a_later_round_resumes_from_the_bookmark_under_the_adapters_name(
    log: list[str], moment: list[datetime], store: Store
) -> None:
    source = Scripted(log)
    source.listed = ["y1"]
    run(source, store)
    at(log, moment, NOW + timedelta(minutes=5))
    source.new = ["y2"]
    result = run(source, store)
    assert result == mail_sync().SyncResult("family", "delta", ("family/y2",), None, False)
    assert log == ["begin", "resume b2", "fetch y2"]
    later = NOW + timedelta(minutes=5)
    assert store.sync_state("yahoo", "family") == SyncState(bookmark="b3", synced_at=later)
    source.resumed = "history"
    source.new = []
    assert run(source, store).kind == "history"


@pytest.mark.parametrize(
    ("offline", "after", "gap"),
    [
        (timedelta(days=2), datetime(2026, 11, 13, 8, 0, tzinfo=UTC), False),
        (timedelta(days=14), datetime(2026, 11, 13, 9, 0, tzinfo=UTC), False),
        (timedelta(days=20), datetime(2026, 11, 19, 9, 0, tzinfo=UTC), True),
    ],
    ids=["2-days", "14-days", "20-days"],
)
def test_an_expired_bookmark_catches_up_with_an_hour_overlap_and_14_days_at_most(
    log: list[str],
    moment: list[datetime],
    store: Store,
    offline: timedelta,
    after: datetime,
    gap: bool,
) -> None:
    source = Scripted(log)
    run(source, store)
    at(log, moment, NOW + offline)
    source.new = None
    source.listed = ["y1"]
    result = run(source, store)
    assert result == mail_sync().SyncResult("family", "catch_up", ("family/y1",), NOW, gap)
    assert log == ["begin", "resume b2", f"start {after.isoformat()}", "fetch y1"]
    assert store.sync_state("yahoo", "family") == SyncState(bookmark="b3", synced_at=NOW + offline)


def test_a_stored_message_is_not_fetched_again_and_skips_are_left_out(
    log: list[str], moment: list[datetime], store: Store
) -> None:
    source = Scripted(log)
    source.listed = ["y1"]
    run(source, store)
    at(log, moment, NOW + timedelta(minutes=1))
    source.new = ["y1", "y2", "y3", "y4", "y5", "y6"]
    source.missing = {"y2"}
    source.broken = {
        "y3": {"thread_id": "t" * 1001},
        "y4": {"link": "javascript:alert(1)"},
        "y5": {"received_at": datetime(2026, 11, 12, 8, 0)},
    }
    result = run(source, store)
    assert result.stored == ("family/y6",)
    assert log == ["begin", "resume b2"] + [f"fetch y{n}" for n in range(2, 7)]
    for name in ("y2", "y3", "y4", "y5"):
        assert store.get("yahoo", f"family/{name}") is None


def test_an_interrupted_round_keeps_the_bookmark_and_what_it_stored(
    log: list[str], moment: list[datetime], store: Store
) -> None:
    source = Scripted(log)
    run(source, store)
    before = store.sync_state("yahoo", "family")
    at(log, moment, NOW + timedelta(minutes=1))
    source.new = ["y1", "y2"]
    source.failing = {"y2"}
    with pytest.raises(RuntimeError):
        run(source, store)
    assert store.sync_state("yahoo", "family") == before
    assert store.get("yahoo", "family/y1") is not None
    at(log, moment, NOW + timedelta(minutes=2))
    source.failing = set()
    assert run(source, store).stored == ("family/y2",)
    assert log == ["begin", "resume b2", "fetch y2"]


def test_accounts_of_one_provider_keep_their_own_bookmarks_and_ids(
    log: list[str], moment: list[datetime], store: Store
) -> None:
    family, work = Scripted(log), Scripted(log, account="work")
    family.listed = work.listed = ["y1"]
    assert run(family, store).stored == ("family/y1",)
    assert run(work, store).stored == ("work/y1",)
    assert store.sync_state("yahoo", "family").bookmark == "b2"
    assert store.sync_state("yahoo", "work").bookmark == "b2"
