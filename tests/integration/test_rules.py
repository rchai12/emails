from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from mailroom.config import get_settings
from mailroom.record import Record
from mailroom.rules import Screening, screen
from mailroom.store import Store, open_store

BASE = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing",
    subject="Your bill",
    sent_at=None,
    body_text="",
    list_unsubscribe=False,
    authentication_results=(),
)
PASSING = ("mx.google.com; dmarc=pass header.from=example.test",)
FAILING = ("mx.google.com; dmarc=fail header.from=example.test",)


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


@pytest.mark.parametrize("results", [PASSING, FAILING], ids=["verified", "forged"])
def test_mail_from_a_muted_sender_is_dropped(store: Store, results: tuple[str, ...]) -> None:
    store.set_sender_status("billing@example.test", "muted")
    record = replace(BASE, authentication_results=results)
    assert screen(record, store) == Screening(
        action="drop", trusted=False, verified=results == PASSING, bulk=False
    )


def test_a_verified_trusted_sender_is_trusted(store: Store) -> None:
    store.set_sender_status("billing@example.test", "trusted")
    record = replace(BASE, authentication_results=PASSING)
    assert screen(record, store) == Screening(
        action="extract", trusted=True, verified=True, bulk=False
    )


def test_a_trusted_address_that_fails_the_checks_is_not_trusted(store: Store) -> None:
    store.set_sender_status("billing@example.test", "trusted")
    record = replace(BASE, authentication_results=FAILING)
    assert screen(record, store) == Screening(
        action="extract", trusted=False, verified=False, bulk=False
    )


def test_bulk_mail_is_marked_but_never_dropped(store: Store) -> None:
    record = replace(BASE, list_unsubscribe=True)
    assert screen(record, store) == Screening(
        action="extract", trusted=False, verified=False, bulk=True
    )


def test_mail_without_a_sender_is_screened_without_a_lookup(store: Store) -> None:
    record = replace(BASE, sender="", authentication_results=PASSING)
    assert screen(record, store) == Screening(
        action="extract", trusted=False, verified=False, bulk=False
    )
