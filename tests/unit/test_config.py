import stat
from pathlib import Path

import pytest

from mailroom.config import DATA_DIR_MESSAGE, ConfigError, get_settings, prepare_data_dir


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_default_data_dir_is_in_application_support(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("MAILROOM_DATA_DIR")
    expected = tmp_path / "home" / "Library" / "Application Support" / "mailroom"
    assert get_settings().data_dir == expected


def test_the_data_dir_comes_from_the_environment(tmp_path: Path) -> None:
    assert get_settings().data_dir == tmp_path / "data"


def test_a_leading_tilde_is_the_home_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MAILROOM_DATA_DIR", "~/mail")
    assert get_settings().data_dir == tmp_path / "home" / "mail"


@pytest.mark.parametrize("value", ["data", "./data", ""])
def test_a_relative_data_dir_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MAILROOM_DATA_DIR", value)
    with pytest.raises(ConfigError) as raised:
        get_settings()
    assert str(raised.value) == DATA_DIR_MESSAGE == "MAILROOM_DATA_DIR must be an absolute path"


def test_settings_are_read_again_on_each_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = get_settings().data_dir
    monkeypatch.setenv("MAILROOM_DATA_DIR", str(tmp_path / "other"))
    assert (first, get_settings().data_dir) == (tmp_path / "data", tmp_path / "other")


def test_prepare_creates_the_data_dir_private(tmp_path: Path) -> None:
    settings = get_settings()
    found = prepare_data_dir(settings)
    assert found == tmp_path / "data"
    assert found.is_dir()
    assert mode(found) == 0o700


def test_prepare_creates_missing_parents(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MAILROOM_DATA_DIR")
    found = prepare_data_dir(get_settings())
    assert found == tmp_path / "home" / "Library" / "Application Support" / "mailroom"
    assert mode(found) == 0o700


def test_prepare_makes_an_existing_data_dir_private(tmp_path: Path) -> None:
    folder = tmp_path / "data"
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    prepare_data_dir(get_settings())
    assert mode(folder) == 0o700
