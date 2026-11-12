from datetime import date

import httpx
import pytest

from mailroom.config import Settings, get_settings
from mailroom.extractor import (
    Extraction,
    ModelUnavailable,
    Rejected,
    extract,
    open_model_http,
)
from tests.fakes import FakeOllama
from tests.integration.test_extractor import GOOD, NO_DEADLINE, RECORD, run


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b")
    monkeypatch.setenv("MAILROOM_TIME_ZONE", "America/New_York")
    return get_settings()


def test_a_reply_that_is_not_the_model_message_is_rejected(settings: Settings) -> None:
    not_json, _ = run(settings, httpx.Response(200, text="not json"))
    no_message, _ = run(settings, httpx.Response(200, json={"done_reason": "stop"}))
    listed, _ = run(settings, httpx.Response(200, json=["not an object"]))
    number, _ = run(
        settings,
        httpx.Response(200, json={"message": {"content": 1}, "done_reason": "stop"}),
    )
    assert not_json == no_message == listed == number == Rejected("response")
    assert "not json" not in str(not_json)


def test_a_content_list_is_rejected(settings: Settings) -> None:
    result, fake = run(settings, "[1, 2]")
    assert result == Rejected("content")
    assert len(fake.requests) == 1


def test_open_model_http_stays_on_this_machine_and_times_out() -> None:
    client = open_model_http()
    assert client.timeout == httpx.Timeout(120.0)
    assert client.trust_env is False
    assert client.follow_redirects is False


def test_an_unset_time_zone_does_not_call_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_EXTRACTOR_MODEL", "qwen-test:27b")
    fake = FakeOllama()
    http = httpx.Client(transport=httpx.MockTransport(fake.handler))
    with pytest.raises(ModelUnavailable) as caught:
        extract(RECORD, get_settings(), http)
    assert str(caught.value) == "model unavailable (not configured)"
    assert fake.requests == []


def test_a_deadline_without_a_time_is_kept(settings: Settings) -> None:
    result, _ = run(settings, {**GOOD, "deadline_time": "", "urgent": True})
    assert isinstance(result, Extraction)
    assert result.urgent is True
    assert result.deadline is not None
    assert result.deadline.time is None
    assert result.deadline.date == date(2026, 11, 20)


def test_an_impossible_time_is_rejected(settings: Settings) -> None:
    result, _ = run(settings, {**GOOD, "deadline_time": "24:00"})
    assert result == Rejected("deadline_time")


def test_a_time_without_a_deadline_is_rejected(settings: Settings) -> None:
    result, _ = run(settings, {**NO_DEADLINE, "deadline_time": "17:00"})
    assert result == Rejected("deadline_time")


def test_a_non_actionable_email_may_have_no_title(settings: Settings) -> None:
    result, _ = run(settings, {**NO_DEADLINE, "actionable": False, "title": ""})
    assert isinstance(result, Extraction)
    assert result.actionable is False
    assert result.title == ""
    assert result.deadline is None


def test_a_reason_without_suspicion_is_rejected(settings: Settings) -> None:
    result, _ = run(settings, {**GOOD, "suspicion_reason": "Looks odd."})
    assert result == Rejected("suspicion_reason")


def test_a_suspicious_email_keeps_its_reason(settings: Settings) -> None:
    result, _ = run(
        settings, {**GOOD, "suspicious": True, "suspicion_reason": "Asks for a password."}
    )
    assert isinstance(result, Extraction)
    assert result.suspicious is True
    assert result.suspicion_reason == "Asks for a password."


def test_an_unknown_confidence_is_rejected(settings: Settings) -> None:
    for confidence in ("High", {"a": 1}):
        result, _ = run(settings, {**GOOD, "confidence": confidence})
        assert result == Rejected("confidence")


def test_a_deadline_date_that_is_not_text_is_rejected(settings: Settings) -> None:
    result, _ = run(settings, {**GOOD, "deadline_date": None})
    assert result == Rejected("deadline_date")
