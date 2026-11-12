from mailroom.config import get_settings
from mailroom.store import open_store


def test_an_empty_database_has_no_posts() -> None:
    with open_store(get_settings()) as store:
        assert store.pending_posts() == ()
        assert store.post("yahoo", "missing") is None
