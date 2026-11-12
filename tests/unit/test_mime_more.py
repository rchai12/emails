import inspect
from datetime import UTC, datetime
from email.message import EmailMessage

import pytest

from mailroom.mime import clean_line, clean_text, html_to_text, parse_message
from mailroom.record import Envelope

ENVELOPE = Envelope(
    provider="gmail",
    message_id="18c2f0a1b2c3d4e5",
    thread_id="18c2f0a1b2c3d4e0",
    received_at=datetime(2026, 11, 3, 14, 15, 5, tzinfo=UTC),
    link="https://mail.google.com/mail/u/0/#all/18c2f0a1b2c3d4e5",
)

RAW = (
    b"From: Ann <ann@example.test>\r\n"
    b"Subject: Hello\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Hello there\r\n"
)


def test_a_surrogate_run_before_more_text_is_decoded() -> None:
    assert clean_line("A\udcc3\udca9B", 100) == "AéB"
    assert clean_text("A\udcc3\udca9B", 100) == "AéB"


def test_a_stray_script_end_does_not_drop_the_following_text() -> None:
    assert html_to_text("<p>Hi</p></script><p>there</p>") == "Hi\n\nthere"


def test_an_unreadable_subject_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    original = EmailMessage.__getitem__

    def getitem(self: EmailMessage, name: str) -> object:
        if name == "Subject":
            raise RuntimeError("subject")
        return original(self, name)

    monkeypatch.setattr(EmailMessage, "__getitem__", getitem)
    record = parse_message(RAW, ENVELOPE)
    assert record.subject == ""
    assert record.sender == "ann@example.test"
    assert record.body_text == "Hello there"


def test_unreadable_authentication_results_count_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = EmailMessage.get_all

    def get_all(self: EmailMessage, name: str, failobj: object = None) -> object:
        if name == "Authentication-Results":
            raise RuntimeError("auth")
        return original(self, name, failobj)

    monkeypatch.setattr(EmailMessage, "get_all", get_all)
    record = parse_message(RAW, ENVELOPE)
    assert record.authentication_results == ()
    assert record.subject == "Hello"


def test_one_unreadable_authentication_result_drops_the_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Bad:
        def __str__(self) -> str:
            raise RuntimeError("value")

    original = EmailMessage.get_all

    def get_all(self: EmailMessage, name: str, failobj: object = None) -> object:
        if name == "Authentication-Results":
            return [Bad(), "mx.example.test; none"]
        return original(self, name, failobj)

    monkeypatch.setattr(EmailMessage, "get_all", get_all)
    assert parse_message(RAW, ENVELOPE).authentication_results == ()


def test_a_body_whose_payload_cannot_be_read_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_content(self: EmailMessage) -> str:
        raise LookupError("charset")

    def get_payload(self: EmailMessage, decode: bool = False) -> bytes:
        raise RuntimeError("payload")

    monkeypatch.setattr(EmailMessage, "get_content", get_content)
    monkeypatch.setattr(EmailMessage, "get_payload", get_payload)
    record = parse_message(RAW, ENVELOPE)
    assert record.body_text == ""
    assert record.subject == "Hello"


def test_a_body_payload_that_is_not_bytes_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_content(self: EmailMessage) -> str:
        raise LookupError("charset")

    def get_payload(self: EmailMessage, decode: bool = False) -> None:
        return None

    monkeypatch.setattr(EmailMessage, "get_content", get_content)
    monkeypatch.setattr(EmailMessage, "get_payload", get_payload)
    assert parse_message(RAW, ENVELOPE).body_text == ""


def test_a_body_that_is_not_text_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_content(self: EmailMessage) -> bytes:
        return b"not text"

    monkeypatch.setattr(EmailMessage, "get_content", get_content)
    assert parse_message(RAW, ENVELOPE).body_text == ""


def test_a_body_whose_type_cannot_be_read_is_still_plain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = EmailMessage.get_content_type

    def get_content_type(self: EmailMessage) -> str:
        if any(frame.function == "_decode_part" for frame in inspect.stack()):
            raise RuntimeError("type")
        return original(self)

    monkeypatch.setattr(EmailMessage, "get_content_type", get_content_type)
    assert parse_message(RAW, ENVELOPE).body_text == "Hello there"


def test_a_body_that_cannot_be_chosen_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_body(self: EmailMessage, preferencelist: tuple[str, ...] = ()) -> None:
        raise RuntimeError("body")

    monkeypatch.setattr(EmailMessage, "get_body", get_body)
    record = parse_message(RAW, ENVELOPE)
    assert record.body_text == ""
    assert record.subject == "Hello"
