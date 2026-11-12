from pathlib import Path

from mailroom.reports import Problem, check_reports, parse_progress, parse_review

HEADING = "heading must be `## Phase <id>: <title> (YYYY-MM-DD)`"

PATH = "docs/reviews/phase-02a-contracts.md"

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
"""

ENTRY = """## Phase 2a: contracts (2026-10-26)
- Tests: 70 -> 114 (given 38)
- New public names: None
- Changed files: 8
- Deviations:
  - None
- Follow-ups:
  - None
"""

ENTRY_1 = """## Phase 1: skeleton (2026-10-25)
- Tests: 0 -> 70 (given 65)
- New public names: None
- Changed files: 6
- Deviations:
  - None
- Follow-ups:
  - None
"""


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_review_that_ends_after_none() -> None:
    text = """# Review: Phase 2a

- Verdict: PASS
- Passed: 114
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None"""
    _review, problems = parse_review(text, PATH)
    assert problems == [
        Problem(
            PATH,
            12,
            "expected `Parts that needed a repair: <parts or none>`",
        )
    ]


def test_findings_that_reach_the_end_of_the_file() -> None:
    text = """# Review: Phase 2a

- Verdict: FAIL
- Passed: 1
- Findings: 1
- Approved deviations: None
- For the architect: None

## Findings

R1 | a.py:1 | expected one | found two"""
    _review, problems = parse_review(text, PATH)
    assert problems == [
        Problem(
            PATH,
            12,
            "expected `Parts that needed a repair: <parts or none>`",
        )
    ]


def test_a_findings_count_of_two_with_one_listed() -> None:
    text = """# Review: Phase 2a

- Verdict: FAIL
- Passed: 1
- Findings: 2
- Approved deviations: None
- For the architect: None

## Findings

R1 | a.py:1 | expected one | found two

Parts that needed a repair: none

Built beyond the spec: none
"""
    review, problems = parse_review(text, PATH)
    assert review is None
    assert problems == [Problem(PATH, 5, "Findings says 2 but 1 are listed")]


def test_line_8_must_be_empty() -> None:
    lines = PASS_REVIEW.split("\n")
    lines[7] = "not empty"
    _review, problems = parse_review("\n".join(lines), PATH)
    assert problems == [Problem(PATH, 8, "expected an empty line")]


def test_line_10_must_be_empty() -> None:
    lines = PASS_REVIEW.split("\n")
    lines[9] = "not empty"
    _review, problems = parse_review("\n".join(lines), PATH)
    assert problems == [Problem(PATH, 10, "expected an empty line")]


def test_a_findings_count_must_be_a_number() -> None:
    text = PASS_REVIEW.replace("- Findings: 0", "- Findings: x")
    review, problems = parse_review(text, PATH)
    assert review is None
    assert problems == [Problem(PATH, 5, "expected `- Findings: <n>`")]


def test_the_architect_line_needs_text() -> None:
    text = PASS_REVIEW.replace("- For the architect: None", "- For the architect: ")
    review, problems = parse_review(text, PATH)
    assert review is None
    assert problems == [Problem(PATH, 7, "expected `- For the architect: <text or None>`")]


def test_a_review_named_notes_expects_the_literal_id(tmp_path: Path) -> None:
    write(tmp_path, "docs/progress.md", f"# Progress\n\n{ENTRY_1}")
    write(tmp_path, "docs/phases/notes.md", "# Notes\n")
    write(tmp_path, "docs/reviews/notes.md", PASS_REVIEW)
    assert check_reports(tmp_path) == [
        Problem("docs/reviews/notes.md", 1, "expected `# Review: Phase <id>`")
    ]


def test_an_entry_needs_a_deviations_heading() -> None:
    text = ENTRY.replace("- Deviations:", "- Deviation:")
    entries, problems = parse_progress(text)
    assert entries == []
    assert problems == [Problem("docs/progress.md", 5, "expected `- Deviations:`")]


def test_phase_ids_zero_padded_and_two_letters_are_refused() -> None:
    for heading in (
        "## Phase 00: skeleton (2026-10-25)",
        "## Phase 2ab: contracts (2026-10-26)",
    ):
        text = ENTRY.replace("## Phase 2a: contracts (2026-10-26)", heading)
        entries, problems = parse_progress(text)
        assert entries == []
        assert problems == [Problem("docs/progress.md", 1, HEADING)]


def test_a_note_heading_between_entries() -> None:
    text = f"{ENTRY_1}## Notes\n{ENTRY}"
    entries, problems = parse_progress(text)
    assert [entry.phase for entry in entries] == ["1", "2a"]
    assert problems == [Problem("docs/progress.md", 9, HEADING)]


def test_a_broken_entry_is_not_a_progress_entry(tmp_path: Path) -> None:
    broken = ENTRY.replace("- Changed files: 8", "- Changed files: eight")
    write(tmp_path, "docs/progress.md", f"# Progress\n\n{broken}")
    write(tmp_path, "docs/phases/phase-02a-contracts.md", "# Phase 2a\n")
    write(tmp_path, "docs/reviews/phase-02a-contracts.md", PASS_REVIEW)
    assert check_reports(tmp_path) == [
        Problem("docs/progress.md", 6, "expected `- Changed files: <n>`"),
        Problem(PATH, 1, "no progress entry for Phase 2a"),
    ]


def test_a_missing_field_past_the_end_of_the_text() -> None:
    text = "## Phase 3: model client (2026-10-27)\n- Tests: 1 -> 2 (given 1)"
    entries, problems = parse_progress(text)
    assert entries == []
    assert problems == [
        Problem("docs/progress.md", 3, "expected `- New public names: <names or None>`")
    ]


def test_a_heading_in_place_of_a_field_starts_the_next_entry() -> None:
    text = f"## Phase 1: skeleton (2026-10-25)\n{ENTRY}"
    entries, problems = parse_progress(text)
    assert [entry.phase for entry in entries] == ["2a"]
    assert problems == [
        Problem("docs/progress.md", 2, "expected `- Tests: <before> -> <after> (given <n>)`")
    ]


def test_a_review_that_ends_before_the_verdict() -> None:
    review, problems = parse_review("# Review: Phase 2a\n", PATH)
    assert review is None
    assert problems == [Problem(PATH, 3, "expected `- Verdict: PASS or FAIL`")]


def test_a_review_that_ends_on_its_heading() -> None:
    review, problems = parse_review("# Review: Phase 2a", PATH)
    assert review is None
    assert problems == [Problem(PATH, 2, "expected an empty line")]


def test_a_bad_review_is_not_also_a_missing_entry(tmp_path: Path) -> None:
    write(tmp_path, "docs/progress.md", f"# Progress\n\n{ENTRY}")
    write(tmp_path, "docs/phases/phase-02a-contracts.md", "# Phase 2a\n")
    write(tmp_path, "docs/reviews/phase-02a-contracts.md", "# Review: Phase 2a")
    assert check_reports(tmp_path) == [Problem(PATH, 2, "expected an empty line")]


def test_an_entry_may_end_on_its_last_follow_up() -> None:
    text = ENTRY.rstrip("\n")
    entries, problems = parse_progress(text)
    assert problems == []
    assert len(entries) == 1
    assert entries[0].follow_ups == ("None",)
