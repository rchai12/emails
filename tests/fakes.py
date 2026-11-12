"""Fakes for systems tests must never reach. They import nothing from mailroom."""

import base64
import hashlib
import json

import httpx
from keyring.backend import KeyringBackend
from keyring.compat import properties


class FakeKeychain(KeyringBackend):
    """An in-memory keychain. `secrets` maps (service, name) to a value.

    `calls` records every (service, name) asked for and `writes` every one stored. When `error` is
    set, every call raises it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.secrets: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str]] = []
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
        if self.error is not None:
            raise self.error
        self.writes.append((service, username))
        self.secrets[(service, username)] = password

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
        self.granted_scope = "https://www.googleapis.com/auth/gmail.readonly"
        self.codes: dict[str, dict[str, str]] = {}
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

    def consent(self, url: str, *, approve: bool = True) -> str:
        """Google's consent page: check the request, and return where it sends the browser.

        An approved consent gives a one-time code, kept with the request's PKCE challenge and
        redirect address; the token endpoint checks both when the code is exchanged.
        """
        request = httpx.URL(url)
        params = request.params
        expected = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
            "code_challenge_method": "S256",
        }
        assert (request.scheme, request.host, request.path) == (
            "https",
            "accounts.google.com",
            "/o/oauth2/v2/auth",
        ), "not Google's consent page"
        for key, value in expected.items():
            assert params.get_list(key) == [value], f"consent request: {key}"
        for key in ("redirect_uri", "code_challenge", "state"):
            assert len(params.get_list(key)) == 1, f"consent request: {key}"
        redirect = params["redirect_uri"]
        if not approve:
            return str(
                httpx.URL(redirect, params={"error": "access_denied", "state": params["state"]})
            )
        code = f"code-{len(self.codes) + 1}"
        self.codes[code] = {"challenge": params["code_challenge"], "redirect_uri": redirect}
        answer = {"state": params["state"], "code": code, "scope": self.granted_scope}
        return str(httpx.URL(redirect, params=answer))

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
        if form.get("grant_type") == "authorization_code":
            return self._exchange(request, form)
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

    def _exchange(self, request: httpx.Request, form: dict[str, str]) -> httpx.Response:
        """The authorization-code grant: a code is used once, with its PKCE verifier."""
        grant = self.codes.pop(form.get("code", ""), None)
        verifier = form.get("code_verifier", "")
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        keys = {"code", "client_id", "client_secret", "redirect_uri", "grant_type", "code_verifier"}
        if (
            request.method != "POST"
            or set(form) != keys
            or grant is None
            or (form["client_id"], form["client_secret"]) != (self.client_id, self.client_secret)
            or form["redirect_uri"] != grant["redirect_uri"]
            or challenge != grant["challenge"]
        ):
            return httpx.Response(
                400,
                json={"error": "invalid_grant", "error_description": "Bad Request"},
            )
        self.refresh_token = f"refresh-token-from-{form['code']}"
        token = f"access-{len(self.issued) + 1}"
        self.issued.append(token)
        self.valid.add(token)
        return httpx.Response(
            200,
            json={
                "access_token": token,
                "expires_in": self.expires_in,
                "refresh_token": self.refresh_token,
                "scope": self.granted_scope,
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


class FakeOllama:
    """Ollama's `POST /api/chat`, non-streaming, for httpx.MockTransport.

    Each call answers with the next entry of `replies`: a dict (sent as the JSON text of
    `message.content`), a string (sent as the content as it is), an `httpx.Response`, or an
    exception to raise. `done_reason` is "stop" unless the entry is a `(content, done_reason)`
    pair. An unknown model gets 404, as Ollama answers. Every request is kept in `requests`.
    """

    URL = "http://127.0.0.1:11434/api/chat"

    def __init__(self) -> None:
        self.model = "qwen-test:27b"
        self.replies: list[object] = []
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method != "POST" or request.url.path != "/api/chat":
            return httpx.Response(404, text="404 page not found")
        body = json.loads(request.content)
        if body.get("model") != self.model:
            return httpx.Response(404, json={"error": f"model '{body.get('model')}' not found"})
        if body.get("stream") is not False or "format" not in body:
            return httpx.Response(400, json={"error": "mailroom asks for one JSON reply"})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        content, done_reason = reply if isinstance(reply, tuple) else (reply, "stop")
        text = content if isinstance(content, str) else json.dumps(content)
        return httpx.Response(
            200,
            json={
                "model": self.model,
                "created_at": "2026-11-12T09:00:00.000000Z",
                "message": {"role": "assistant", "content": text},
                "done": True,
                "done_reason": done_reason,
                "total_duration": 4_000_000_000,
                "eval_count": 120,
            },
        )


class FakeDiscord:
    """Discord's REST API v10 Create Message, for httpx.MockTransport, checked against the docs.

    `POST /api/v10/channels/<channel_id>/messages` with `Authorization: Bot <token>` and a
    `DiscordBot (...)` User-Agent. The body is checked against the documented limits: content 2000,
    nonce 25, 10 embeds with title 256, description 4096, 25 fields (name 256, value 1024), footer
    2048 and 6000 in all; at most 5 action rows of at most 5 buttons; a button's label at most 80;
    a non-link button needs a unique `custom_id` of 1 to 100 and no `url`; a link button (style 5)
    needs a `url` of at most 512 and no `custom_id`. A breach answers 400 with code 50035. With
    `enforce_nonce` and a nonce already used, the existing message is returned and nothing is made.

    Each entry of `failures` answers one request before any check: an exception is raised, a
    response is returned, and "lost-reply" creates the message and then raises `ReadTimeout`, as
    if the reply were lost. `messages` holds every message made; `requests` every request.

    Interactions: `press(custom_id)` and `submit(custom_id, value)` return the Gateway's
    INTERACTION_CREATE data for a button press (type 3) or a form submission (type 5, a Label
    holding a Text Input), from `owner_id` in `channel_id` unless told otherwise.
    `POST /api/v10/interactions/<id>/<token>/callback` needs the User-Agent but no Authorization.
    It answers 204,
    or 404 (code 10062) for an unknown interaction and 400 (code 40060) for a second response.
    It also answers 400 (code 50035) for a type the interaction can't take: 4, 6, 7 or 9 for a
    press, and 4, 6 or 7 for a submission. Messages (4, 7) are checked like a new message, with
    only flag 64 allowed. A form (9) needs a `custom_id` of 1 to 100, a title of 1 to 45, and 1 to
    5 Labels (type 18, label 1 to 45), each holding a Text Input (type 4) with a `custom_id` of 1
    to 100, style 1 or 2, lengths within 0 to 4000 and a value of at most 4000. `callbacks` holds
    every accepted (interaction id, body).
    """

    API = "https://discord.com/api/v10"

    def __init__(self) -> None:
        self.token = "discord-token-test"
        self.channel_id = "111111111111111111"
        self.messages: list[dict] = []
        self.requests: list[httpx.Request] = []
        self.failures: list[object] = []
        self.owner_id = "444444444444444444"
        self.callbacks: list[tuple[str, dict]] = []
        self._interactions: dict[str, dict] = {}

    def press(
        self,
        custom_id: str,
        *,
        user_id: str | None = None,
        channel_id: str | None = None,
        message_id: str = "1300000000000000001",
    ) -> dict:
        data = {"custom_id": custom_id, "component_type": 2}
        return self._interaction(3, data, user_id, channel_id, message_id)

    def submit(self, custom_id: str, value: str, *, user_id: str | None = None) -> dict:
        text_input = {"type": 4, "id": 2, "custom_id": "title", "value": value}
        data = {
            "custom_id": custom_id,
            "components": [{"type": 18, "id": 1, "component": text_input}],
        }
        return self._interaction(5, data, user_id, None, "1300000000000000001")

    def _interaction(
        self, kind: int, data: dict, user_id: str | None, channel_id: str | None, message_id: str
    ) -> dict:
        number = len(self._interactions) + 1
        interaction_id = str(1400000000000000000 + number)
        channel = channel_id or self.channel_id
        event = {
            "id": interaction_id,
            "application_id": "222222222222222222",
            "type": kind,
            "token": f"interaction-token-{number}",
            "version": 1,
            "guild_id": "333333333333333333",
            "channel_id": channel,
            "member": {
                "user": {"id": user_id or self.owner_id, "username": "someone"},
                "roles": [],
            },
            "data": data,
            "message": {"id": message_id, "channel_id": channel},
        }
        self._interactions[interaction_id] = {"event": event, "answered": False}
        return event

    def _callback(self, request: httpx.Request) -> httpx.Response:
        if not request.headers.get("user-agent", "").startswith("DiscordBot ("):
            return httpx.Response(403, text="error code: 1010")
        parts = request.url.path.split("/")
        known = self._interactions.get(parts[4]) if len(parts) == 7 else None
        if request.method != "POST" or known is None or known["event"]["token"] != parts[5]:
            return httpx.Response(404, json={"message": "Unknown interaction", "code": 10062})
        if known["answered"]:
            return httpx.Response(
                400, json={"message": "Interaction has already been acknowledged.", "code": 40060}
            )
        body = json.loads(request.content)
        allowed = (4, 6, 7, 9) if known["event"]["type"] == 3 else (4, 6, 7)
        kind = body.get("type")
        data = body.get("data", {})
        if kind not in allowed:
            problem = "response type"
        elif kind in (4, 7):
            problem = self._problem(data) or (
                "flags" if data.get("flags", 0) not in (0, 64) else ""
            )
        elif kind == 9:
            problem = self._form_problem(data)
        else:
            problem = "data" if data else ""
        if problem:
            return httpx.Response(
                400, json={"message": "Invalid Form Body", "code": 50035, "errors": problem}
            )
        known["answered"] = True
        self.callbacks.append((parts[4], body))
        return httpx.Response(204)

    @staticmethod
    def _form_problem(data: dict) -> str:
        if (
            not 0 < len(data.get("custom_id", "")) <= 100
            or not 0 < len(data.get("title", "")) <= 45
        ):
            return "form"
        labels = data.get("components", [])
        if not 0 < len(labels) <= 5:
            return "form components"
        for label in labels:
            field = label.get("component", {})
            if label.get("type") != 18 or not 0 < len(label.get("label", "")) <= 45:
                return "label"
            if field.get("type") != 4 or field.get("style") not in (1, 2):
                return "text input"
            if not 0 < len(field.get("custom_id", "")) <= 100:
                return "text input custom_id"
            low, high = field.get("min_length", 0), field.get("max_length", 4000)
            if not (0 <= low <= 4000 and 1 <= high <= 4000 and low <= high):
                return "text input lengths"
            if len(field.get("value", "")) > 4000:
                return "text input value"
        return ""

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        lost = False
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            if isinstance(failure, httpx.Response):
                return failure
            lost = failure == "lost-reply"
        if request.url.path.startswith("/api/v10/interactions/"):
            return self._callback(request)
        if request.headers.get("authorization") != f"Bot {self.token}":
            return httpx.Response(401, json={"message": "401: Unauthorized", "code": 0})
        if not request.headers.get("user-agent", "").startswith("DiscordBot ("):
            return httpx.Response(403, text="error code: 1010")
        path = f"/api/v10/channels/{self.channel_id}/messages"
        if request.method != "POST" or request.url.path != path:
            return httpx.Response(404, json={"message": "Unknown Channel", "code": 10003})
        body = json.loads(request.content)
        problem = self._problem(body)
        if problem:
            return httpx.Response(
                400, json={"message": "Invalid Form Body", "code": 50035, "errors": problem}
            )
        if body.get("enforce_nonce") and body.get("nonce") is not None:
            for message in self.messages:
                if message["nonce"] == body["nonce"]:
                    return httpx.Response(200, json=message)
        message = {
            "id": str(1300000000000000001 + len(self.messages)),
            "channel_id": self.channel_id,
            "type": 0,
            "content": body.get("content", ""),
            "embeds": body.get("embeds", []),
            "components": body.get("components", []),
            "nonce": body.get("nonce"),
            "timestamp": "2026-11-12T09:00:00.000000+00:00",
        }
        self.messages.append(message)
        if lost:
            raise httpx.ReadTimeout("reply lost")
        return httpx.Response(200, json=message)

    @staticmethod
    def _problem(body: dict) -> str:
        if not (body.get("content") or body.get("embeds") or body.get("components")):
            return "empty message"
        if len(body.get("content", "")) > 2000:
            return "content"
        nonce = body.get("nonce")
        if nonce is not None and (not isinstance(nonce, str | int) or len(str(nonce)) > 25):
            return "nonce"
        mentions = body.get("allowed_mentions", {"parse": []})
        if not set(mentions.get("parse", [])) <= {"roles", "users", "everyone"}:
            return "allowed_mentions"
        embeds = body.get("embeds", [])
        total = 0
        if len(embeds) > 10:
            return "embeds"
        for embed in embeds:
            limits = [("title", 256), ("description", 4096)]
            for key, limit in limits:
                if len(embed.get(key, "")) > limit:
                    return f"embed {key}"
                total += len(embed.get(key, ""))
            fields = embed.get("fields", [])
            if len(fields) > 25:
                return "embed fields"
            for field in fields:
                if not 0 < len(field["name"]) <= 256 or not 0 < len(field["value"]) <= 1024:
                    return "embed field"
                total += len(field["name"]) + len(field["value"])
            footer = embed.get("footer", {}).get("text", "")
            if len(footer) > 2048:
                return "embed footer"
            total += len(footer)
        if total > 6000:
            return "embeds total"
        rows = body.get("components", [])
        if len(rows) > 5:
            return "components"
        seen: set[str] = set()
        for row in rows:
            buttons = row.get("components", [])
            if row.get("type") != 1 or not 0 < len(buttons) <= 5:
                return "action row"
            for button in buttons:
                if button.get("type") != 2 or button.get("style") not in (1, 2, 3, 4, 5):
                    return "button"
                if len(button.get("label", "")) > 80:
                    return "button label"
                if button["style"] == 5:
                    url = button.get("url", "")
                    if "custom_id" in button or not 0 < len(url) <= 512:
                        return "link button"
                else:
                    custom_id = button.get("custom_id", "")
                    if "url" in button or not 0 < len(custom_id) <= 100 or custom_id in seen:
                        return "button custom_id"
                    seen.add(custom_id)
        return ""
