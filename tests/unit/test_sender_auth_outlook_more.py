"""A Microsoft header that cannot be read does not verify the sender."""

from dataclasses import replace

from mailroom.sender_auth import verified
from tests.unit.test_sender_auth_outlook import COMPAUTH, DKIM, DMARC, OUTLOOK, SPF


def test_an_unclosed_comment_is_not_verified() -> None:
    header = f"{SPF}; {DKIM}; {DMARC}; {COMPAUTH} (cut off"
    assert verified(replace(OUTLOOK, authentication_results=(header,))) is False
