import re
import unicodedata
from datetime import UTC, datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from mailroom.record import Envelope, Record

SUBJECT_LIMIT = 200
NAME_LIMIT = 100
ADDRESS_LIMIT = 254
HEADER_LIMIT = 2000
AUTH_RESULTS_LIMIT = 10
BODY_LIMIT = 100_000

_ADDRESS = re.compile(r"[^@\s<>]+@[^@\s<>]+")
_LINE_TAGS = frozenset(
    {
        "br",
        "div",
        "li",
        "tr",
        "dt",
        "dd",
        "header",
        "footer",
        "section",
        "article",
        "aside",
        "address",
        "pre",
        "hr",
    }
)
_PARAGRAPH_TAGS = frozenset(
    {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl", "table", "blockquote"}
)
_LINK_SCHEMES = ("http://", "https://", "mailto:")


def _repair_surrogates(text: str) -> str:
    parts: list[str] = []
    pending = bytearray()
    for character in text:
        code = ord(character)
        if 0xDC80 <= code <= 0xDCFF:
            pending.append(code - 0xDC00)
            continue
        if pending:
            parts.append(bytes(pending).decode("utf-8", errors="replace"))
            pending.clear()
        if 0xD800 <= code <= 0xDFFF:
            parts.append("\ufffd")
        else:
            parts.append(character)
    if pending:
        parts.append(bytes(pending).decode("utf-8", errors="replace"))
    return "".join(parts)


def _invisible(character: str) -> bool:
    return unicodedata.category(character) in ("Cc", "Cf")


def _kept_on_line(character: str) -> bool:
    return not (_invisible(character) and not character.isspace())


def clean_line(text: str, limit: int) -> str:
    text = _repair_surrogates(text)
    text = "".join(character for character in text if _kept_on_line(character))
    return " ".join(text.split())[:limit].rstrip()


def _kept_in_body(character: str) -> bool:
    return character in "\n\t" or not _invisible(character)


def clean_text(text: str, limit: int) -> str:
    text = _repair_surrogates(text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(character for character in text if _kept_in_body(character))
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
    return text[:limit].rstrip()


def _collapse_spaces(text: str) -> str:
    parts: list[str] = []
    in_space = False
    for character in text:
        if character.isspace():
            if not in_space:
                parts.append(" ")
            in_space = True
        else:
            parts.append(character)
            in_space = False
    return "".join(parts)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.pending = 0
        self.started = False
        self.skip: str | None = None
        self.href: str | None = None
        self.anchor: list[str] = []

    def _request(self, count: int) -> None:
        self.pending = max(self.pending, count)

    def _text(self, piece: str) -> None:
        if piece == " " and self.pending:
            return
        if self.started and self.pending:
            self.out.append("\n" * self.pending)
        self.pending = 0
        self.started = True
        self.out.append(piece)
        if self.href is not None:
            self.anchor.append(piece)

    def _breaks(self, tag: str) -> None:
        if tag in _PARAGRAPH_TAGS:
            self._request(2)
        elif tag in _LINE_TAGS:
            self._request(1)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.skip = tag
            return
        self._breaks(tag)
        if tag != "a":
            return
        hrefs = [value for name, value in attrs if name == "href"]
        href = hrefs[0].strip() if hrefs and hrefs[0] is not None else None
        remembered = href if href is not None and href.lower().startswith(_LINK_SCHEMES) else None
        self.href = remembered
        self.anchor = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            if self.skip == tag:
                self.skip = None
            return
        self._breaks(tag)
        if tag in ("td", "th"):
            self._text(" ")
        if tag == "a" and self.href is not None:
            href = self.href
            self.href = None
            if " ".join("".join(self.anchor).split()) != href:
                self._text(f" ({href})")

    def handle_data(self, data: str) -> None:
        if self.skip is None:
            self._text(_collapse_spaces(data))


def html_to_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    parser.close()
    text = "".join(parser.out)
    text = "\n".join(" ".join(line.split()) for line in text.split("\n"))
    return clean_text(text, BODY_LIMIT)


def _unparsed(raw: bytes, envelope: Envelope) -> Record:
    return Record(
        provider=envelope.provider,
        message_id=envelope.message_id,
        thread_id=envelope.thread_id,
        received_at=envelope.received_at,
        link=envelope.link,
        sender="",
        sender_name="",
        subject="",
        sent_at=None,
        list_unsubscribe=False,
        authentication_results=(),
        body_text=clean_text(raw.decode("utf-8", errors="replace"), BODY_LIMIT),
    )


def _header_text(message: Message, name: str) -> str | None:
    try:
        value = message[name]
        if value is None:
            return None
        return str(value)
    except Exception:
        return None


def _sender(message: Message) -> tuple[str, str]:
    try:
        header = message["From"]
        if header is None:
            return "", ""
        addresses = header.addresses
        if not addresses:
            return "", ""
        address = addresses[0]
        raw_address = address.addr_spec
        raw_name = address.display_name
    except Exception:
        return "", ""
    lowered = raw_address.lower()
    matches = _ADDRESS.fullmatch(lowered) is not None and len(lowered) <= ADDRESS_LIMIT
    return (lowered if matches else ""), clean_line(raw_name, NAME_LIMIT)


def _sent_at(message: Message) -> datetime | None:
    try:
        text = _header_text(message, "Date")
        if text is None:
            return None
        found = parsedate_to_datetime(text)
    except Exception:
        return None
    if found.tzinfo is None:
        return found.replace(tzinfo=UTC)
    return found.astimezone(UTC)


def _list_unsubscribe(message: Message) -> bool:
    text = _header_text(message, "List-Unsubscribe")
    return text is not None and text.strip() != ""


def _authentication_results(message: Message) -> tuple[str, ...]:
    try:
        values = message.get_all("Authentication-Results")
    except Exception:
        return ()
    if not values:
        return ()
    kept: list[str] = []
    for value in values:
        try:
            text = clean_line(str(value), HEADER_LIMIT)
        except Exception:
            return ()
        if text:
            kept.append(text)
        if len(kept) == AUTH_RESULTS_LIMIT:
            break
    return tuple(kept)


def _decode_part(part: Message) -> str:
    try:
        content = part.get_content()
    except Exception:
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            return ""
        if not isinstance(payload, bytes):
            return ""
        content = payload.decode("utf-8", errors="replace")
    if not isinstance(content, str):
        return ""
    try:
        if part.get_content_type() == "text/html":
            content = html_to_text(content)
    except Exception:
        return clean_text(content, BODY_LIMIT)
    return clean_text(content, BODY_LIMIT)


def _body(message: Message) -> str:
    try:
        part = message.get_body(preferencelist=("plain", "html"))
    except Exception:
        return ""
    if part is None:
        return ""
    return _decode_part(part)


def parse_message(raw: bytes, envelope: Envelope) -> Record:
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception:
        return _unparsed(raw, envelope)
    sender, sender_name = _sender(message)
    subject = _header_text(message, "Subject")
    return Record(
        provider=envelope.provider,
        message_id=envelope.message_id,
        thread_id=envelope.thread_id,
        received_at=envelope.received_at,
        link=envelope.link,
        sender=sender,
        sender_name=sender_name,
        subject="" if subject is None else clean_line(subject, SUBJECT_LIMIT),
        sent_at=_sent_at(message),
        body_text=_body(message),
        list_unsubscribe=_list_unsubscribe(message),
        authentication_results=_authentication_results(message),
    )
