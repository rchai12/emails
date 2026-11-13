import threading

import pytest

from mailroom import service
from mailroom.config import BACKUP_MESSAGE, ConfigError
from tests.support import run


def test_run_reports_a_data_folder_it_cannot_exclude_and_exits_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_service(settings, *, say, stop: threading.Event) -> None:
        raise ConfigError(BACKUP_MESSAGE)

    monkeypatch.setattr(service, "run_service", fake_service)
    result = run("run")
    assert (result.exit_code, result.output) == (
        1,
        "could not exclude the data folder from Time Machine\n",
    )
