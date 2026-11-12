"""Fakes for systems tests must never reach. They import nothing from mailroom."""

import base64

import httpx
from keyring.backend import KeyringBackend
from keyring.compat import properties


class FakeKeychain(KeyringBackend):
    """An in-memory keychain. `secrets` maps (service, name) to a value.

    `calls` records every (service, name) asked for. When `error` is set, every call raises it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.secrets: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, str]] = []
        self.error: Exception | None = None

    @properties.classproperty
    def priority(cls) -> float:
        return 0

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append((service, username))
        if self.error is not None:
            raise self.error
        return self.secrets.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        raise AssertionError("mailroom never writes to the keychain in this phase")

    def delete_password(self, service: str, username: str) -> None:
        raise AssertionError("mailroom never deletes from the keychain in this phase")


class FakeGmail:
    """Google's token endpoint and the four Gmail calls mailroom reads, for httpx.MockTransport.

    Shapes follow the Gmail API reference: list fields are left out when empty, message ids in
    history records carry only `id` and `threadId`, `raw` is base64url without padding, and
    `internalDate` is epoch milliseconds as a string. Every request is kept in `requests`.
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API = "https://gmail.googleapis.com/gmail/v1/users/me"
    HISTORY_KEYS = {
        "messageAdded": "messagesAdded",
        "messageDeleted": "messagesDeleted",
        "labelAdded": "labelsAdded",
        "labelRemoved": "labelsRemoved",
    }

    def __init__(self) -> None:
        self.client_id = "client-id-1"
        self.client_secret = "client-secret-1"
        self.refresh_token = "refresh-token-1"
        self.email_address = "owner@example.test"
        self.history_id = 1000
        self.oldest_history_id = 0
        self.messages: dict[str, dict[str, object]] = {}
        self.history: list[dict[str, object]] = []
        self.page_size: int | None = None
        self.expires_in = 3599
        self.issued: list[str] = []
        self.valid: set[str] = set()
        self.failures: list[httpx.Response | Exception] = []
        self.requests: list[httpx.Request] = []

    def add_message(
        self,
        message_id: str,
        raw: bytes,
        *,
        thread_id: str | None = None,
        labels: tuple[str, ...] = ("INBOX", "UNREAD"),
        internal_ms: int = 1_793_000_000_000,
    ) -> None:
        """Deliver a message: store it and add a `messagesAdded` history record."""
        thread = thread_id or message_id
        self.messages[message_id] = {
            "threadId": thread,
            "labelIds": list(labels),
            "internalDate": str(internal_ms),
            "raw": raw,
        }
        self._record("messagesAdded", message_id, thread, list(labels), None)

    def add_labels(self, message_id: str, *labels: str) -> None:
        """Add labels to a stored message and a `labelsAdded` history record."""
        message = self.messages[message_id]
        current = [label for label in message["labelIds"] if label not in labels]
        message["labelIds"] = current + list(labels)
        thread = str(message["threadId"])
        self._record("labelsAdded", message_id, thread, list(message["labelIds"]), list(labels))

    def invalidate_tokens(self) -> None:
        """Every access token issued so far now gets 401."""
        self.valid.clear()

    def _record(
        self, kind: str, message_id: str, thread: str, labels: list[str], added: list[str] | None
    ) -> None:
        self.history_id += 1
        entry: dict[str, object] = {"message": {"id": message_id, "threadId": thread}}
        if added is not None:
            entry["labelIds"] = added
        self.history.append(
            {
                "id": str(self.history_id),
                "messages": [{"id": message_id, "threadId": thread}],
                kind: [entry],
                "_labels": labels,
            }
        )

    @staticmethod
    def _error(code: int, status: str, message: str) -> httpx.Response:
        return httpx.Response(
            code, json={"error": {"code": code, "message": message, "status": status}}
        )

    def _page(self, items: list, request: httpx.Request) -> tuple[list, str | None]:
        size = self.page_size or int(request.url.params.get("maxResults", "100"))
        start = int(request.url.params.get("pageToken", "0"))
        following = start + size
        return items[start:following], (str(following) if following < len(items) else None)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) == self.TOKEN_URL:
            return self._token(request)
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in self.valid:
            return self._error(401, "UNAUTHENTICATED", "Request had invalid credentials.")
        path = request.url.path.removeprefix("/gmail/v1/users/me")
        if request.method != "GET" or request.url.host != "gmail.googleapis.com":
            return self._error(400, "INVALID_ARGUMENT", "Not a call mailroom may make.")
        if path == "/profile":
            return httpx.Response(
                200,
                json={
                    "emailAddress": self.email_address,
                    "messagesTotal": len(self.messages),
                    "threadsTotal": len(self.messages),
                    "historyId": str(self.history_id),
                },
            )
        if path == "/history":
            return self._history(request)
        if path == "/messages":
            return self._list(request)
        if path.startswith("/messages/"):
            return self._get(request, path.removeprefix("/messages/"))
        return self._error(404, "NOT_FOUND", "Requested entity was not found.")

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        expected = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }
        if request.method != "POST" or form != expected:
            return httpx.Response(
                400,
                json={"error": "invalid_grant", "error_description": "Bad Request"},
            )
        token = f"access-{len(self.issued) + 1}"
        self.issued.append(token)
        self.valid.add(token)
        return httpx.Response(
            200,
            json={
                "access_token": token,
                "expires_in": self.expires_in,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
                "token_type": "Bearer",
            },
        )

    def _history(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        start = int(params["startHistoryId"])
        if start < self.oldest_history_id:
            return self._error(404, "NOT_FOUND", "Requested entity was not found.")
        label = params.get("labelId")
        kinds = params.get_list("historyTypes")
        records = []
        for record in self.history:
            if int(str(record["id"])) <= start:
                continue
            if label is not None and label not in record["_labels"]:
                continue
            if kinds and not any(self.HISTORY_KEYS[kind] in record for kind in kinds):
                continue
            records.append({key: value for key, value in record.items() if key != "_labels"})
        page, following = self._page(records, request)
        body: dict[str, object] = {"historyId": str(self.history_id)}
        if page:
            body["history"] = page
        if following is not None:
            body["nextPageToken"] = following
        return httpx.Response(200, json=body)

    def _list(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        query = params.get("q", "")
        after = int(query.removeprefix("after:")) * 1000 if query.startswith("after:") else 0
        wanted = params.get_list("labelIds")
        found = []
        for message_id, message in self.messages.items():
            labels = message["labelIds"]
            if {"SPAM", "TRASH"} & set(labels):
                continue
            if any(label not in labels for label in wanted):
                continue
            if int(str(message["internalDate"])) <= after:
                continue
            found.append((int(str(message["internalDate"])), message_id, message["threadId"]))
        found.sort(reverse=True)
        page, following = self._page(found, request)
        body: dict[str, object] = {"resultSizeEstimate": len(found)}
        if page:
            body["messages"] = [{"id": item[1], "threadId": item[2]} for item in page]
        if following is not None:
            body["nextPageToken"] = following
        return httpx.Response(200, json=body)

    def _get(self, request: httpx.Request, message_id: str) -> httpx.Response:
        if request.url.params.get("format") != "raw":
            return self._error(400, "INVALID_ARGUMENT", "mailroom asks for format=raw only.")
        message = self.messages.get(message_id)
        if message is None:
            return self._error(404, "NOT_FOUND", "Requested entity was not found.")
        raw = base64.urlsafe_b64encode(message["raw"]).decode().rstrip("=")
        return httpx.Response(
            200,
            json={
                "id": message_id,
                "threadId": message["threadId"],
                "labelIds": message["labelIds"],
                "snippet": "",
                "historyId": str(self.history_id),
                "internalDate": message["internalDate"],
                "sizeEstimate": len(message["raw"]),
                "raw": raw,
            },
        )
