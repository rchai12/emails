import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


phase_tools = load("email_phase_tools", ROOT / ".claude/skills/phase-architect/phase_tools.py")
accept = load("email_accept", ROOT / "scripts/accept.py")
progress = load("email_progress", ROOT / "scripts/progress.py")

ENTRY = """## Phase 5a: Synthetic tooling (2026-11-17)
- Tests: 10 -> 12 (given 2)
- New public names: None
- Changed files: 3
- Deviations:
  - None
- Follow-ups:
  - None
"""

SPEC = """# Phase 5a: Synthetic tooling

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first tooling` | All checks passed. |
| `.venv/bin/python -m coverage report --fail-under=100` | TOTAL 100% |

### Searches

```zsh
git grep --untracked -n -E 'forbidden|also_bad' -- src
```
"""


def test_clone_refuses_existing_work_without_invoking_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "fail05a"
    folder.mkdir()
    sentinel = folder / "notes.txt"
    sentinel.write_text("unfinished synthetic work\n")
    calls = []
    monkeypatch.setattr(phase_tools.subprocess, "run", lambda *a, **kw: calls.append(a))
    assert phase_tools.make_clone("5a", tmp_path) == 1
    assert sentinel.read_text() == "unfinished synthetic work\n"
    assert calls == []


def test_search_execution_errors_are_not_reported_as_silence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("### Searches\n\n```zsh\ngit grep '[broken' -- src\n```\n")
    monkeypatch.setattr(
        phase_tools.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 2, "", "invalid pattern"),
    )
    assert phase_tools.run_searches(spec, tmp_path) == 1


def test_acceptance_keeps_shell_alternation_and_command_order() -> None:
    assert accept.read_rows(SPEC, "Acceptance") == [
        ("A1", ".venv/bin/python scripts/check.py --first tooling"),
        ("A2", ".venv/bin/python -m coverage report --fail-under=100"),
        ("Q1", "git grep --untracked -n -E 'forbidden|also_bad' -- src"),
    ]
    guide = r"""## 5. Searches

| # | Rule | Command |
|---|---|---|
| Q1 | Refusal | `git grep -E 'first\|second' -- src` |
"""
    assert accept.read_rows(guide, "5. Searches") == [("Q1", "git grep -E 'first|second' -- src")]


@pytest.mark.parametrize("code", [0, 1, 2])
def test_acceptance_stops_before_coverage_on_check_failure_and_keeps_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    folder = tmp_path / "docs/phases"
    folder.mkdir(parents=True)
    (folder / "phase-05a-synthetic.md").write_text(SPEC)
    calls = []

    def run(command: str, root: Path) -> tuple[int, str]:
        assert root == tmp_path
        calls.append(command)
        return (code, "synthetic check output\n") if len(calls) == 1 else (0, "")

    monkeypatch.setattr(accept, "run_shell", run)
    logs = tmp_path / "evidence"
    assert accept.main(["--phase", "5a", "--root", str(tmp_path), "--log-dir", str(logs)]) == (
        0 if code == 0 else 1
    )
    assert len(calls) == (3 if code == 0 else 1)
    assert (logs / "000.log").read_text() == (
        f"$ .venv/bin/python scripts/check.py --first tooling\nexit: {code}\n"
        "synthetic check output\n"
    )


def test_dry_run_does_not_execute_or_create_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "docs/phases"
    folder.mkdir(parents=True)
    (folder / "phase-05a-synthetic.md").write_text(SPEC)
    calls = []
    monkeypatch.setattr(accept, "run_shell", lambda *a: calls.append(a))
    logs = tmp_path / "evidence"
    assert (
        accept.main(["--phase", "5a", "--root", str(tmp_path), "--log-dir", str(logs), "--dry-run"])
        == 0
    )
    assert calls == []
    assert not logs.exists()


def test_shell_pipeline_failure_is_preserved(tmp_path: Path) -> None:
    assert accept.run_shell("false | cat", tmp_path) == (1, "")


def test_progress_appends_and_only_replaces_the_named_phase() -> None:
    original = "# Progress\n\n" + ENTRY + "\n" + ENTRY.replace("5a", "5b")
    updated = progress.put_entry(original, ENTRY.replace("5a", "5c"))
    assert updated == original.rstrip("\n") + "\n\n" + ENTRY.replace("5a", "5c")
    corrected = ENTRY.replace("10 -> 12", "10 -> 13")
    assert progress.put_entry(original, corrected, replace=True) == (
        "# Progress\n\n" + corrected + "\n" + ENTRY.replace("5a", "5b")
    )


