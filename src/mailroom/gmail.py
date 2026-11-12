import base64
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from mailroom import clock, keychain

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
PAGE_SIZE = 500
TIMEOUT_SECONDS = 30.0
TOKEN_MARGIN = timedelta(seconds=60)
ACCOUNT_MESSAGE = "invalid account name"
MESSAGE_ID_MESSAGE = "invalid message id"

_ACCOUNT = re.compile(r"[a-z][a-z0-9-]{0,31}")
_MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,256}")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class GmailError(Exception):
    pass


class GmailAuthError(GmailError):
    def __init__(self, account: str) -> None:
        super().__init__(f"gmail sign-in needed: {account}")


class GmailUnavailable(GmailError):
    def __init__(self, account: str, detail: int | str) -> None:
        super().__init__(f"gmail unavailable: {account} ({detail})")


class BookmarkExpired(GmailError):
    def __init__(self, account: str) -> None:
        super().__init__(f"gmail history expired: {account}")


class MessageGone(GmailError):
    def __init__(self, account: str) -> None:
        super().__init__(f"gmail message gone: {account}")


@dataclass(frozen=True)
class Profile:
    email_address: str
    history_id: str


@dataclass(frozen=True)
class MessageRef:
    id: str
    thread_id: str


@dataclass(frozen=True)
class History:
    added: tuple[MessageRef, ...]
    history_id: str


@dataclass(frozen=True)
class RawMessage:
    id: str
    thread_id: str
    label_ids: tuple[str, ...]
    internal_date: datetime
    raw: bytes


def _invalid_grant(response: httpx.Response) -> bool:
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError, IndexError):
        error = None
    return error == "invalid_grant"


