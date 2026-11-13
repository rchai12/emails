from mailroom.config import Settings, prepare_data_dir
from mailroom.store.alerts import Alert, Problem
from mailroom.store.alerts import AlertStore as _AlertStore
from mailroom.store.base import DB_FILENAME, SCHEMA_MESSAGE, StoreError
from mailroom.store.messages import TEXT_RETENTION, StoredMessage
from mailroom.store.messages import MessageStore as _MessageStore
from mailroom.store.posts import Answer, Post
from mailroom.store.posts import PostStore as _PostStore
from mailroom.store.senders import SENDER_MESSAGE, STATUS_MESSAGE
from mailroom.store.senders import SenderStore as _SenderStore
from mailroom.store.sync import SyncState
from mailroom.store.sync import SyncStore as _SyncStore
from mailroom.store.triage import Due, StoredTriage, Verdict
from mailroom.store.triage import TriageStore as _TriageStore

__all__ = [
    "DB_FILENAME",
    "Due",
    "SCHEMA_MESSAGE",
    "SENDER_MESSAGE",
    "STATUS_MESSAGE",
    "TEXT_RETENTION",
    "Alert",
    "Answer",
    "Post",
    "Problem",
    "Store",
    "StoreError",
    "StoredMessage",
    "StoredTriage",
    "SyncState",
    "Verdict",
    "open_store",
]


class Store(_MessageStore, _SyncStore, _SenderStore, _TriageStore, _PostStore, _AlertStore):
    pass


def open_store(settings: Settings) -> Store:
    return Store(prepare_data_dir(settings) / DB_FILENAME)
