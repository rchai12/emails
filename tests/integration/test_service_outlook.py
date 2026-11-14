"""Outlook in the service: each round syncs it beside Gmail, alerts for it, and stage 4's test."""

import threading
from collections.abc import Iterator
from datetime import datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.outlook import OutlookClient
from mailroom.service import run_round, run_service
from mailroom.store import Store, open_store
from tests.fakes import FakeGraph, FakeKeychain
from tests.integration.test_service import GOOD, NOW, Rounds, World, raw

OWNER = "444444444444444444"
GMAIL_AUTH = (
    "mx.google.com; dkim=pass header.i=@example.test header.s=s1 header.b=abc; "
    "spf=pass (google.com: domain of sam1@example.test designates 192.0.2.1 as permitted sender) "
    "smtp.mailfrom=sam1@example.test; dmarc=pass (p=REJECT sp=REJECT dis=NONE) "
    "header.from=example.test"
)
OUTLOOK_AUTH = (
    "spf=pass (sender IP is 192.0.2.1) smtp.mailfrom=example.test; dkim=pass (signature was "
    "verified) header.d=example.test;dmarc=pass action=none header.from=example.test;"
    "compauth=pass reason=100"
)


class BothWorld(World):
    """test_service's World with one Outlook account, `live`, beside Gmail's."""

    def __init__(self, keychain: FakeKeychain, accounts: tuple[str, ...] = ("personal",)) -> None:
        super().__init__(keychain, accounts)
        self.graph = FakeGraph()
        keychain.secrets[("mailroom", "outlook.live.client-id")] = self.graph.client_id
        keychain.secrets[("mailroom", "outlook.live.refresh-token")] = self.graph.refresh_token

    def outlook(self, account: str = "live") -> OutlookClient:
        return OutlookClient(
            account, httpx.Client(transport=httpx.MockTransport(self.graph.handler))
        )

    def both_round(self, store: Store, settings: Settings) -> list[str]:
        before = len(self.lines)
        clients = [self.client(account) for account in self.gmail] + [self.outlook()]
        run_round(
            store,
            settings,
            clients,
            self.model_http(),
            self.discord_http(),
            self.tasks_http(),
            self.health,
        )
        return self.lines[before:]


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    return now


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, moment: list[datetime]) -> Settings:
    for name, value in (
        ("MAILROOM_GMAIL_ACCOUNTS", "personal"),
        ("MAILROOM_OUTLOOK_ACCOUNTS", "live"),
        ("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b"),
        ("MAILROOM_TIME_ZONE", "America/New_York"),
        ("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111"),
        ("MAILROOM_DISCORD_OWNER_ID", OWNER),
    ):
        monkeypatch.setenv(name, value)
    return get_settings()


@pytest.fixture
def store(settings: Settings) -> Iterator[Store]:
    with open_store(settings) as opened:
        yield opened


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def arrive_outlook(world: BothWorld, number: int, moment: datetime, top: str = "") -> None:
    body = raw(number) if not top else f"Authentication-Results: {top}\r\n".encode() + raw(number)
    world.graph.add_message(f"AAMk{number}=", body, received=stamp(moment - timedelta(hours=1)))


def posted(world: BothWorld) -> list[str]:
    return [message["content"] for message in world.discord.messages if message["content"]]


