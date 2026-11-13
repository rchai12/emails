import logging

import pytest
import websockets.sync.client

from mailroom.gateway import GATEWAY_URL_MESSAGE, gateway_url_allowed, open_gateway


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("wss://gateway.discord.gg/?v=10&encoding=json", True),
        ("wss://gateway-us-east1-b.discord.gg/?v=10&encoding=json", True),
        ("ws://gateway.discord.gg/?v=10&encoding=json", False),
        ("https://gateway.discord.gg/?v=10&encoding=json", False),
        ("wss://gateway.discord.gg.evil.test/?v=10&encoding=json", False),
        ("wss://evildiscord.gg/?v=10&encoding=json", False),
        ("wss://discord.gg/?v=10&encoding=json", False),
        ("wss://user@gateway.discord.gg/?v=10&encoding=json", False),
        ("wss://gateway.discord.gg:8443/?v=10&encoding=json", False),
        ("wss://gateway.discord.gg/other?v=10&encoding=json", False),
    ],
    ids=[
        "gateway",
        "regional",
        "not-tls",
        "not-websocket",
        "look-alike-suffix",
        "look-alike-name",
        "bare-domain",
        "user-name",
        "port",
        "path",
    ],
)
def test_only_discord_gateway_addresses_are_allowed(url: str, allowed: bool) -> None:
    assert gateway_url_allowed(url) is allowed


def test_a_refused_address_is_never_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("connected")

    monkeypatch.setattr(websockets.sync.client, "connect", fail)
    with pytest.raises(ValueError) as caught:
        open_gateway("wss://gateway.discord.gg.evil.test/?v=10&encoding=json")
    assert (
        str(caught.value) == GATEWAY_URL_MESSAGE == "refused a Gateway address outside discord.gg"
    )


def test_the_connection_is_direct_quiet_and_bounded(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(
        websockets.sync.client, "connect", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    open_gateway("wss://gateway.discord.gg/?v=10&encoding=json")
    ((args, kwargs),) = calls
    logger = kwargs.pop("logger")
    assert args == ("wss://gateway.discord.gg/?v=10&encoding=json",)
    assert kwargs == {
        "user_agent_header": "DiscordBot (mailroom, 0.1.0)",
        "proxy": None,
        "compression": None,
        "ping_interval": None,
        "open_timeout": 30.0,
        "max_size": 1048576,
    }
    caplog.set_level(logging.DEBUG)
    for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
        assert logger.isEnabledFor(level) is False
        logger.log(level, "> TEXT %s", '{"op": 2, "d": {"token": "discord-token-test"}}')
    assert caplog.text == ""
