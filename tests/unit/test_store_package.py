"""The store is a package with one module per area, and its public face is unchanged."""

import importlib
import inspect

import pytest

import mailroom.store
from mailroom.store import Store

AREAS = ("base", "messages", "sync", "senders", "triage", "posts", "alerts", "approvals")

METHODS = {
    "close": "base",
    "add": "messages",
    "get": "messages",
    "clear_expired_text": "messages",
    "sync_state": "sync",
    "save_sync_state": "sync",
    "sender_status": "senders",
    "set_sender_status": "senders",
    "senders": "senders",
    "save_triage": "triage",
    "triage": "triage",
    "untriaged": "triage",
    "queue_notified": "posts",
    "pending_posts": "posts",
    "post": "posts",
    "mark_posted": "posts",
    "post_by_item": "posts",
    "record_answer": "posts",
    "choose_card": "posts",
    "answer": "posts",
    "problem": "alerts",
    "open_problem": "alerts",
    "mark_alerted": "alerts",
    "close_problem": "alerts",
    "queue_alert": "alerts",
    "pending_alerts": "alerts",
    "mark_alert_posted": "alerts",
    "record_approval": "approvals",
    "approval": "approvals",
    "record_combined": "approvals",
}

NAMES = {
    "StoreError": "base",
    "DB_FILENAME": "base",
    "SCHEMA_MESSAGE": "base",
    "StoredMessage": "messages",
    "TEXT_RETENTION": "messages",
    "SyncState": "sync",
    "SENDER_MESSAGE": "senders",
    "STATUS_MESSAGE": "senders",
    "Verdict": "triage",
    "StoredTriage": "triage",
    "Post": "posts",
    "Answer": "posts",
    "Problem": "alerts",
    "Alert": "alerts",
    "Approval": "approvals",
}


def test_each_area_is_its_own_module() -> None:
    for area in AREAS:
        importlib.import_module(f"mailroom.store.{area}")
    assert Store.__module__ == "mailroom.store"
    assert mailroom.store.open_store.__module__ == "mailroom.store"


def test_the_store_keeps_exactly_its_public_methods() -> None:
    public = sorted(name for name in dir(Store) if not name.startswith("_"))
    assert public == sorted(METHODS)


@pytest.mark.parametrize(("method", "area"), sorted(METHODS.items()), ids=sorted(METHODS))
def test_each_method_lives_in_its_area(method: str, area: str) -> None:
    assert getattr(Store, method).__module__ == f"mailroom.store.{area}"


@pytest.mark.parametrize(("name", "area"), sorted(NAMES.items()), ids=sorted(NAMES))
def test_each_name_is_defined_in_its_area_and_still_imported_from_the_store(
    name: str, area: str
) -> None:
    module = importlib.import_module(f"mailroom.store.{area}")
    found = getattr(mailroom.store, name)
    assert found is getattr(module, name)
    if isinstance(found, type):
        assert found.__module__ == f"mailroom.store.{area}"
    else:
        assert f"\n{name} = " in inspect.getsource(module)
