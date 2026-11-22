"""A rotated Outlook token the Keychain will not save, seen from the service's rounds.

One client lives across rounds, as in `run_service`; `restart()` replaces it, as a new
process would. The owner is pinged on the first unsaved round, no mail is read until the
save works, and the fix is announced only by a round that read mail.
"""

import re
from collections.abc import Iterator
from datetime import datetime, timedelta

import httpx
import keyring.core
import pytest

from mailroom import clock
from mailroom.config import Settings, get_settings
from mailroom.outlook import OutlookClient
from mailroom.store import Store, open_store
from tests.integration.test_outlook_rotation import TOKEN_NAME, SaveFails
from tests.integration.test_service import GOOD, NOW
from tests.integration.test_service_outlook import BothWorld, arrive_outlook, posted

OWNER = "444444444444444444"
UNSAVED_LINE = "outlook live: outlook new sign-in not saved: live"
UNSAVED_ALERT = (
    f"<@{OWNER}> Outlook live got a new sign-in that the Keychain would not save. "
    "Mailroom keeps it in memory and tries again each round. "
    "If Mailroom stops before then, run: mailroom outlook-login live"
)
SAVED = "Outlook live works again and its sign-in is saved."
SIGN_IN = f"<@{OWNER}> Outlook sign-in needed for live. Run: mailroom outlook-login live"


class HeldWorld(BothWorld):
    """BothWorld with Outlook only, whose client is kept from round to round."""

    def __init__(self, keychain: SaveFails) -> None:
        super().__init__(keychain, ())
        self.kept: OutlookClient | None = None

    def outlook(self, account: str = "live") -> OutlookClient:
        if self.kept is None:
            self.kept = super().outlook(account)
        return self.kept

    def restart(self) -> None:
        self.kept = None


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    return now


@pytest.fixture
def keychain(monkeypatch: pytest.MonkeyPatch) -> SaveFails:
    fake = SaveFails()
    monkeypatch.setattr(keyring.core, "_keyring_backend", fake)
    return fake


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, moment: list[datetime]) -> Settings:
    for name, value in (
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


def later(moment: list[datetime], minutes: int) -> None:
    moment[0] = NOW + timedelta(minutes=minutes)


def cards(world: HeldWorld) -> list[dict]:
    return [message for message in world.discord.messages if message["embeds"]]


def test_an_unsaved_token_is_its_round_s_status_and_pings_at_once(
    store: Store, settings: Settings, keychain: SaveFails
) -> None:
    world = HeldWorld(keychain)
    lines = world.both_round(store, settings)
    assert lines[0] == UNSAVED_LINE
    assert "outlook live: ok" not in lines
    assert posted(world) == [UNSAVED_ALERT]


def test_no_mail_is_read_while_the_token_is_unsaved(
    store: Store, settings: Settings, keychain: SaveFails, moment: list[datetime]
) -> None:
    world = HeldWorld(keychain)
    arrive_outlook(world, 1, NOW)
    assert world.both_round(store, settings)[0] == UNSAVED_LINE
    later(moment, 5)
    world.both_round(store, settings)
    assert [r for r in world.graph.requests if r.url.host == "graph.microsoft.com"] == []
    assert cards(world) == []
    assert store.sync_state("outlook", "live") is None


def test_the_ping_is_sent_once_however_many_rounds_stay_unsaved(
    store: Store, settings: Settings, keychain: SaveFails, moment: list[datetime]
) -> None:
    world = HeldWorld(keychain)
    for minutes in range(0, 50, 5):
        later(moment, minutes)
        world.both_round(store, settings)
    assert [line for line in world.lines if line.startswith("outlook ")] == [UNSAVED_LINE]
    assert posted(world) == [UNSAVED_ALERT]
    assert keychain.tries == [TOKEN_NAME] * 10


def test_the_round_after_the_keychain_recovers_saves_reads_and_says_so(
    store: Store, settings: Settings, keychain: SaveFails, moment: list[datetime]
) -> None:
    world = HeldWorld(keychain)
    world.both_round(store, settings)
    keychain.refuse = False
    later(moment, 5)
    arrive_outlook(world, 1, NOW)
    world.model.replies.append(GOOD)
    assert world.both_round(store, settings)[0] == "outlook live: ok"
    assert len(cards(world)) == 1
    assert posted(world) == [UNSAVED_ALERT, SAVED]
    assert keychain.secrets[TOKEN_NAME] == world.graph.refresh_token
    later(moment, 10)
    world.both_round(store, settings)
    assert posted(world) == [UNSAVED_ALERT, SAVED]


def test_a_second_unsaved_episode_pings_again(
    store: Store, settings: Settings, keychain: SaveFails, moment: list[datetime]
) -> None:
    world = HeldWorld(keychain)
    world.both_round(store, settings)
    keychain.refuse = False
    later(moment, 5)
    world.both_round(store, settings)
    keychain.refuse = True
    later(moment, 125)
    assert world.both_round(store, settings)[0] == UNSAVED_LINE
    assert posted(world) == [UNSAVED_ALERT, SAVED, UNSAVED_ALERT]


def test_a_restart_before_the_save_asks_for_sign_in_and_is_not_called_saved(
    store: Store, settings: Settings, keychain: SaveFails, moment: list[datetime]
) -> None:
    world = HeldWorld(keychain)
    world.both_round(store, settings)
    keychain.refuse = False
    world.restart()
    later(moment, 5)
    assert world.both_round(store, settings)[0] == "outlook live: outlook sign-in needed: live"
    assert posted(world) == [UNSAVED_ALERT, SIGN_IN]
    keychain.secrets[TOKEN_NAME] = world.graph.refresh_token
    later(moment, 10)
    assert world.both_round(store, settings)[0] == "outlook live: ok"
    assert sorted(posted(world)[2:]) == sorted(["Outlook live works again.", SAVED])


def test_other_outlook_failures_leave_the_unsaved_alert_open(
    store: Store, settings: Settings, keychain: SaveFails, moment: list[datetime]
) -> None:
    world = HeldWorld(keychain)
    world.both_round(store, settings)
    keychain.refuse = False
    world.graph.token_failures.append(httpx.Response(503))
    later(moment, 5)
    assert world.both_round(store, settings)[0] == "outlook live: outlook unavailable: live (503)"
    assert posted(world) == [UNSAVED_ALERT]
    later(moment, 10)
    assert world.both_round(store, settings)[0] == "outlook live: ok"
    assert posted(world) == [UNSAVED_ALERT, SAVED]


def test_no_token_text_reaches_a_status_line_or_alert(
    store: Store, settings: Settings, keychain: SaveFails, moment: list[datetime]
) -> None:
    world = HeldWorld(keychain)
    for minutes in (0, 5):
        later(moment, minutes)
        world.both_round(store, settings)
    keychain.refuse = False
    later(moment, 10)
    world.both_round(store, settings)
    shown = world.lines + posted(world)
    assert UNSAVED_LINE in world.lines
    assert not [text for text in shown if re.search(r"refresh-token-\d|access-\d", text)]
