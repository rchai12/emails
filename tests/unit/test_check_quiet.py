import json
from pathlib import Path

import pytest

from tests.unit.test_agent_tools import ROOT, load

check = load("email_check_quiet", ROOT / "scripts/check.py")
JUNIT = '<testsuite><testcase classname="tests.unit.test_a" name="test_one"/></testsuite>'
FULL_TABLE = (
    "Sections:\n"
    "  tooling         0 passed    0 failed    0 skipped\n"
    "  core            1 passed    0 failed    0 skipped\n"
)
CORE_TABLE = "Sections:\n  core            1 passed    0 failed    0 skipped\n"


class Runner:
    """Stands in for the commands: writes each one's output to its log and its reports."""

    def __init__(self, failing: str | None = None) -> None:
        self.failing = failing
        self.logs: list[Path | None] = []

    def __call__(self, command: list[str], cwd: Path, log: Path | None = None) -> int:
        self.logs.append(log)
        name = "format" if "format" in command else "lint" if "ruff" in command else "tests"
        for part in command:
            if part.startswith("--junitxml="):
                Path(part.removeprefix("--junitxml=")).write_text(JUNIT, encoding="utf-8")
            if part.startswith("--cov-report=json:"):
                modules = check.read_critical(check.CRITICAL_FILE.read_text(encoding="utf-8"))
                files = {
                    f"src/mailroom/{module}": {
                        "summary": {"missing_lines": 0, "missing_branches": 0}
                    }
                    for module in modules
                }
                Path(part.removeprefix("--cov-report=json:")).write_text(
                    json.dumps({"files": files}), encoding="utf-8"
                )
        if log is not None:
            lines = [f"{name} line {number}" for number in range(1, 31)]
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1 if name == self.failing else 0


def test_a_quiet_run_prints_the_tables_and_the_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = Runner()
    assert check.main(["--quiet", "--log-dir", str(tmp_path)], run=runner) == 0
    assert capsys.readouterr().out == (
        FULL_TABLE + "\n"
        "Summary:\n"
        "  lint: passed\n"
        "  format: passed\n"
        "  tests: passed\n"
        "  critical coverage: passed\n"
        f"Logs: {tmp_path}\n"
        "All checks passed.\n"
    )
    assert runner.logs == [tmp_path / "lint.log", tmp_path / "format.log", tmp_path / "tests.log"]
    assert (tmp_path / "lint.log").read_text(encoding="utf-8").startswith("lint line 1\n")


def test_a_quiet_failure_shows_the_last_lines_of_its_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert check.main(["--quiet", "--log-dir", str(tmp_path)], run=Runner("format")) == 1
    tail = "".join(f"format line {number}\n" for number in range(11, 31))
    assert capsys.readouterr().out == (
        f"Last 20 lines of {tmp_path / 'format.log'}:\n" + tail + "\n"
        "Summary:\n"
        "  lint: passed\n"
        "  format: FAILED\n"
        "  tests: not run\n"
        "  critical coverage: not run\n"
        f"Logs: {tmp_path}\n"
        "Check failed at: format\n"
    )


def test_quiet_sections_first_and_alone_log_each_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = Runner()
    assert check.main(["--quiet", "--first", "core", "--log-dir", str(tmp_path)], run=first) == 0
    assert first.logs == [
        tmp_path / "lint.log",
        tmp_path / "format.log",
        tmp_path / "tests-first.log",
        tmp_path / "tests.log",
    ]
    assert capsys.readouterr().out.startswith(CORE_TABLE + FULL_TABLE + "\nSummary:\n")
    alone = Runner()
    assert check.main(["--quiet", "--section", "core", "--log-dir", str(tmp_path)], run=alone) == 0
    assert alone.logs == [tmp_path / "section.log"]
    assert capsys.readouterr().out == CORE_TABLE + f"Section core: passed.\nLogs: {tmp_path}\n"


def test_without_quiet_the_output_is_as_before(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = Runner()
    assert check.main([], run=runner) == 0
    assert runner.logs == [None, None, None]
    out = capsys.readouterr().out
    assert out.startswith("== lint\n== format\n== tests\n" + FULL_TABLE + "== critical coverage\n")
    assert "Logs:" not in out
