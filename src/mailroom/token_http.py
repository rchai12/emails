"""A cached bearer token, its refresh post and the safe API request that uses it."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import unquote, urlsplit

import httpx

from mailroom import clock

TOKEN_MARGIN = timedelta(seconds=60)


@dataclass(frozen=True)
class Grant:
    access_token: str
    expires_in: int
    body: dict[str, object]


def _nothing() -> None:
    return None


class TokenSession:
    def __init__(
        self,
        http: httpx.Client,
        *,
        api_url: str,
        token_url: str,
        auth_codes: frozenset[str],
        refresh: Callable[[], Grant],
        auth_error: Callable[[], Exception],
        unavailable: Callable[[int | str], Exception],
        prepare: Callable[[], None] = _nothing,
    ) -> None:
        self._http = http
        self._api = urlsplit(api_url)
        self._token_url = token_url
        self._auth_codes = auth_codes
        self._refresh = refresh
        self._auth_error = auth_error
        self._unavailable = unavailable
        self._prepare = prepare
        self._token: str | None = None
        self._expiry: datetime | None = None

    def ensure(self) -> None:
        self._prepare()
        if self._token is None or self._expiry is None or clock.now() >= self._expiry:
            self._forget()
            grant = self._refresh()
            self._token = grant.access_token
            self._expiry = clock.now() + timedelta(seconds=grant.expires_in) - TOKEN_MARGIN

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        if not self._inside(url):
            raise self._unavailable("response") from None
        for _attempt in range(2):
            self.ensure()
            sent = {
                name: value
                for name, value in (headers or {}).items()
                if name.lower() != "authorization"
            }
            sent["Authorization"] = f"Bearer {self._token}"
            try:
                response = self._http.get(url, params=params, headers=sent)
            except httpx.TransportError:
                raise self._unavailable("network") from None
            if response.status_code != 401:
                return response
            self._forget()
        raise self._auth_error() from None

    def grant(self, form: dict[str, str]) -> Grant:
        try:
            response = self._http.post(self._token_url, data=form)
        except httpx.TransportError:
            raise self._unavailable("network") from None
        status = response.status_code
        if status in (400, 401) and self._refused(response):
            raise self._auth_error() from None
        if status != 200:
            raise self._unavailable(status) from None
        try:
            body = response.json()
        except ValueError:
            raise self._unavailable("response") from None
        if type(body) is not dict:
            raise self._unavailable("response") from None
        token = body.get("access_token")
        expires_in = body.get("expires_in")
        if type(token) is not str or type(expires_in) is not int:
            raise self._unavailable("response") from None
        return Grant(access_token=token, expires_in=expires_in, body=body)

    def _forget(self) -> None:
        self._token = None
        self._expiry = None

    def _refused(self, response: httpx.Response) -> bool:
        try:
            body = response.json()
        except ValueError:
            return False
        if type(body) is not dict:
            return False
        error = body.get("error")
        return type(error) is str and error in self._auth_codes

    def _inside(self, url: str) -> bool:
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return False
        path = unquote(parts.path)
        base = unquote(self._api.path)
        return (
            parts.scheme == "https"
            and parts.hostname == self._api.hostname
            and port is None
            and parts.username is None
            and parts.password is None
            and (path == base or path.startswith(base + "/"))
            and not {".", ".."} & set(path.split("/"))
        )
