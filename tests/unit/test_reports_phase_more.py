from pathlib import Path

import pytest

from mailroom.reports import PHASE_MESSAGE, Problem, check_reports

ENTRY = """## Phase 5: routing (2026-11-09)
- Tests: 1 -> 2 (given 1)
- New public names: None
- Changed files: 1
- Deviations:
  - None
- Follow-ups:
  - None
"""


def test_neither_spec_nor_entry_names_the_spec_first(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "progress.md").write_text("# Progress\n", encoding="utf-8")
    assert check_reports(tmp_path, phase="5a") == [
        Problem("docs/phases", 1, "no spec for Phase 5a"),
        Problem("docs/progress.md", 1, "no progress entry for Phase 5a"),
    ]


def test_phase_5_matches_a_zero_padded_spec(tmp_path: Path) -> None:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "phase-05-x.md").write_text("# Phase 5\n", encoding="utf-8")
    (tmp_path / "docs" / "progress.md").write_text("# Progress\n\n" + ENTRY, encoding="utf-8")
    assert check_reports(tmp_path, phase="5") == []


def test_phase_0_matches_its_spec(tmp_path: Path) -> None:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "phase-00-skeleton.md").write_text(
        "# Phase 0\n", encoding="utf-8"
    )
    entry = ENTRY.replace("## Phase 5: routing", "## Phase 0: skeleton")
    (tmp_path / "docs" / "progress.md").write_text("# Progress\n\n" + entry, encoding="utf-8")
    assert check_reports(tmp_path, phase="0") == []


def test_an_empty_phase_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as raised:
        check_reports(tmp_path, phase="")
    assert str(raised.value) == PHASE_MESSAGE


def test_a_malformed_entry_is_also_a_missing_entry(tmp_path: Path) -> None:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "phase-05a-routing.md").write_text(
        "# Phase 5a\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "progress.md").write_text(
        "# Progress\n\n## Phase 5a: routing (2026-11-09)\n- Tests: wrong\n",
        encoding="utf-8",
    )
    assert check_reports(tmp_path, phase="5a") == [
        Problem(
            "docs/progress.md",
            4,
            "expected `- Tests: <before> -> <after> (given <n>)`",
        ),
        Problem("docs/progress.md", 1, "no progress entry for Phase 5a"),
    ]
