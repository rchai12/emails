from datetime import date
from pathlib import Path

import pytest

from mailroom.reports import (
    Finding,
    Problem,
    ProgressEntry,
    Review,
    check_reports,
    parse_progress,
    parse_review,
    phase_of,
)

ENTRY_1 = """## Phase 1: skeleton (2026-10-25)
- Tests: 0 -> 70 (given 65)
- New public names: `events`: `EventLog`
- Changed files: 6
- Deviations:
  - An invalid event raises ValueError("event is not valid").
- Follow-ups:
  - None
"""

ENTRY_2A = """## Phase 2a: contracts (2026-10-26)
- Tests: 70 -> 114 (given 38)
- New public names: None
- Changed files: 8
- Deviations:
  - None
- Follow-ups:
  - The tree had edits this phase did not make.
  - A second follow-up.
"""

PROGRESS = f"# Progress\n\nThe coding agent appends one entry per phase.\n\n{ENTRY_1}\n{ENTRY_2A}"

PASS_REVIEW = """# Review: Phase 2a

- Verdict: PASS
- Passed: 114
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gate output

Anything at all may follow, | even | pipes.
"""

FAIL_REVIEW = """# Review: Phase 2a

- Verdict: FAIL
- Passed: 112
- Findings: 2
- Approved deviations: None
- For the architect: R3's example contradicts its rule

## Findings

R3 | src/mailroom/contracts/base.py:12 | expected `^` anchoring | found an unanchored pattern
Scope audit | tests/unit/test_contracts_plans.py:1 | expected the given file | found it re-sorted

Parts that needed a repair: Part 1

Built beyond the spec: a `to_dict` helper
"""


def lines_with(text: str, number: int, replacement: str | None) -> str:
    """The text with line `number` (from 1) replaced, or removed when replacement is None."""
    lines = text.split("\n")
    if replacement is None:
        del lines[number - 1]
    else:
        lines[number - 1] = replacement
    return "\n".join(lines)


def test_phase_ids_from_spec_names() -> None:
    assert phase_of("phase-00-skeleton.md") == "0"
    assert phase_of("phase-01-skeleton.md") == "1"
    assert phase_of("phase-02a-contracts.md") == "2a"
    assert phase_of("phase-12-finance-domain.md") == "12"
    assert phase_of("phase-2a-contracts.md") is None
    assert phase_of("notes.md") is None


def test_a_good_progress_file() -> None:
    entries, problems = parse_progress(PROGRESS)
    assert problems == []
    assert entries == [
        ProgressEntry(
            phase="1",
            title="skeleton",
            date=date(2026, 10, 25),
            tests_before=0,
            tests_after=70,
            given=65,
            new_names="`events`: `EventLog`",
            changed_files=6,
            deviations=('An invalid event raises ValueError("event is not valid").',),
            follow_ups=("None",),
            line=5,
        ),
        ProgressEntry(
            phase="2a",
            title="contracts",
            date=date(2026, 10, 26),
            tests_before=70,
            tests_after=114,
            given=38,
            new_names="None",
            changed_files=8,
            deviations=("None",),
            follow_ups=("The tree had edits this phase did not make.", "A second follow-up."),
            line=14,
        ),
    ]


def test_a_progress_file_with_no_entries_yet() -> None:
    assert parse_progress("# Progress\n\nThe coding agent appends one entry per phase.\n") == (
        [],
        [],
    )


@pytest.mark.parametrize(
    ("number", "replacement", "line", "message"),
    [
        (
            1,
            "## Phase 2a contracts (2026-10-26)",
            1,
            "heading must be `## Phase <id>: <title> (YYYY-MM-DD)`",
        ),
        (1, "## Phase 2a: contracts (2026-02-30)", 1, "the date is not a real date"),
        (2, "- Tests: 70 -> 114", 2, "expected `- Tests: <before> -> <after> (given <n>)`"),
        (3, None, 3, "expected `- New public names: <names or None>`"),
        (4, "- Changed files: eight", 4, "expected `- Changed files: <n>`"),
        (6, "  -", 6, "expected at least one `  - ` line under Deviations"),
        (7, "- Follow ups:", 7, "expected `- Follow-ups:`"),
        (8, "- None", 8, "expected at least one `  - ` line under Follow-ups"),
        (10, "Done.", 10, "unexpected line in the entry"),
    ],
)
def test_the_first_problem_in_an_entry(
    number: int, replacement: str | None, line: int, message: str
) -> None:
    entries, problems = parse_progress(lines_with(ENTRY_2A, number, replacement))
    assert problems == [Problem("docs/progress.md", line, message)]
    assert entries == []


def test_an_entry_cut_short_is_reported_where_the_line_is_missing() -> None:
    _, problems = parse_progress(
        "## Phase 3: model client (2026-10-27)\n- Tests: 1 -> 2 (given 1)\n"
    )
    assert problems == [
        Problem("docs/progress.md", 3, "expected `- New public names: <names or None>`")
    ]


