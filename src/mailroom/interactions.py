import unicodedata

import httpx

from mailroom import __version__
from mailroom import discord_layout as L
from mailroom.checkpoint import _block, answered_message
from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.record import Record
from mailroom.store import Store, Verdict

_PRESS_ACTIONS = frozenset({"full", "yes", "edit", "notask", "mute", "trust"})
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def handle_interaction(
    event: dict[str, object], store: Store, settings: Settings, http: httpx.Client
) -> str:
    if settings.discord_owner_id == "" or settings.discord_channel_id == "":
        raise DiscordUnavailable("not configured") from None
    kind = event["type"]
    if kind not in (3, 5):
        return "ignored"
    action, item_id = _button(event)
    if (
        _presser(event) != settings.discord_owner_id
        or event.get("channel_id") != settings.discord_channel_id
        or action == ""
        or (kind == 3 and action not in _PRESS_ACTIONS)
        or (kind == 5 and action != L.FORM_ACTION)
        or store.post_by_item(item_id) is None
    ):
        _send(http, event, {"type": L.DEFERRED_UPDATE})
        return "ignored"
    post = store.post_by_item(item_id)
    stored = store.get(post.provider, post.message_id)
    triaged = store.triage(post.provider, post.message_id)
    record = stored.record
    verdict = triaged.verdict
    if kind == 5:
        return _submission(event, store, http, record, verdict, item_id)
    if action == "full":
        _send(http, event, _private(_full_text(record, stored.text_cleared_at is not None)))
        return "full"
    if action == "trust":
        return _trust(event, store, http, record)
    if store.answer(item_id) is not None:
        _send(http, event, _private(L.ALREADY_TEXT))
        return "already"
    if action == "mute" and record.sender == "":
        _send(http, event, _private(L.NO_SENDER_TEXT))
        return "no-sender"
    if action == "edit" or (action == "yes" and _proposed(verdict) == ""):
        _send(http, event, _form(record, verdict, item_id))
        return "form"
    if action == "yes":
        store.record_answer(item_id, "yes", verdict.extraction.title)
    elif action == "notask":
        store.record_answer(item_id, "notask", "")
    else:
        store.set_sender_status(record.sender, "muted")
        store.record_answer(item_id, "mute", "")
    _send(
        http,
        event,
        {
            "type": L.UPDATE_MESSAGE,
            "data": answered_message(record, verdict, item_id, action, _kept(verdict, action)),
        },
    )
    return "answered"


def _presser(event: dict[str, object]) -> str:
    if "member" in event:
        return event["member"]["user"]["id"]
    return event["user"]["id"]


def _button(event: dict[str, object]) -> tuple[str, str]:
    parts = str(event["data"]["custom_id"]).split(":")
    if len(parts) == 3 and parts[0] == L.PREFIX:
        return parts[1], parts[2]
    return "", ""


def _send(http: httpx.Client, event: dict[str, object], payload: dict[str, object]) -> None:
    try:
        response = http.post(
            f"{L.API_URL}/interactions/{event['id']}/{event['token']}/callback",
            json=payload,
            headers={"User-Agent": L.USER_AGENT.format(version=__version__)},
        )
    except httpx.TransportError:
        raise DiscordUnavailable("network") from None
    if response.status_code != 204:
        raise DiscordUnavailable(str(response.status_code)) from None


def _private(content: str) -> dict[str, object]:
    return {
        "type": L.CHANNEL_MESSAGE,
        "data": {"content": content, "flags": L.EPHEMERAL, "allowed_mentions": {"parse": []}},
    }


def _full_text(record: Record, cleared: bool) -> str:
    if cleared:
        return L.FULL_EXPIRED
    if record.body_text == "":
        return L.FULL_EMPTY
    shown = _block(record.body_text[: L.FULL_LIMIT])
    if len(record.body_text) > L.FULL_LIMIT:
        return shown + "\n" + L.FULL_CUT_NOTE
    return shown


def _trust(event: dict[str, object], store: Store, http: httpx.Client, record: Record) -> str:
    if record.sender == "":
        _send(http, event, _private(L.NO_SENDER_TEXT))
        return "no-sender"
    store.set_sender_status(record.sender, "trusted")
    _send(http, event, _private(L.TRUSTED_REPLY + "\n" + _block(record.sender)))
    return "trusted"


def _proposed(verdict: Verdict) -> str:
    extraction = verdict.extraction
    if extraction is None or extraction.title == "":
        return ""
    return extraction.title


def _kept(verdict: Verdict, action: str) -> str:
    if action == "yes":
        return _proposed(verdict)
    return ""


def _form(record: Record, verdict: Verdict, item_id: str) -> dict[str, object]:
    prefill = _proposed(verdict) or record.subject[: L.FORM_TITLE_LIMIT]
    field: dict[str, object] = {
        "type": 4,
        "custom_id": L.FORM_INPUT_ID,
        "style": 1,
        "min_length": 1,
        "max_length": L.FORM_TITLE_LIMIT,
        "required": True,
    }
    if prefill != "":
        field["value"] = prefill
    return {
        "type": L.MODAL,
        "data": {
            "custom_id": f"{L.PREFIX}:{L.FORM_ACTION}:{item_id}",
            "title": L.FORM_TITLE,
            "components": [{"type": 18, "label": L.FORM_LABEL, "component": field}],
        },
    }


def _submission(
    event: dict[str, object],
    store: Store,
    http: httpx.Client,
    record: Record,
    verdict: Verdict,
    item_id: str,
) -> str:
    if store.answer(item_id) is not None:
        _send(http, event, _private(L.ALREADY_TEXT))
        return "already"
    title = _accepted_title(_submitted_title(event["data"]))
    if title is None:
        _send(http, event, _private(L.BAD_TITLE_TEXT))
        return "bad-title"
    store.record_answer(item_id, "edit", title)
    _send(
        http,
        event,
        {
            "type": L.UPDATE_MESSAGE,
            "data": answered_message(record, verdict, item_id, "edit", title),
        },
    )
    return "answered"


def _submitted_title(data: dict[str, object]) -> str:
    for label in data["components"]:
        field = label["component"]
        if field.get("custom_id") == L.FORM_INPUT_ID:
            return field["value"].strip()
    return ""


def _accepted_title(title: str) -> str | None:
    if title == "" or len(title) > L.FORM_TITLE_LIMIT:
        return None
    if any(unicodedata.category(character) in _BAD_CATEGORIES for character in title):
        return None
    return title
