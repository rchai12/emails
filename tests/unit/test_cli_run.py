import signal
import threading

import pytest

from mailroom import service
from mailroom.service import ServiceError
from tests.support import run


def test_run_starts_the_service_and_stops_it_on_a_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    handlers: dict[int, object] = {}
    monkeypatch.setattr(
        signal, "signal", lambda number, handler: handlers.update({number: handler})
    )
    seen: dict[str, object] = {}

    def fake_service(settings, *, say, stop: threading.Event) -> None:
        say("discord gateway: running")
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        seen["stopped"] = stop.is_set()

    monkeypatch.setattr(service, "run_service", fake_service)
    result = run("run")
    assert (result.exit_code, result.output) == (0, "discord gateway: running\n")
    assert seen == {"stopped": True}
    assert set(handlers) == {signal.SIGTERM, signal.SIGINT}


def test_run_reports_missing_settings_and_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_service(settings, *, say, stop: threading.Event) -> None:
        raise ServiceError("not configured: MAILROOM_GMAIL_ACCOUNTS")

    monkeypatch.setattr(service, "run_service", fake_service)
    result = run("run")
    assert (result.exit_code, result.output) == (1, "not configured: MAILROOM_GMAIL_ACCOUNTS\n")


def test_run_reports_bad_settings_and_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILROOM_POLL_SECONDS", "5")
    monkeypatch.setattr(service, "run_service", lambda *args, **kwargs: None)
    result = run("run")
    assert (result.exit_code, result.output) == (
        1,
        "MAILROOM_POLL_SECONDS must be a whole number from 30 to 600\n",
    )
