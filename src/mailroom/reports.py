import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

_HEADING_MESSAGE = "heading must be `## Phase <id>: <title> (YYYY-MM-DD)`"
_DATE_MESSAGE = "the date is not a real date"
_TESTS_MESSAGE = "expected `- Tests: <before> -> <after> (given <n>)`"
_NAMES_MESSAGE = "expected `- New public names: <names or None>`"
_CHANGED_MESSAGE = "expected `- Changed files: <n>`"
_DEVIATIONS_MESSAGE = "expected `- Deviations:`"
_FOLLOW_UPS_MESSAGE = "expected `- Follow-ups:`"
_UNEXPECTED_MESSAGE = "unexpected line in the entry"
_EMPTY_MESSAGE = "expected an empty line"
_VERDICT_MESSAGE = "expected `- Verdict: PASS or FAIL`"
_PASSED_MESSAGE = "expected `- Passed: <n>`"
_FINDINGS_COUNT_MESSAGE = "expected `- Findings: <n>`"
_DEVIATIONS_TEXT_MESSAGE = "expected `- Approved deviations: <text or None>`"
_ARCHITECT_MESSAGE = "expected `- For the architect: <text or None>`"
_FINDINGS_HEADING_MESSAGE = "expected `## Findings`"
_FINDING_MESSAGE = (
    "expected `<requirement> | <file>:<line> | expected <...> | found <...>` or `None`"
)
_REPAIRED_MESSAGE = "expected `Parts that needed a repair: <parts or none>`"
_BUILT_MESSAGE = "expected `Built beyond the spec: <what or none>`"
_PASS_FINDINGS_MESSAGE = "a PASS review has no findings"
_FAIL_FINDINGS_MESSAGE = "a FAIL review lists at least one finding"
PHASE_MESSAGE = "phase must be a phase id such as 0 or 5a"

