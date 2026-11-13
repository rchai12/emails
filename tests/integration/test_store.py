import sqlite3
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailroom.config import get_settings
from mailroom.record import Record
from mailroom.store import StoredMessage, StoreError, open_store
from tests.support import fixed_times

RECORD = Record(
    provider="gmail",
    message_id="18c2f0a1b2c3d4e5",
    thread_id="18c2f0a1b2c3d4e0",
    received_at=datetime(2026, 11, 3, 14, 15, 5, tzinfo=UTC),
    link="https://mail.google.com/mail/u/0/#all/18c2f0a1b2c3d4e5",
    sender="billing@billing.example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=datetime(2026, 11, 3, 14, 15, tzinfo=UTC),
    body_text="Hello,\n\nYour bill of $42.00 is due on November 20.",
    list_unsubscribe=True,
    authentication_results=(
        "mx.google.com; dmarc=pass header.from=billing.example.test",
        "mx2.example.test; spf=pass",
    ),
)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def database(tmp_path: Path) -> Path:
    return tmp_path / "data" / "mailroom.sqlite3"


def raw_row(tmp_path: Path, query: str) -> tuple[object, ...]:
    connection = sqlite3.connect(database(tmp_path))
    try:
        return connection.execute(query).fetchone()
    finally:
        connection.close()


def test_opening_creates_a_private_database(tmp_path: Path) -> None:
    open_store(get_settings()).close()
    assert mode(tmp_path / "data") == 0o700
    assert mode(database(tmp_path)) == 0o600
    assert raw_row(tmp_path, "PRAGMA user_version") == (9,)
    assert raw_row(tmp_path, "SELECT count(*) FROM messages") == (0,)


def test_opening_tightens_an_existing_database(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    sqlite3.connect(database(tmp_path)).close()
    database(tmp_path).chmod(0o644)
    open_store(get_settings()).close()
    assert mode(database(tmp_path)) == 0o600
    assert raw_row(tmp_path, "PRAGMA user_version") == (9,)


def test_a_newer_schema_is_refused(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    connection = sqlite3.connect(database(tmp_path))
    connection.execute("PRAGMA user_version = 99")
    connection.close()
    with pytest.raises(StoreError) as caught:
        open_store(get_settings())
    assert str(caught.value) == "unsupported schema version: 99"


def test_a_record_is_stored_and_read_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_times(monkeypatch, "2026-11-11T09:00:00+00:00")
    with open_store(get_settings()) as store:
        assert store.add(RECORD) is True
        assert store.get("gmail", "18c2f0a1b2c3d4e5") == StoredMessage(
            record=RECORD,
            fetched_at=datetime(2026, 11, 11, 9, 0, tzinfo=UTC),
            text_cleared_at=None,
        )
        assert store.get("gmail", "18c2f0a1b2c3d4e6") is None
        assert store.get("outlook", "18c2f0a1b2c3d4e5") is None


def test_a_record_without_optional_values_round_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_times(monkeypatch, "2026-11-11T09:00:00+00:00")
    bare = replace(RECORD, sent_at=None, list_unsubscribe=False, authentication_results=())
    with open_store(get_settings()) as store:
        store.add(bare)
        found = store.get("gmail", "18c2f0a1b2c3d4e5")
    assert found is not None
    assert found.record == bare


def test_the_same_message_is_stored_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-11T09:00:00+00:00",
        "2026-11-11T09:01:00+00:00",
        "2026-11-11T09:02:00+00:00",
    )
    with open_store(get_settings()) as store:
        assert store.add(RECORD) is True
        assert store.add(replace(RECORD, subject="Changed")) is False
        assert store.add(replace(RECORD, provider="outlook")) is True
        first = store.get("gmail", "18c2f0a1b2c3d4e5")
    assert first is not None
    assert first.record.subject == "Your November bill"
    assert first.fetched_at == datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


def test_rows_survive_reopening(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_times(monkeypatch, "2026-11-11T09:00:00+00:00")
    with open_store(get_settings()) as store:
        store.add(RECORD)
    with open_store(get_settings()) as store:
        assert store.get("gmail", "18c2f0a1b2c3d4e5") is not None


def test_times_are_stored_as_utc_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixed_times(monkeypatch, "2026-11-11T04:00:00-05:00")
    india = timezone(timedelta(hours=5, minutes=30))
    with open_store(get_settings()) as store:
        store.add(replace(RECORD, sent_at=datetime(2026, 11, 3, 19, 45, 0, 250, tzinfo=india)))
    assert raw_row(tmp_path, "SELECT received_at, sent_at, fetched_at FROM messages") == (
        "2026-11-03T14:15:05.000000+00:00",
        "2026-11-03T14:15:00.000250+00:00",
        "2026-11-11T09:00:00.000000+00:00",
    )


def test_email_text_is_cleared_24_hours_after_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T09:00:00+00:00",
        "2026-11-10T09:00:00.000001+00:00",
        "2026-11-11T08:59:59.999999+00:00",
        "2026-11-11T09:00:00+00:00",
        "2026-11-11T09:00:00.000001+00:00",
        "2026-11-11T09:00:00.000002+00:00",
    )
    later = replace(RECORD, message_id="18c2f0a1b2c3d4e6")
    with open_store(get_settings()) as store:
        store.add(RECORD)
        store.add(later)
        assert store.clear_expired_text() == 0
        assert store.clear_expired_text() == 1
        cleared = store.get("gmail", "18c2f0a1b2c3d4e5")
        kept = store.get("gmail", "18c2f0a1b2c3d4e6")
        assert store.clear_expired_text() == 1
        assert store.clear_expired_text() == 0
    assert cleared == StoredMessage(
        record=replace(RECORD, body_text="", authentication_results=()),
        fetched_at=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        text_cleared_at=datetime(2026, 11, 11, 9, 0, tzinfo=UTC),
    )
    assert kept == StoredMessage(
        record=later,
        fetched_at=datetime(2026, 11, 10, 9, 0, 0, 1, tzinfo=UTC),
        text_cleared_at=None,
    )


def test_a_cleared_message_is_still_a_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T09:00:00+00:00",
        "2026-11-11T10:00:00+00:00",
        "2026-11-11T10:05:00+00:00",
    )
    with open_store(get_settings()) as store:
        store.add(RECORD)
        assert store.clear_expired_text() == 1
        assert store.add(RECORD) is False
        found = store.get("gmail", "18c2f0a1b2c3d4e5")
    assert found is not None
    assert found.record.body_text == ""
    assert found.text_cleared_at == datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


def test_cleared_text_is_gone_from_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed_times(
        monkeypatch,
        "2026-11-10T09:00:00+00:00",
        "2026-11-10T09:00:00+00:00",
        "2026-11-11T09:00:00+00:00",
    )
    marked = replace(
        RECORD,
        body_text="ZQX-BODY-7 " * 20,
        authentication_results=("mx.example.test; ZQX-AUTH-7",),
    )
    with open_store(get_settings()) as store:
        store.add(marked)
        store.add(replace(marked, message_id="18c2f0a1b2c3d4e6"))
        assert store.clear_expired_text() == 2
    content = database(tmp_path).read_bytes()
    assert b"ZQX-BODY-7" not in content
    assert b"ZQX-AUTH-7" not in content
    assert b"Your November bill" in content
