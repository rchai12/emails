from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from mailroom.extractor import Deadline, Extraction, Rejected
from mailroom.record import Record
from mailroom.rules import Screening
from mailroom.store import Verdict
from mailroom.triage import rank, should_notify

UNTRUSTED = Screening(action="extract", trusted=False, verified=False, bulk=False)
NOT_A_TASK = Extraction(
    summary="A weekly newsletter about gardening.",
    actionable=False,
    urgent=False,
    title="",
    deadline=None,
    suspicious=False,
    suspicion_reason="",
    confidence="high",
)
FRIDAY = Deadline(date=date(2026, 11, 20), time=None, explicit=True, quote="by Friday")


# The notify decision


@pytest.mark.parametrize(
    ("screening", "result", "notify"),
    [
        (UNTRUSTED, NOT_A_TASK, False),
        (UNTRUSTED, replace(NOT_A_TASK, actionable=True, title="Reply to Sam"), True),
        (UNTRUSTED, replace(NOT_A_TASK, urgent=True), True),
        (UNTRUSTED, replace(NOT_A_TASK, deadline=FRIDAY), True),
        (UNTRUSTED, replace(NOT_A_TASK, confidence="medium"), True),
        (replace(UNTRUSTED, bulk=True), NOT_A_TASK, False),
        (replace(UNTRUSTED, bulk=True), replace(NOT_A_TASK, confidence="medium"), False),
        (replace(UNTRUSTED, bulk=True), replace(NOT_A_TASK, confidence="low"), True),
        (replace(UNTRUSTED, trusted=True, verified=True), NOT_A_TASK, True),
        (
            UNTRUSTED,
            replace(NOT_A_TASK, suspicious=True, suspicion_reason="Asks for a password"),
            False,
        ),
        (UNTRUSTED, Rejected("title"), True),
        (replace(UNTRUSTED, bulk=True), Rejected("timeout"), True),
        (replace(UNTRUSTED, action="drop"), None, False),
    ],
    ids=[
        "sure-not-a-task",
        "actionable",
        "urgent",
        "deadline",
        "medium-confidence",
        "bulk-sure-not-a-task",
        "bulk-medium-confidence",
        "bulk-low-confidence",
        "trusted",
        "suspicious-alone",
        "unreadable",
        "bulk-unreadable",
        "dropped",
    ],
)
def test_only_sure_non_tasks_and_dropped_mail_are_not_notified(
    screening: Screening, result: Extraction | Rejected | None, notify: bool
) -> None:
    assert should_notify(screening, result) is notify


# Ranking

TASK = replace(
    NOT_A_TASK,
    summary="Sam asks for a reply.",
    actionable=True,
    title="Reply to Sam",
    confidence="medium",
)
PLAIN = Verdict(
    outcome="extracted", trusted=False, verified=True, bulk=False, notify=True, extraction=TASK
)
RECORD = Record(
    provider="gmail",
    message_id="m0",
    thread_id="t0",
    received_at=datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m0",
    sender="sam@example.test",
    sender_name="Sam",
    subject="A question",
    sent_at=None,
    body_text="Can you reply?",
    list_unsubscribe=False,
    authentication_results=(),
)


def task(**changes: object) -> Verdict:
    return replace(PLAIN, extraction=replace(TASK, **changes))


def at(message_id: str, hour: int = 9, provider: str = "gmail") -> Record:
    return replace(
        RECORD,
        provider=provider,
        message_id=message_id,
        received_at=datetime(2026, 11, 12, hour, 0, tzinfo=UTC),
    )


def deadline(day: int, when: time | None = None) -> Deadline:
    return Deadline(date=date(2026, 11, day), time=when, explicit=True, quote="due then")


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ((at("a"), replace(PLAIN, trusted=True)), (at("b", 10), task(urgent=True))),
        (
            (at("a"), PLAIN),
            (at("b", 10), task(urgent=True, suspicious=True, suspicion_reason="Fake invoice")),
        ),
        ((at("a"), task(urgent=True)), (at("b", 10), task(deadline=deadline(13)))),
        ((at("a"), task(deadline=deadline(25))), (at("b", 10), task(confidence="high"))),
        ((at("a"), task(deadline=deadline(13))), (at("b", 10), task(deadline=deadline(14)))),
        (
            (at("a"), task(deadline=deadline(13, time(23, 0)))),
            (at("b", 10), task(deadline=deadline(13))),
        ),
        (
            (at("a"), task(deadline=deadline(13, time(9, 0)))),
            (at("b", 10), task(deadline=deadline(13, time(17, 0)))),
        ),
        ((at("a"), task(confidence="high")), (at("b", 10), PLAIN)),
        ((at("a"), PLAIN), (at("b", 10), task(confidence="low"))),
        ((at("b", 10), PLAIN), (at("a"), PLAIN)),
        ((at("a"), PLAIN), (at("b"), PLAIN)),
        ((at("b"), PLAIN), (at("a", provider="yahoo"), PLAIN)),
    ],
    ids=[
        "trusted-before-urgent",
        "suspicious-last",
        "urgent-before-deadline",
        "deadline-before-confidence",
        "sooner-date",
        "a-time-before-the-end-of-the-day",
        "earlier-time",
        "high-before-medium",
        "medium-before-low",
        "newest-first",
        "then-message-id",
        "then-provider",
    ],
)
def test_two_emails_rank_in_the_documented_order(
    first: tuple[Record, Verdict], second: tuple[Record, Verdict]
) -> None:
    assert rank([second, first]) == [first, second]
    assert rank([first, second]) == [first, second]


UNREADABLE = Verdict(
    outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="title"
)
CLEARED = replace(PLAIN, extraction=None)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ((at("a"), task(confidence="low")), (at("b", 8), UNREADABLE)),
        ((at("b", 10), UNREADABLE), (at("a"), task(confidence="low"))),
        ((at("a"), UNREADABLE), (at("b", 10), task(suspicious=True, suspicion_reason="Phishing"))),
        ((at("a"), replace(UNREADABLE, trusted=True)), (at("b", 10), task(urgent=True))),
        ((at("a"), task(confidence="low")), (at("b", 8), CLEARED)),
    ],
    ids=[
        "known-low-before-older-unreadable",
        "newer-unreadable-before-known-low",
        "unreadable-before-suspicious",
        "trusted-unreadable-first",
        "cleared-is-unknown",
    ],
)
def test_an_email_with_no_extraction_ranks_as_if_nothing_is_known(
    first: tuple[Record, Verdict], second: tuple[Record, Verdict]
) -> None:
    assert rank([second, first]) == [first, second]


def test_a_mixed_list_is_ranked_and_the_input_is_left_alone() -> None:
    entries = [
        (at("plain", 9), PLAIN),
        (at("phish", 11), task(urgent=True, suspicious=True, suspicion_reason="Fake invoice")),
        (at("unreadable", 12), UNREADABLE),
        (at("trusted", 7), replace(PLAIN, trusted=True)),
        (at("dated", 8), task(deadline=deadline(20))),
        (at("urgent", 6), task(urgent=True)),
        (at("sure", 10), task(confidence="high")),
    ]
    before = list(entries)
    ranked = rank(entries)
    assert [record.message_id for record, _ in ranked] == [
        "trusted",
        "urgent",
        "dated",
        "sure",
        "plain",
        "unreadable",
        "phish",
    ]
    assert entries == before
