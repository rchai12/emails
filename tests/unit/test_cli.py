from importlib import metadata

import mailroom
from tests.support import run


def test_version_prints_the_name_and_version() -> None:
    result = run("version")
    assert result.exit_code == 0
    assert result.output == "mailroom 0.1.0\n"


def test_the_package_version_matches_the_installed_one() -> None:
    assert mailroom.__version__ == metadata.version("mailroom") == "0.1.0"


def test_the_mailroom_command_runs_the_cli() -> None:
    (found,) = metadata.entry_points(group="console_scripts", name="mailroom")
    assert found.value == "mailroom.cli:app"
