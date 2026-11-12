import base64
import hashlib
import secrets
from collections.abc import Callable
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx

from mailroom import clock, gmail, keychain

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
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


def consent_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    return str(
        httpx.URL(
            AUTH_URL,
            params={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": gmail.SCOPE,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            },
        )
    )


class Callback:
    def __init__(self, account: str, *, request_timeout: float = REQUEST_TIMEOUT_SECONDS) -> None:
        self._account = account
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
                raise LoginError(f"gmail login timed out: {self._account}") from None
            self._server.timeout = (deadline - moment).total_seconds()
            self._server.handle_request()
            if self._code is not None:
                return self._code
            if self._cancelled:
                raise LoginError(f"gmail login cancelled: {self._account}") from None

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


def exchange_code(
    http: httpx.Client,
    account: str,
    *,
    client_id: str,
    client_secret: str,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> str:
    try:
        response = http.post(
            gmail.TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
    except httpx.TransportError:
        raise LoginError(f"gmail login failed: {account} (network)") from None
    if response.status_code != 200:
        raise LoginError(f"gmail login failed: {account} ({response.status_code})") from None
    try:
        body = response.json()
        refresh_token = body.get("refresh_token")
        scope = body.get("scope")
    except (ValueError, AttributeError):
        raise LoginError(f"gmail login failed: {account} (response)") from None
    if not isinstance(refresh_token, str) or not isinstance(scope, str):
        raise LoginError(f"gmail login failed: {account} (response)") from None
    if set(scope.split()) != {gmail.SCOPE}:
        raise LoginError(f"gmail login scope refused: {account}") from None
    return refresh_token


def login(
    account: str,
    http: httpx.Client,
    *,
    ask: Callable[[str], str],
    open_browser: Callable[[str], object],
    new_client: bool = False,
) -> str:
    client = gmail.GmailClient(account, http)
    client_id, client_secret, asked = _client_keys(account, ask, new_client=new_client)
    verifier = new_verifier()
    state = secrets.token_urlsafe(32)
    with Callback(account) as callback:
        open_browser(consent_url(client_id, callback.redirect_uri, state, code_challenge(verifier)))
        code = callback.wait(state)
        refresh_token = exchange_code(
            http,
            account,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            verifier=verifier,
            redirect_uri=callback.redirect_uri,
        )
    if asked:
        keychain.set_secret(f"gmail.{account}.client-id", client_id)
        keychain.set_secret(f"gmail.{account}.client-secret", client_secret)
    keychain.set_secret(f"gmail.{account}.refresh-token", refresh_token)
    return client.profile().email_address


def new_http() -> httpx.Client:
    return httpx.Client(timeout=gmail.TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)


def _client_keys(
    account: str, ask: Callable[[str], str], *, new_client: bool
) -> tuple[str, str, bool]:
    if not new_client:
        try:
            client_id = keychain.get_secret(f"gmail.{account}.client-id")
            client_secret = keychain.get_secret(f"gmail.{account}.client-secret")
        except keychain.SecretMissing:
            pass
        else:
            return client_id, client_secret, False
    return ask("Gmail OAuth client ID"), ask("Gmail OAuth client secret"), True
