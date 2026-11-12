from datetime import UTC, datetime, timedelta

import pytest

from mailroom.mime import clean_line, clean_text, html_to_text, parse_message
from mailroom.record import Envelope, Record

ENVELOPE = Envelope(
    provider="gmail",
    message_id="18c2f0a1b2c3d4e5",
    thread_id="18c2f0a1b2c3d4e0",
    received_at=datetime(2026, 11, 3, 14, 15, 5, tzinfo=UTC),
    link="https://mail.google.com/mail/u/0/#all/18c2f0a1b2c3d4e5",
)

AUTH_BLOCK = (
    b"Authentication-Results: mx.google.com;\r\n"
    b"       dkim=pass header.i=@billing.example.test;\r\n"
    b"       spf=pass smtp.mailfrom=billing.example.test;\r\n"
    b"       dmarc=pass header.from=billing.example.test\r\n"
)
HEAD = AUTH_BLOCK + (
    b"From: Billing Team <Billing@Billing.Example.TEST>\r\n"
    b"To: owner@example.test\r\n"
    b"Subject: Your November bill\r\n"
    b"Date: Tue, 03 Nov 2026 09:15:00 -0500\r\n"
    b"Message-ID: <bill-1@billing.example.test>\r\n"
    b"List-Unsubscribe: <mailto:unsubscribe@billing.example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
)
BASE = HEAD + (
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Hello,\r\n\r\nYour bill of $42.00 is due on November 20.\r\n"
)


def variant(old: bytes, new: bytes) -> bytes:
    """BASE with exactly one occurrence of `old` replaced by `new`."""
    assert BASE.count(old) == 1
    return BASE.replace(old, new)


# clean_line and clean_text


def test_clean_line_collapses_whitespace_and_drops_invisible_characters() -> None:
    assert clean_line("  Pay\tthe\r\n  bill\x00 now​!‮ ", 100) == "Pay the bill now!"


def test_clean_line_cuts_to_the_limit_then_trims() -> None:
    assert clean_line("abcde fghij", 6) == "abcde"
    assert clean_line("abcdefgh", 3) == "abc"
    assert clean_line(" \t ", 10) == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Jos\udcc3\udca9", "José"),
        ("caf\udce9", "caf�"),
        ("\ud800x", "�x"),
    ],
    ids=["escapes", "bad-byte", "lone-surrogate"],
)
def test_undecodable_bytes_become_text(text: str, expected: str) -> None:
    assert clean_line(text, 100) == expected
    assert clean_text(text, 100) == expected


def test_clean_text_normalizes_lines() -> None:
    text = "\r\n  \r\nHello  \r\nWorld\x07\tnow\t\r\rBye​\n\n\n\n  indented\n\n"
    assert clean_text(text, 1000) == "Hello\nWorld\tnow\n\nBye\n\n  indented"


def test_clean_text_cuts_to_the_limit_then_trims() -> None:
    assert clean_text("abc\ndef", 4) == "abc"
    assert clean_text("abc\ndef", 5) == "abc\nd"


# html_to_text


def test_html_blocks_links_and_scripts() -> None:
    html = (
        "<html><head><style>p { color: red }</style></head><body>"
        "<p>Your bill&nbsp;is <b>due</b>.</p>"
        '<div>Pay at <a href="https://pay.example.test/bill?id=7&amp;x=1">the portal</a></div>'
        "<script>track()</script>"
        "<ul><li>One</li><li>Two</li></ul>"
        "Line<br>break<br/>done</body></html>"
    )
    assert html_to_text(html) == (
        "Your bill is due.\n\n"
        "Pay at the portal (https://pay.example.test/bill?id=7&x=1)\n\n"
        "One\nTwo\n\n"
        "Line\nbreak\ndone"
    )


def test_html_tables_and_link_schemes() -> None:
    html = (
        "<table><tr><td>Amount</td><td>$42.00</td></tr>\n  "
        "<tr><td>Due</td><td>Nov 20</td></tr></table>"
        '<p><a href="https://x.example.test/a">https://x.example.test/a</a>'
        ' and <a href="javascript:evil()">click</a>'
        ' and <a href="mailto:help@x.example.test">email us</a>'
        ' and <a href=" HTTPS://X.example.test/B ">B</a></p>'
    )
    assert html_to_text(html) == (
        "Amount $42.00\n"
        "Due Nov 20\n\n"
        "https://x.example.test/a and click and email us (mailto:help@x.example.test)"
        " and B (HTTPS://X.example.test/B)"
    )


def test_html_skips_script_and_style_even_unclosed() -> None:
    html = "<P>Hi</P><STYLE>p {}</STYLE><SCRIPT>track()</SCRIPT><p>there</p><script>never()"
    assert html_to_text(html) == "Hi\n\nthere"


def test_html_text_is_cut_to_the_body_limit() -> None:
    assert html_to_text("<p>" + "A" * 150_000 + "</p>") == "A" * 100_000


# parse_message


