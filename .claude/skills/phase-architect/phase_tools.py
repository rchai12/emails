"""Small jobs the phase-architect checklist repeats, each printing only what the next step needs.

    python3.12 .claude/skills/phase-architect/phase_tools.py searches SPEC [--cwd DIR]
        Run each command of the spec's "### Searches" block in DIR (default: the repository) and
        print how many lines each one matched. Use it on today's code (expect 0s) and on a copy
        with planted lines (expect matches).

    python3.12 .claude/skills/phase-architect/phase_tools.py embedded GUIDE FILE
        Check that the guide's ```python block is byte for byte the probe FILE (phases 0 and 1a,
        which embed the probe; later phases commit it as docs/verification/probe-NNx.py).

    python3.12 .claude/skills/phase-architect/phase_tools.py new --id 1b --slug gmail-adapter \
            --title "Gmail adapter" --n 165 --given tests/unit/test_gmail.py \
            --create src/mailroom/gmail.py [--sections core] [--out DIR]
        Write a spec skeleton with every fixed section filled; the architect replaces each TODO.

    python3.12 .claude/skills/phase-architect/phase_tools.py guide SPEC [--out FILE]
        Write the verification guide's fixed parts from a finished spec: Coder ran, Gates, the
        probe section, Searches and Verdict. Spot checks and variations are left as TODO.

It only reads files and runs the spec's own read-only git grep commands.
"""

import argparse
import re
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


STANDING_SEARCHES = (
    "git grep --untracked -n -E 'import (socket|ssl|imaplib|smtplib|http|urllib|requests|httpx)"
    "([^A-Za-z_]|$)|from (socket|ssl|imaplib|smtplib|http|urllib|requests|httpx)([^A-Za-z_]|$)'"
    " -- src",
    "git grep --untracked -n -E 'print\\(|logging|logger|warnings\\.warn' -- src"
    " ':!src/mailroom/cli.py'",
    "git grep --untracked -n -E 'datetime\\.now|datetime\\.utcnow|date\\.today|time\\.time\\(|"
    "from mailroom\\.(clock|ids) import' -- src ':!src/mailroom/clock.py'",
    "git grep --untracked -n -E 'pragma: no cover|noqa' -- {created}",
)


def file_id(phase: str) -> str:
    found = re.fullmatch(r"(0|[1-9][0-9]*)([a-z]?)", phase)
    if found is None:
        raise SystemExit("phase id must look like 0 or 1b")
    return f"{int(found.group(1)):02d}{found.group(2)}"


def spec_skeleton(args: argparse.Namespace) -> str:
    padded = file_id(args.id)
    probe = f"docs/verification/probe-{padded}.py"
    args.given = [path for path in args.given if path != probe]  # the template adds it
    given_tests = [path for path in args.given if Path(path).name.startswith("test_")]
    created_src = [path for path in args.create if path.startswith("src/")]
    ignores = " ".join(f"--ignore={path}" for path in given_tests)
    given_rows = "\n".join(f"| `{path}` | TODO |" for path in args.given)
    scope_rows = "\n".join(f"| `{path}` | create |" for path in args.create)
    coverage = ",".join(created_src) or "TODO"
    searches = "\n".join(
        line.replace("{created}", " ".join(created_src) or "src") for line in STANDING_SEARCHES
    )
    return f"""# Phase {args.id}: {args.title}

## Goal

TODO: one paragraph: what this phase makes possible, and what it leaves for later.

Sections: `{args.sections}`. The `tooling` section runs in the full check.

Follow `docs/phase-conventions.md`. N is {args.n}, the tests the previous phase left passing.

Start: `.venv/bin/python -m pytest --no-cov -q {ignores}` must show `TODO passed` \
(N plus the given tests that already pass). The ignored files import modules you create. \
(TODO: keep only the files that cannot import yet.)

## Facts

TODO: what spikes and the library's code showed, each checked on this machine.

## Owner's decisions

TODO

## Architect's decisions

TODO

## Requirements

1. TODO

N. **Progress entry** for `## Phase {args.id}: {args.title} (YYYY-MM-DD)` at the end of \
`docs/progress.md`.

## Given files

Already committed with this spec; never change them.

| File | What it is |
|---|---|
{given_rows}
| `docs/verification/probe-{padded}.py` | The verifier's probe |

Given test count: **TODO**.

## Tests to write

The given tests cover every requirement's main cases. To reach full coverage, add behaviour tests \
in new `*_more.py` files, never by changing a given test.

## Scope

| Path | Change |
|---|---|
{scope_rows}
| `docs/progress.md` | append your entry |

## Out of scope

- TODO: what a capable coder would over-deliver.
- Any change to a given file, `AGENTS.md` or the design docs.

## Rules that bite

- TODO: the project rules this phase could break.
- **Time through the module**: `clock.now()`, never `datetime.now()`, and never \
`from mailroom.clock import now`.

## Acceptance

| Command | Must show |
|---|---|
| `.venv/bin/python scripts/check.py --first {args.sections}` | last line `All checks passed.`; \
summary lists `tests ({args.sections}): passed`; at least N + TODO passed, 0 failed, 0 skipped |
| `.venv/bin/python -m pytest {" ".join(given_tests)} --no-cov -q` | `TODO passed` |
| `.venv/bin/python -m coverage report --include={coverage} --fail-under=100`, right after \
`check.py` | exit 0, `TOTAL` at `100%` |
| `grep -c "^## Phase {args.id}: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase {args.id}` | `Reports OK.` |
| `git diff HEAD --stat -- {" ".join(args.given)} docs/verification/probe-{padded}.py` | no output |
| `git status --short` | only the Scope paths |

### Searches

Each prints nothing.

```zsh
{searches}
```
"""


