import secrets
from collections.abc import Callable

import httpx

from mailroom import gmail, keychain, oauth
from mailroom.oauth import (
    CALLBACK_TIMEOUT,
    CANCELLED_PAGE,
    DONE_PAGE,
    REQUEST_TIMEOUT_SECONDS,
    LoginError,
    code_challenge,
    new_verifier,
)

__all__ = [
    "AUTH_URL",
    "CALLBACK_TIMEOUT",
    "CANCELLED_PAGE",
    "DONE_PAGE",
    "REQUEST_TIMEOUT_SECONDS",
    "Callback",
    "LoginError",
    "code_challenge",
    "consent_url",
    "exchange_code",
    "login",
    "new_http",
    "new_verifier",
]

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


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


class Callback(oauth.Callback):
    def __init__(
        self,
        account: str,
        *,
        provider: str = "gmail",
        request_timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(account, provider=provider, request_timeout=request_timeout)


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
    refresh_token, scope = oauth.token_reply(
        http,
        gmail.TOKEN_URL,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
        provider="gmail",
        account=account,
    )
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