def test_a_round_syncs_outlook_beside_gmail_and_posts_its_card(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = BothWorld(fake_keychain)
    arrive_outlook(world, 1, NOW)
    world.model.replies.append(GOOD)
    assert world.both_round(store, settings)[:3] == [
        "gmail personal: ok",
        "outlook live: ok",
        "triage: ok",
    ]
    (card,) = [message for message in world.discord.messages if message["embeds"]]
    assert card["embeds"][0]["footer"]["text"] == "Outlook live · Sender not verified"
    assert store.post("outlook", "live/AAMk1=").posted_at == NOW


def test_one_provider_failing_does_not_stop_the_other(
    store: Store, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    world = BothWorld(fake_keychain)
    world.graph.failures.append(httpx.Response(503))
    lines = world.both_round(store, settings)
    assert lines[:2] == ["gmail personal: ok", "outlook live: outlook unavailable: live (503)"]
    assert store.sync_state("gmail", "personal") is not None


def test_a_signed_out_outlook_account_pings_you_and_its_fix_is_announced(
    store: Store, settings: Settings, fake_keychain: FakeKeychain, moment: list[datetime]
) -> None:
    world = BothWorld(fake_keychain)
    fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] = "revoked"
    assert world.both_round(store, settings)[1] == "outlook live: outlook sign-in needed: live"
    assert posted(world) == [
        f"<@{OWNER}> Outlook sign-in needed for live. Run: mailroom outlook-login live"
    ]
    fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] = world.graph.refresh_token
    moment[0] = NOW + timedelta(minutes=1)
    world.both_round(store, settings)
    assert posted(world)[1:] == ["Outlook live works again."]


def test_an_outlook_catch_up_is_announced_with_its_provider(
    store: Store, settings: Settings, fake_keychain: FakeKeychain, moment: list[datetime]
) -> None:
    world = BothWorld(fake_keychain)
    world.both_round(store, settings)
    world.graph.expire_deltas()
    moment[0] = NOW + timedelta(hours=3)
    arrive_outlook(world, 2, moment[0])
    world.model.replies.append(GOOD)
    world.both_round(store, settings)
    assert posted(world) == ["Outlook live caught up after 3 hours offline: 1 new email."]


@pytest.mark.parametrize(
    ("gmail_top", "outlook_top", "trusted"),
    [
        (GMAIL_AUTH, OUTLOOK_AUTH, True),
        (GMAIL_AUTH, OUTLOOK_AUTH, False),
        ("", "", True),
    ],
    ids=["authenticated-trusted", "authenticated", "unauthenticated-trusted"],
)
def test_identical_emails_get_identical_verdicts_from_gmail_and_outlook(
    store: Store,
    settings: Settings,
    fake_keychain: FakeKeychain,
    gmail_top: str,
    outlook_top: str,
    trusted: bool,
) -> None:
    world = BothWorld(fake_keychain)
    if trusted:
        store.set_sender_status("sam1@example.test", "trusted")
    gmail_raw = (
        raw(1) if not gmail_top else f"Authentication-Results: {gmail_top}\r\n".encode() + raw(1)
    )
    moment = round((NOW - timedelta(hours=1)).timestamp() * 1000)
    world.gmail["personal"].add_message("m1", gmail_raw, internal_ms=moment)
    arrive_outlook(world, 1, NOW, outlook_top)
    world.model.replies.extend([GOOD, GOOD])
    world.both_round(store, settings)
    gmail = store.triage("gmail", "personal/m1").verdict
    outlook = store.triage("outlook", "live/AAMk1=").verdict
    assert gmail == outlook
    assert (gmail.verified, gmail.trusted) == (bool(gmail_top), trusted and bool(gmail_top))


def test_the_service_runs_with_outlook_alone_and_closes_its_clients(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, fake_keychain: FakeKeychain
) -> None:
    monkeypatch.setenv("MAILROOM_GMAIL_ACCOUNTS", "")
    world = BothWorld(fake_keychain, ())
    opened: list[OutlookClient] = []

    def open_outlook(account: str) -> OutlookClient:
        client = world.outlook(account)
        opened.append(client)
        return client

    def gateway(store: Store, gateway_settings: Settings, http: httpx.Client, *, stop) -> None:
        while not stop():
            threading.Event().wait(0.001)

    run_service(
        get_settings(),
        say=world.lines.append,
        stop=Rounds(2),
        open_gmail=world.client,
        open_outlook=open_outlook,
        open_model_http=world.model_http,
        open_discord_http=world.discord_http,
        open_tasks_http=world.tasks_http,
        gateway=gateway,
    )
    assert [client.account for client in opened] == ["live"]
    assert opened[0].http.is_closed
    assert "outlook live: ok" in world.lines
    assert not any(line.startswith("gmail ") for line in world.lines)
