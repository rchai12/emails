"""Slash commands that trust, untrust, unmute and list senders."""

import json
from typing import cast

import httpx

from mailroom import __version__, keychain
from mailroom import discord_layout as L
from mailroom.checkpoint import _block
from mailroom.config import Settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.store import Store


def register_commands(settings: Settings, http: httpx.Client) -> int:
    if settings.discord_guild_id == "":
        raise DiscordUnavailable("not configured") from None
    token = keychain.get_secret(L.TOKEN_NAME)
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": L.USER_AGENT.format(version=__version__),
    }
    found = _call(http, "GET", f"{L.API_URL}/applications/@me", headers)
    application = _body(found)
    application_id = application.get("id") if isinstance(application, dict) else None
    if not isinstance(application_id, str):
        raise DiscordUnavailable("response") from None
    replaced = _call(
        http,
        "PUT",
        f"{L.API_URL}/applications/{application_id}/guilds/{settings.discord_guild_id}/commands",
        headers,
        list(L.COMMANDS),
    )
    commands = _body(replaced)
    if not isinstance(commands, list):
        raise DiscordUnavailable("response") from None
    return len(commands)


def handle_command(event: dict[str, object], store: Store) -> tuple[str, str]:
    data = cast(dict[str, object], event["data"])
    name = data["name"]
    if name == "trusted" or name == "muted":
        return "listed", _listed(store, str(name))
    raw = _raw_address(data)
    if not isinstance(raw, str):
        return "bad-address", L.BAD_ADDRESS_TEXT
    try:
        status = store.sender_status(raw)
    except ValueError:
        return "bad-address", L.BAD_ADDRESS_TEXT
    lowered = raw.lower()
    if name == "trust":
        store.set_sender_status(lowered, "trusted")
        return "trusted", L.TRUSTED_REPLY + "\n" + _block(lowered)
    if name == "untrust":
        return _cleared(
            store, lowered, status, "trusted", "untrusted", L.UNTRUSTED_REPLY, L.NOT_TRUSTED_REPLY
        )
    return _cleared(store, lowered, status, "muted", "unmuted", L.UNMUTED_REPLY, L.NOT_MUTED_REPLY)


def _call(
    http: httpx.Client,
    method: str,
    url: str,
    headers: dict[str, str],
    payload: object = None,
) -> httpx.Response:
    try:
        if method == "GET":
            return http.get(url, headers=headers)
        return http.put(url, headers=headers, json=payload)
    except httpx.TransportError:
        raise DiscordUnavailable("network") from None


def _body(response: httpx.Response) -> object:
    if response.status_code != 200:
        raise DiscordUnavailable(str(response.status_code)) from None
    try:
        return response.json()
    except json.JSONDecodeError:
        raise DiscordUnavailable("response") from None


def _raw_address(data: dict[str, object]) -> object:
    found: object = None
    for option in data.get("options") or []:
        if option.get("name") == L.ADDRESS_OPTION:
            found = option.get("value")
            break
    return found


def _cleared(
    store: Store,
    address: str,
    status: str | None,
    kind: str,
    outcome: str,
    removed: str,
    absent: str,
) -> tuple[str, str]:
    if status == kind:
        store.set_sender_status(address, None)
        return outcome, removed + "\n" + _block(address)
    return "unchanged", absent + "\n" + _block(address)


def _listed(store: Store, name: str) -> str:
    if name == "trusted":
        addresses, heading, empty = store.senders("trusted"), L.TRUSTED_LIST, L.NONE_TRUSTED
    else:
        addresses, heading, empty = store.senders("muted"), L.MUTED_LIST, L.NONE_MUTED
    if not addresses:
        return empty
    shown: list[str] = []
    for address in addresses:
        if len("\n".join([*shown, address])) > L.LIST_LIMIT:
            break
        shown.append(address)
    text = f"{heading}\n" + _block("\n".join(shown))
    rest = len(addresses) - len(shown)
    if rest:
        text += "\n" + L.MORE_TEXT.format(count=rest)
    return text
