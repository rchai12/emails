import re
from datetime import UTC, datetime, timedelta

import pytest

from mailroom import clock, ids
from tests.support import fixed_ids, fixed_times


def test_now_is_an_aware_utc_moment() -> None:
    moment = clock.now()
    assert moment.tzinfo is UTC
    assert moment.utcoffset() == timedelta(0)


def test_now_is_the_current_moment() -> None:
    before = datetime.now(UTC)
    moment = clock.now()
    after = datetime.now(UTC)
    assert before <= moment <= after


def test_a_new_id_is_32_lowercase_hex_characters() -> None:
    assert re.fullmatch(r"[0-9a-f]{32}", ids.new_id())


def test_new_ids_differ() -> None:
    assert len({ids.new_id() for _ in range(100)}) == 100


def test_fixed_times_and_ids_replace_the_module_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_times(monkeypatch, "2026-11-11T09:30:00+00:00")
    fixed_ids(monkeypatch, "id-1")
    assert clock.now() == datetime(2026, 11, 11, 9, 30, tzinfo=UTC)
    assert ids.new_id() == "id-1"
