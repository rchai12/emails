from dataclasses import replace
from datetime import UTC, datetime

from mailroom.record import Record
from mailroom.sender_auth import AuthResult, parse_results, verified

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


def test_a_part_without_a_method_or_a_result_is_skipped() -> None:
    assert parse_results(
        "mx.google.com; dmarc=; =pass; spf pass; ; dkim=pass header.d=Example.TEST note"
    ) == (
        "mx.google.com",
        (AuthResult("dkim", "pass", (("header.d", "Example.TEST"),)),),
    )
    assert parse_results("") == ("", ())


def test_a_bare_mailfrom_domain_counts_and_header_d_wins() -> None:
    both = (
        "mx.google.com; dkim=pass header.i=@example.test header.d=evil.test; "
        "spf=pass smtp.mailfrom=example.test"
    )
    assert verified(replace(BASE, authentication_results=(both,))) is False
    bare = (
        "mx.google.com; dkim=pass header.i=@badexample.test header.d=mail.example.test; "
        "spf=pass smtp.mailfrom=mail.example.test"
    )
    assert verified(replace(BASE, authentication_results=(bare,))) is True


def test_dkim_or_spf_alone_does_not_verify() -> None:
    dkim_only = (
        "mx.google.com; dkim=pass header.d=example.test; spf=fail smtp.mailfrom=example.test"
    )
    no_domain = (
        "mx.google.com; dkim=pass header.i=example.test; spf=pass smtp.mailfrom=example.test"
    )
    missing = "mx.google.com; dkim=pass; spf=pass smtp.mailfrom=example.test"
    for header in (dkim_only, no_domain, missing):
        assert verified(replace(BASE, authentication_results=(header,))) is False
