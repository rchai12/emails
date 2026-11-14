import pytest

from mailroom.config import TASKS_URL_MESSAGE, ConfigError, get_settings


def test_the_tasks_app_address_is_unset_by_default() -> None:
    assert get_settings().tasks_url == ""


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8765", "http://localhost:9000", "http://[::1]:8765"]
)
def test_a_tasks_app_on_this_machine_is_accepted(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("MAILROOM_TASKS_URL", url)
    assert get_settings().tasks_url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://192.0.2.1:8765",
        "https://127.0.0.1:8765",
        "http://127.0.0.1:8765/tasks",
        "http://127.0.0.1:8765/",
        "http://user@127.0.0.1:8765",
        "http://127.0.0.1:99999",
    ],
    ids=["other-host", "https", "path", "slash", "user", "bad-port"],
)
def test_a_tasks_app_address_off_this_machine_is_refused(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("MAILROOM_TASKS_URL", url)
    with pytest.raises(ConfigError) as caught:
        get_settings()
    assert str(caught.value) == TASKS_URL_MESSAGE
    assert TASKS_URL_MESSAGE == (
        "MAILROOM_TASKS_URL must be empty or http:// on 127.0.0.1, localhost or [::1], with no path"
    )
