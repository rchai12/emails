"""Behaviours the main Graph tests leave unvisited: repeats, raw-body failures, odd tokens."""

from datetime import UTC, datetime

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
)
from tests.fakes import FakeGraph, FakeKeychain

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
SINCE = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
DELTA = "https://graph.microsoft.com/v1.0/me/mailFolders('inbox')/messages/delta"
META = {
    "id": "AAMk1=",
    "conversationId": "conversation-7",
    "parentFolderId": "inbox-folder-1",
    "receivedDateTime": "2026-11-10T08:00:00Z",
    "webLink": "https://outlook.live.com/owa/?ItemID=AAMk1=&exvsurl=1",
}


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


def outlook(graph: FakeGraph) -> OutlookClient:
    return OutlookClient("live", httpx.Client(transport=httpx.MockTransport(graph.handler)))


def page(value: list[object]) -> httpx.Response:
    return httpx.Response(200, json={"value": value, "@odata.deltaLink": f"{DELTA}?$deltatoken=d1"})


def test_a_repeated_message_is_kept_once_with_its_first_thread(graph: FakeGraph) -> None:
    graph.failures.append(
        page(
            [
                {"id": "AAMk1=", "conversationId": "first"},
                {"id": "AAMk1=", "conversationId": "second"},
                {"id": "AAMk2=", "conversationId": "other"},
            ]
        )
    )
    assert outlook(graph).first_delta(SINCE) == Delta(
        added=(MessageRef("AAMk1=", "first"), MessageRef("AAMk2=", "other")),
        delta_link=f"{DELTA}?$deltatoken=d1",
    )


def test_a_missing_raw_body_is_gone_after_the_metadata(graph: FakeGraph) -> None:
    graph.failures.extend([httpx.Response(200, json=META), httpx.Response(404)])
    with pytest.raises(MessageGone) as caught:
        outlook(graph).fetch("AAMk1=")
    assert str(caught.value) == "outlook message gone: live"
    assert graph.requests[-1].url.path == "/v1.0/me/messages/AAMk1=/$value"


def test_a_failed_raw_body_is_named_by_its_status(graph: FakeGraph) -> None:
    graph.failures.extend([httpx.Response(200, json=META), httpx.Response(503)])
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).fetch("AAMk1=")
    assert str(caught.value) == "outlook unavailable: live (503)"


@pytest.mark.parametrize("refresh_token", ["", 7], ids=["empty", "not-text"])
def test_a_refresh_token_that_is_not_text_is_refused(
    graph: FakeGraph, fake_keychain: FakeKeychain, refresh_token: object
) -> None:
    graph.token_failures.append(
        httpx.Response(
            200,
            json={"access_token": "access-9", "expires_in": 3600, "refresh_token": refresh_token},
        )
    )
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).profile()
    assert str(caught.value) == "outlook unavailable: live (response)"
    assert fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] == "refresh-token-1"


def test_the_same_refresh_token_is_left_as_it_is(
    graph: FakeGraph, fake_keychain: FakeKeychain
) -> None:
    graph.token_failures.append(
        httpx.Response(
            200,
            json={
                "access_token": "access-9",
                "expires_in": 3600,
                "refresh_token": "refresh-token-1",
            },
        )
    )
    graph.valid.add("access-9")
    assert outlook(graph).profile() == Profile("owner@example.test", "inbox-folder-1")
    assert fake_keychain.secrets[("mailroom", "outlook.live.refresh-token")] == "refresh-token-1"


def test_a_delta_refusal_that_is_not_json_is_not_an_expiry(graph: FakeGraph) -> None:
    graph.failures.append(httpx.Response(400, text="not json"))
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).first_delta(SINCE)
    assert not isinstance(caught.value, DeltaExpired)
    assert str(caught.value) == "outlook unavailable: live (400)"


def test_a_token_refusal_that_is_not_json_is_not_a_sign_in_error(graph: FakeGraph) -> None:
    graph.token_failures.append(httpx.Response(400, text="not json"))
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).profile()
    assert not isinstance(caught.value, OutlookAuthError)
    assert str(caught.value) == "outlook unavailable: live (400)"


def test_a_token_error_that_is_not_a_name_is_the_status(graph: FakeGraph) -> None:
    graph.token_failures.append(
        httpx.Response(401, json={"error": {"code": "temporarily_unavailable"}})
    )
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).profile()
    assert str(caught.value) == "outlook unavailable: live (401)"


def test_a_delta_page_that_is_not_an_object_is_refused(graph: FakeGraph) -> None:
    graph.failures.append(httpx.Response(200, json=["nope"]))
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).first_delta(SINCE)
    assert str(caught.value) == "outlook unavailable: live (response)"


def test_a_delta_page_whose_list_is_not_a_list_is_refused(graph: FakeGraph) -> None:
    graph.failures.append(
        httpx.Response(200, json={"value": "nope", "@odata.deltaLink": f"{DELTA}?$deltatoken=d1"})
    )
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).first_delta(SINCE)
    assert str(caught.value) == "outlook unavailable: live (response)"


def test_a_delta_item_that_is_not_an_object_is_refused(graph: FakeGraph) -> None:
    graph.failures.append(page(["AAMk1="]))
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).first_delta(SINCE)
    assert str(caught.value) == "outlook unavailable: live (response)"


def test_a_conversation_id_that_is_not_text_is_refused(graph: FakeGraph) -> None:
    graph.failures.append(page([{"id": "AAMk1=", "conversationId": 7}]))
    with pytest.raises(OutlookUnavailable) as caught:
        outlook(graph).first_delta(SINCE)
    assert str(caught.value) == "outlook unavailable: live (response)"
