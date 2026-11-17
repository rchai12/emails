"""Run trusted phase-document commands sequentially and retain a compact evidence digest.

This executes shell code from the chosen spec/guide; inspect --dry-run first.
Exit status detects command errors, not compliance with the document's Must show column.
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_rows(markdown: str, heading: str) -> list[tuple[str, str]]:
    marker = f"## {heading}"
    lines = markdown.splitlines()
    if marker not in lines:
        raise ValueError("missing command section")
    rows = []
    in_code = False
    for line in lines[lines.index(marker) + 1 :]:
        if line.startswith("## "):
            break
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code and line.strip():
            rows.append((f"Q{sum(label.startswith('Q') for label, _ in rows) + 1}", line))
        elif line.startswith("|"):
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
            command_cell = 0 if cells[0].startswith("`") else 1 if heading == "2. Gates" else 2
            if command_cell >= len(cells):
                continue
            found = re.match(r"`([^`]+)`", cells[command_cell])
            if found is not None:
                label = f"A{len(rows) + 1}" if command_cell == 0 else cells[0]
                rows.append((label, found.group(1).replace("\\|", "|")))
    if not rows:
        raise ValueError("empty command section")
    return rows


def digest(label: str, command: str, code: int, output: str) -> list[str]:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    result = [f"{label}: exit {code}; {lines[-1] if lines else 'empty'}"]
    if "scripts/check.py" in command:
        for i, line in enumerate(lines):
            if line == "Sections:":
                result.append(line)
                for row in lines[i + 1 :]:
                    if not row.startswith("  "):
                        break
                    result.append(row)
    elif command.startswith(("git status", "git diff", "git grep")):
        result.extend(lines[:20])
    elif code:
        result.extend(lines[-20:-1])
    return result


def run_shell(command: str, root: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["/bin/zsh", "-o", "pipefail", "-c", command],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "command timed out"
    return result.returncode, result.stdout + result.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--guide", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument(
        "--dry-run", action="store_true", help="List commands without executing them."
    )
    args = parser.parse_args(argv)
    match = re.fullmatch(r"(0|[1-9][0-9]*)([a-z]?)", args.phase)
    if match is None:
        parser.error("phase must be an unpadded id such as 0 or 5a")
    padded = f"{int(match.group(1)):02d}{match.group(2)}"
    root = args.root.resolve()
    folder = root / "docs" / ("verification" if args.guide else "phases")
    files = sorted(folder.glob(f"phase-{padded}-*.md"))
    if len(files) != 1:
        parser.error("expected exactly one phase document")
    try:
        text = files[0].read_text(encoding="utf-8")
        rows = (
            read_rows(text, "2. Gates") + read_rows(text, "5. Searches")
            if args.guide
            else read_rows(text, "Acceptance")
        )
    except ValueError:
        parser.error("missing or empty command section; use the document's commands directly")
    if args.dry_run:
        for label, command in rows:
            print(f"{label}: {command}")
        return 0
    log_dir = args.log_dir or Path(tempfile.mkdtemp(prefix=f"mailroom-accept-{args.phase}-"))
    log_dir.mkdir(parents=True, exist_ok=True)
    for label, command in rows:
        code, output = run_shell(command, root)
        # Labels come from trusted documents; filenames still stay inside the log directory.
        log = log_dir / f"{len(list(log_dir.glob('*.log'))):03d}.log"
        log.write_text(f"$ {command}\nexit: {code}\n{output}", encoding="utf-8")
        print("\n".join(digest(label, command, code, output)), flush=True)
        search = command.startswith("git grep")
        if code != 0 and not (search and code == 1):
            print(f"Stopped at {label}. Logs: {log_dir}")
            return 1
    print(f"Commands completed; compare outputs with Must show. Logs: {log_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
