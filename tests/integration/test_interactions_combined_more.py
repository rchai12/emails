from collections.abc import Iterator
from datetime import datetime

import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.store import Store
from tests.integration.test_interactions import posted_store
from tests.integration.test_interactions_combined import ALREADY, DATED, ITEM, NOW, press
from tests.support import fixed_ids


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    return get_settings()


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    fixed_ids(monkeypatch, ITEM)
    return now


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    opened = posted_store(verdict=DATED)
    opened.choose_card(ITEM, "combined")
    yield opened
    opened.close()


def test_a_combined_decision_another_writer_already_stored_is_refused(
    store: Store, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "record_combined", lambda *_args, **_kwargs: False)
    assert press(store, settings, "approve") == ("already", ALREADY)
    assert (store.answer(ITEM), store.approval(ITEM)) == (None, None)
