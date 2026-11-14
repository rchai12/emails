"""Browser sign-in for one live.com account, as a public client, read-only."""

import secrets
from collections.abc import Callable

import httpx

from mailroom import keychain, outlook
from mailroom.gmail_login import Callback, LoginError, code_challenge, new_verifier

AUTH_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
CLIENT_ID_LABEL = "Microsoft app (client) ID"
_READ = "https://graph.microsoft.com/mail.read"
_ALLOWED = {_READ, "offline_access"}


def consent_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    return str(
        httpx.URL(
            AUTH_URL,
            params={
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "response_mode": "query",
                "scope": outlook.SCOPE,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            },
        )
    )


def exchange_code(
    http: httpx.Client,
    account: str,
    *,
    client_id: str,
    code: str,
    verifier: str,
    redirect_uri: str,
) -> str:
    try:
        response = http.post(
            outlook.TOKEN_URL,
            data={
                "client_id": client_id,
                "scope": outlook.SCOPE,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
    except httpx.TransportError:
        raise LoginError(f"outlook login failed: {account} (network)") from None
    if response.status_code != 200:
        raise LoginError(f"outlook login failed: {account} ({response.status_code})") from None
    try:
        body = response.json()
        refresh_token = body.get("refresh_token")
        scope = body.get("scope")
    except (ValueError, AttributeError):
        raise LoginError(f"outlook login failed: {account} (response)") from None
    if not isinstance(refresh_token, str) or refresh_token == "" or not isinstance(scope, str):
        raise LoginError(f"outlook login failed: {account} (response)") from None
    granted = {part.lower() for part in scope.split()}
    if _READ not in granted or not granted <= _ALLOWED:
        raise LoginError(f"outlook login scope refused: {account}") from None
    return refresh_token


def login(
    account: str,
    http: httpx.Client,
    *,
    ask: Callable[[str], str],
    open_browser: Callable[[str], object],
    new_client: bool = False,
) -> str:
    client = outlook.OutlookClient(account, http)
    client_id, asked = _client_id(account, ask, new_client=new_client)
    verifier = new_verifier()
    state = secrets.token_urlsafe(32)
    with Callback(account, provider="outlook") as callback:
        open_browser(consent_url(client_id, callback.redirect_uri, state, code_challenge(verifier)))
        code = callback.wait(state)
        refresh_token = exchange_code(
            http,
            account,
            client_id=client_id,
            code=code,
            verifier=verifier,
            redirect_uri=callback.redirect_uri,
        )
    if asked:
        keychain.set_secret(f"outlook.{account}.client-id", client_id)
    keychain.set_secret(f"outlook.{account}.refresh-token", refresh_token)
    return client.profile().email_address


def new_http() -> httpx.Client:
    return httpx.Client(timeout=outlook.TIMEOUT_SECONDS, trust_env=False, follow_redirects=False)


def _client_id(account: str, ask: Callable[[str], str], *, new_client: bool) -> tuple[str, bool]:
    if not new_client:
        try:
            return keychain.get_secret(f"outlook.{account}.client-id"), False
        except keychain.SecretMissing:
            pass
    return ask(CLIENT_ID_LABEL), True