def test_a_plain_message_becomes_a_record() -> None:
    record = parse_message(BASE, ENVELOPE)
    assert record == Record(
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
            "mx.google.com; dkim=pass header.i=@billing.example.test;"
            " spf=pass smtp.mailfrom=billing.example.test;"
            " dmarc=pass header.from=billing.example.test",
        ),
    )
    assert record.sent_at is not None
    assert record.sent_at.utcoffset() == timedelta(0)


FROM = b"From: Billing Team <Billing@Billing.Example.TEST>"


@pytest.mark.parametrize(
    ("new", "sender", "sender_name"),
    [
        (b'From: "Lee, Ann" <ann@example.test>', "ann@example.test", "Lee, Ann"),
        (
            b"From: =?utf-8?q?Jos=C3=A9_P=C3=A9rez?= <jose@example.test>",
            "jose@example.test",
            "José Pérez",
        ),
        ("From: José <jose@example.test>".encode(), "jose@example.test", "José"),
        (
            b'From: "billing@bank.example.test" <evil@phish.example.test>',
            "evil@phish.example.test",
            "billing@bank.example.test",
        ),
        (b"From: a@example.test, b@example.test", "a@example.test", ""),
        (b"From: undisclosed-recipients:;", "", ""),
        (b"From: <<>>", "", ""),
        (b"From: justaname", "", ""),
        (b"From: <" + b"a" * 250 + b"@example.test>", "", ""),
        (b"From: " + b"N" * 150 + b" <n@example.test>", "n@example.test", "N" * 100),
    ],
    ids=[
        "quoted-comma",
        "encoded-word",
        "raw-utf8",
        "address-as-name",
        "two-addresses",
        "group",
        "empty-angle",
        "no-at",
        "long-address",
        "long-name",
    ],
)
def test_the_sender_comes_from_the_first_from_address(
    new: bytes, sender: str, sender_name: str
) -> None:
    record = parse_message(variant(FROM, new), ENVELOPE)
    assert (record.sender, record.sender_name) == (sender, sender_name)


def test_a_missing_from_header_leaves_the_sender_empty() -> None:
    record = parse_message(variant(FROM + b"\r\n", b""), ENVELOPE)
    assert (record.sender, record.sender_name) == ("", "")


SUBJECT = b"Subject: Your November bill\r\n"


@pytest.mark.parametrize(
    ("new", "subject"),
    [
        (b"Subject: =?utf-8?b?w6lsw6h2ZQ==?=\r\n", "élève"),
        (b"Subject: Pay\r\n\tnow\r\n", "Pay now"),
        (b"Subject: " + b"S" * 250 + b"\r\n", "S" * 200),
        ("Subject: inv‮oice\r\n".encode(), "invoice"),
        (b"", ""),
    ],
    ids=["encoded-word", "folded", "long", "bidi", "missing"],
)
def test_the_subject_is_one_clean_line(new: bytes, subject: str) -> None:
    assert parse_message(variant(SUBJECT, new), ENVELOPE).subject == subject


DATE = b"Date: Tue, 03 Nov 2026 09:15:00 -0500\r\n"


@pytest.mark.parametrize(
    ("new", "sent_at"),
    [
        (b"Date: Tue, 03 Nov 2026 09:15:00 -0000\r\n", datetime(2026, 11, 3, 9, 15, tzinfo=UTC)),
        (b"Date: Tue, 03 Nov 2026 23:30:00 +0530\r\n", datetime(2026, 11, 3, 18, 0, tzinfo=UTC)),
        (b"Date: garbage\r\n", None),
        (b"", None),
    ],
    ids=["minus-zero", "plus-0530", "garbage", "missing"],
)
def test_the_sent_time_is_utc_or_none(new: bytes, sent_at: datetime | None) -> None:
    record = parse_message(variant(DATE, new), ENVELOPE)
    assert record.sent_at == sent_at
    if sent_at is not None:
        assert record.sent_at is not None
        assert record.sent_at.utcoffset() == timedelta(0)


UNSUBSCRIBE = b"List-Unsubscribe: <mailto:unsubscribe@billing.example.test>\r\n"


@pytest.mark.parametrize("new", [b"", b"List-Unsubscribe:  \r\n"], ids=["missing", "empty"])
def test_list_unsubscribe_needs_a_value(new: bytes) -> None:
    assert parse_message(variant(UNSUBSCRIBE, new), ENVELOPE).list_unsubscribe is False


@pytest.mark.parametrize(
    ("new", "results"),
    [
        (b"", ()),
        (b"Authentication-Results: \r\n", ()),
        (
            b"".join(b"Authentication-Results: mx%d.example.test; none\r\n" % i for i in range(12)),
            tuple(f"mx{i}.example.test; none" for i in range(10)),
        ),
        (
            b"Authentication-Results: mx.example.test; " + b"x" * 2500 + b"\r\n",
            ("mx.example.test; " + "x" * 1983,),
        ),
    ],
    ids=["missing", "empty", "twelve", "long"],
)
def test_authentication_results_are_kept_in_order_with_limits(
    new: bytes, results: tuple[str, ...]
) -> None:
    assert parse_message(variant(AUTH_BLOCK, new), ENVELOPE).authentication_results == results


