import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote, urlsplit

import httpx

from mailroom import clock, keychain
from mailroom.record import ACCOUNT_PATTERN

TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
API_URL = "https://graph.microsoft.com/v1.0/me"
SCOPE = "https://graph.microsoft.com/Mail.Read offline_access"
PAGE_SIZE = 50
TIMEOUT_SECONDS = 30.0
TOKEN_MARGIN = timedelta(seconds=60)
ACCOUNT_MESSAGE = "invalid account name"
MESSAGE_ID_MESSAGE = "invalid message id"
IMMUTABLE_ID = 'IdType="ImmutableId"'

_ACCOUNT = re.compile(ACCOUNT_PATTERN)
_MESSAGE_ID = re.compile(r"[A-Za-z0-9_=-]{1,512}")
_AUTH_ERRORS = frozenset({"invalid_grant", "interaction_required"})
_DELTA_PREFER = f"{IMMUTABLE_ID}, odata.maxpagesize={PAGE_SIZE}"


class OutlookError(Exception):
    pass


class OutlookAuthError(OutlookError):
    def __init__(self, account: str) -> None:
        super().__init__(f"outlook sign-in needed: {account}")


class OutlookUnavailable(OutlookError):
    def __init__(self, account: str, detail: int | str) -> None:
        super().__init__(f"outlook unavailable: {account} ({detail})")


class DeltaExpired(OutlookError):
    def __init__(self, account: str) -> None:
        super().__init__(f"outlook delta expired: {account}")


class MessageGone(OutlookError):
    def __init__(self, account: str) -> None:
        super().__init__(f"outlook message gone: {account}")


@dataclass(frozen=True)
class Profile:
    email_address: str
    inbox_id: str


@dataclass(frozen=True)
class MessageRef:
    id: str
    thread_id: str


@dataclass(frozen=True)
class Delta:
    added: tuple[MessageRef, ...]
    delta_link: str


@dataclass(frozen=True)
class RawMessage:
    id: str
    thread_id: str
    folder_id: str
    received_at: datetime
    web_link: str
    raw: bytes


class OutlookClient:
    def __init__(self, account: str, http: httpx.Client) -> None:
        if _ACCOUNT.fullmatch(account) is None:
            raise ValueError(ACCOUNT_MESSAGE)
        self.account = account
        self.http = http
        self._access_token: str | None = None
        self._expiry: datetime | None = None

    def profile(self) -> Profile:
        me = self._json(f"{API_URL}", {"$select": "mail,userPrincipalName"})
        inbox = self._json(f"{API_URL}/mailFolders/inbox", {"$select": "id"})
        return Profile(
            email_address=_address(me, self.account),
            inbox_id=_text(inbox.get("id"), self.account),
        )

    def first_delta(self, since: datetime) -> Delta:
        stamp = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._delta(
            f"{API_URL}/mailFolders/inbox/messages/delta",
            {
                "changeType": "created",
                "$select": "conversationId,receivedDateTime",
                "$filter": f"receivedDateTime ge {stamp}",
            },
        )

    def next_delta(self, delta_link: str) -> Delta:
        _check_delta_link(delta_link, self.account)
        return self._delta(delta_link, None)

    def fetch(self, message_id: str) -> RawMessage:
        if _MESSAGE_ID.fullmatch(message_id) is None:
            raise ValueError(MESSAGE_ID_MESSAGE)
        body = self._json(
            f"{API_URL}/messages/{message_id}",
            {"$select": "conversationId,parentFolderId,receivedDateTime,webLink"},
            gone=True,
        )
        raw = self._bytes(f"{API_URL}/messages/{message_id}/$value")
        return RawMessage(
            id=message_id,
            thread_id=_text(body.get("conversationId"), self.account),
            folder_id=_text(body.get("parentFolderId"), self.account),
            received_at=_received(body.get("receivedDateTime"), self.account),
            web_link=_text(body.get("webLink"), self.account),
            raw=raw,
        )

    def _delta(self, url: str, params: dict[str, str] | None) -> Delta:
        added: list[MessageRef] = []
        seen: set[str] = set()
        while True:
            page = self._json(url, params, delta=True)
            params = None
            for item in _items(page.get("value"), self.account):
                message_id = _message_id(item.get("id"), self.account)
                if "@removed" in item:
                    continue
                if message_id in seen:
                    continue
                seen.add(message_id)
                added.append(
                    MessageRef(
                        id=message_id,
                        thread_id=_text(item.get("conversationId"), self.account),
                    )
                )
            delta_link = page.get("@odata.deltaLink")
            if type(delta_link) is str:
                return Delta(added=tuple(added), delta_link=delta_link)
            next_link = page.get("@odata.nextLink")
            if type(next_link) is not str:
                raise self._bad()
            _check_delta_link(next_link, self.account)
            url = next_link

    def _json(
        self,
        url: str,
        params: dict[str, str] | None,
        *,
        delta: bool = False,
        gone: bool = False,
    ) -> dict[str, object]:
        response = self._get(url, params, delta=delta)
        if delta and _delta_expired(response):
            raise DeltaExpired(self.account) from None
        if gone and response.status_code == 404:
            raise MessageGone(self.account) from None
        if response.status_code != 200:
            raise OutlookUnavailable(self.account, response.status_code) from None
        return _object(self._parsed(response), self.account)

    def _bytes(self, url: str) -> bytes:
        response = self._get(url, None)
        if response.status_code == 404:
            raise MessageGone(self.account) from None
        if response.status_code != 200:
            raise OutlookUnavailable(self.account, response.status_code) from None
        return response.content

    def _get(
        self, url: str, params: dict[str, str] | None, *, delta: bool = False
    ) -> httpx.Response:
        prefer = _DELTA_PREFER if delta else IMMUTABLE_ID
        for _attempt in range(2):
            self._ensure_token()
            response = self._send(
                lambda: self.http.get(
                    url,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Prefer": prefer,
                    },
                )
            )
            if response.status_code != 401:
                return response
            self._access_token = None
        raise OutlookAuthError(self.account) from None

    def _ensure_token(self) -> None:
        if self._access_token is None or clock.now() >= self._expiry:
            self._refresh()

    def _refresh(self) -> None:
        try:
            client_id = keychain.get_secret(f"outlook.{self.account}.client-id")
            refresh_token = keychain.get_secret(f"outlook.{self.account}.refresh-token")
        except keychain.SecretMissing:
            raise OutlookAuthError(self.account) from None
        response = self._send(
            lambda: self.http.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": SCOPE,
                },
            )
        )
        if response.status_code in (400, 401) and _oauth_error(response) in _AUTH_ERRORS:
            raise OutlookAuthError(self.account) from None
        if response.status_code != 200:
            raise OutlookUnavailable(self.account, response.status_code) from None
        body = _object(self._parsed(response), self.account)
        token = body.get("access_token")
        expires_in = body.get("expires_in")
        if type(token) is not str or type(expires_in) is not int:
            raise self._bad()
        if "refresh_token" in body:
            rotated = body["refresh_token"]
            if type(rotated) is not str or rotated == "":
                raise self._bad()
            if rotated != refresh_token:
                keychain.set_secret(f"outlook.{self.account}.refresh-token", rotated)
        self._access_token = token
        self._expiry = clock.now() + timedelta(seconds=expires_in) - TOKEN_MARGIN

    def _parsed(self, response: httpx.Response) -> object:
        try:
            return response.json()
        except ValueError:
            raise self._bad() from None

    def _send(self, send: Callable[[], httpx.Response]) -> httpx.Response:
        try:
            return send()
        except httpx.TransportError:
            raise OutlookUnavailable(self.account, "network") from None

    def _bad(self) -> OutlookUnavailable:
        return OutlookUnavailable(self.account, "response")


