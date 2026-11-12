"""Run everything a phase must pass: lint, format, tests, and the critical coverage gate.

Run it as: .venv/bin/python scripts/check.py [--first A,B | --section NAME]
"""

import argparse
import fnmatch
import json
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRITICAL_FILE = Path(__file__).resolve().parent / "critical_modules.txt"
SECTIONS_FILE = ROOT / "tests" / "sections.toml"
COVERAGE_STEP = "critical coverage"
LAYERS = ("unit", "integration", "e2e")


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str] | None


@dataclass(frozen=True)
class Tally:
    passed: int
    failed: int
    skipped: int


def read_critical(text: str) -> list[str]:
    """Return the module paths in the text, without comments and blank lines."""
    modules = []
    for line in text.splitlines():
        module = line.split("#", 1)[0].strip()
        if module:
            modules.append(module)
    return modules


def coverage_gaps(report: dict, modules: list[str]) -> list[str]:
    """Return one line for each module that is not fully covered, in the order of modules."""
    files = report["files"]
    gaps = []
    for module in modules:
        found = files.get(f"src/mailroom/{module}")
        if found is None:
            gaps.append(f"{module}: not measured")
            continue
        lines = found["summary"]["missing_lines"]
        branches = found["summary"]["missing_branches"]
        if lines or branches:
            gaps.append(f"{module}: {lines} lines and {branches} branches not covered")
    return gaps


def read_sections(text: str) -> list[tuple[str, list[str]]]:
    return [(table["name"], list(table["patterns"])) for table in tomllib.loads(text)["section"]]


def section_of(path: str, sections: list[tuple[str, list[str]]]) -> str:
    for name, patterns in sections:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            return name
    raise ValueError(f"no section for {path}")


def _case_path(classname: str, name: str) -> str:
    parts = (classname or name).split(".")
    return f"{parts[1]}/{parts[2]}.py"


def tally(report: str, sections: list[tuple[str, list[str]]]) -> dict[str, Tally]:
    counts = {name: [0, 0, 0] for name, _ in sections}
    for case in ET.fromstring(report).iter("testcase"):
        section = section_of(_case_path(case.get("classname", ""), case.get("name", "")), sections)
        tags = {child.tag for child in case}
        if "failure" in tags or "error" in tags:
            counts[section][1] += 1
        elif "skipped" in tags:
            counts[section][2] += 1
        else:
            counts[section][0] += 1
    return {
        name: Tally(passed=passed, failed=failed, skipped=skipped)
        for name, (passed, failed, skipped) in counts.items()
    }


def section_lines(tallies: dict[str, Tally]) -> list[str]:
    lines = ["Sections:"]
    for name, found in tallies.items():
        line = (
            f"  {name:<11}{found.passed:>6} passed{found.failed:>5} failed"
            f"{found.skipped:>5} skipped"
        )
        if found.failed:
            line += f"  rerun: .venv/bin/python scripts/check.py --section {name}"
        lines.append(line)
    return lines


def section_files(names: list[str]) -> list[str]:
    sections = read_sections(SECTIONS_FILE.read_text(encoding="utf-8"))
    wanted = set(names)
    found = []
    for layer in LAYERS:
        for path in (ROOT / "tests" / layer).glob("test_*.py"):
            relative = path.relative_to(ROOT / "tests").as_posix()
            if section_of(relative, sections) in wanted:
                found.append(f"tests/{relative}")
    return sorted(found)


def steps(python: str, coverage_json: Path, *, first: list[str] | None = None) -> list[Step]:
    found = [
        Step("lint", [python, "-m", "ruff", "check", "."]),
        Step("format", [python, "-m", "ruff", "format", "--check", "."]),
    ]
    if first:
        found.append(
            Step(
                f"tests ({','.join(first)})",
                [
                    python,
                    "-m",
                    "pytest",
                    "--no-cov",
                    f"--junitxml={coverage_json.with_name('first.xml')}",
                    "--continue-on-collection-errors",
                    *section_files(first),
                ],
            )
        )
    found.extend(
        [
            Step(
                "tests",
                [
                    python,
                    "-m",
                    "pytest",
                    f"--cov-report=json:{coverage_json}",
                    f"--junitxml={coverage_json.with_name('junit.xml')}",
                    "--continue-on-collection-errors",
                ],
            ),
            Step(COVERAGE_STEP, None),
        ]
    )
    return found


def run_command(command: list[str], cwd: Path) -> int:
    return subprocess.run(command, cwd=cwd, check=False).returncode


def _critical_coverage(coverage_json: Path) -> bool:
    report = json.loads(coverage_json.read_text(encoding="utf-8"))
    modules = read_critical(CRITICAL_FILE.read_text(encoding="utf-8"))
    gaps = coverage_gaps(report, modules)
    for gap in gaps:
        print(f"  {gap}")
    return not gaps


def _print_table(report_path: Path, names: list[str] | None) -> None:
    if not report_path.is_file():
        return
    sections = read_sections(SECTIONS_FILE.read_text(encoding="utf-8"))
    if names is not None:
        wanted = set(names)
        sections = [(name, patterns) for name, patterns in sections if name in wanted]
    print("\n".join(section_lines(tally(report_path.read_text(encoding="utf-8"), sections))))


def _section_names() -> list[str]:
    return [name for name, _ in read_sections(SECTIONS_FILE.read_text(encoding="utf-8"))]


def _run_one_section(name: str, run: Callable[[list[str], Path], int]) -> int:
    files = section_files([name])
    with tempfile.TemporaryDirectory() as folder:
        report_path = Path(folder) / "junit.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "--no-cov",
            f"--junitxml={report_path}",
            "--continue-on-collection-errors",
            *files,
        ]
        code = run(command, ROOT)
        _print_table(report_path, [name])
    print(f"Section {name}: {'passed.' if code == 0 else 'FAILED.'}")
    return 0 if code == 0 else 1


def main(argv: list[str] | None = None, run: Callable[[list[str], Path], int] = run_command) -> int:
    names = _section_names()
    parser = argparse.ArgumentParser(description="Run every check a phase must pass.")
    exclusive = parser.add_mutually_exclusive_group()
    exclusive.add_argument(
        "--section",
        choices=names,
        help="Run one section's tests alone, with no lint, format, or coverage.",
    )
    exclusive.add_argument(
        "--first",
        metavar="A[,B…]",
        help="Run these sections first; the full check only once they pass.",
    )
    options = parser.parse_args(argv)
    if options.section is not None:
        return _run_one_section(options.section, run)
    first: list[str] | None = None
    if options.first is not None:
        first = options.first.split(",")
        known = set(names)
        for name in first:
            if name not in known:
                parser.error(f"unknown section: {name}")
    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as folder:
        coverage_json = Path(folder) / "coverage.json"
        planned = steps(sys.executable, coverage_json, first=first)
        failed = None
        for step in planned:
            print(f"== {step.name}", flush=True)
            if step.command is None:
                passed = _critical_coverage(coverage_json)
            else:
                passed = run(step.command, ROOT) == 0
                for part in step.command:
                    if part.startswith("--junitxml="):
                        wanted = first if step.name.startswith("tests (") else None
                        _print_table(Path(part.removeprefix("--junitxml=")), wanted)
                        break
            results[step.name] = "passed" if passed else "FAILED"
            if not passed:
                failed = step.name
                break
    print()
    print("Summary:")
    for step in planned:
        print(f"  {step.name}: {results.get(step.name, 'not run')}")
    print("All checks passed." if failed is None else f"Check failed at: {failed}")
    return 0 if failed is None else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
