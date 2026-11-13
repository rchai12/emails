import httpx
import pytest

from mailroom import __version__
from mailroom.config import Settings, get_settings
from mailroom.discord_post import PostReport, send_messages
from mailroom.keychain import SecretMissing
from tests.fakes import FakeDiscord, FakeKeychain

URL = "https://discord.com/api/v10/channels/111111111111111111/messages"
ITEMS = ("first", "second", "third")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    return get_settings()


@pytest.fixture
def discord(fake_keychain: FakeKeychain) -> FakeDiscord:
    fake = FakeDiscord()
    fake_keychain.secrets[("mailroom", "discord.bot-token")] = fake.token
    return fake


class Calls:
    """Records which bodies were built and which items were marked."""

    def __init__(self) -> None:
        self.built: list[str] = []
        self.marked: list[tuple[str, str]] = []

    def body(self, item: str) -> dict[str, object]:
        self.built.append(item)
        return {
            "content": f"Note {item}.",
            "allowed_mentions": {"parse": []},
            "nonce": f"nonce-{item}",
            "enforce_nonce": True,
        }

    def mark(self, item: str, message_id: str) -> None:
        self.marked.append((item, message_id))


def send(settings: Settings, discord: FakeDiscord, items: tuple[str, ...], calls: Calls):
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    return send_messages(settings, http, items, calls.body, calls.mark)


def test_nothing_to_send_reads_no_token_and_sends_nothing(
    settings: Settings, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    calls = Calls()
    assert send(settings, discord, (), calls) == PostReport(posted=0, waiting=0, stopped="")
    assert (fake_keychain.calls, discord.requests, calls.built, calls.marked) == ([], [], [], [])


def test_each_item_is_sent_in_order_and_marked_with_its_message_id(
    settings: Settings, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    calls = Calls()
    assert send(settings, discord, ITEMS, calls) == PostReport(posted=3, waiting=0, stopped="")
    assert [message["content"] for message in discord.messages] == [
        "Note first.",
        "Note second.",
        "Note third.",
    ]
    assert calls.marked == [
        (item, message["id"]) for item, message in zip(ITEMS, discord.messages, strict=True)
    ]
    assert fake_keychain.calls == [("mailroom", "discord.bot-token")]
    for request in discord.requests:
        assert (request.method, str(request.url)) == ("POST", URL)
        assert request.headers["Authorization"] == f"Bot {discord.token}"
        assert request.headers["User-Agent"] == f"DiscordBot (mailroom, {__version__})"


@pytest.mark.parametrize(
    ("failure", "stopped"),
    [
        (httpx.Response(429, json={"message": "Slow down.", "retry_after": 1.5}), "429"),
        (httpx.Response(503, text="busy"), "503"),
        (httpx.ConnectError("refused"), "network"),
        ("lost-reply", "network"),
        (httpx.Response(200, json={"channel_id": "111111111111111111"}), "response"),
    ],
    ids=["rate-limited", "server-error", "network", "lost-reply", "no-message-id"],
)
def test_a_failure_stops_at_that_item_and_builds_nothing_after_it(
    settings: Settings, discord: FakeDiscord, failure: object, stopped: str
) -> None:
    discord.failures.extend([None, failure])
    calls = Calls()
    assert send(settings, discord, ITEMS, calls) == PostReport(posted=1, waiting=2, stopped=stopped)
    assert calls.built == ["first", "second"]
    assert calls.marked == [("first", discord.messages[0]["id"])]


def test_a_missing_token_stops_before_anything_is_sent(
    settings: Settings, discord: FakeDiscord, fake_keychain: FakeKeychain
) -> None:
    del fake_keychain.secrets[("mailroom", "discord.bot-token")]
    calls = Calls()
    with pytest.raises(SecretMissing):
        send(settings, discord, ITEMS, calls)
    assert (discord.requests, calls.built, calls.marked) == ([], [], [])
