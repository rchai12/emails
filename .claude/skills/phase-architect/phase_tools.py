"""Small jobs the phase-architect checklist repeats, each printing only what the next step needs.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py searches SPEC [--cwd DIR]
        Run each command of the spec's "### Searches" block in DIR (default: the repository) and
        print how many lines each one matched. Use it on today's code (expect 0s) and on a copy
        with planted lines (expect matches).

    Add --plant FILE to append each `path<TAB>line` of FILE to its file (in --cwd), run the
        searches, and restore every file exactly; each search should then match.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py context MODULE...
        Print the public outline of each module: signatures, dataclass fields, public constants.
        MODULE is a file path, `gmail_sync`, or `mailroom.gmail_sync`.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py clone 1h --scratch DIR
        Make (or remake) DIR/fail01h from the repository with the venv linked, and say whether
        `mailroom` imports from the clone.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py failcheck CLONE TEST...
        Run only these tests in the clone and print the summary and each distinct failure reason.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py promote CLONE FILE... \
            [--ignore TEST...]
        Copy given files from the clone into the repository, compare each byte for byte, then run
        the Start command (the whole suite without the --ignore files) and print its last line.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py new --id 1b \
            --slug gmail-adapter --title "Gmail adapter" --n 165 --given tests/unit/test_gmail.py \
            --create src/mailroom/gmail.py [--sections core] [--out DIR]
        Write a spec skeleton with every fixed section filled; the architect replaces each TODO.

    .venv/bin/python .claude/skills/phase-architect/phase_tools.py guide SPEC [--out FILE]
        Write the verification guide's fixed parts from a finished spec: Coder ran, Gates, the
        probe section, Searches and Verdict. Spot checks and variations are left as TODO.

Only `clone`, `promote` and `--plant` write files: the clone, the given files, and planted lines
that are restored before it returns.
"""

import argparse
import ast
import filecmp
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
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


def plant_and_search(spec_path: Path, cwd: Path, plant: Path) -> int:
    planted: dict[Path, list[str]] = {}
    for line in plant.read_text(encoding="utf-8").splitlines():
        if line.strip():
            path, text = line.split("\t", 1)
            planted.setdefault(cwd / path, []).append(text)
    saved = {path: path.read_bytes() if path.exists() else None for path in planted}
    try:
        for path, lines in planted.items():
            before = (saved[path] or b"").decode()
            if before and not before.endswith("\n"):
                before += "\n"
            path.write_text(before + "\n".join(lines) + "\n", encoding="utf-8")
        return run_searches(spec_path, cwd)
    finally:
        for path, content in saved.items():
            if content is None:
                path.unlink()
            else:
                path.write_bytes(content)
        print("planted lines removed")


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"def {node.name}({ast.unparse(node.args)}){returns}"


def module_path(name: Path) -> Path:
    """A file path as given; `gmail_sync` or `mailroom.gmail_sync` as its file in src/mailroom."""
    if name.suffix == ".py":
        return name
    return ROOT / "src" / "mailroom" / (str(name).removeprefix("mailroom.") + ".py")


def outline(path: Path) -> list[str]:
    lines = [f"== {path}"]
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if not node.name.startswith("_"):
                lines.append(signature(node))
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(base) for base in node.bases)
            lines.append(f"class {node.name}({bases})" if bases else f"class {node.name}")
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    lines.append("    " + ast.unparse(item))
                elif isinstance(item, ast.FunctionDef) and (
                    not item.name.startswith("_") or item.name == "__init__"
                ):
                    lines.append("    " + signature(item))
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [ast.unparse(target) for target in targets]
            if all(name[0].isupper() and (name.isupper() or "_" not in name) for name in names):
                text = ast.unparse(node).replace("\n", " ")
                lines.append(text if len(text) <= 100 else text[:97] + "...")
    return lines


def clone_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": "src:.", "PYTHONDONTWRITEBYTECODE": "1"}


def make_clone(phase: str, scratch: Path) -> int:
    dest = scratch.resolve() / f"fail{file_id(phase)}"
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(["git", "clone", "-q", str(ROOT), str(dest)], check=True)
    (dest / ".venv").symlink_to(ROOT / ".venv")
    found = subprocess.run(
        [".venv/bin/python", "-c", "import mailroom; print(mailroom.__file__)"],
        cwd=dest,
        env=clone_env(),
        capture_output=True,
        text=True,
    ).stdout.strip()
    inside = Path(found).resolve().is_relative_to(dest)
    print(f"{dest}\nmailroom imports from the clone: {'yes' if inside else 'NO: ' + found}")
    return 0 if inside else 1


def fail_check(clone: Path, tests: list[str]) -> int:
    done = subprocess.run(
        [".venv/bin/python", "-m", "pytest", "--no-cov", "-q", "-p", "no:cacheprovider", "-rfE"]
        + ["--tb=line", *tests],
        cwd=clone,
        env=clone_env(),
        capture_output=True,
        text=True,
    )
    lines = done.stdout.splitlines()
    reasons: Counter[str] = Counter()
    for line in lines:
        found = re.fullmatch(r"\S+:[0-9]+: (.*)", line)
        if found is not None:
            reasons[found.group(1)[:110]] += 1
    for reason, count in reasons.most_common():
        print(f"{count:4}  {reason}")
    print(lines[-1] if lines else "no output")
    return 0


def promote(clone: Path, files: list[str], ignore: list[str]) -> int:
    differ = []
    for name in files:
        (ROOT / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(clone / name, ROOT / name)
        if not filecmp.cmp(clone / name, ROOT / name, shallow=False):
            differ.append(name)
    print(f"copied {len(files)}; differ: {', '.join(differ) or 'none'}")
    done = subprocess.run(
        [".venv/bin/python", "-m", "pytest", "--no-cov", "-q", "-p", "no:cacheprovider"]
        + [f"--ignore={name}" for name in ignore],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
    )
    lines = done.stdout.splitlines()
    print("Start:", lines[-1] if lines else "no output")
    return 1 if differ else 0


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
    searches.add_argument("--plant", type=Path)
    context = commands.add_parser("context")
    context.add_argument("modules", nargs="+", type=Path)
    clone = commands.add_parser("clone")
    clone.add_argument("id")
    clone.add_argument("--scratch", type=Path, required=True)
    failcheck = commands.add_parser("failcheck")
    failcheck.add_argument("clone", type=Path)
    failcheck.add_argument("tests", nargs="+")
    given = commands.add_parser("promote")
    given.add_argument("clone", type=Path)
    given.add_argument("files", nargs="+")
    given.add_argument("--ignore", nargs="+", default=[])
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
        if args.plant is not None:
            return plant_and_search(args.spec, args.cwd, args.plant)
        return run_searches(args.spec, args.cwd)
    if args.command == "context":
        for module in args.modules:
            print("\n".join(outline(module_path(module))))
        return 0
    if args.command == "clone":
        return make_clone(args.id, args.scratch)
    if args.command == "failcheck":
        return fail_check(args.clone, args.tests)
    if args.command == "promote":
        return promote(args.clone, args.files, args.ignore)
    if args.command == "new":
        name = f"phase-{file_id(args.id)}-{args.slug}.md"
        return write(spec_skeleton(args), target(args.out, name))
    return write(guide_from_spec(args.spec), target(args.out, args.spec.name))


if __name__ == "__main__":
    sys.exit(main())
