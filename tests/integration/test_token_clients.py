"""Phase 4m: both mail clients send every bearer request and token post through one session."""

import importlib
from types import ModuleType

import pytest

from mailroom import gmail, outlook
from tests.fakes import FakeGmail, FakeGraph
from tests.integration.test_gmail import client_for as gmail_client
from tests.integration.test_gmail import gmail as gmail_fake
from tests.integration.test_outlook import client as outlook_client
from tests.integration.test_outlook import graph as graph
from tests.integration.test_outlook import moment as moment

assert gmail_fake and graph and moment


@pytest.fixture
def token_http() -> ModuleType:
    return importlib.import_module("mailroom.token_http")


class Spy:
    def __init__(self) -> None:
        self.built: list[dict[str, object]] = []
        self.gets: list[str] = []
        self.grants: list[tuple[str, ...]] = []


@pytest.fixture
def spy(token_http: ModuleType, monkeypatch: pytest.MonkeyPatch) -> Spy:
    seen = Spy()
    session = token_http.TokenSession
    real_init, real_get, real_grant = session.__init__, session.get, session.grant

    def init(self: object, http: object, **options: object) -> None:
        seen.built.append(options)
        real_init(self, http, **options)

    def get(self: object, url: str, **options: object) -> object:
        seen.gets.append(url)
        return real_get(self, url, **options)

    def grant(self: object, form: dict[str, str]) -> object:
        seen.grants.append(tuple(sorted(form)))
        return real_grant(self, form)

    monkeypatch.setattr(session, "__init__", init)
    monkeypatch.setattr(session, "get", get)
    monkeypatch.setattr(session, "grant", grant)
    return seen


def test_gmail_builds_one_session_for_its_api_and_token_url(
    gmail_fake: FakeGmail, spy: Spy
) -> None:
    gmail_client(gmail_fake)
    assert len(spy.built) == 1
    options = spy.built[0]
    assert options["api_url"] == gmail.API_URL
    assert options["token_url"] == gmail.TOKEN_URL
    assert options["auth_codes"] == frozenset({"invalid_grant"})


def test_outlook_builds_one_session_for_its_api_and_token_url(graph: FakeGraph, spy: Spy) -> None:
    outlook_client(graph)
    assert len(spy.built) == 1
    options = spy.built[0]
    assert options["api_url"] == outlook.API_URL
    assert options["token_url"] == outlook.TOKEN_URL
    assert options["auth_codes"] == frozenset({"invalid_grant", "interaction_required"})
    assert callable(options["prepare"])


def test_every_gmail_request_and_token_post_goes_through_the_session(
    gmail_fake: FakeGmail, spy: Spy
) -> None:
    gmail_fake.add_message("m1", b"Subject: Hi\r\n\r\nHello.\r\n", internal_ms=1)
    client = gmail_client(gmail_fake)
    client.profile()
    client.fetch("m1")
    gets = [request for request in gmail_fake.requests if request.method == "GET"]
    posts = [request for request in gmail_fake.requests if request.method == "POST"]
    assert spy.gets == [str(request.url.copy_with(query=None)) for request in gets]
    assert spy.grants == [("client_id", "client_secret", "grant_type", "refresh_token")]
    assert len(posts) == 1


def test_every_outlook_request_and_token_post_goes_through_the_session(
    graph: FakeGraph, spy: Spy
) -> None:
    client = outlook_client(graph)
    client.profile()
    gets = [request for request in graph.requests if request.method == "GET"]
    posts = [request for request in graph.requests if request.method == "POST"]
    assert spy.gets == [str(request.url.copy_with(query=None)) for request in gets]
    assert spy.grants == [("client_id", "grant_type", "refresh_token", "scope")]
    assert len(posts) == 1


def test_both_clients_keep_the_shared_margin(token_http: ModuleType) -> None:
    assert gmail.TOKEN_MARGIN is token_http.TOKEN_MARGIN
    assert outlook.TOKEN_MARGIN is token_http.TOKEN_MARGIN
