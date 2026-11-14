import re

import httpx

from mailroom.config import Settings
from mailroom.discord_post import PostReport
from mailroom.store import Approval, Link, Store, Task

_TASK_ID = re.compile(r"\A[A-Za-z0-9_-]{1,100}\Z")


class TasksUnavailable(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(f"tasks app unavailable ({detail})")


def task_key(provider: str, message_id: str) -> str:
    return f"{provider}:{message_id}"


def task_payload(task: Task, approval: Approval, link: str, time_zone: str) -> dict[str, object]:
    due = approval.due
    if due is None:
        deadline: dict[str, object] | None = None
    else:
        deadline = {
            "date": due.date.isoformat(),
            "time": None if due.time is None else due.time.strftime("%H:%M"),
            "time_zone": time_zone,
        }
    return {
        "source": "email",
        "title": approval.title,
        "deadline": deadline,
        "provider": task.provider,
        "message_id": task.message_id,
        "link": link,
    }


def is_task_id(task_id: str) -> bool:
    return _TASK_ID.fullmatch(task_id) is not None


def link_payload(link: Link, email_link: str) -> dict[str, object]:
    return {
        "source": "email",
        "provider": link.provider,
        "message_id": link.message_id,
        "link": email_link,
    }


def open_tasks_http() -> httpx.Client:
    return httpx.Client(timeout=30.0, trust_env=False, follow_redirects=False)


def send_tasks(store: Store, settings: Settings, http: httpx.Client) -> PostReport:
    if settings.tasks_url == "":
        raise TasksUnavailable("not configured") from None
    store.queue_approved()
    pending = store.pending_tasks()
    posted = 0
    for index, task in enumerate(pending):
        approval = store.approval(task.item_id)
        link = store.get(task.provider, task.message_id).record.link
        try:
            response = http.post(
                f"{settings.tasks_url}/tasks",
                json=task_payload(task, approval, link, settings.time_zone),
                headers={"Idempotency-Key": task_key(task.provider, task.message_id)},
            )
        except httpx.TransportError:
            return PostReport(posted, len(pending) - index, "network")
        if response.status_code not in (200, 201):
            return PostReport(posted, len(pending) - index, str(response.status_code))
        task_id = _task_id(response)
        if task_id is None:
            return PostReport(posted, len(pending) - index, "response")
        store.mark_task_sent(task.item_id, task_id)
        posted += 1
    return _send_links(store, settings, http, posted)


def _task_id(response: httpx.Response) -> str | None:
    try:
        found = response.json()["id"]
    except (ValueError, TypeError, KeyError):
        return None
    if isinstance(found, str) and is_task_id(found):
        return found
    return None


def _send_links(store: Store, settings: Settings, http: httpx.Client, posted: int) -> PostReport:
    store.queue_linked()
    pending = store.pending_links()
    linked = 0
    for index, link in enumerate(pending):
        email_link = store.get(link.provider, link.message_id).record.link
        try:
            response = http.post(
                f"{settings.tasks_url}/tasks/{link.task_id}/links",
                json=link_payload(link, email_link),
                headers={"Idempotency-Key": task_key(link.provider, link.message_id)},
            )
        except httpx.TransportError:
            return PostReport(posted + linked, len(pending) - index, "network")
        if response.status_code not in (200, 201):
            return PostReport(posted + linked, len(pending) - index, str(response.status_code))
        store.mark_link_sent(link.item_id)
        linked += 1
    return PostReport(posted + linked, 0, "")
