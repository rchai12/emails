from pathlib import Path

import pytest

from mailroom.reports import PHASE_MESSAGE, Problem, check_reports

ENTRY = """## Phase 5a: routing (2026-11-09)
- Tests: 423 -> 460 (given 37)
- New public names: None
- Changed files: 12
- Deviations:
  - None
- Follow-ups:
  - None
"""


def repository(root: Path, *, spec: bool, entry: bool) -> Path:
    (root / "docs" / "phases").mkdir(parents=True)
    if spec:
        (root / "docs" / "phases" / "phase-05a-routing.md").write_text("# Phase 5a\n")
    (root / "docs" / "progress.md").write_text("# Progress\n\n" + (ENTRY if entry else ""))
    return root


@pytest.mark.parametrize(
    ("spec", "entry", "problems"),
    [
        (True, True, []),
        (True, False, [Problem("docs/progress.md", 1, "no progress entry for Phase 5a")]),
        (False, True, [Problem("docs/phases", 1, "no spec for Phase 5a")]),
    ],
)
def test_a_phase_needs_its_spec_and_its_entry(
    tmp_path: Path, spec: bool, entry: bool, problems: list[Problem]
) -> None:
    root = repository(tmp_path, spec=spec, entry=entry)
    assert check_reports(root, phase="5a") == problems
    assert check_reports(root) == []


@pytest.mark.parametrize("phase", ["00", "05a", "5A"])
def test_a_phase_id_is_checked(tmp_path: Path, phase: str) -> None:
    root = repository(tmp_path, spec=True, entry=True)
    with pytest.raises(ValueError) as raised:
        check_reports(root, phase=phase)
    assert str(raised.value) == PHASE_MESSAGE == "phase must be a phase id such as 0 or 5a"
