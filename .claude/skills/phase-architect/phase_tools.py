"""Small jobs the phase-architect checklist repeats, each printing only what the next step needs.

    python3.12 .claude/skills/phase-architect/phase_tools.py searches SPEC [--cwd DIR]
        Run each command of the spec's "### Searches" block in DIR (default: the repository) and
        print how many lines each one matched. Use it on today's code (expect 0s) and on a copy
        with planted lines (expect matches).

    python3.12 .claude/skills/phase-architect/phase_tools.py embedded GUIDE FILE
        Check that the guide's ```python block is byte for byte the probe FILE.

It only reads files and runs the spec's own read-only git grep commands.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def search_commands(spec: str) -> list[str]:
    lines = spec.splitlines()
    try:
        start = lines.index("### Searches")
    except ValueError:
        return []
    commands, inside = [], False
    for line in lines[start + 1 :]:
        if line.startswith("```"):
            if inside:
                break
            inside = True
            continue
        if inside and line.strip():
            commands.append(line)
    return commands


def run_searches(spec_path: Path, cwd: Path) -> int:
    commands = search_commands(spec_path.read_text(encoding="utf-8"))
    if not commands:
        print("no ### Searches block")
        return 1
    for command in commands:
        done = subprocess.run(["zsh", "-c", command], cwd=cwd, capture_output=True, text=True)
        count = len([line for line in done.stdout.splitlines() if line.strip()])
        print(f"{count:3}  {command[:90]}")
    return 0


def check_embedded(guide_path: Path, file_path: Path) -> int:
    guide = guide_path.read_text(encoding="utf-8")
    marker = "```python\n"
    if marker not in guide:
        print("no ```python block")
        return 1
    start = guide.index(marker) + len(marker)
    end = guide.index("\n```", start) + 1
    same = guide[start:end] == file_path.read_text(encoding="utf-8")
    print("embedded copy identical" if same else "embedded copy DIFFERS")
    return 0 if same else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    searches = commands.add_parser("searches")
    searches.add_argument("spec", type=Path)
    searches.add_argument("--cwd", type=Path, default=ROOT)
    embedded = commands.add_parser("embedded")
    embedded.add_argument("guide", type=Path)
    embedded.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.command == "searches":
        return run_searches(args.spec, args.cwd)
    return check_embedded(args.guide, args.file)


if __name__ == "__main__":
    sys.exit(main())
