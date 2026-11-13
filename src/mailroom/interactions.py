import unicodedata
from datetime import date
from zoneinfo import ZoneInfo

import httpx

from mailroom import __version__, clock
from mailroom import discord_layout as L
from mailroom.checkpoint import _block, answered_message, approved_message, checkpoint2_message
from mailroom.commands import handle_command
from mailroom.config import Settings
from mailroom.deadlines import read_deadline
from mailroom.discord_post import DiscordUnavailable
from mailroom.record import Record
from mailroom.store import Answer, Due, Store, Verdict

_PRESS_ACTIONS = frozenset(
    {
        "full",
        "yes",
        "edit",
        "notask",
        "mute",
        "trust",
        "approve",
        "change",
        "nodeadline",
        "drop",
    }
)
_SECOND_ACTIONS = frozenset({"approve", "change", "nodeadline", "drop"})
_FORM_ACTIONS = frozenset({L.FORM_ACTION, L.TASK_FORM_ACTION})
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})
_COMMAND_NAMES = tuple(command["name"] for command in L.COMMANDS)


def handle_interaction(
    event: dict[str, object], store: Store, settings: Settings, http: httpx.Client
) -> str:
    if settings.discord_owner_id == "" or settings.discord_channel_id == "":
        raise DiscordUnavailable("not configured") from None
    kind = event["type"]
    if kind == 2:
        answered = _slash(event, store, settings, http)
        if answered is not None:
            return answered
    if kind not in (3, 5):
        return "ignored"
    action, item_id = _button(event)
    if (
        _presser(event) != settings.discord_owner_id
        or event.get("channel_id") != settings.discord_channel_id
        or action == ""
        or (kind == 3 and action not in _PRESS_ACTIONS)
        or (kind == 5 and action not in _FORM_ACTIONS)
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
        return _form_reply(event, store, settings, http, record, verdict, item_id, action)
    if action == "full":
        _send(http, event, _private(_full_text(record, stored.text_cleared_at is not None)))
        return "full"
    if action == "trust":
        return _trust(event, store, http, record)
    found = store.answer(item_id)
    if found is None:
        if action in _SECOND_ACTIONS:
            _send(http, event, {"type": L.DEFERRED_UPDATE})
            return "ignored"
        return _first_answer(event, store, http, record, verdict, item_id, action)
    if found.answer in ("yes", "edit") and store.approval(item_id) is None:
        return _second_answer(event, store, http, record, verdict, item_id, action, found)
    _send(http, event, _private(L.ALREADY_TEXT))
    return "already"


def _slash(
    event: dict[str, object], store: Store, settings: Settings, http: httpx.Client
) -> str | None:
    name = event["data"].get("name")
    if name not in _COMMAND_NAMES:
        return None
    if (
        _presser(event) != settings.discord_owner_id
        or event.get("channel_id") != settings.discord_channel_id
    ):
        _send(http, event, _private(L.NOT_YOURS_TEXT))
        return "refused"
    outcome, text = handle_command(event, store)
    _send(http, event, _private(text))
    return outcome


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
            "data": checkpoint2_message(record, verdict, item_id, title),
        },
    )
    return "answered"


def _submitted_title(data: dict[str, object]) -> str:
    return _field(data, L.FORM_INPUT_ID)


def _field(data: dict[str, object], custom_id: str) -> str:
    for label in data["components"]:
        field = label["component"]
        if field.get("custom_id") == custom_id:
            return field["value"].strip()
    return ""


def _form_reply(
    event: dict[str, object],
    store: Store,
    settings: Settings,
    http: httpx.Client,
    record: Record,
    verdict: Verdict,
    item_id: str,
    action: str,
) -> str:
    if action == L.FORM_ACTION:
        return _submission(event, store, http, record, verdict, item_id)
    found = store.answer(item_id)
    if found is None:
        _send(http, event, {"type": L.DEFERRED_UPDATE})
        return "ignored"
    if found.answer not in ("yes", "edit") or store.approval(item_id) is not None:
        _send(http, event, _private(L.ALREADY_TEXT))
        return "already"
    return _task_submission(event, store, settings, http, record, verdict, item_id)


def _first_answer(
    event: dict[str, object],
    store: Store,
    http: httpx.Client,
    record: Record,
    verdict: Verdict,
    item_id: str,
    action: str,
) -> str:
    if action == "mute" and record.sender == "":
        _send(http, event, _private(L.NO_SENDER_TEXT))
        return "no-sender"
    if action == "edit" or (action == "yes" and _proposed(verdict) == ""):
        _send(http, event, _form(record, verdict, item_id))
        return "form"
    if action == "yes":
        title = _proposed(verdict)
        store.record_answer(item_id, "yes", title)
        reply = checkpoint2_message(record, verdict, item_id, title)
    elif action == "notask":
        store.record_answer(item_id, "notask", "")
        reply = answered_message(record, verdict, item_id, action, "")
    else:
        store.set_sender_status(record.sender, "muted")
        store.record_answer(item_id, "mute", "")
        reply = answered_message(record, verdict, item_id, action, "")
    _send(http, event, {"type": L.UPDATE_MESSAGE, "data": reply})
    return "answered"


