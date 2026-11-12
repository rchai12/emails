from mailroom import discord_layout as L
from mailroom.record import Record
from mailroom.store import Verdict


def checkpoint_message(record: Record, verdict: Verdict, item_id: str) -> dict[str, object]:
    def block(text: str) -> str:
        return "```\n" + text.replace(L.BACKTICK, L.BACKTICK_STAND_IN) + "\n```"

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
        summary = block(extraction.summary)
    elif verdict.outcome == "rejected":
        summary = L.UNREAD_TEXT.replace("{reason}", verdict.reason)
    else:
        summary = L.EXPIRED_TEXT
    fields: list[dict[str, str]] = [
        {"name": L.FROM_NAME, "value": block(sender)},
        {"name": L.SUBJECT_NAME, "value": block(subject)},
        {"name": L.SUMMARY_NAME, "value": summary},
    ]
    if extraction is not None and extraction.title:
        fields.append({"name": L.TASK_NAME, "value": block(extraction.title)})
    if extraction is not None and extraction.suspicious:
        fields.append({"name": L.WARNING_NAME, "value": block(extraction.suspicion_reason)})
    if verdict.trusted:
        standing = L.TRUSTED_TEXT
    elif verdict.verified:
        standing = L.VERIFIED_TEXT
    else:
        standing = L.UNVERIFIED_TEXT
    footer = [L.PROVIDER_NAMES[record.provider], standing]
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
