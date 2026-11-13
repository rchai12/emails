from mailroom import discord_layout as L
from mailroom.record import Record, account_of
from mailroom.store import Verdict


def _block(text: str) -> str:
    return "```\n" + text.replace(L.BACKTICK, L.BACKTICK_STAND_IN) + "\n```"


def checkpoint_message(record: Record, verdict: Verdict, item_id: str) -> dict[str, object]:
    address = record.sender if record.sender else L.NO_ADDRESS
    sender = f"{record.sender_name} <{address}>" if record.sender_name else address
    subject = record.subject if record.subject else L.NO_SUBJECT
    extraction = verdict.extraction
    if extraction is not None and extraction.suspicious:
        color = L.COLOR_SUSPECTED
    elif extraction is None:
        color = L.COLOR_UNREAD
    else:
        color = L.COLOR_NORMAL
    if extraction is not None:
        summary = _block(extraction.summary)
    elif verdict.outcome == "rejected":
        summary = L.UNREAD_TEXT.replace("{reason}", verdict.reason)
    else:
        summary = L.EXPIRED_TEXT
    fields: list[dict[str, str]] = [
        {"name": L.FROM_NAME, "value": _block(sender)},
        {"name": L.SUBJECT_NAME, "value": _block(subject)},
        {"name": L.SUMMARY_NAME, "value": summary},
    ]
    if extraction is not None and extraction.title:
        fields.append({"name": L.TASK_NAME, "value": _block(extraction.title)})
    if extraction is not None and extraction.suspicious:
        fields.append({"name": L.WARNING_NAME, "value": _block(extraction.suspicion_reason)})
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
    footer = [provider, standing]
    if verdict.bulk:
        footer.append(L.BULK_TEXT)
    answers = [
        {
            "type": 2,
            "style": style,
            "label": label,
            "custom_id": f"{L.PREFIX}:{action}:{item_id}",
        }
        for action, label, style in (*L.FIRST_ROW, *L.SECOND_ROW)
    ]
    second = answers[len(L.FIRST_ROW) :]
    if len(record.link) <= L.LINK_LIMIT:
        second.append({"type": 2, "style": L.LINK_STYLE, "label": L.OPEN_LABEL, "url": record.link})
    return {
        "embeds": [
            {
                "title": L.TITLE,
                "color": color,
                "fields": fields,
                "footer": {"text": L.FOOTER_JOIN.join(footer)},
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
    if len(record.link) <= L.LINK_LIMIT:
        row.append({"type": 2, "style": L.LINK_STYLE, "label": L.OPEN_LABEL, "url": record.link})
    return {
        "embeds": [embed],
        "components": [{"type": 1, "components": row}],
        "allowed_mentions": {"parse": []},
    }
