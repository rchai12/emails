import plistlib
import subprocess
from pathlib import Path

import pytest

from mailroom import config
from mailroom.config import (
    BACKUP_ATTRIBUTE,
    BACKUP_MESSAGE,
    BACKUP_VALUE,
    ConfigError,
    exclude_from_backup,
    get_settings,
    prepare_data_dir,
)


def attribute(path: Path) -> bytes | None:
    """The folder's Time Machine attribute, read by macOS's own xattr tool."""
    found = subprocess.run(
        ["/usr/bin/xattr", "-px", BACKUP_ATTRIBUTE, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if found.returncode != 0:
        return None
    return bytes.fromhex(found.stdout)


def test_the_attribute_is_the_one_tmutil_writes() -> None:
    assert BACKUP_ATTRIBUTE == "com.apple.metadata:com_apple_backup_excludeItem"
    assert BACKUP_VALUE == plistlib.dumps("com.apple.backupd", fmt=plistlib.FMT_BINARY)
    assert BACKUP_MESSAGE == "could not exclude the data folder from Time Machine"


def test_excluding_a_folder_sets_the_attribute(tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()
    assert attribute(folder) is None
    exclude_from_backup(folder)
    assert attribute(folder) == BACKUP_VALUE


def test_excluding_twice_and_over_another_value_leaves_one_exclusion(tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()
    subprocess.run(["/usr/bin/xattr", "-w", BACKUP_ATTRIBUTE, "other", str(folder)], check=True)
    exclude_from_backup(folder)
    exclude_from_backup(folder)
    assert attribute(folder) == BACKUP_VALUE


def test_a_folder_name_outside_ascii_is_excluded(tmp_path: Path) -> None:
    folder = tmp_path / "données é"
    folder.mkdir()
    exclude_from_backup(folder)
    assert attribute(folder) == BACKUP_VALUE


def test_a_folder_that_cannot_be_excluded_raises_the_fixed_message(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        exclude_from_backup(tmp_path / "missing")
    assert str(caught.value) == BACKUP_MESSAGE
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


def test_preparing_the_data_folder_excludes_it_from_backup(tmp_path: Path) -> None:
    found = prepare_data_dir(get_settings())
    assert attribute(found) == BACKUP_VALUE
    assert attribute(tmp_path) is None


def test_preparing_stops_when_the_folder_cannot_be_excluded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[Path] = []

    def refuse(folder: Path) -> None:
        seen.append(folder)
        raise ConfigError(BACKUP_MESSAGE)

    monkeypatch.setattr(config, "exclude_from_backup", refuse)
    with pytest.raises(ConfigError) as caught:
        prepare_data_dir(get_settings())
    assert str(caught.value) == BACKUP_MESSAGE
    assert seen == [tmp_path / "data"]
