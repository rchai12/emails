"""Write a validated phase progress entry without rewriting other phases.

Run with .venv/bin/python scripts/progress.py --help.
"""

import argparse
import re
import sys
from pathlib import Path

from mailroom.reports import parse_progress

ROOT = Path(__file__).resolve().parent.parent


def put_entry(original: str, entry: str, *, replace: bool = False) -> str:
    entries, problems = parse_progress(entry)
    existing, old_problems = parse_progress(original)
    if problems or old_problems or len(entries) != 1:
        raise ValueError("progress entries must match docs/phase-conventions.md")
    phase = entries[0].phase
    matches = [item for item in existing if item.phase == phase]
    if len(matches) > 1 or (matches and not replace):
        raise ValueError("phase entry already exists; use --replace for a correction")
    if replace and not matches:
        raise ValueError("cannot replace a missing phase entry")
    if not matches:
        return original.rstrip("\n") + "\n\n" + entry.rstrip("\n") + "\n"
    lines = original.splitlines(keepends=True)
    start = matches[0].line - 1
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    suffix = "".join(lines[end:])
    return "".join(lines[:start]) + entry.rstrip("\n") + "\n" + ("\n" + suffix if suffix else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write one validated progress entry.")
    parser.add_argument("--file", type=Path, default=ROOT / "docs/progress.md")
    for name in ("phase", "title", "date", "names"):
        parser.add_argument(f"--{name}", required=True)
    for name in ("tests-before", "tests-after", "given", "changed"):
        parser.add_argument(f"--{name}", required=True, type=int)
    parser.add_argument("--deviation", action="append", default=[])
    parser.add_argument("--follow-up", action="append", default=[])
    parser.add_argument(
        "--replace", action="store_true", help="Replace this phase on a correction."
    )
    args = parser.parse_args(argv)
    strings = [args.phase, args.title, args.date, args.names, *args.deviation, *args.follow_up]
    if any(not value.strip() or re.search(r"[\r\n]", value) for value in strings):
        parser.error("fields must be nonempty single lines")
    if min(args.tests_before, args.tests_after, args.given, args.changed) < 0:
        parser.error("counts must be nonnegative")
    lines = [
        f"## Phase {args.phase}: {args.title} ({args.date})",
        f"- Tests: {args.tests_before} -> {args.tests_after} (given {args.given})",
        f"- New public names: {args.names}",
        f"- Changed files: {args.changed}",
        "- Deviations:",
        *[f"  - {value}" for value in (args.deviation or ["None"])],
        "- Follow-ups:",
        *[f"  - {value}" for value in (args.follow_up or ["None"])],
    ]
    try:
        updated = put_entry(
            args.file.read_text(encoding="utf-8"), "\n".join(lines), replace=args.replace
        )
    except ValueError:
        print("Error: invalid progress or duplicate/missing phase; inspect entries and --replace.")
        return 2
    args.file.write_text(updated, encoding="utf-8")
    print(f"Progress entry for Phase {args.phase} written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
