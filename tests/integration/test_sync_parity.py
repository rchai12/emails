"""Gmail and Outlook run the same shared round, so one timeline gives the same results for both."""

import importlib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock, gmail_sync, outlook_sync
from mailroom.config import get_settings
from mailroom.gmail import GmailClient
from mailroom.outlook import OutlookClient
from mailroom.store import Store, open_store
from tests.fakes import FakeGmail, FakeGraph, FakeKeychain
from tests.integration import test_gmail_sync as gmail_case
from tests.integration import test_outlook_sync as outlook_case

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
# (minutes after NOW, delivered at, expire the bookmark first)
TIMELINE = [
    (0, "2026-11-12T08:00:00", False),
    (1, "2026-11-13T08:30:00", False),
    (2 * 24 * 60, "2026-11-15T08:00:00", True),
    (2 * 24 * 60 + 1, None, False),
    (22 * 24 * 60, None, True),
]
# (kind, how many stored, offline since, gap); the resumed kind is the provider's own name
EXPECTED = [
    ("first", 1, None, False),
    ("resumed", 1, None, False),
    ("catch_up", 1, NOW + timedelta(minutes=1), False),
    ("resumed", 0, None, False),
    ("catch_up", 0, NOW + timedelta(days=2, minutes=1), True),
]


def mail_sync():
    return importlib.import_module("mailroom.mail_sync")


class Gmail:
    provider, account, resumed = "gmail", "personal", "history"

    def __init__(self, keychain: FakeKeychain) -> None:
        keychain.secrets.update(gmail_case.SECRETS)
        self.fake = FakeGmail()
        self.count = 0

    def deliver(self, moment: str) -> str:
        self.count += 1
        gmail_case.deliver(self.fake, self.count, f"{moment}+00:00")
        return f"personal/m{self.count}"

    def expire(self) -> None:
        self.fake.history_id += 1
        self.fake.oldest_history_id = self.fake.history_id

    def sync(self, store: Store):
        client = GmailClient(
            "personal", httpx.Client(transport=httpx.MockTransport(self.fake.handler))
        )
        return gmail_sync.sync_gmail(client, store)


class Outlook:
    provider, account, resumed = "outlook", "live", "delta"

    def __init__(self, keychain: FakeKeychain) -> None:
        self.fake = FakeGraph()
        keychain.secrets[("mailroom", "outlook.live.client-id")] = self.fake.client_id
        keychain.secrets[("mailroom", "outlook.live.refresh-token")] = self.fake.refresh_token
        self.count = 0

    def deliver(self, moment: str) -> str:
        self.count += 1
        outlook_case.deliver(self.fake, self.count, f"{moment}Z")
        return f"live/AAMk{self.count}="

    def expire(self) -> None:
        self.fake.expire_deltas()

    def sync(self, store: Store):
        client = OutlookClient(
            "live", httpx.Client(transport=httpx.MockTransport(self.fake.handler))
        )
        return outlook_sync.sync_outlook(client, store)


PROVIDERS: dict[str, Callable[[FakeKeychain], Gmail | Outlook]] = {
    "gmail": Gmail,
    "outlook": Outlook,
}


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    return now


@pytest.fixture
def store(moment: list[datetime]) -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_one_timeline_gives_the_same_rounds_through_the_shared_round(
    monkeypatch: pytest.MonkeyPatch,
    fake_keychain: FakeKeychain,
    moment: list[datetime],
    store: Store,
    provider: str,
) -> None:
    shared = mail_sync()
    real = shared.run_round
    sources: list[object] = []

    def spy(source, found: Store):
        sources.append(source)
        return real(source, found)

    monkeypatch.setattr(shared, "run_round", spy)
    case = PROVIDERS[provider](fake_keychain)
    seen = []
    delivered: list[str] = []
    for minutes, delivery, expire in TIMELINE:
        if expire:
            case.expire()
        if delivery is not None:
            delivered.append(case.deliver(delivery))
        moment[0] = NOW + timedelta(minutes=minutes)
        result = case.sync(store)
        assert result.account == case.account
        kind = "resumed" if result.kind == case.resumed else result.kind
        seen.append((kind, len(result.stored), result.offline_since, result.gap))
        assert set(result.stored) <= set(delivered)
        state = store.sync_state(provider, case.account)
        assert state is not None and state.synced_at == moment[0]
    assert seen == EXPECTED
    assert [store.get(provider, kept) is not None for kept in delivered] == [True, True, True]
    assert [(source.provider, source.account) for source in sources] == [
        (provider, case.account)
    ] * len(TIMELINE)
