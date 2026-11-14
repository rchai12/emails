"""Outlook mail is verified from Microsoft's own header: the first one, with no server name."""

from dataclasses import replace

import pytest

from mailroom.sender_auth import verified
from tests.unit.test_sender_auth import BASE, GOOD

OUTLOOK = replace(
    BASE,
    provider="outlook",
    message_id="live/AAMk1=",
    thread_id="live/conversation-1",
    link="https://outlook.live.com/owa/?ItemID=AAMk1=",
)
SPF = "spf=pass (sender IP is 192.0.2.1) smtp.mailfrom=example.test"
DKIM = "dkim=pass (signature was verified) header.d=example.test"
DMARC = "dmarc=pass action=none header.from=example.test"
COMPAUTH = "compauth=pass reason=100"


def header(*parts: str) -> str:
    return ";".join(parts)


@pytest.mark.parametrize(
    ("first", "expected"),
    [
        (header(SPF, DKIM, DMARC, COMPAUTH), True),
        (header(SPF, DKIM, "dmarc=none action=none header.from=example.test", COMPAUTH), True),
        (
            header(
                "spf=fail (sender IP is 192.0.2.9) smtp.mailfrom=example.test",
                DKIM,
                DMARC,
                COMPAUTH,
            ),
            True,
        ),
        (
            header(
                SPF,
                "dkim=none (message not signed) header.d=none",
                "dmarc=none action=none header.from=example.test",
                "compauth=fail reason=001",
            ),
            False,
        ),
        (header(SPF, DKIM, DMARC), False),
        (header("mx.microsoft.com", SPF, DKIM, DMARC, COMPAUTH), False),
        (
            header(SPF, DKIM, "dmarc=pass action=none header.from=other.example.test", COMPAUTH),
            False,
        ),
        (
            header(
                SPF,
                "dkim=pass (signature was verified) header.d=other.example.test",
                "dmarc=none action=none header.from=example.test",
                COMPAUTH,
            ),
            False,
        ),
        (GOOD, False),
        ("", False),
    ],
    ids=[
        "dmarc-pass",
        "spf-and-dkim",
        "dmarc-despite-spf-fail",
        "nothing-passes",
        "no-compauth",
        "server-name",
        "dmarc-other-domain",
        "dkim-other-domain",
        "gmail-header",
        "empty",
    ],
)
def test_microsofts_first_header_decides(first: str, expected: bool) -> None:
    assert verified(replace(OUTLOOK, authentication_results=(first,))) is expected


def test_only_the_first_header_counts() -> None:
    forged = header(SPF, DKIM, DMARC, COMPAUTH)
    weak = header(
        SPF,
        "dkim=none header.d=none",
        "dmarc=fail action=none header.from=example.test",
        "compauth=fail reason=000",
    )
    assert verified(replace(OUTLOOK, authentication_results=(weak, forged))) is False
    assert verified(replace(OUTLOOK, authentication_results=(forged, weak))) is True


def test_a_microsoft_header_on_gmail_mail_is_not_trusted() -> None:
    gmail = replace(BASE, authentication_results=(header(SPF, DKIM, DMARC, COMPAUTH),))
    assert verified(gmail) is False
    assert verified(replace(BASE, authentication_results=(GOOD,))) is True


def test_outlook_mail_without_a_sender_domain_is_not_verified() -> None:
    record = replace(
        OUTLOOK, sender="", authentication_results=(header(SPF, DKIM, DMARC, COMPAUTH),)
    )
    assert verified(record) is False