class GmailClient:
    def __init__(self, account: str, http: httpx.Client) -> None:
        if _ACCOUNT.fullmatch(account) is None:
            raise ValueError(ACCOUNT_MESSAGE)
        self.account = account
        self.http = http
        self._access_token: str | None = None
        self._expiry: datetime | None = None

    def profile(self) -> Profile:
        body = self._read("/profile", {})
        return Profile(
            email_address=self._text(body.get("emailAddress")),
            history_id=self._text(body.get("historyId")),
        )

    def history(self, start_history_id: str) -> History:
        pages = self._pages(
            "/history",
            {
                "startHistoryId": start_history_id,
                "labelId": "INBOX",
                "historyTypes": ["messageAdded", "labelAdded"],
                "maxResults": PAGE_SIZE,
            },
            expired_bookmark=True,
        )
        found: list[MessageRef] = []
        seen: set[str] = set()
        history_id = ""
        for page in pages:
            history_id = self._text(page.get("historyId"))
            for record in self._items(page, "history"):
                entry = self._mapping(record)
                self._collect(found, seen, self._items(entry, "messagesAdded"), inbox=False)
                self._collect(found, seen, self._items(entry, "labelsAdded"), inbox=True)
        return History(added=tuple(found), history_id=history_id)

    def list_inbox(self, after: datetime) -> tuple[MessageRef, ...]:
        pages = self._pages(
            "/messages",
            {
                "q": f"after:{int(after.timestamp())}",
                "labelIds": ["INBOX"],
                "maxResults": PAGE_SIZE,
            },
        )
        found: list[MessageRef] = []
        seen: set[str] = set()
        for page in pages:
            for item in self._items(page, "messages"):
                message = self._mapping(item)
                self._remember(found, seen, message.get("id"), message.get("threadId"))
        return tuple(found)

    def fetch(self, message_id: str) -> RawMessage:
        if _MESSAGE_ID.fullmatch(message_id) is None:
            raise ValueError(MESSAGE_ID_MESSAGE)
        body = self._read(f"/messages/{message_id}", {"format": "raw"}, gone=True)
        raw = self._raw_bytes(self._text(body.get("raw")))
        millis = self._millis(self._text(body.get("internalDate")))
        labels = tuple(self._text(label) for label in self._items(body, "labelIds"))
        return RawMessage(
            id=self._text(body.get("id")),
            thread_id=self._text(body.get("threadId")),
            label_ids=labels,
            internal_date=_EPOCH + timedelta(milliseconds=millis),
            raw=raw,
        )

    def _pages(
        self,
        path: str,
        params: dict[str, object],
        *,
        expired_bookmark: bool = False,
    ) -> list[dict[str, object]]:
        query = dict(params)
        pages: list[dict[str, object]] = []
        while True:
            body = self._read(path, query, expired_bookmark=expired_bookmark)
            pages.append(body)
            token = body.get("nextPageToken")
            if token is None:
                return pages
            query["pageToken"] = self._text(token)

    def _read(
        self,
        path: str,
        params: dict[str, object],
        *,
        expired_bookmark: bool = False,
        gone: bool = False,
    ) -> dict[str, object]:
        response = self._get(path, params)
        if expired_bookmark and response.status_code == 404:
            raise BookmarkExpired(self.account) from None
        if gone and response.status_code == 404:
            raise MessageGone(self.account) from None
        if response.status_code != 200:
            raise GmailUnavailable(self.account, response.status_code) from None
        return self._mapping(self._json_body(response))

    def _get(self, path: str, params: dict[str, object]) -> httpx.Response:
        for _ in range(2):
            response = self._request(path, params)
            if response.status_code != 401:
                return response
            self._access_token = None
        raise GmailAuthError(self.account) from None

    def _request(self, path: str, params: dict[str, object]) -> httpx.Response:
        self._ensure_token()
        return self._send(
            lambda: self.http.get(
                f"{API_URL}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        )

    def _ensure_token(self) -> None:
        if self._access_token is None or clock.now() >= self._expiry:
            self._refresh()

    def _refresh(self) -> None:
        try:
            client_id = keychain.get_secret(f"gmail.{self.account}.client-id")
            client_secret = keychain.get_secret(f"gmail.{self.account}.client-secret")
            refresh_token = keychain.get_secret(f"gmail.{self.account}.refresh-token")
        except keychain.SecretMissing:
            raise GmailAuthError(self.account) from None
        response = self._send(
            lambda: self.http.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        )
        if response.status_code in (400, 401) and _invalid_grant(response):
            raise GmailAuthError(self.account) from None
        if response.status_code != 200:
            raise GmailUnavailable(self.account, response.status_code) from None
        body = self._mapping(self._json_body(response))
        token = body.get("access_token")
        expires_in = body.get("expires_in")
        if type(token) is not str or type(expires_in) is not int:
            raise GmailUnavailable(self.account, "response") from None
        self._access_token = token
        self._expiry = clock.now() + timedelta(seconds=expires_in) - TOKEN_MARGIN

    def _json_body(self, response: httpx.Response) -> object:
        try:
            return response.json()
        except ValueError:
            raise GmailUnavailable(self.account, "response") from None

    def _collect(
        self,
        found: list[MessageRef],
        seen: set[str],
        entries: list[object],
        *,
        inbox: bool,
    ) -> None:
        for entry in entries:
            item = self._mapping(entry)
            if inbox and "INBOX" not in self._items(item, "labelIds"):
                continue
            message = self._mapping(item.get("message"))
            self._remember(found, seen, message.get("id"), message.get("threadId"))

    def _remember(
        self, found: list[MessageRef], seen: set[str], message_id: object, thread_id: object
    ) -> None:
        ref_id = self._text(message_id)
        if ref_id in seen:
            return
        seen.add(ref_id)
        found.append(MessageRef(id=ref_id, thread_id=self._text(thread_id)))

    def _items(self, body: dict[str, object], key: str) -> list[object]:
        return self._expect(body.get(key, []), list)

    def _mapping(self, value: object) -> dict[str, object]:
        return self._expect(value, dict)

    def _text(self, value: object) -> str:
        return self._expect(value, str)

    def _expect[T](self, value: object, kind: type[T]) -> T:
        if isinstance(value, kind):
            return value
        raise GmailUnavailable(self.account, "response") from None

    def _raw_bytes(self, text: str) -> bytes:
        try:
            return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        except ValueError:
            raise GmailUnavailable(self.account, "response") from None

    def _millis(self, text: str) -> int:
        try:
            return int(text)
        except ValueError:
            raise GmailUnavailable(self.account, "response") from None

    def _send(self, send: Callable[[], httpx.Response]) -> httpx.Response:
        try:
            return send()
        except httpx.TransportError:
            raise GmailUnavailable(self.account, "network") from None


def open_gmail(account: str) -> GmailClient:
    http = httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)
    return GmailClient(account, http)