_HEADING = re.compile(
    r"^## Phase ((?:0|[1-9][0-9]*)[a-z]?): (.+) \(([0-9]{4}-[0-9]{2}-[0-9]{2})\)$"
)
_TESTS = re.compile(r"^- Tests: ([0-9]+) -> ([0-9]+) \(given ([0-9]+)\)$")
_NAMES = re.compile(r"^- New public names: (.+)$")
_CHANGED = re.compile(r"^- Changed files: ([0-9]+)$")
_DEVIATIONS = re.compile(r"^- Deviations:$")
_FOLLOW_UPS = re.compile(r"^- Follow-ups:$")
_ITEM = re.compile(r"^  - (.+)$")
_SPEC_NAME = re.compile(r"^phase-([0-9]{2,})([a-z])?-.+\.md$")
_VERDICT = re.compile(r"^- Verdict: (PASS|FAIL)$")
_PASSED = re.compile(r"^- Passed: ([0-9]+)$")
_FINDINGS_COUNT = re.compile(r"^- Findings: ([0-9]+)$")
_DEVIATIONS_TEXT = re.compile(r"^- Approved deviations: (.+)$")
_ARCHITECT = re.compile(r"^- For the architect: (.+)$")
_FINDING = re.compile(r"^([^|]+) \| ([^|:]+):([0-9]+) \| expected ([^|]+) \| found (.+)$")
_REPAIRED = re.compile(r"^Parts that needed a repair: (.+)$")
_BUILT = re.compile(r"^Built beyond the spec: (.+)$")
_PHASE = re.compile(r"^(?:0|[1-9][0-9]*)[a-z]?$")


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    message: str

    @property
    def text(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


@dataclass(frozen=True)
class ProgressEntry:
    phase: str
    title: str
    date: date
    tests_before: int
    tests_after: int
    given: int
    new_names: str
    changed_files: int
    deviations: tuple[str, ...]
    follow_ups: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class Finding:
    requirement: str
    file: str
    line: int
    expected: str
    found: str


@dataclass(frozen=True)
class Review:
    phase: str
    verdict: Literal["PASS", "FAIL"]
    passed: int
    findings: tuple[Finding, ...]
    approved_deviations: str
    for_architect: str
    repaired: str
    built_beyond: str


def phase_of(spec_name: str) -> str | None:
    found = _SPEC_NAME.fullmatch(spec_name)
    if found is None:
        return None
    letter = found.group(2) or ""
    return str(int(found.group(1))) + letter


def parse_progress(
    text: str, path: str = "docs/progress.md"
) -> tuple[list[ProgressEntry], list[Problem]]:
    lines = text.split("\n")
    entries: list[ProgressEntry] = []
    problems: list[Problem] = []
    index = 0
    while index < len(lines) and not lines[index].startswith("## "):
        index += 1
    while index < len(lines):
        outcome = _one_entry(lines, index, path)
        if isinstance(outcome, Problem):
            problems.append(outcome)
            index = _resume(lines, index, outcome.line)
        else:
            entry, index = outcome
            entries.append(entry)
    return entries, problems


def parse_review(text: str, path: str) -> tuple[Review | None, list[Problem]]:
    lines = text.split("\n")
    phase_text = phase_of(Path(path).name)
    if phase_text is None:
        phase_text = "<id>"
    heading = _at(lines, 0)
    if heading != f"# Review: Phase {phase_text}":
        return None, [Problem(path, 1, f"expected `# Review: Phase {phase_text}`")]
    problem = _blank(lines, 1, path)
    if problem is not None:
        return None, [problem]
    verdict_found = _fullmatch(lines, 2, _VERDICT)
    if verdict_found is None:
        return None, [Problem(path, 3, _VERDICT_MESSAGE)]
    verdict: Literal["PASS", "FAIL"] = "PASS" if verdict_found.group(1) == "PASS" else "FAIL"
    passed_found = _fullmatch(lines, 3, _PASSED)
    if passed_found is None:
        return None, [Problem(path, 4, _PASSED_MESSAGE)]
    count_found = _fullmatch(lines, 4, _FINDINGS_COUNT)
    if count_found is None:
        return None, [Problem(path, 5, _FINDINGS_COUNT_MESSAGE)]
    deviations_found = _fullmatch(lines, 5, _DEVIATIONS_TEXT)
    if deviations_found is None:
        return None, [Problem(path, 6, _DEVIATIONS_TEXT_MESSAGE)]
    architect_found = _fullmatch(lines, 6, _ARCHITECT)
    if architect_found is None:
        return None, [Problem(path, 7, _ARCHITECT_MESSAGE)]
    problem = _blank(lines, 7, path)
    if problem is not None:
        return None, [problem]
    findings_heading = _at(lines, 8)
    if findings_heading != "## Findings":
        return None, [Problem(path, 9, _FINDINGS_HEADING_MESSAGE)]
    problem = _blank(lines, 9, path)
    if problem is not None:
        return None, [problem]
    findings, index, problem = _findings(lines, 10, path)
    if problem is not None:
        return None, [problem]
    stated = int(count_found.group(1))
    if stated != len(findings):
        return None, [Problem(path, 5, f"Findings says {stated} but {len(findings)} are listed")]
    if verdict == "PASS" and findings:
        return None, [Problem(path, 3, _PASS_FINDINGS_MESSAGE)]
    if verdict == "FAIL" and not findings:
        return None, [Problem(path, 3, _FAIL_FINDINGS_MESSAGE)]
    repaired, index, problem = _closing(lines, index, _REPAIRED, _REPAIRED_MESSAGE, path)
    if problem is not None:
        return None, [problem]
    built, _index, problem = _closing(lines, index, _BUILT, _BUILT_MESSAGE, path)
    if problem is not None:
        return None, [problem]
    review = Review(
        phase=phase_text,
        verdict=verdict,
        passed=int(passed_found.group(1)),
        findings=tuple(findings),
        approved_deviations=deviations_found.group(1),
        for_architect=architect_found.group(1),
        repaired=repaired,
        built_beyond=built,
    )
    return review, []


def check_reports(root: Path, *, phase: str | None = None) -> list[Problem]:
    if phase is not None and _PHASE.fullmatch(phase) is None:
        raise ValueError(PHASE_MESSAGE)
    problems: list[Problem] = []
    progress = root / "docs" / "progress.md"
    if not progress.is_file():
        problems.append(Problem("docs/progress.md", 1, "missing"))
        phases: set[str] = set()
    else:
        entries, found = parse_progress(progress.read_text(encoding="utf-8"), "docs/progress.md")
        problems.extend(found)
        phases = {entry.phase for entry in entries}
    reviews = root / "docs" / "reviews"
    if reviews.is_dir():
        _check_reviews(root, reviews, phases, problems)
    if phase is not None:
        specs = [phase_of(path.name) for path in (root / "docs" / "phases").glob("*.md")]
        if phase not in specs:
            problems.append(Problem("docs/phases", 1, f"no spec for Phase {phase}"))
        if phase not in phases:
            problems.append(Problem("docs/progress.md", 1, f"no progress entry for Phase {phase}"))
    return problems


def _check_reviews(root: Path, reviews: Path, phases: set[str], problems: list[Problem]) -> None:
    for path in sorted(reviews.glob("*.md")):
        relative = f"docs/reviews/{path.name}"
        if not (root / "docs" / "phases" / path.name).is_file():
            problems.append(Problem(relative, 1, f"no spec docs/phases/{path.name}"))
            continue
        review, found = parse_review(path.read_text(encoding="utf-8"), relative)
        if review is None:
            problems.extend(found)
            continue
        if review.phase not in phases:
            problems.append(Problem(relative, 1, f"no progress entry for Phase {review.phase}"))


def _at(lines: list[str], index: int) -> str | None:
    if index >= len(lines):
        return None
    return lines[index]


def _fullmatch(lines: list[str], index: int, pattern: re.Pattern[str]) -> re.Match[str] | None:
    line = _at(lines, index)
    if line is None:
        return None
    return pattern.fullmatch(line)


def _blank(lines: list[str], index: int, path: str) -> Problem | None:
    if _at(lines, index) != "":
        return Problem(path, index + 1, _EMPTY_MESSAGE)
    return None


def _heading(line: str) -> tuple[str, str, date] | str:
    found = _HEADING.fullmatch(line)
    if found is None:
        return _HEADING_MESSAGE
    try:
        when = date.fromisoformat(found.group(3))
    except ValueError:
        return _DATE_MESSAGE
    return found.group(1), found.group(2), when


def _take(
    lines: list[str], index: int, pattern: re.Pattern[str], message: str, path: str
) -> tuple[re.Match[str], int] | Problem:
    if index < len(lines):
        found = pattern.fullmatch(lines[index])
        if found is not None:
            return found, index + 1
    return Problem(path, index + 1, message)


def _items(
    lines: list[str], index: int, label: str, path: str
) -> tuple[tuple[str, ...], int] | Problem:
    items: list[str] = []
    while index < len(lines):
        found = _ITEM.fullmatch(lines[index])
        if found is None:
            break
        items.append(found.group(1))
        index += 1
    if not items:
        return Problem(path, index + 1, f"expected at least one `  - ` line under {label}")
    return tuple(items), index


def _one_entry(lines: list[str], index: int, path: str) -> Problem | tuple[ProgressEntry, int]:
    heading_line = index + 1
    parsed = _heading(lines[index])
    if isinstance(parsed, str):
        return Problem(path, heading_line, parsed)
    phase, title, when = parsed
    index += 1
    tests = _take(lines, index, _TESTS, _TESTS_MESSAGE, path)
    if isinstance(tests, Problem):
        return tests
    tests_found, index = tests
    names = _take(lines, index, _NAMES, _NAMES_MESSAGE, path)
    if isinstance(names, Problem):
        return names
    names_found, index = names
    changed = _take(lines, index, _CHANGED, _CHANGED_MESSAGE, path)
    if isinstance(changed, Problem):
        return changed
    changed_found, index = changed
    deviations_head = _take(lines, index, _DEVIATIONS, _DEVIATIONS_MESSAGE, path)
    if isinstance(deviations_head, Problem):
        return deviations_head
    _head, index = deviations_head
    deviations = _items(lines, index, "Deviations", path)
    if isinstance(deviations, Problem):
        return deviations
    deviation_items, index = deviations
    follow_head = _take(lines, index, _FOLLOW_UPS, _FOLLOW_UPS_MESSAGE, path)
    if isinstance(follow_head, Problem):
        return follow_head
    _head, index = follow_head
    follow_ups = _items(lines, index, "Follow-ups", path)
    if isinstance(follow_ups, Problem):
        return follow_ups
    follow_items, index = follow_ups
    while index < len(lines):
        if lines[index] == "":
            index += 1
            continue
        if lines[index].startswith("## "):
            break
        return Problem(path, index + 1, _UNEXPECTED_MESSAGE)
    entry = ProgressEntry(
        phase=phase,
        title=title,
        date=when,
        tests_before=int(tests_found.group(1)),
        tests_after=int(tests_found.group(2)),
        given=int(tests_found.group(3)),
        new_names=names_found.group(1),
        changed_files=int(changed_found.group(1)),
        deviations=deviation_items,
        follow_ups=follow_items,
        line=heading_line,
    )
    return entry, index


def _resume(lines: list[str], heading_index: int, problem_line: int) -> int:
    problem_index = problem_line - 1
    if problem_index == heading_index:
        start = heading_index + 1
    elif problem_index < len(lines) and lines[problem_index].startswith("## "):
        start = problem_index
    else:
        start = problem_line
    while start < len(lines) and not lines[start].startswith("## "):
        start += 1
    return start


def _findings(lines: list[str], index: int, path: str) -> tuple[list[Finding], int, Problem | None]:
    if index < len(lines) and lines[index] == "None":
        return [], index + 1, None
    findings: list[Finding] = []
    while index < len(lines) and lines[index] != "":
        found = _FINDING.fullmatch(lines[index])
        if found is None:
            return [], index, Problem(path, index + 1, _FINDING_MESSAGE)
        findings.append(
            Finding(
                requirement=found.group(1),
                file=found.group(2),
                line=int(found.group(3)),
                expected=found.group(4),
                found=found.group(5),
            )
        )
        index += 1
    return findings, index, None


def _closing(
    lines: list[str],
    index: int,
    pattern: re.Pattern[str],
    message: str,
    path: str,
) -> tuple[str, int, Problem | None]:
    while index < len(lines) and lines[index] == "":
        index += 1
    if index >= len(lines):
        return "", index, Problem(path, index + 1, message)
    found = pattern.fullmatch(lines[index])
    if found is None:
        return "", index, Problem(path, index + 1, message)
    return found.group(1), index + 1, None
