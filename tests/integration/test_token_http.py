"""Phase 4m: the shared bearer-token session, run against a scripted token server and API."""

import importlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import ModuleType

import httpx
import pytest

from mailroom import clock

API = "https://api.example.test/v2/users/me"
TOKEN = "https://login.example.test/oauth/token"
FORM = {"client_id": "client-id-1", "refresh_token": "refresh-token-1"}
START = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)


class Failed(Exception):
    def __init__(self, kind: str, detail: object = None) -> None:
        super().__init__(kind, detail)
        self.kind = kind
        self.detail = detail


class World:
    """A token server and an API. Each answers from its queue, then with its default."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_replies: list[httpx.Response | Exception] = []
        self.api_replies: list[httpx.Response | Exception] = []
        self.issued = 0
        self.prepared = 0
        self.refreshed = 0
        self.expires_in = 3600

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST":
            if self.token_replies:
                return self._reply(self.token_replies.pop(0), request)
            self.issued += 1
            return httpx.Response(
                200,
                json={"access_token": f"access-{self.issued}", "expires_in": self.expires_in},
            )
        if self.api_replies:
            return self._reply(self.api_replies.pop(0), request)
        return httpx.Response(200, json={"ok": True})

    def _reply(self, reply: httpx.Response | Exception, request: httpx.Request) -> httpx.Response:
        if isinstance(reply, Exception):
            raise reply
        return reply

    def calls(self) -> list[tuple[str, str]]:
        return [
            (request.method, str(request.url.copy_with(query=None))) for request in self.requests
        ]


@pytest.fixture
def token_http() -> ModuleType:
    return importlib.import_module("mailroom.token_http")


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [START]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    return now


@pytest.fixture
def world() -> World:
    return World()


def session_for(
    token_http: ModuleType,
    world: World,
    *,
    refresh: Callable[[], object] | None = None,
) -> object:
    http = httpx.Client(transport=httpx.MockTransport(world.handler))
    holder: list[object] = []

    def default_refresh() -> object:
        world.refreshed += 1
        return holder[0].grant(dict(FORM))  # type: ignore[attr-defined]

    def prepare() -> None:
        world.prepared += 1

    session = token_http.TokenSession(
        http,
        api_url=API,
        token_url=TOKEN,
        auth_codes=frozenset({"invalid_grant", "interaction_required"}),
        refresh=refresh or default_refresh,
        auth_error=lambda: Failed("auth"),
        unavailable=lambda detail: Failed("unavailable", detail),
        prepare=prepare,
    )
    holder.append(session)
    return session


def failure(call: Callable[[], object]) -> Failed:
    with pytest.raises(Failed) as caught:
        call()
    assert caught.value.__suppress_context__ is True
    return caught.value


# Requests and the cached token


def test_a_get_refreshes_once_and_sends_the_bearer_token_with_its_headers(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    session = session_for(token_http, world)
    response = session.get(f"{API}/profile", params={"a": "1"}, headers={"Prefer": "x"})
    assert response.status_code == 200
    assert world.calls() == [("POST", TOKEN), ("GET", f"{API}/profile")]
    sent = world.requests[1]
    assert sent.headers["authorization"] == "Bearer access-1"
    assert sent.headers["prefer"] == "x"
    assert sent.url.params["a"] == "1"
    assert dict(httpx.QueryParams(world.requests[0].content.decode())) == FORM


def test_a_get_with_no_headers_sends_only_the_bearer_token(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    session_for(token_http, world).get(API)
    assert world.requests[1].headers["authorization"] == "Bearer access-1"
    assert "prefer" not in world.requests[1].headers


def test_the_token_is_reused_until_its_margin_then_refreshed(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    session = session_for(token_http, world)
    session.get(API)
    moment[0] = START + timedelta(seconds=3600) - token_http.TOKEN_MARGIN - timedelta(seconds=1)
    session.get(API)
    assert world.issued == 1
    moment[0] = START + timedelta(seconds=3600) - token_http.TOKEN_MARGIN
    session.get(API)
    assert world.issued == 2
    assert world.requests[-1].headers["authorization"] == "Bearer access-2"


def test_the_margin_is_sixty_seconds(token_http: ModuleType) -> None:
    assert token_http.TOKEN_MARGIN == timedelta(seconds=60)


def test_prepare_runs_before_every_token_check(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    session = session_for(token_http, world)
    session.ensure()
    assert (world.prepared, world.refreshed, world.issued) == (1, 1, 1)
    session.ensure()
    assert (world.prepared, world.refreshed, world.issued) == (2, 1, 1)
    assert world.calls() == [("POST", TOKEN)]


def test_a_rejected_token_is_refreshed_and_the_request_sent_once_more(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    world.api_replies.append(httpx.Response(401))
    response = session_for(token_http, world).get(API)
    assert response.status_code == 200
    assert world.calls() == [("POST", TOKEN), ("GET", API), ("POST", TOKEN), ("GET", API)]
    assert world.requests[-1].headers["authorization"] == "Bearer access-2"
    assert world.prepared == 2


def test_a_second_rejection_is_the_auth_error(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    world.api_replies.extend([httpx.Response(401), httpx.Response(401)])
    session = session_for(token_http, world)
    assert failure(lambda: session.get(API)).kind == "auth"
    assert world.calls() == [("POST", TOKEN), ("GET", API), ("POST", TOKEN), ("GET", API)]


def test_after_a_second_rejection_the_next_request_refreshes_first(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    world.api_replies.extend([httpx.Response(401), httpx.Response(401)])
    session = session_for(token_http, world)
    failure(lambda: session.get(API))
    session.get(API)
    assert world.calls()[-2:] == [("POST", TOKEN), ("GET", API)]


@pytest.mark.parametrize("status", [200, 403, 404, 500])
def test_any_other_status_is_returned_to_the_client(
    token_http: ModuleType, world: World, moment: list[datetime], status: int
) -> None:
    world.api_replies.append(httpx.Response(status))
    assert session_for(token_http, world).get(API).status_code == status
    assert world.issued == 1


def test_a_transport_failure_on_a_request_is_unavailable_network(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    world.api_replies.append(httpx.ConnectError("refused: access-1"))
    error = failure(lambda: session_for(token_http, world).get(API))
    assert (error.kind, error.detail) == ("unavailable", "network")


def test_a_failed_refresh_leaves_no_token_for_the_next_request(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    session = session_for(token_http, world)
    session.get(API)
    moment[0] = START + timedelta(hours=2)
    world.token_replies.append(httpx.Response(503))
    assert failure(lambda: session.get(API)).detail == 503
    moment[0] = START
    session.get(API)
    assert world.calls()[-2:] == [("POST", TOKEN), ("GET", API)]
    assert world.requests[-1].headers["authorization"] == "Bearer access-2"


def test_a_refresh_error_from_the_client_propagates_unchanged(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    def refuse() -> object:
        raise Failed("auth", "keychain")

    session = session_for(token_http, world, refresh=refuse)
    with pytest.raises(Failed) as caught:
        session.get(API)
    assert (caught.value.kind, caught.value.detail) == ("auth", "keychain")
    assert world.requests == []


# Where a token may go


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.test/v2/users/me/profile",
        "https://other.example.test/v2/users/me/profile",
        "https://api.example.test.evil.test/v2/users/me",
        "https://api.example.test:8443/v2/users/me",
        "https://owner@api.example.test/v2/users/me",
        "https://owner:pw@api.example.test/v2/users/me",
        "https://api.example.test/v2/users/meX",
        "https://api.example.test/v2/users",
        "https://api.example.test/v2/users/me/../../admin",
        "https://api.example.test/v2/users/me/%2e%2e/admin",
        "https://api.example.test/v2/users/me/./profile",
        "https://login.example.test/oauth/token",
    ],
    ids=[
        "http",
        "other-host",
        "host-suffix",
        "port",
        "user",
        "user-password",
        "path-prefix",
        "path-parent",
        "dot-dot",
        "encoded-dot-dot",
        "dot",
        "token-url",
    ],
)
def test_a_url_outside_the_api_is_refused_before_any_request(
    token_http: ModuleType, world: World, moment: list[datetime], url: str
) -> None:
    error = failure(lambda: session_for(token_http, world).get(url))
    assert (error.kind, error.detail) == ("unavailable", "response")
    assert world.requests == []
    assert world.prepared == 0


@pytest.mark.parametrize(
    "url",
    [API, f"{API}/", f"{API}/messages/m1", f"{API}/messages/m1?format=raw", f"{API}/a%2Fb"],
    ids=["base", "slash", "child", "query", "encoded-slash"],
)
def test_a_url_under_the_api_is_sent(
    token_http: ModuleType, world: World, moment: list[datetime], url: str
) -> None:
    assert session_for(token_http, world).get(url).status_code == 200
    assert world.requests[-1].method == "GET"


def test_the_api_host_is_compared_without_case(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    session_for(token_http, world).get("https://API.Example.test/v2/users/me/profile")
    assert world.requests[-1].method == "GET"


# The token reply


def grant_failure(
    token_http: ModuleType, world: World, reply: httpx.Response | Exception
) -> Failed:
    world.token_replies.append(reply)
    session = session_for(token_http, world)
    return failure(lambda: session.grant(dict(FORM)))


def test_a_grant_returns_the_token_its_lifetime_and_the_whole_reply(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    body = {"access_token": "access-x", "expires_in": 120, "refresh_token": "refresh-2"}
    world.token_replies.append(httpx.Response(200, json=body))
    grant = session_for(token_http, world).grant(dict(FORM))
    assert grant == token_http.Grant(access_token="access-x", expires_in=120, body=body)
    assert world.calls() == [("POST", TOKEN)]


def test_a_grant_lifetime_sets_the_expiry(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    world.expires_in = 120
    session = session_for(token_http, world)
    session.get(API)
    moment[0] = START + timedelta(seconds=59)
    session.get(API)
    assert world.issued == 1
    moment[0] = START + timedelta(seconds=60)
    session.get(API)
    assert world.issued == 2


@pytest.mark.parametrize("status", [400, 401])
@pytest.mark.parametrize("code", ["invalid_grant", "interaction_required"])
def test_a_listed_refusal_is_the_auth_error(
    token_http: ModuleType, world: World, moment: list[datetime], status: int, code: str
) -> None:
    error = grant_failure(token_http, world, httpx.Response(status, json={"error": code}))
    assert error.kind == "auth"


@pytest.mark.parametrize(
    ("reply", "detail"),
    [
        (httpx.Response(400, json={"error": "invalid_client"}), 400),
        (httpx.Response(400, json={"error": ["invalid_grant"]}), 400),
        (httpx.Response(400, json={"error": {"code": "invalid_grant"}}), 400),
        (httpx.Response(400, json=["invalid_grant"]), 400),
        (httpx.Response(400, content=b"invalid_grant"), 400),
        (httpx.Response(403, json={"error": "invalid_grant"}), 403),
        (httpx.Response(500, json={"error": "invalid_grant"}), 500),
        (httpx.Response(201, json={"access_token": "a", "expires_in": 1}), 201),
    ],
    ids=[
        "other-code",
        "code-list",
        "code-object",
        "body-list",
        "not-json",
        "403",
        "500",
        "201",
    ],
)
def test_any_other_refusal_is_unavailable_with_its_status(
    token_http: ModuleType, world: World, moment: list[datetime], reply: httpx.Response, detail: int
) -> None:
    error = grant_failure(token_http, world, reply)
    assert (error.kind, error.detail) == ("unavailable", detail)


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        json.dumps(["access-x", 3600]).encode(),
        json.dumps({"expires_in": 3600}).encode(),
        json.dumps({"access_token": 7, "expires_in": 3600}).encode(),
        json.dumps({"access_token": "access-x"}).encode(),
        json.dumps({"access_token": "access-x", "expires_in": "3600"}).encode(),
        json.dumps({"access_token": "access-x", "expires_in": 3600.0}).encode(),
        json.dumps({"access_token": "access-x", "expires_in": True}).encode(),
    ],
    ids=[
        "not-json",
        "list",
        "no-token",
        "token-number",
        "no-lifetime",
        "lifetime-text",
        "lifetime-float",
        "lifetime-bool",
    ],
)
def test_an_unusable_grant_is_unavailable_response(
    token_http: ModuleType, world: World, moment: list[datetime], content: bytes
) -> None:
    error = grant_failure(token_http, world, httpx.Response(200, content=content))
    assert (error.kind, error.detail) == ("unavailable", "response")


def test_a_transport_failure_on_the_token_post_is_unavailable_network(
    token_http: ModuleType, world: World, moment: list[datetime]
) -> None:
    error = grant_failure(token_http, world, httpx.ConnectError("refused: refresh-token-1"))
    assert (error.kind, error.detail) == ("unavailable", "network")
    assert "refresh-token-1" not in str(error)