def _second_answer(
    event: dict[str, object],
    store: Store,
    http: httpx.Client,
    record: Record,
    verdict: Verdict,
    item_id: str,
    action: str,
    found: Answer,
) -> str:
    if action in ("yes", "edit"):
        _send(
            http,
            event,
            {
                "type": L.UPDATE_MESSAGE,
                "data": checkpoint2_message(record, verdict, item_id, found.title),
            },
        )
        return "again"
    if action in ("notask", "mute"):
        _send(http, event, _private(L.ALREADY_TEXT))
        return "already"
    if action == "change":
        _send(http, event, _task_form(item_id, found.title, verdict.due))
        return "form"
    if action == "approve" and verdict.due is None:
        _send(http, event, {"type": L.DEFERRED_UPDATE})
        return "ignored"
    if action == "approve":
        return _decide(
            event,
            store,
            http,
            record,
            verdict,
            item_id,
            "approve",
            found.title,
            verdict.due,
            "approved",
        )
    if action == "nodeadline":
        return _decide(
            event,
            store,
            http,
            record,
            verdict,
            item_id,
            "nodeadline",
            found.title,
            None,
            "approved",
        )
    return _decide(event, store, http, record, verdict, item_id, "drop", "", None, "dropped")


def _task_form(item_id: str, title: str, due: Due | None) -> dict[str, object]:
    title_input: dict[str, object] = {
        "type": 4,
        "custom_id": L.FORM_INPUT_ID,
        "style": 1,
        "min_length": 1,
        "max_length": L.FORM_TITLE_LIMIT,
        "required": True,
        "value": title,
    }
    deadline_input: dict[str, object] = {
        "type": 4,
        "custom_id": L.DEADLINE_INPUT_ID,
        "style": 1,
        "min_length": 0,
        "max_length": L.DEADLINE_LIMIT,
        "required": False,
    }
    prefill = _deadline_prefill(due)
    if prefill is not None:
        deadline_input["value"] = prefill
    return {
        "type": L.MODAL,
        "data": {
            "custom_id": f"{L.PREFIX}:{L.TASK_FORM_ACTION}:{item_id}",
            "title": L.TASK_FORM_TITLE,
            "components": [
                {"type": 18, "label": L.FORM_LABEL, "component": title_input},
                {"type": 18, "label": L.DEADLINE_LABEL, "component": deadline_input},
            ],
        },
    }


def _deadline_prefill(due: Due | None) -> str | None:
    if due is None:
        return None
    if due.time is None:
        return due.date.isoformat()
    shown = due.time.hour % 12 or 12
    suffix = "am" if due.time.hour < 12 else "pm"
    return f"{due.date.isoformat()} {shown}:{due.time.minute:02d} {suffix}"


def _task_submission(
    event: dict[str, object],
    store: Store,
    settings: Settings,
    http: httpx.Client,
    record: Record,
    verdict: Verdict,
    item_id: str,
) -> str:
    title = _accepted_title(_submitted_title(event["data"]))
    if title is None:
        _send(http, event, _private(L.BAD_TITLE_TEXT))
        return "bad-title"
    text = _field(event["data"], L.DEADLINE_INPUT_ID)
    due = None
    if text != "":
        found = read_deadline(text, _today(settings))
        if found is None:
            _send(http, event, _private(L.BAD_DEADLINE_TEXT))
            return "bad-deadline"
        due_date, due_time = found
        due = Due(date=due_date, time=due_time)
    return _decide(event, store, http, record, verdict, item_id, "change", title, due, "approved")


def _today(settings: Settings) -> date:
    name = settings.time_zone or "UTC"
    return clock.now().astimezone(ZoneInfo(name)).date()


def _decide(
    event: dict[str, object],
    store: Store,
    http: httpx.Client,
    record: Record,
    verdict: Verdict,
    item_id: str,
    outcome: str,
    title: str,
    due: Due | None,
    result: str,
) -> str:
    if not store.record_approval(item_id, outcome, title, due):
        _send(http, event, _private(L.ALREADY_TEXT))
        return "already"
    recorded = store.approval(item_id)
    _send(
        http,
        event,
        {"type": L.UPDATE_MESSAGE, "data": approved_message(record, verdict, item_id, recorded)},
    )
    return result


def _accepted_title(title: str) -> str | None:
    if title == "" or len(title) > L.FORM_TITLE_LIMIT:
        return None
    if any(unicodedata.category(character) in _BAD_CATEGORIES for character in title):
        return None
    return title
