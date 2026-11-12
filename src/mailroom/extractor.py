import datetime
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import cast
from zoneinfo import ZoneInfo

import httpx

from mailroom.config import Settings
from mailroom.extractor_prompt import (
    BODY_LIMIT,
    CUT_NOTE,
    FIELDS,
    KEEP_ALIVE,
    OPTIONS,
    QUOTE_LIMIT,
    REASON_LIMIT,
    SCHEMA,
    SUMMARY_LIMIT,
    SYSTEM_PROMPT,
    TAG_NOTE,
    TITLE_LIMIT,
)
from mailroom.record import Record

TIMEOUT_SECONDS = 120.0

_TAG = re.compile(r"</?email\s*>", re.IGNORECASE)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TIME = re.compile(r"[0-9]{2}:[0-9]{2}")
_FLAGS = frozenset({"actionable", "urgent", "has_deadline", "deadline_explicit", "suspicious"})
_CONFIDENCE = ("high", "medium", "low")
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


class ModelUnavailable(Exception):
    def __init__(self, detail: str | int) -> None:
        super().__init__(f"model unavailable ({detail})")


@dataclass(frozen=True)
class Deadline:
    date: datetime.date
    time: datetime.time | None
    explicit: bool
    quote: str


@dataclass(frozen=True)
class Extraction:
    summary: str
    actionable: bool
    urgent: bool
    title: str
    deadline: Deadline | None
    suspicious: bool
    suspicion_reason: str
    confidence: str


@dataclass(frozen=True)
class Rejected:
    reason: str


def _show(text: str) -> str:
    return _TAG.sub(TAG_NOTE, text)


def user_message(record: Record, time_zone: str) -> str:
    if record.sent_at is None:
        label = "Received"
        moment = record.received_at
    else:
        label = "Sent"
        moment = record.sent_at
    shown = moment.astimezone(ZoneInfo(time_zone)).strftime("%A %Y-%m-%d %H:%M")
    body = _show(record.body_text)
    if len(body) > BODY_LIMIT:
        body = f"{body[:BODY_LIMIT]}\n{CUT_NOTE}"
    return "\n".join(
        [
            f"{label}: {shown} ({time_zone})",
            "<email>",
            f"From: {_show(record.sender_name)} <{record.sender}>",
            f"Subject: {_show(record.subject)}",
            "",
            body,
            "</email>",
        ]
    )


def _plain(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= limit
        and not any(unicodedata.category(character) in _BAD_CATEGORIES for character in value)
    )


def _real_date(value: str) -> datetime.date | None:
    if _DATE.fullmatch(value) is None:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def _real_time(value: str) -> datetime.time | None:
    if _TIME.fullmatch(value) is None:
        return None
    try:
        return datetime.time.fromisoformat(value)
    except ValueError:
        return None


def _text_fails(value: object, limit: int, mode: str) -> bool:
    if not _plain(value, limit):
        return True
    text = cast(str, value)
    if mode == "filled":
        return text.strip() == ""
    if mode == "empty":
        return text != ""
    return False


def _schedule_fails(value: object, needed: object, kind: str) -> bool:
    if not isinstance(value, str):
        return True
    if needed is not True:
        return value != ""
    if kind == "time" and value == "":
        return False
    parsed = _real_time(value) if kind == "time" else _real_date(value)
    return parsed is None


def _fails(name: str, payload: dict[str, object]) -> bool:
    value = payload[name]
    if name in _FLAGS:
        return type(value) is not bool
    if name == "confidence":
        return value not in _CONFIDENCE
    if name == "summary":
        return _text_fails(value, SUMMARY_LIMIT, "filled")
    if name == "title":
        mode = "filled" if payload["actionable"] else "plain"
        return _text_fails(value, TITLE_LIMIT, mode)
    if name == "deadline_date":
        return _schedule_fails(value, payload["has_deadline"], "date")
    if name == "deadline_time":
        return _schedule_fails(value, payload["has_deadline"], "time")
    if name == "deadline_quote":
        mode = "filled" if payload["has_deadline"] else "empty"
        return _text_fails(value, QUOTE_LIMIT, mode)
    mode = "filled" if payload["suspicious"] else "empty"
    return _text_fails(value, REASON_LIMIT, mode)


def _build(payload: dict[str, object]) -> Extraction:
    deadline = None
    if payload["has_deadline"] is True:
        raw_time = payload["deadline_time"]
        deadline = Deadline(
            date=datetime.date.fromisoformat(cast(str, payload["deadline_date"])),
            time=None if raw_time == "" else datetime.time.fromisoformat(cast(str, raw_time)),
            explicit=payload["deadline_explicit"] is True,
            quote=cast(str, payload["deadline_quote"]),
        )
    return Extraction(
        summary=cast(str, payload["summary"]),
        actionable=payload["actionable"] is True,
        urgent=payload["urgent"] is True,
        title=cast(str, payload["title"]),
        deadline=deadline,
        suspicious=payload["suspicious"] is True,
        suspicion_reason=cast(str, payload["suspicion_reason"]),
        confidence=cast(str, payload["confidence"]),
    )


def _interpret(body: object) -> Extraction | Rejected:
    if not isinstance(body, dict):
        return Rejected("response")
    message = body.get("message")
    if not isinstance(message, dict):
        return Rejected("response")
    content = message.get("content")
    if not isinstance(content, str):
        return Rejected("response")
    if body.get("done_reason") != "stop":
        return Rejected("done_reason")
    try:
        parsed = json.loads(content)
    except ValueError:
        return Rejected("content")
    if not isinstance(parsed, dict):
        return Rejected("content")
    if set(parsed) != set(FIELDS):
        return Rejected("fields")
    for name in FIELDS:
        if _fails(name, parsed):
            return Rejected(name)
    return _build(parsed)


def extract(record: Record, settings: Settings, http: httpx.Client) -> Extraction | Rejected:
    if settings.extractor_model == "" or settings.time_zone == "":
        raise ModelUnavailable("not configured") from None
    try:
        response = http.post(
            f"{settings.extractor_url}/api/chat",
            json={
                "model": settings.extractor_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message(record, settings.time_zone)},
                ],
                "format": SCHEMA,
                "stream": False,
                "options": OPTIONS,
                "keep_alive": KEEP_ALIVE,
            },
        )
    except httpx.ReadTimeout:
        return Rejected("timeout")
    except httpx.TransportError:
        raise ModelUnavailable("network") from None
    if response.status_code != 200:
        raise ModelUnavailable(response.status_code) from None
    try:
        body = response.json()
    except ValueError:
        return Rejected("response")
    return _interpret(body)


def open_model_http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)