ALTERNATIVE = (
    b"Content-Type: multipart/alternative; boundary=BB\r\n\r\n"
    b"--BB\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>HTML part</p>\r\n"
    b"--BB\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nPlain part\r\n"
    b"--BB--\r\n"
)
HTML_ONLY = (
    b"Content-Type: text/html; charset=utf-8\r\n\r\n"
    b'<p>Your bill is <b>due</b>.</p><p>Pay <a href="https://pay.example.test/7">here</a></p>\r\n'
)
ATTACHED_TEXT = (
    b"Content-Type: multipart/mixed; boundary=BB\r\n\r\n"
    b"--BB\r\nContent-Type: text/plain; charset=utf-8\r\n"
    b'Content-Disposition: attachment; filename="notes.txt"\r\n\r\nAttached notes\r\n'
    b"--BB\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>HTML body</p>\r\n"
    b"--BB--\r\n"
)
ONLY_ATTACHMENT = (
    b"Content-Type: multipart/mixed; boundary=BB\r\n\r\n"
    b"--BB\r\nContent-Type: application/pdf\r\n"
    b'Content-Disposition: attachment; filename="bill.pdf"\r\n\r\n%PDF-1.7\r\n'
    b"--BB--\r\n"
)
UNKNOWN_CHARSET = b"Content-Type: text/plain; charset=x-unknown\r\n\r\ncaf\xc3\xa9 \xe9\r\n"
LATIN_1 = (
    b"Content-Type: text/plain; charset=iso-8859-1\r\n"
    b"Content-Transfer-Encoding: quoted-printable\r\n\r\n"
    b"Caf=E9 au lait=\r\n today\r\n"
)
BASE64 = (
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Transfer-Encoding: base64\r\n\r\n"
    b"RHVlIEZyaWRheSDinJMK\r\n"
)
LONG = b"Content-Type: text/plain; charset=utf-8\r\n\r\n" + b"A" * 150_000 + b"\r\n"


@pytest.mark.parametrize(
    ("rest", "body"),
    [
        (ALTERNATIVE, "Plain part"),
        (HTML_ONLY, "Your bill is due.\n\nPay here (https://pay.example.test/7)"),
        (ATTACHED_TEXT, "HTML body"),
        (ONLY_ATTACHMENT, ""),
        (UNKNOWN_CHARSET, "café �"),
        (LATIN_1, "Café au lait today"),
        (BASE64, "Due Friday ✓"),
        (LONG, "A" * 100_000),
    ],
    ids=[
        "alternative",
        "html-only",
        "attached-text",
        "only-attachment",
        "unknown-charset",
        "latin-1",
        "base64",
        "long",
    ],
)
def test_the_body_is_the_plain_part_or_the_html_part_as_text(rest: bytes, body: str) -> None:
    assert parse_message(HEAD + rest, ENVELOPE).body_text == body


def test_a_header_the_email_package_cannot_read_counts_as_missing() -> None:
    record = parse_message(variant(FROM, b"From: :;\xe6"), ENVELOPE)
    assert (record.sender, record.sender_name) == ("", "")
    assert record.subject == "Your November bill"


def test_a_body_that_cannot_be_decoded_falls_back_to_its_bytes() -> None:
    raw = HEAD + b"Content-Type: charset=\x00\r\n\r\nHello there\r\n"
    assert parse_message(raw, ENVELOPE).body_text == "Hello there"


def test_a_message_the_email_package_cannot_parse_keeps_its_text() -> None:
    raw = HEAD + b"Content-Type: ;\xd9*\r\n\r\nHello there\r\n"
    assert parse_message(raw, ENVELOPE) == Record(
        provider="gmail",
        message_id="18c2f0a1b2c3d4e5",
        thread_id="18c2f0a1b2c3d4e0",
        received_at=datetime(2026, 11, 3, 14, 15, 5, tzinfo=UTC),
        link="https://mail.google.com/mail/u/0/#all/18c2f0a1b2c3d4e5",
        sender="",
        sender_name="",
        subject="",
        sent_at=None,
        body_text=(
            "Authentication-Results: mx.google.com;\n"
            "       dkim=pass header.i=@billing.example.test;\n"
            "       spf=pass smtp.mailfrom=billing.example.test;\n"
            "       dmarc=pass header.from=billing.example.test\n"
            "From: Billing Team <Billing@Billing.Example.TEST>\n"
            "To: owner@example.test\n"
            "Subject: Your November bill\n"
            "Date: Tue, 03 Nov 2026 09:15:00 -0500\n"
            "Message-ID: <bill-1@billing.example.test>\n"
            "List-Unsubscribe: <mailto:unsubscribe@billing.example.test>\n"
            "MIME-Version: 1.0\n"
            "Content-Type: ;�*\n"
            "\n"
            "Hello there"
        ),
        list_unsubscribe=False,
        authentication_results=(),
    )