def open_outlook(account: str) -> OutlookClient:
    http = httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)
    return OutlookClient(account, http)


def _check_delta_link(link: str, account: str) -> None:
    parts = urlsplit(link)
    path = unquote(parts.path)
    if (
        parts.scheme != "https"
        or parts.hostname != "graph.microsoft.com"
        or parts.port is not None
        or parts.username is not None
        or not path.startswith("/v1.0/me/mailFolders")
        or not path.endswith("/messages/delta")
    ):
        raise OutlookUnavailable(account, "response") from None


def _delta_expired(response: httpx.Response) -> bool:
    if response.status_code == 410:
        return True
    if response.status_code not in (400, 404):
        return False
    try:
        code = response.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return False
    return type(code) is str and code.lower() == "syncstatenotfound"


def _oauth_error(response: httpx.Response) -> str | None:
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return None
    if type(error) is str:
        return error
    return None


def _address(body: dict[str, object], account: str) -> str:
    mail = body.get("mail")
    if type(mail) is str and mail != "":
        return mail
    return _text(body.get("userPrincipalName"), account)


def _items(value: object, account: str) -> list[dict[str, object]]:
    if type(value) is not list:
        raise OutlookUnavailable(account, "response")
    items: list[dict[str, object]] = []
    for item in value:
        if type(item) is not dict:
            raise OutlookUnavailable(account, "response")
        items.append(item)
    return items


def _message_id(value: object, account: str) -> str:
    if type(value) is str and _MESSAGE_ID.fullmatch(value) is not None:
        return value
    raise OutlookUnavailable(account, "response")


def _object(value: object, account: str) -> dict[str, object]:
    if type(value) is not dict:
        raise OutlookUnavailable(account, "response")
    return value


def _text(value: object, account: str) -> str:
    if type(value) is str and value != "":
        return value
    raise OutlookUnavailable(account, "response")


def _received(value: object, account: str) -> datetime:
    text = _text(value, account)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise OutlookUnavailable(account, "response") from None
    if parsed.tzinfo is None:
        raise OutlookUnavailable(account, "response") from None
    return parsed.astimezone(UTC)