def section(text: str, heading: str) -> str:
    start = text.index(heading) + len(heading)
    following = re.search(r"^#{2,3} ", text[start:], flags=re.MULTILINE)
    return text[start : start + following.start()] if following else text[start:]


def table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
            rows.append(cells)
    return rows[1:]


def paths_in(cell: str) -> list[str]:
    paths, folder = [], ""
    for name in re.findall(r"`([^`]+)`", cell):
        if "/" in name:
            folder = name.rsplit("/", 1)[0] + "/"
            paths.append(name)
        else:
            paths.append(folder + name)
    return paths


def guide_from_spec(spec_path: Path) -> str:
    spec = spec_path.read_text(encoding="utf-8")
    head = re.match(r"# Phase ([0-9]+[a-z]?): (.+)", spec)
    if head is None:
        raise SystemExit("the spec must start with '# Phase <id>: <title>'")
    phase, title = head.groups()
    padded = file_id(phase)
    given = [p for row in table_rows(section(spec, "## Given files")) for p in paths_in(row[0])]
    scope = table_rows(section(spec, "## Scope"))
    created = [paths_in(row[0])[0] for row in scope if row[1] == "create"]
    acceptance = table_rows(section(spec, "## Acceptance"))
    searches = search_commands(spec)
    search_intro = section(spec, "### Searches").strip().splitlines()[0]
    count = re.search(r"Given test count: \*\*([0-9]+)\*\*", spec)
    tracked = " ".join([f"docs/phases/{spec_path.name}", *given])
    gates = "\n".join(
        f"| G{number} | {row[0]} | {row[1]} |" for number, row in enumerate(acceptance, start=1)
    )
    last = len(acceptance) + 1
    search_rows = "\n".join(
        f"| Q{number} | TODO | `{command.replace('|', chr(92) + '|')}` |"
        for number, command in enumerate(searches, start=1)
    )
    present = "\n".join(f"- `{path}`" for path in created)
    return f"""# Verification guide: Phase {phase} ({title})

Spec: `docs/phases/{spec_path.name}`. Follow `docs/phase-conventions.md` ("For the verifier"). \
Never connect to a real mail provider, Discord, the tasks app or the model, never read the \
Keychain, and never open the real data folder.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

{present}
- `grep -c "^## Phase {phase}: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch {tracked}` \
fails: the diff gates can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order. Given test count: \
{count.group(1) if count else "TODO"}.

| # | Command | Must show |
|---|---|---|
{gates}
| G{last} | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this \
phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote.
3. Run the deciding test with \
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails \
with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is \
as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | TODO | TODO | TODO | TODO | TODO |

## 4. Probe

Run `.venv/bin/python docs/verification/probe-{padded}.py` from the repository root. It is a given \
file: do not edit it. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at \
the probe's own `assert` lines, before its self-check prints `ok`, is the probe's fault: report it \
under "For the architect", not as a finding. The probe uses temporary folders for `HOME` and the \
data folder and touches no network or Keychain.

TODO: one line on what the probe checks that the given tests do not.

## 5. Searches

{search_intro} A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
{search_rows}

(In the table, `\\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- TODO
- Private helpers inside the Scope modules, and extra behaviour tests in `*_more.py` files.

## 7. Verdict

Write `docs/reviews/{spec_path.name}` in the form `docs/phase-conventions.md` gives \
(`# Review: Phase {phase}`), then run `.venv/bin/python scripts/check_reports.py --phase {phase}`; \
it must print `Reports OK.`
"""


def target(out: Path | None, name: str) -> Path | None:
    """`--out` may name a folder (the file keeps its phase name) or the file itself."""
    return out / name if out is not None and out.is_dir() else out


def write(text: str, out: Path | None) -> int:
    if out is None:
        print(text, end="")
    else:
        out.write_text(text, encoding="utf-8")
        todos = text.count("TODO")
        print(f"wrote {out} ({len(text.splitlines())} lines, {todos} TODO)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    searches = commands.add_parser("searches")
    searches.add_argument("spec", type=Path)
    searches.add_argument("--cwd", type=Path, default=ROOT)
    embedded = commands.add_parser("embedded")
    embedded.add_argument("guide", type=Path)
    embedded.add_argument("file", type=Path)
    new = commands.add_parser("new")
    new.add_argument("--id", required=True)
    new.add_argument("--slug", required=True)
    new.add_argument("--title", required=True)
    new.add_argument("--n", required=True, type=int)
    new.add_argument("--sections", default="core")
    new.add_argument("--given", nargs="+", default=[])
    new.add_argument("--create", nargs="+", default=[])
    new.add_argument("--out", type=Path)
    guide = commands.add_parser("guide")
    guide.add_argument("spec", type=Path)
    guide.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "searches":
        return run_searches(args.spec, args.cwd)
    if args.command == "embedded":
        return check_embedded(args.guide, args.file)
    if args.command == "new":
        name = f"phase-{file_id(args.id)}-{args.slug}.md"
        return write(spec_skeleton(args), target(args.out, name))
    return write(guide_from_spec(args.spec), target(args.out, args.spec.name))


if __name__ == "__main__":
    sys.exit(main())