def test_a_bad_entry_does_not_hide_the_good_ones() -> None:
    broken = lines_with(ENTRY_1, 4, "- Changed files: six")
    entries, problems = parse_progress(f"# Progress\n\n{broken}\n{ENTRY_2A}")
    assert [entry.phase for entry in entries] == ["2a"]
    assert problems == [Problem("docs/progress.md", 6, "expected `- Changed files: <n>`")]
    assert problems[0].text == "docs/progress.md:6: expected `- Changed files: <n>`"


def test_a_pass_review() -> None:
    review, problems = parse_review(PASS_REVIEW, "docs/reviews/phase-02a-contracts.md")
    assert problems == []
    assert review == Review(
        phase="2a",
        verdict="PASS",
        passed=114,
        findings=(),
        approved_deviations="None",
        for_architect="None",
        repaired="none",
        built_beyond="none",
    )


def test_a_fail_review_with_its_findings() -> None:
    review, problems = parse_review(FAIL_REVIEW, "docs/reviews/phase-02a-contracts.md")
    assert problems == []
    assert review is not None
    assert (review.verdict, review.passed, review.for_architect) == (
        "FAIL",
        112,
        "R3's example contradicts its rule",
    )
    assert review.findings == (
        Finding(
            requirement="R3",
            file="src/mailroom/contracts/base.py",
            line=12,
            expected="`^` anchoring",
            found="an unanchored pattern",
        ),
        Finding(
            requirement="Scope audit",
            file="tests/unit/test_contracts_plans.py",
            line=1,
            expected="the given file",
            found="it re-sorted",
        ),
    )
    assert (review.repaired, review.built_beyond) == ("Part 1", "a `to_dict` helper")


@pytest.mark.parametrize(
    ("text", "number", "replacement", "line", "message"),
    [
        (PASS_REVIEW, 1, "# Review: Phase 2", 1, "expected `# Review: Phase 2a`"),
        (PASS_REVIEW, 2, "Verdict below.", 2, "expected an empty line"),
        (PASS_REVIEW, 3, "- Verdict: PASSED", 3, "expected `- Verdict: PASS or FAIL`"),
        (PASS_REVIEW, 4, "- Passed: many", 4, "expected `- Passed: <n>`"),
        (PASS_REVIEW, 6, None, 6, "expected `- Approved deviations: <text or None>`"),
        (PASS_REVIEW, 9, "## Findings:", 9, "expected `## Findings`"),
        (PASS_REVIEW, 5, "- Findings: 1", 5, "Findings says 1 but 0 are listed"),
        (
            FAIL_REVIEW,
            12,
            "R3 | base.py | expected x | found y",
            12,
            "expected `<requirement> | <file>:<line> | expected <...> | found <...>` or `None`",
        ),
        (FAIL_REVIEW, 3, "- Verdict: PASS", 3, "a PASS review has no findings"),
        (PASS_REVIEW, 3, "- Verdict: FAIL", 3, "a FAIL review lists at least one finding"),
        (
            PASS_REVIEW,
            13,
            "Parts repaired: none",
            13,
            "expected `Parts that needed a repair: <parts or none>`",
        ),
        (
            PASS_REVIEW,
            15,
            "Built beyond: none",
            15,
            "expected `Built beyond the spec: <what or none>`",
        ),
    ],
)
def test_the_first_problem_in_a_review(
    text: str, number: int, replacement: str | None, line: int, message: str
) -> None:
    path = "docs/reviews/phase-02a-contracts.md"
    review, problems = parse_review(lines_with(text, number, replacement), path)
    assert (review, problems) == (None, [Problem(path, line, message)])


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_checking_a_repository(tmp_path: Path) -> None:
    write(tmp_path, "docs/progress.md", PROGRESS)
    write(tmp_path, "docs/phases/phase-01-skeleton.md", "# Phase 1: skeleton\n")
    write(tmp_path, "docs/phases/phase-02a-contracts.md", "# Phase 2a: contracts\n")
    write(tmp_path, "docs/phases/phase-02b-report-checker.md", "# Phase 2b: report checker\n")
    write(tmp_path, "docs/reviews/phase-02a-contracts.md", PASS_REVIEW)
    assert check_reports(tmp_path) == []
    write(tmp_path, "docs/reviews/phase-02b-report-checker.md", PASS_REVIEW.replace("2a", "2b"))
    write(tmp_path, "docs/reviews/phase-09-later.md", PASS_REVIEW.replace("2a", "9"))
    write(tmp_path, "docs/reviews/README.txt", "not a review")
    assert check_reports(tmp_path) == [
        Problem("docs/reviews/phase-02b-report-checker.md", 1, "no progress entry for Phase 2b"),
        Problem("docs/reviews/phase-09-later.md", 1, "no spec docs/phases/phase-09-later.md"),
    ]


def test_a_repository_without_a_progress_file(tmp_path: Path) -> None:
    assert check_reports(tmp_path) == [Problem("docs/progress.md", 1, "missing")]
