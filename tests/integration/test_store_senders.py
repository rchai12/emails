import pytest

from mailroom.config import get_settings
from mailroom.store import open_store


def test_a_sender_is_kept_in_lowercase_and_listed_in_order() -> None:
    with open_store(get_settings()) as store:
        store.set_sender_status("Zed@Example.TEST", "trusted")
        store.set_sender_status("ann@example.test", "trusted")
    with open_store(get_settings()) as store:
        assert store.sender_status("zed@example.test") == "trusted"
        assert store.sender_status("ZED@example.test") == "trusted"
        assert store.senders("trusted") == ("ann@example.test", "zed@example.test")
        assert store.senders("muted") == ()
        assert store.sender_status("bob@example.test") is None


def test_a_sender_has_one_status_and_can_be_cleared() -> None:
    with open_store(get_settings()) as store:
        store.set_sender_status("ann@example.test", "trusted")
        store.set_sender_status("ann@example.test", "muted")
        assert store.sender_status("ann@example.test") == "muted"
        assert store.senders("trusted") == ()
        store.set_sender_status("ann@example.test", None)
        store.set_sender_status("bob@example.test", None)
        assert store.sender_status("ann@example.test") is None
        assert store.senders("muted") == ()


@pytest.mark.parametrize(
    "address",
    ["", "ann@@example.test", "ann b@example.test", "x" * 245 + "@example.test"],
    ids=["empty", "two-at", "space", "too-long"],
)
def test_an_invalid_address_is_refused(address: str) -> None:
    with open_store(get_settings()) as store:
        for call in (
            lambda: store.set_sender_status(address, "trusted"),
            lambda: store.sender_status(address),
        ):
            with pytest.raises(ValueError) as caught:
                call()
            assert str(caught.value) == "invalid sender address"
        assert store.senders("trusted") == ()


def test_an_unknown_status_is_refused() -> None:
    with open_store(get_settings()) as store:
        with pytest.raises(ValueError) as caught:
            store.set_sender_status("ann@example.test", "blocked")
        assert str(caught.value) == "invalid sender status"
        with pytest.raises(ValueError):
            store.senders("blocked")
