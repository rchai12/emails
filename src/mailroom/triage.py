from collections.abc import Iterable
from datetime import date, time

import httpx

from mailroom.config import Settings
from mailroom.extractor import Extraction, Rejected, extract
from mailroom.record import Record
from mailroom.rules import Screening, screen
from mailroom.store import Store, Verdict

_CONFIDENCE = {"high": 0, "medium": 1, "low": 2}


def should_notify(screening: Screening, result: Extraction | Rejected | None) -> bool:
    if result is None:
        return False
    if isinstance(result, Rejected):
        return True
    if screening.trusted:
        return True
    if result.actionable or result.urgent or result.deadline is not None:
        return True
    if result.confidence == "high":
        return False
    if result.confidence == "medium" and screening.bulk:
        return False
    return True


def _rank_key(item: tuple[Record, Verdict]) -> tuple[object, ...]:
    record, verdict = item
    extraction = verdict.extraction
    if extraction is None:
        suspicious = False
        urgent = False
        deadline_rank: tuple[int, date, time] = (1, date.min, time.min)
        confidence = _CONFIDENCE["low"]
    else:
        suspicious = extraction.suspicious
        urgent = extraction.urgent
        deadline = extraction.deadline
        if deadline is None:
            deadline_rank = (1, date.min, time.min)
        else:
            moment = time.max if deadline.time is None else deadline.time
            deadline_rank = (0, deadline.date, moment)
        confidence = _CONFIDENCE[extraction.confidence]
    return (
        not verdict.trusted,
        suspicious,
        not urgent,
        deadline_rank,
        confidence,
        -record.received_at.timestamp(),
        record.provider,
        record.message_id,
    )


def rank(entries: Iterable[tuple[Record, Verdict]]) -> list[tuple[Record, Verdict]]:
    return sorted(entries, key=_rank_key)


def triage_message(
    store: Store,
    provider: str,
    message_id: str,
    settings: Settings,
    http: httpx.Client,
) -> Verdict | None:
    stored = store.get(provider, message_id)
    if stored is None:
        return None
    existing = store.triage(provider, message_id)
    if existing is not None:
        return existing.verdict
    if stored.text_cleared_at is not None:
        return None
    record = stored.record
    screening = screen(record, store)
    result: Extraction | Rejected | None
    if screening.action == "drop":
        result = None
    else:
        result = extract(record, settings, http)
    if result is None:
        outcome = "dropped"
        extraction = None
        reason = ""
    elif isinstance(result, Rejected):
        outcome = "rejected"
        extraction = None
        reason = result.reason
    else:
        outcome = "extracted"
        extraction = result
        reason = ""
    verdict = Verdict(
        outcome=outcome,
        trusted=screening.trusted,
        verified=screening.verified,
        bulk=screening.bulk,
        notify=should_notify(screening, result),
        extraction=extraction,
        reason=reason,
    )
    store.save_triage(provider, message_id, verdict)
    return verdict
