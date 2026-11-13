from mailroom import discord_layout as L
from mailroom.record import Record, account_of
from mailroom.store import Approval, Due, Verdict


def _block(text: str) -> str:
    return "```\n" + text.replace(L.BACKTICK, L.BACKTICK_STAND_IN) + "\n```"


def _identity_fields(record: Record) -> list[dict[str, str]]:
    address = record.sender if record.sender else L.NO_ADDRESS
    sender = f"{record.sender_name} <{address}>" if record.sender_name else address
    subject = record.subject if record.subject else L.NO_SUBJECT
    return [
        {"name": L.FROM_NAME, "value": _block(sender)},
        {"name": L.SUBJECT_NAME, "value": _block(subject)},
    ]


def _colour(verdict: Verdict) -> int:
    extraction = verdict.extraction
    if extraction is not None and extraction.suspicious:
        return L.COLOR_SUSPECTED
    if extraction is None:
        return L.COLOR_UNREAD
    return L.COLOR_NORMAL


def _footer(record: Record, verdict: Verdict) -> str:
    if verdict.trusted:
        standing = L.TRUSTED_TEXT
    elif verdict.verified:
        standing = L.VERIFIED_TEXT
    else:
        standing = L.UNVERIFIED_TEXT
    provider = L.PROVIDER_NAMES[record.provider]
    account = account_of(record.message_id)
    if account is not None:
        provider = f"{provider} {account}"
    parts = [provider, standing]
    if verdict.bulk:
        parts.append(L.BULK_TEXT)
    return L.FOOTER_JOIN.join(parts)


def _button(action: str, label: str, style: int, item_id: str) -> dict[str, object]:
    return {
        "type": 2,
        "style": style,
        "label": label,
        "custom_id": f"{L.PREFIX}:{action}:{item_id}",
    }


def _open_button(record: Record) -> dict[str, object] | None:
    if len(record.link) > L.LINK_LIMIT:
        return None
    return {"type": 2, "style": L.LINK_STYLE, "label": L.OPEN_LABEL, "url": record.link}


def _deadline_line(due: Due | None, missing: str) -> str:
    if due is None:
        return missing
    shown = due.date.strftime(L.DATE_FORMAT)
    if due.time is not None:
        shown += due.time.strftime(L.TIME_FORMAT)
    return shown


def checkpoint_message(record: Record, verdict: Verdict, item_id: str) -> dict[str, object]:
    extraction = verdict.extraction
    if extraction is not None:
        summary = _block(extraction.summary)
    elif verdict.outcome == "rejected":
        summary = L.UNREAD_TEXT.replace("{reason}", verdict.reason)
    else:
        summary = L.EXPIRED_TEXT
    fields: list[dict[str, str]] = [
        *_identity_fields(record),
        {"name": L.SUMMARY_NAME, "value": summary},
    ]
    if extraction is not None and extraction.title:
        fields.append({"name": L.TASK_NAME, "value": _block(extraction.title)})
    if extraction is not None and extraction.suspicious:
        fields.append({"name": L.WARNING_NAME, "value": _block(extraction.suspicion_reason)})
    answers = [
        _button(action, label, style, item_id)
        for action, label, style in (*L.FIRST_ROW, *L.SECOND_ROW)
    ]
    second = answers[len(L.FIRST_ROW) :]
    open_email = _open_button(record)
    if open_email is not None:
        second.append(open_email)
    return {
        "embeds": [
            {
                "title": L.TITLE,
                "color": _colour(verdict),
                "fields": fields,
                "footer": {"text": _footer(record, verdict)},
            }
        ],
        "components": [
            {"type": 1, "components": answers[: len(L.FIRST_ROW)]},
            {"type": 1, "components": second},
        ],
        "allowed_mentions": {"parse": []},
        "nonce": item_id[: L.NONCE_LENGTH],
        "enforce_nonce": True,
    }


def answered_message(
    record: Record, verdict: Verdict, item_id: str, answer: str, title: str
) -> dict[str, object]:
    card = checkpoint_message(record, verdict, item_id)
    embed = card["embeds"][0]
    shown = L.ANSWER_TEXT[answer]
    if answer in ("yes", "edit"):
        shown = shown + "\n" + _block(title)
    embed["fields"].append({"name": L.ANSWER_NAME, "value": shown})
    full = card["components"][0]["components"][0]
    row = [full]
    open_email = _open_button(record)
    if open_email is not None:
        row.append(open_email)
    return {
        "embeds": [embed],
        "components": [{"type": 1, "components": row}],
        "allowed_mentions": {"parse": []},
    }


