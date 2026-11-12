"""Print problems in progress entries and reviews.

Run it as: .venv/bin/python scripts/check_reports.py [--root PATH] [--phase ID]
"""

import argparse
import sys
from pathlib import Path

from mailroom.reports import check_reports

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check progress entries and reviews.")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root (default: the folder above scripts/).",
    )
    parser.add_argument(
        "--phase",
        default=None,
        help="Also require this phase's spec and progress entry.",
    )
    options = parser.parse_args(argv)
    try:
        problems = check_reports(options.root, phase=options.phase)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem.text)
    count = len(problems)
    if count == 0:
        print("Reports OK.")
        return 0
    if count == 1:
        print("1 problem.")
    else:
        print(f"{count} problems.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
