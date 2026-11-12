from dataclasses import replace
from datetime import UTC, datetime

import pytest

from mailroom.record import Record
from mailroom.sender_auth import AUTHSERV_IDS, AuthResult, parse_results, verified

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
GOOD = (
    "mx.google.com; dkim=pass header.i=@example.test header.s=s1 header.b=abc; "
    "spf=pass (google.com: domain of bounce@mail.example.test designates 192.0.2.1 as permitted "
    "sender) smtp.mailfrom=bounce@mail.example.test; "
    "dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from=example.test"
)


def test_gmail_s_results_are_the_only_ones_known() -> None:
    assert AUTHSERV_IDS == {"gmail": "mx.google.com"}


def test_a_gmail_header_is_parsed_into_its_results() -> None:
    assert parse_results(GOOD) == (
        "mx.google.com",
        (
            AuthResult(
                "dkim",
                "pass",
                (("header.i", "@example.test"), ("header.s", "s1"), ("header.b", "abc")),
            ),
            AuthResult("spf", "pass", (("smtp.mailfrom", "bounce@mail.example.test"),)),
            AuthResult("dmarc", "pass", (("header.from", "example.test"),)),
        ),
    )


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (
            "MX.Google.COM 1; DKIM=Pass Header.D=Example.TEST",
            ("mx.google.com", (AuthResult("dkim", "pass", (("header.d", "Example.TEST"),)),)),
        ),
        ("mx.google.com; none", ("mx.google.com", ())),
        (
            "mx.google.com; spf=fail (a (dmarc=pass header.from=example.test) b) "
            "smtp.mailfrom=x@evil.test",
            ("mx.google.com", (AuthResult("spf", "fail", (("smtp.mailfrom", "x@evil.test"),)),)),
        ),
        ("mx.google.com; dmarc=pass (open header.from=example.test", ("", ())),
        ("mx.google.com; dmarc=pass) header.from=example.test", ("", ())),
    ],
    ids=["case-and-version", "none", "nested-comment", "unclosed-comment", "stray-close"],
)
def test_comments_case_and_broken_headers(header: str, expected: tuple) -> None:
    assert parse_results(header) == expected


@pytest.mark.parametrize(
    ("headers", "changes", "expected"),
    [
        ([GOOD], {}, True),
        (
            [
                "mx.google.com; dkim=pass header.i=@example.test; "
                "spf=pass smtp.mailfrom=bounce@mail.example.test; dmarc=fail "
                "header.from=example.test"
            ],
            {},
            True,
        ),
        (
            [
                "mx.google.com; dkim=pass header.d=mail.example.test; spf=pass "
                "smtp.mailfrom=example.test"
            ],
            {},
            True,
        ),
        (
            [
                "mx.google.com; dkim=fail header.i=@example.test; spf=pass "
                "smtp.mailfrom=example.test"
            ],
            {},
            False,
        ),
        (
            ["mx.google.com; dkim=pass header.i=@other.test; spf=pass smtp.mailfrom=example.test"],
            {},
            False,
        ),
        (
            [
                "mx.google.com; dkim=pass header.i=@badexample.test; "
                "spf=pass smtp.mailfrom=x@badexample.test; dmarc=pass "
                "header.from=example.test.evil.test"
            ],
            {},
            False,
        ),
        (
            [
                "mx.google.com; dmarc=fail header.from=example.test",
                "mx.google.com; dmarc=pass header.from=example.test",
            ],
            {},
            False,
        ),
        (["mx.evil.test; dmarc=pass header.from=example.test"], {}, False),
        (
            [
                "mx.google.com; dmarc=fail (dmarc=pass header.from=example.test) "
                "header.from=example.test"
            ],
            {},
            False,
        ),
        ([GOOD], {"provider": "outlook"}, False),
        ([GOOD], {"sender": ""}, False),
        ([], {}, False),
    ],
    ids=[
        "dmarc",
        "spf-and-dkim",
        "dkim-header-d",
        "spf-only",
        "dkim-other-domain",
        "look-alike",
        "forged-second-header",
        "other-server",
        "pass-in-a-comment",
        "unknown-provider",
        "no-sender",
        "no-header",
    ],
)
def test_a_sender_is_verified_only_by_its_provider_s_own_checks(
    headers: list[str], changes: dict, expected: bool
) -> None:
    record = replace(BASE, authentication_results=tuple(headers), **changes)
    assert verified(record) is expected
