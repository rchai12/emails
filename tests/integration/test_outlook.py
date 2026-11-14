"""The Graph client: tokens that rotate, inbox delta rounds, and the raw message, read-only."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from mailroom import clock
from mailroom.outlook import (
    Delta,
    DeltaExpired,
    MessageGone,
    MessageRef,
    OutlookAuthError,
    OutlookClient,
    OutlookUnavailable,
    Profile,
    RawMessage,
    open_outlook,
)
from tests.fakes import FakeGraph, FakeKeychain

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
SINCE = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
RAW = b"From: Sam <sam@example.test>\r\nSubject: Report\r\n\r\nCan you send it?\r\n"
DELTA = "https://graph.microsoft.com/v1.0/me/mailFolders('inbox')/messages/delta"


@pytest.fixture
def moment(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [NOW]
    monkeypatch.setattr(clock, "now", lambda: now[0])
    return now


@pytest.fixture
def graph(fake_keychain: FakeKeychain, moment: list[datetime]) -> FakeGraph:
    fake = FakeGraph()
    fake_keychain.secrets[("mailroom", "outlook.live.client-id")] = fake.client_id
    fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] = fake.refresh_token
    return fake


def client(graph: FakeGraph) -> OutlookClient:
    return OutlookClient("live", httpx.Client(transport=httpx.MockTransport(graph.handler)))


def graph_requests(graph: FakeGraph) -> list[httpx.Request]:
    return [request for request in graph.requests if request.url.host == "graph.microsoft.com"]


# Tokens


def test_a_token_is_asked_for_as_a_public_client_and_the_new_refresh_token_saved(
    graph: FakeGraph, fake_keychain: FakeKeychain
) -> None:
    client(graph).profile()
    token_request = graph.requests[0]
    assert str(token_request.url) == (
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    )
    assert dict(httpx.QueryParams(token_request.content.decode())) == {
        "client_id": "client-id-1",
        "refresh_token": "refresh-token-1",
        "grant_type": "refresh_token",
        "scope": "https://graph.microsoft.com/Mail.Read offline_access",
    }
    assert fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] == "refresh-token-2"


def test_the_token_is_kept_until_a_minute_before_it_expires(
    graph: FakeGraph, moment: list[datetime], fake_keychain: FakeKeychain
) -> None:
    outlook = client(graph)
    outlook.profile()
    moment[0] = NOW + timedelta(seconds=3540 - 1)
    outlook.profile()
    assert len(graph.issued) == 1
    moment[0] = NOW + timedelta(seconds=3540)
    outlook.profile()
    assert len(graph.issued) == 2
    assert fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] == "refresh-token-3"


def test_a_rejected_access_token_is_refreshed_once(graph: FakeGraph) -> None:
    outlook = client(graph)
    outlook.profile()
    graph.invalidate_tokens()
    assert outlook.profile().email_address == "owner@example.test"
    assert len(graph.issued) == 2
    graph.failures.extend([httpx.Response(401), httpx.Response(401)])
    with pytest.raises(OutlookAuthError) as caught:
        outlook.profile()
    assert str(caught.value) == "outlook sign-in needed: live"


@pytest.mark.parametrize(
    ("answer", "error", "text"),
    [
        (
            httpx.Response(400, json={"error": "invalid_grant", "error_description": "x"}),
            OutlookAuthError,
            "outlook sign-in needed: live",
        ),
        (
            httpx.Response(400, json={"error": "interaction_required"}),
            OutlookAuthError,
            "outlook sign-in needed: live",
        ),
        (httpx.Response(503), OutlookUnavailable, "outlook unavailable: live (503)"),
        (httpx.ConnectError("refused"), OutlookUnavailable, "outlook unavailable: live (network)"),
        (
            httpx.Response(200, json={"access_token": "a", "expires_in": "3600"}),
            OutlookUnavailable,
            "outlook unavailable: live (response)",
        ),
        (
            httpx.Response(200, text="not json"),
            OutlookUnavailable,
            "outlook unavailable: live (response)",
        ),
    ],
    ids=["invalid-grant", "interaction-required", "503", "network", "bad-expiry", "not-json"],
)
def test_a_token_failure_is_named_without_its_text(
    graph: FakeGraph, answer: object, error: type, text: str
) -> None:
    graph.token_failures.append(answer)
    with pytest.raises(error) as caught:
        client(graph).profile()
    assert str(caught.value) == text


def test_a_missing_secret_asks_for_sign_in(graph: FakeGraph, fake_keychain: FakeKeychain) -> None:
    del fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")]
    with pytest.raises(OutlookAuthError):
        client(graph).profile()
    assert graph.requests == []


def test_a_reply_without_a_new_refresh_token_keeps_the_old(
    graph: FakeGraph, fake_keychain: FakeKeychain
) -> None:
    graph.token_failures.append(
        httpx.Response(200, json={"access_token": "access-9", "expires_in": 3600})
    )
    graph.valid.add("access-9")
    client(graph).profile()
    assert fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] == "refresh-token-1"


# Reads


def test_the_profile_falls_back_to_the_sign_in_name_and_finds_the_inbox(graph: FakeGraph) -> None:
    graph.mail = None
    graph.user_principal_name = "owner@outlook.example.test"
    assert client(graph).profile() == Profile(
        email_address="owner@outlook.example.test", inbox_id="inbox-folder-1"
    )
    first, second = graph_requests(graph)
    assert (first.url.params["$select"], second.url.path) == (
        "mail,userPrincipalName",
        "/v1.0/me/mailFolders/inbox",
    )
    assert all(
        request.headers["prefer"].startswith('IdType="ImmutableId"') for request in (first, second)
    )


def test_a_first_round_reads_the_inbox_since_a_moment_page_by_page(graph: FakeGraph) -> None:
    for number, day in ((1, 9), (2, 10), (3, 11), (4, 12)):
        graph.add_message(f"AAMk{number}=", RAW, received=f"2026-11-{day:02d}T08:00:00Z")
    graph.add_message("AAMk5=", RAW, folder="junkemail", received="2026-11-12T09:00:00Z")
    delta = client(graph).first_delta(SINCE)
    assert delta == Delta(
        added=(
            MessageRef("AAMk3=", "conversation-AAMk3="),
            MessageRef("AAMk4=", "conversation-AAMk4="),
        ),
        delta_link=f"{DELTA}?$deltatoken=d4",
    )
    first = graph_requests(graph)[0]
    assert dict(first.url.params) == {
        "changeType": "created",
        "$select": "conversationId,receivedDateTime",
        "$filter": "receivedDateTime ge 2026-11-10T09:00:00Z",
    }
    assert first.headers["prefer"] == 'IdType="ImmutableId", odata.maxpagesize=50'


def test_a_later_round_follows_every_page_and_skips_removed_mail(graph: FakeGraph) -> None:
    outlook = client(graph)
    link = outlook.first_delta(SINCE).delta_link
    for number in range(1, 56):
        graph.add_message(f"AAMk{number}=", RAW, received="2026-11-12T08:00:00Z")
    graph.move("AAMk7=", "junkemail")
    delta = outlook.next_delta(link)
    assert len(delta.added) == 55
    assert delta.added[6] == MessageRef("AAMk7=", "conversation-AAMk7=")
    assert delta.delta_link == f"{DELTA}?$deltatoken=d56"
    requests = graph_requests(graph)
    assert str(requests[-2].url) == f"{DELTA}?$deltatoken=d0"
    assert "$skiptoken=" in str(requests[-1].url)


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.example.test/v1.0/me/mailFolders('inbox')/messages/delta?$skiptoken=s1",
        "http://graph.microsoft.com/v1.0/me/mailFolders('inbox')/messages/delta?$skiptoken=s1",
        "https://graph.microsoft.com:8443/v1.0/me/mailFolders('inbox')/messages/delta",
        "https://user@graph.microsoft.com/v1.0/me/mailFolders('inbox')/messages/delta",
        "https://graph.microsoft.com/v1.0/me/messages/AAMk1=",
    ],
    ids=["other-host", "http", "port", "user", "other-path"],
)
def test_a_page_link_anywhere_else_is_never_followed(graph: FakeGraph, link: str) -> None:
    graph.failures.append(httpx.Response(200, json={"value": [], "@odata.nextLink": link}))
    outlook = client(graph)
    with pytest.raises(OutlookUnavailable) as caught:
        outlook.first_delta(SINCE)
    assert str(caught.value) == "outlook unavailable: live (response)"
    assert all(
        request.url.host in ("graph.microsoft.com", "login.microsoftonline.com")
        for request in graph.requests
    )
    assert len(graph_requests(graph)) == 1
    with pytest.raises(OutlookUnavailable):
        outlook.next_delta(link)
    assert len(graph_requests(graph)) == 1


@pytest.mark.parametrize("code", ["", "syncStateNotFound"], ids=["410", "sync-state-not-found"])
def test_an_expired_delta_link_asks_for_a_new_round(graph: FakeGraph, code: str) -> None:
    outlook = client(graph)
    link = outlook.first_delta(SINCE).delta_link
    graph.expire_deltas()
    graph.expired_code = code
    with pytest.raises(DeltaExpired) as caught:
        outlook.next_delta(link)
    assert str(caught.value) == "outlook delta expired: live"


def test_a_message_is_fetched_with_its_folder_link_and_raw_text(graph: FakeGraph) -> None:
    graph.add_message("AAMk1=", RAW, conversation_id="conversation-7")
    assert client(graph).fetch("AAMk1=") == RawMessage(
        id="AAMk1=",
        thread_id="conversation-7",
        folder_id="inbox-folder-1",
        received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
        web_link="https://outlook.live.com/owa/?ItemID=AAMk1=&exvsurl=1",
        raw=RAW,
    )
    metadata, value = graph_requests(graph)
    assert (
        metadata.url.params["$select"] == "conversationId,parentFolderId,receivedDateTime,webLink"
    )
    assert value.url.path == "/v1.0/me/messages/AAMk1=/$value"


def test_a_message_gone_is_named(graph: FakeGraph) -> None:
    with pytest.raises(MessageGone) as caught:
        client(graph).fetch("AAMk404=")
    assert str(caught.value) == "outlook message gone: live"


@pytest.mark.parametrize(
    "message_id",
    ["", "a/b", "..", "AAMk 1", "a?b", "a" * 513],
    ids=["empty", "slash", "dots", "space", "query", "long"],
)
def test_a_message_id_that_cannot_name_a_path_is_refused_before_any_request(
    graph: FakeGraph, message_id: str
) -> None:
    with pytest.raises(ValueError, match="^invalid message id$"):
        client(graph).fetch(message_id)
    assert graph.requests == []


@pytest.mark.parametrize(
    ("answer", "detail"),
    [
        (httpx.Response(429, headers={"retry-after": "30"}), "429"),
        (httpx.Response(503), "503"),
        (httpx.ConnectError("refused"), "network"),
        (httpx.Response(200, text="<html>"), "response"),
        (
            httpx.Response(
                200,
                json={
                    "value": [{"id": "a/b", "conversationId": "c"}],
                    "@odata.deltaLink": f"{DELTA}?$deltatoken=d0",
                },
            ),
            "response",
        ),
        (httpx.Response(200, json={"value": []}), "response"),
    ],
    ids=["throttled", "503", "network", "not-json", "bad-id", "no-link"],
)
def test_a_graph_failure_is_named_without_its_text(
    graph: FakeGraph, answer: object, detail: str
) -> None:
    graph.failures.append(answer)
    with pytest.raises(OutlookUnavailable) as caught:
        client(graph).first_delta(SINCE)
    assert str(caught.value) == f"outlook unavailable: live ({detail})"


@pytest.mark.parametrize(
    "received", ["yesterday", "2026-11-10T08:00:00"], ids=["not-a-time", "no-zone"]
)
def test_a_message_with_an_unreadable_time_is_refused(graph: FakeGraph, received: str) -> None:
    graph.add_message("AAMk1=", RAW, received=received)
    with pytest.raises(OutlookUnavailable) as caught:
        client(graph).fetch("AAMk1=")
    assert str(caught.value) == "outlook unavailable: live (response)"


def test_an_invalid_account_name_is_refused() -> None:
    with pytest.raises(ValueError, match="^invalid account name$"):
        OutlookClient("Live!", httpx.Client())


def test_the_client_ignores_proxies_and_redirects() -> None:
    outlook = open_outlook("live")
    try:
        assert outlook.account == "live"
        assert (outlook.http.trust_env, outlook.http.follow_redirects) == (False, False)
        assert outlook.http.timeout == httpx.Timeout(30.0)
    finally:
        outlook.http.close()
