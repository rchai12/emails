from collections.abc import Iterator

import httpx
import pytest

from mailroom.config import Settings, get_settings
from mailroom.interactions import handle_interaction
from mailroom.store import Store, open_store
from tests.fakes import FakeDiscord


def ephemeral(text: str) -> dict:
    return {"type": 4, "data": {"content": text, "flags": 64, "allowed_mentions": {"parse": []}}}


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        opened.set_sender_status("trusted@example.test", "trusted")
        opened.set_sender_status("muted@example.test", "muted")
        yield opened


def use(store: Store, settings: Settings, event: dict, discord: FakeDiscord) -> tuple[str, object]:
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    before = len(discord.callbacks)
    outcome = handle_interaction(event, store, settings, http)
    replies = [body for _, body in discord.callbacks[before:]]
    assert len(replies) <= 1
    return outcome, replies[0] if replies else None


def test_trust_adds_the_exact_address_in_lower_case(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    outcome, reply = use(store, settings, discord.command("trust", "Sam@Example.TEST"), discord)
    assert (outcome, reply) == (
        "trusted",
        ephemeral("Added to your trusted senders:\n```\nsam@example.test\n```"),
    )
    assert store.sender_status("sam@example.test") == "trusted"


def test_trusting_a_muted_address_unmutes_it(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    outcome, _ = use(store, settings, discord.command("trust", "muted@example.test"), discord)
    assert outcome == "trusted"
    assert store.sender_status("muted@example.test") == "trusted"


@pytest.mark.parametrize(
    ("name", "address", "outcome", "text", "status"),
    [
        (
            "untrust",
            "trusted@example.test",
            "untrusted",
            "Removed from your trusted senders:",
            None,
        ),
        ("untrust", "muted@example.test", "unchanged", "Not on your trusted senders:", "muted"),
        ("unmute", "muted@example.test", "unmuted", "No longer muted:", None),
        ("unmute", "trusted@example.test", "unchanged", "Not on your muted senders:", "trusted"),
    ],
    ids=["untrust", "untrust-not-trusted", "unmute", "unmute-not-muted"],
)
def test_untrust_and_unmute_remove_only_their_own_status(
    store: Store,
    settings: Settings,
    name: str,
    address: str,
    outcome: str,
    text: str,
    status: str | None,
) -> None:
    discord = FakeDiscord()
    got, reply = use(store, settings, discord.command(name, address), discord)
    assert (got, reply) == (outcome, ephemeral(f"{text}\n```\n{address}\n```"))
    assert store.sender_status(address) == status


@pytest.mark.parametrize("name", ["trust", "untrust", "unmute"])
@pytest.mark.parametrize("address", ["not-an-address", "two@at@example.test", None])
def test_an_address_that_is_not_one_is_refused(
    store: Store, settings: Settings, name: str, address: str | None
) -> None:
    discord = FakeDiscord()
    outcome, reply = use(store, settings, discord.command(name, address), discord)
    assert (outcome, reply) == ("bad-address", ephemeral("That is not an email address."))
    assert store.senders("trusted") == ("trusted@example.test",)
    assert store.senders("muted") == ("muted@example.test",)


def test_the_lists_are_sorted_in_code_blocks(store: Store, settings: Settings) -> None:
    store.set_sender_status("a`b@example.test", "trusted")
    discord = FakeDiscord()
    trusted = use(store, settings, discord.command("trusted"), discord)
    muted = use(store, settings, discord.command("muted"), discord)
    assert trusted == (
        "listed",
        ephemeral("Your trusted senders:\n```\naˋb@example.test\ntrusted@example.test\n```"),
    )
    assert muted == ("listed", ephemeral("Your muted senders:\n```\nmuted@example.test\n```"))


def test_empty_lists_say_so(settings: Settings) -> None:
    discord = FakeDiscord()
    with open_store(get_settings()) as empty:
        trusted = use(empty, settings, discord.command("trusted"), discord)
        muted = use(empty, settings, discord.command("muted"), discord)
    assert trusted == ("listed", ephemeral("You have no trusted senders."))
    assert muted == ("listed", ephemeral("You have no muted senders."))


def test_a_long_list_is_cut_with_a_count(store: Store, settings: Settings) -> None:
    addresses = [f"{'a' * 190}{index:02d}@example.test" for index in range(12)]
    for address in addresses:
        store.set_sender_status(address, "muted")
    discord = FakeDiscord()
    _, reply = use(store, settings, discord.command("muted"), discord)
    shown = "\n".join(addresses[:8])
    assert reply == ephemeral(f"Your muted senders:\n```\n{shown}\n```\n...and 5 more.")


@pytest.mark.parametrize(
    "where",
    [{"user_id": "555555555555555555"}, {"channel_id": "999999999999999999"}],
    ids=["another-user", "another-channel"],
)
def test_a_command_from_anyone_else_or_elsewhere_is_refused(
    store: Store, settings: Settings, where: dict
) -> None:
    discord = FakeDiscord()
    event = discord.command("untrust", "trusted@example.test", **where)
    outcome, reply = use(store, settings, event, discord)
    assert (outcome, reply) == ("refused", ephemeral("Only the owner can use this here."))
    assert store.sender_status("trusted@example.test") == "trusted"


def test_a_command_that_is_not_ours_gets_no_reply(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    outcome, reply = use(store, settings, discord.command("mute", "x@example.test"), discord)
    assert (outcome, reply) == ("ignored", None)
    assert discord.requests == []