def checkpoint2_message(
    record: Record, verdict: Verdict, item_id: str, title: str
) -> dict[str, object]:
    fields: list[dict[str, str]] = [
        *_identity_fields(record),
        {"name": L.TASK_NAME, "value": _block(title)},
        {"name": L.DEADLINE_NAME, "value": _deadline_line(verdict.due, L.NO_PROPOSAL_TEXT)},
    ]
    if verdict.due is not None:
        extraction = verdict.extraction
        evidence = L.EVIDENCE_EXPIRED if extraction is None else _block(extraction.deadline.quote)
        fields.append({"name": L.EVIDENCE_NAME, "value": evidence})
    extraction = verdict.extraction
    if extraction is not None and extraction.suspicious:
        fields.append({"name": L.WARNING_NAME, "value": _block(extraction.suspicion_reason)})
    buttons = [
        _button(action, label, style, item_id)
        for action, label, style in L.SECOND_BUTTONS
        if action != "approve" or verdict.due is not None
    ]
    components: list[dict[str, object]] = [{"type": 1, "components": buttons}]
    open_email = _open_button(record)
    if open_email is not None:
        components.append({"type": 1, "components": [open_email]})
    return {
        "embeds": [
            {
                "title": L.SECOND_TITLE,
                "color": _colour(verdict),
                "fields": fields,
                "footer": {"text": _footer(record, verdict)},
            }
        ],
        "components": components,
        "allowed_mentions": {"parse": []},
    }


def combined_message(record: Record, verdict: Verdict, item_id: str) -> dict[str, object]:
    extraction = verdict.extraction
    fields = [
        *_identity_fields(record),
        {"name": L.SUMMARY_NAME, "value": _block(extraction.summary)},
        {"name": L.TASK_NAME, "value": _block(extraction.title)},
        {"name": L.DEADLINE_NAME, "value": _deadline_line(verdict.due, L.NO_PROPOSAL_TEXT)},
        {"name": L.EVIDENCE_NAME, "value": _block(extraction.deadline.quote)},
    ]
    first = [
        _button(action, label, style, item_id) for action, label, style in L.COMBINED_FIRST_ROW
    ]
    second = [
        _button(action, label, style, item_id) for action, label, style in L.COMBINED_SECOND_ROW
    ]
    open_email = _open_button(record)
    if open_email is not None:
        second.append(open_email)
    return {
        "embeds": [
            {
                "title": L.COMBINED_TITLE,
                "color": _colour(verdict),
                "fields": fields,
                "footer": {"text": _footer(record, verdict)},
            }
        ],
        "components": [
            {"type": 1, "components": first},
            {"type": 1, "components": second},
        ],
        "allowed_mentions": {"parse": []},
        "nonce": item_id[: L.NONCE_LENGTH],
        "enforce_nonce": True,
    }


def approved_message(
    record: Record, verdict: Verdict, item_id: str, approval: Approval
) -> dict[str, object]:
    fields = [*_identity_fields(record)]
    if approval.outcome != "drop":
        fields.append({"name": L.TASK_NAME, "value": _block(approval.title)})
        fields.append(
            {"name": L.DEADLINE_NAME, "value": _deadline_line(approval.due, L.NO_DEADLINE_TEXT)}
        )
    fields.append({"name": L.ANSWER_NAME, "value": L.APPROVAL_TEXT[approval.outcome]})
    action, label, style = L.SECOND_BUTTONS[0]
    row: list[dict[str, object]] = [_button(action, label, style, item_id)]
    open_email = _open_button(record)
    if open_email is not None:
        row.append(open_email)
    return {
        "embeds": [
            {
                "title": L.SECOND_TITLE,
                "color": _colour(verdict),
                "fields": fields,
                "footer": {"text": _footer(record, verdict)},
            }
        ],
        "components": [{"type": 1, "components": row}],
        "allowed_mentions": {"parse": []},
    }