@pytest.mark.parametrize(
    ("original", "entry", "replace"),
    [
        ("# Progress\n\n" + ENTRY, ENTRY, False),
        ("# Progress\n", ENTRY, True),
        ("# Progress\n", ENTRY.replace("2026-11-17", "2026-99-99"), False),
        ("# Progress\n", ENTRY.replace("10 -> 12", "-1 -> 12"), False),
        ("# Progress\n\n## Broken\n", ENTRY, False),
    ],
)
def test_progress_refuses_duplicates_missing_replacements_and_invalid_entries(
    original: str, entry: str, replace: bool
) -> None:
    with pytest.raises(ValueError):
        progress.put_entry(original, entry, replace=replace)


MUTATIONS = """suite = ["tests/test_calc.py"]

[prefixes]
TC = "tests/test_calc.py::"

[[mutation]]
id = "S1"
file = "src/calc.py"
where = "add"
change = "Subtract instead"
old = "return a + b"
new = "return a - b"
test = "tests/test_calc.py::test_add"
correct = "5"
broken = "-1 | wrong"

[[mutation]]
id = "S2"
file = "src/calc.py"
where = "add"
change = "Swap the operands"
old = "return a + b"
new = "return b + a"
test = "tests/test_calc.py::test_add"
correct = "5"
broken = "5"

[[mutation]]
id = "S3"
file = "src/calc.py"
where = "half"
change = "Floor division"
old = "return n / 2"
new = "return n // 2"
test = "tests/test_add_only.py::test_add"
correct = "2.5"
broken = "2"

[[mutation]]
id = "S4"
file = "src/calc.py"
where = "nowhere"
change = "Text not in the file"
old = "return missing"
new = "return 0"
test = "tests/test_calc.py::test_add"
correct = "-"
broken = "-"
"""


def synthetic_clone(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src/calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef half(n):\n    return n / 2\n"
    )
    test = "import calc\n\n\ndef test_add():\n    assert calc.add(2, 3) == 5\n"
    (root / "tests/test_calc.py").write_text(
        test + "\n\ndef test_half():\n    assert calc.half(5) == 2.5\n"
    )
    (root / "tests/test_add_only.py").write_text(test)
    (root / "pytest.ini").write_text("[pytest]\npythonpath = src\n")
    (root / ".venv").symlink_to(ROOT / ".venv")
    return root


def test_mutate_refuses_the_repository_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = tmp_path / "rows.toml"
    rows.write_text(MUTATIONS)
    calls = []
    monkeypatch.setattr(phase_tools.subprocess, "run", lambda *a, **kw: calls.append(a))
    assert phase_tools.mutate(ROOT, rows, False) == 2
    assert phase_tools.mutate(ROOT / "src", rows, False) == 2
    assert calls == []
    assert "refusing to mutate the repository" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("suite = []\n", "no [[mutation]] rows"),
        ('[[mutation]]\nid = "S1"\n', "mutation 1: missing broken, change, correct"),
        (MUTATIONS.replace('id = "S2"', 'id = "S1"'), "mutation 2: repeated id S1"),
        (MUTATIONS.replace('"return a - b"', '"return a + b"'), "mutation S1: old and new"),
        (MUTATIONS.replace('broken = "5"', 'broken = "5"\nprobe = true'), "no top-level probe"),
        ("[[mutation]\n", "Expected"),
    ],
    ids=["no-rows", "missing-keys", "repeated-id", "no-change", "probe-without-file", "not-toml"],
)
def test_mutate_refuses_a_bad_file_before_touching_the_clone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, reason: str
) -> None:
    clone = synthetic_clone(tmp_path / "clone")
    before = (clone / "src/calc.py").read_bytes()
    rows = tmp_path / "rows.toml"
    rows.write_text(text)
    assert phase_tools.mutate(clone, rows, False) == 2
    assert reason in capsys.readouterr().out
    assert (clone / "src/calc.py").read_bytes() == before


def test_mutate_reports_each_row_restores_bytes_and_prints_guide_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clone = synthetic_clone(tmp_path / "clone")
    before = (clone / "src/calc.py").read_bytes()
    rows = tmp_path / "rows.toml"
    rows.write_text(MUTATIONS)
    assert phase_tools.mutate(clone, rows, True) == 1
    out = capsys.readouterr().out
    assert "caught S1: assert -1 == 5" in out
    assert "MISSED S2: deciding test passed; suite catches: nothing" in out
    assert "MISSED S3: deciding test passed; suite catches: test_half" in out
    assert "SKIPPED S4: old text found 0 times in src/calc.py" in out
    assert "1/4 caught" in out
    assert "| S1 | add | Subtract instead | TC test_add | 5 | -1 \\| wrong |" in out
    assert "| S3 | half | Floor division | tests/test_add_only.py::test_add | 2.5 | 2 |" in out
    assert (clone / "src/calc.py").read_bytes() == before
    assert not [p for p in clone.rglob("__pycache__") if ".venv" not in p.parts]
