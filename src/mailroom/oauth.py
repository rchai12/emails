"""Browser sign-in pieces shared by every provider: callback, PKCE and the token reply check."""

import base64
import hashlib
import secrets
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx

from mailroom import clock

CALLBACK_TIMEOUT = timedelta(minutes=5)
REQUEST_TIMEOUT_SECONDS = 5.0
DONE_PAGE = "Signed in to mailroom. You can close this tab."
CANCELLED_PAGE = "Sign-in cancelled. You can close this tab."
_BAD_PAGE = "Bad request."
_MISSING_PAGE = "Not found."


class LoginError(Exception):
    pass


def new_verifier() -> str:
    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class Callback:
    def __init__(
        self,
        account: str,
        *,
        provider: str,
        request_timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._account = account
        self._provider = provider
        self._state = ""
        self._code: str | None = None
        self._cancelled = False
        self._server = HTTPServer(("127.0.0.1", 0), _handler(self, request_timeout))
        host, port = self._server.server_address
        self.redirect_uri = f"http://{host}:{port}"

    def __enter__(self) -> "Callback":
        return self

    def __exit__(self, *_exc: object) -> None:
        self._server.server_close()

    def wait(self, state: str) -> str:
        self._state = state
        self._code = None
        self._cancelled = False
        deadline = clock.now() + CALLBACK_TIMEOUT
        while True:
            moment = clock.now()
            if moment >= deadline:
                raise LoginError(f"{self._provider} login timed out: {self._account}") from None
            self._server.timeout = (deadline - moment).total_seconds()
            self._server.handle_request()
            if self._code is not None:
                return self._code
            if self._cancelled:
                raise LoginError(f"{self._provider} login cancelled: {self._account}") from None

    def _handle(self, target: str) -> tuple[int, str]:
        parsed = urlsplit(target)
        if parsed.path != "/":
            return 404, _MISSING_PAGE
        query = parse_qs(parsed.query)
        if query.get("state") != [self._state]:
            return 400, _BAD_PAGE
        code = query.get("code", [])
        error = query.get("error", [])
        if len(code) == 1 and code[0] and not error:
            self._code = code[0]
            return 200, DONE_PAGE
        if len(error) == 1 and error[0] and not code:
            self._cancelled = True
            return 200, CANCELLED_PAGE
        return 400, _BAD_PAGE


def _handler(callback: Callback, request_timeout: float) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        timeout = request_timeout

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            status, page = callback._handle(self.path)
            body = page.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def token_reply(
    http: httpx.Client, url: str, data: dict[str, str], *, provider: str, account: str
) -> tuple[str, str]:
    """Post the token form once and return the refresh token and the granted scope."""
    try:
        response = http.post(url, data=data)
    except httpx.TransportError:
        raise LoginError(f"{provider} login failed: {account} (network)") from None
    if response.status_code != 200:
        raise LoginError(f"{provider} login failed: {account} ({response.status_code})") from None
    try:
        body = response.json()
        refresh_token = body.get("refresh_token")
        scope = body.get("scope")
    except (ValueError, AttributeError):
        raise LoginError(f"{provider} login failed: {account} (response)") from None
    if not isinstance(refresh_token, str) or refresh_token == "" or not isinstance(scope, str):
        raise LoginError(f"{provider} login failed: {account} (response)") from None
    return refresh_token, scope
