"""Print the facts step 1 of the phase-architect checklist needs, in one short run.

Run it from anywhere: python3.12 .claude/skills/phase-architect/phase_status.py
(or .venv/bin/python once the environment exists). It only reads; it changes nothing.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC_NAME = re.compile(r"^phase-([0-9]{2,})([a-z]?)-.+\.md$")
HEADING = re.compile(r"^## Phase ([0-9]+[a-z]?): ")


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return done.stdout.rstrip() if done.returncode == 0 else f"(git {args[0]} failed)"


def phase_id(spec_name: str) -> str | None:
    found = SPEC_NAME.fullmatch(spec_name)
    if found is None:
        return None
    return str(int(found.group(1))) + found.group(2)


def last_entry(progress: Path) -> list[str]:
    if not progress.is_file():
        return ["(no docs/progress.md)"]
    lines = progress.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if HEADING.match(line)]
    if not starts:
        return ["(no entries yet)"]
    entry = []
    for line in lines[starts[-1] :]:
        if entry and line.startswith("## "):
            break
        entry.append(line)
    return [line for line in entry if line.strip()]


def main() -> int:
    phases = ROOT / "docs" / "phases"
    reviews = ROOT / "docs" / "reviews"
    specs = sorted(path.name for path in phases.glob("phase-*.md")) if phases.is_dir() else []
    reviewed = {path.name for path in reviews.glob("*.md")} if reviews.is_dir() else set()

    print("== tree")
    print(git("status", "--short") or "clean")
    print("== last commits")
    print(git("log", "--oneline", "-5"))
    print("== specs without a review")
    waiting = [f"{phase_id(name) or '?'}: {name}" for name in specs if name not in reviewed]
    print("\n".join(waiting) or "none")
    print("== latest progress entry")
    entry = last_entry(ROOT / "docs" / "progress.md")
    print("\n".join(entry))
    print("== newest review head")
    if reviewed:
        newest = max(reviews.glob("*.md"), key=lambda path: path.stat().st_mtime)
        head = newest.read_text(encoding="utf-8").splitlines()[:7]
        print(f"{newest.name}:")
        print("\n".join(head))
    else:
        print("none")
    print("== public names the last phase added")
    names = [line for line in entry if line.startswith("- New public names:")]
    print(names[0].removeprefix("- New public names: ") if names else "none recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
