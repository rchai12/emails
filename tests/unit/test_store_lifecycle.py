"""One connection per store: no area may define its own constructor; one due reader and writer."""

from datetime import date, time

import pytest

from mailroom.store import Due, Store, approvals, triage
from mailroom.store.base import StoreBase
from mailroom.store.posts import PostStore


@pytest.mark.parametrize("parent", [StoreBase, PostStore, Store])
def test_defining_a_store_constructor_is_refused_at_definition(parent: type) -> None:
    with pytest.raises(TypeError) as raised:

        class Extra(parent):  # type: ignore[misc, valid-type]
            def __init__(self) -> None:
                pass

    assert str(raised.value) == "a store area must not define __init__: Extra"

    class Plain(parent):  # type: ignore[misc, valid-type]
        def extra(self) -> int:
            return 1

    assert Plain.__init__ is StoreBase.__init__


def test_the_due_columns_round_trip_through_one_reader_and_writer() -> None:
    timed = Due(date=date(2026, 11, 20), time=time(17, 0))
    untimed = Due(date=date(2026, 11, 20), time=None)
    assert triage.due_columns(timed) == ("2026-11-20", "17:00")
    assert triage.due_columns(untimed) == ("2026-11-20", None)
    assert triage.due_columns(None) == (None, None)
    assert triage.read_due("2026-11-20", "17:00") == timed
    assert triage.read_due("2026-11-20", None) == untimed
    assert triage.read_due(None, None) is None
    assert triage.due_columns(Due(date=date(2026, 1, 2), time=time(9, 5, 30))) == (
        "2026-01-02",
        "09:05",
    )


def test_approvals_share_the_triage_due_reader_and_writer() -> None:
    assert approvals.read_due is triage.read_due
    assert approvals.due_columns is triage.due_columns
    assert not hasattr(approvals, "_read_due")
    assert not hasattr(approvals, "_due_columns")
    assert not hasattr(triage, "_read_due")
