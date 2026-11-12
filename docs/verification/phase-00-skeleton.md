# Verification guide: Phase 0 (skeleton)

Spec: `docs/phases/phase-00-skeleton.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never call `get_secret` or `keyring` against the real Keychain, and never connect to a real mail provider, Discord, the tasks app or the model.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/__init__.py`, `clock.py`, `ids.py`, `config.py`, `keychain.py`, `cli.py`
- `.venv/bin/python` and `.venv/bin/mailroom`
- `grep -c "^## Phase 0: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-00-skeleton.md pyproject.toml tests/conftest.py` fails: G6 and G7 can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; `tests (core): passed`; in the `tests` step at least 96 passed, 0 failed, 0 skipped, no warnings summary; every `Sections:` line 0 failed |
| G2 | `.venv/bin/python -m coverage report --include=src/mailroom/__init__.py,src/mailroom/clock.py,src/mailroom/ids.py,src/mailroom/config.py,src/mailroom/keychain.py,src/mailroom/cli.py --fail-under=100` (right after G1) | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_reports.py tests/unit/test_reports_more.py tests/unit/test_reports_phase.py tests/unit/test_reports_phase_more.py tests/unit/test_clock_ids.py tests/unit/test_config.py tests/unit/test_keychain.py tests/unit/test_cli.py --no-cov -q` | `96 passed` |
| G4 | `.venv/bin/mailroom version` | `mailroom 0.1.0` |
| G5 | `.venv/bin/python scripts/check_reports.py --phase 0` | `Reports OK.` |
| G6 | `git diff HEAD --stat -- pyproject.toml scripts src/mailroom/reports.py tests/conftest.py tests/fakes.py tests/support.py tests/sections.toml tests/unit/test_reports.py tests/unit/test_reports_more.py tests/unit/test_reports_phase.py tests/unit/test_reports_phase_more.py tests/unit/test_clock_ids.py tests/unit/test_config.py tests/unit/test_keychain.py tests/unit/test_cli.py` | no output |
| G7 | `git status --short` | only: the six `src/mailroom/` modules above, `docs/progress.md`, and any `tests/unit/test_*_more.py` |
| G8 | `.venv/bin/python -m pip list --format=freeze` | no packages beyond `mailroom`, the dependencies of `pyproject.toml` (with their own dependencies), `pip` and `setuptools` |

## 3. Spot checks

For each row: copy the module outside the repository, make the change described in the module the coder wrote (the one line that does what the "Change" cell names), run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest <test> --no-cov -vv`, and confirm it fails with the "Broken" value. Then restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before. A different failure from the "Broken" column is a note, not a finding; a pass is a finding.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `config.py` | drop the step that sets the mode of an existing folder (keep only creating it) | `tests/unit/test_config.py::test_prepare_makes_an_existing_data_dir_private` | `0o700` (448) | `0o755` (493) |
| S2 | `config.py` | drop the absolute-path check | `tests/unit/test_config.py::test_a_relative_data_dir_is_refused[data]` | `ConfigError` raised | no exception: `data_dir` is `Path('data')` |
| S3 | `config.py` | cache `get_settings()` (for example `functools.cache`) | `tests/unit/test_config.py::test_settings_are_read_again_on_each_call` | `(…/data, …/other)` | `(…/data, …/data)` |
| S4 | `config.py` | compute the default from `Path.home()` once, at import | `tests/unit/test_config.py::test_the_default_data_dir_is_in_application_support` | the test's own `tmp_path/home/…` | the first test's home, or the real home |
| S5 | `keychain.py` | raise `KeychainUnavailable` without `from None` | `tests/unit/test_keychain.py::test_a_keychain_failure_hides_the_backend_text[error]` | `__suppress_context__` is `True` | `False` |
| S6 | `keychain.py` | check the name after the keychain call instead of before | `tests/unit/test_keychain.py::test_an_invalid_name_is_refused_before_the_keychain[capital]` | `calls == []` | `[('mailroom', 'Gmail')]` |
| S7 | `keychain.py` | treat only `None` as missing (an empty value is returned) | `tests/unit/test_keychain.py::test_an_empty_secret_is_missing` | `SecretMissing` | returns `''` |
| S8 | `keychain.py` | catch only `KeyringLocked` instead of `KeyringError` | `tests/unit/test_keychain.py::test_a_keychain_failure_hides_the_backend_text[error]` | `KeychainUnavailable` | `KeyringError` propagates |
| S9 | `keychain.py` | allow 65 characters instead of 64 | `tests/unit/test_keychain.py::test_an_invalid_name_is_refused_before_the_keychain[too-long]` | `ValueError` | `SecretMissing` |
| S10 | `cli.py` | print the version without the name | `tests/unit/test_cli.py::test_version_prints_the_name_and_version` | `'mailroom 0.1.0\n'` | `'0.1.0\n'` |
| S11 | `clock.py` | return `datetime.now()` (naive) | `tests/unit/test_clock_ids.py::test_now_is_an_aware_utc_moment` | `tzinfo` is `UTC` | `None` |

## 4. Probe

Save the script below outside the repository (for example `/tmp/probe-00.py`), run it from the repository root with `.venv/bin/python /tmp/probe-00.py`, and delete it afterwards. Every line must end in `ok`; the last line must be `FAILURES 0`. A stop at the `assert` lines before `oracle: ok` is the probe's fault: report it under "For the architect", not as a finding. The probe installs its own fake keychain and temporary folders before it imports `mailroom`; it never reads the real Keychain.

```python
"""Phase 0 probe: what the given tests do not reach. Run from the repository root.

It installs its own fake keychain and temporary HOME and data folders before importing mailroom,
so it never reads the real Keychain or the real data folder.
"""

import os
import random
import stat
import subprocess
import tempfile
from pathlib import Path

import keyring.core
from keyring.backend import KeyringBackend
from keyring.compat import properties
from keyring.errors import KeyringError, PasswordSetError

FAILURES = 0


def check(label: str, function) -> None:
    global FAILURES
    try:
        passed = function()
    except Exception as error:  # noqa: BLE001
        passed = False
        label = f"{label} (raised {type(error).__name__})"
    if not passed:
        FAILURES += 1
    print(f"{label}: {'ok' if passed else 'FAIL'}")


class Fake(KeyringBackend):
    def __init__(self) -> None:
        super().__init__()
        self.secrets: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, str]] = []
        self.error: Exception | None = None

    @properties.classproperty
    def priority(cls) -> float:
        return 0

    def get_password(self, service, username):
        self.calls.append((service, username))
        if self.error is not None:
            raise self.error
        return self.secrets.get((service, username))

    def set_password(self, service, username, password):
        raise AssertionError("no writes")

    def delete_password(self, service, username):
        raise AssertionError("no deletes")


FAKE = Fake()
keyring.core._keyring_backend = FAKE
WORK = Path(tempfile.mkdtemp())
os.environ["HOME"] = str(WORK / "home")
for key in list(os.environ):
    if key.startswith("MAILROOM_"):
        del os.environ[key]

# Oracle: a secret name is 1 to 64 characters from this table, the first a lowercase letter.
FIRST = set("abcdefghijklmnopqrstuvwxyz")
REST = FIRST | set("0123456789._-")


def oracle_valid(name: str) -> bool:
    return (
        1 <= len(name) <= 64 and name[0] in FIRST and all(c in REST for c in name[1:])
    )


assert oracle_valid("gmail.token")
assert oracle_valid("a" * 64)
assert not oracle_valid("a" * 65)
assert not oracle_valid("gmail.token\n")
assert not oracle_valid("gmailé")
assert not oracle_valid("")
assert not oracle_valid("1gmail")
print("oracle: ok")

from mailroom import config, keychain  # noqa: E402


def name_case(name: str) -> bool:
    FAKE.calls.clear()
    FAKE.error = None
    FAKE.secrets[("mailroom", name)] = "value-1"
    try:
        found = keychain.get_secret(name)
    except ValueError as error:
        return (
            not oracle_valid(name)
            and str(error) == "invalid secret name"
            and FAKE.calls == []
        )
    return oracle_valid(name) and found == "value-1"


for name in [
    "gmail.token\n",
    "gmail\ntoken",
    "gmailé",
    "gmail٣",
    "ｇmail",
    "gmail\t",
    "\ngmail",
]:
    check(f"name {name!r}", lambda name=name: name_case(name))

BASE = "gmail.token"
EXTRA = "abcxyz09._-AZ /\\:é\n\t~*"
rng = random.Random(0)
for _ in range(40):
    where = rng.randrange(len(BASE) + 1)
    char = rng.choice(EXTRA)
    name = BASE[:where] + char + BASE[where:]
    check(f"name {name!r}", lambda name=name: name_case(name))


def hides(error: Exception) -> bool:
    FAKE.error = error
    try:
        keychain.get_secret("gmail.token")
    except keychain.KeychainUnavailable as raised:
        text = str(raised)
        return text == "keychain unavailable: gmail.token" and "value-1" not in repr(
            raised
        )
    finally:
        FAKE.error = None
    return False


check("a KeyringError subclass is hidden", lambda: hides(PasswordSetError("value-1")))
check("a bare KeyringError is hidden", lambda: hides(KeyringError("token value-1")))


def data_dir(value: str) -> Path:
    os.environ["MAILROOM_DATA_DIR"] = value
    try:
        return config.get_settings().data_dir
    finally:
        del os.environ["MAILROOM_DATA_DIR"]


check("'~' alone is the home folder", lambda: data_dir("~") == WORK / "home")
check(
    "a trailing slash is dropped", lambda: data_dir(str(WORK / "x") + "/") == WORK / "x"
)


def refused(value: str) -> bool:
    try:
        data_dir(value)
    except config.ConfigError as error:
        return str(error) == "MAILROOM_DATA_DIR must be an absolute path"
    return False


check("'data/~' is refused", lambda: refused("data/~"))
check("'.' is refused", lambda: refused("."))


def private_under(umask: int, name: str) -> bool:
    old = os.umask(umask)
    try:
        os.environ["MAILROOM_DATA_DIR"] = str(WORK / name)
        found = config.prepare_data_dir(config.get_settings())
    finally:
        os.umask(old)
        del os.environ["MAILROOM_DATA_DIR"]
    return stat.S_IMODE(found.stat().st_mode) == 0o700


check("private under umask 000", lambda: private_under(0o000, "u000"))
check("private under umask 077", lambda: private_under(0o077, "u077"))


def prepare_twice() -> bool:
    os.environ["MAILROOM_DATA_DIR"] = str(WORK / "twice")
    try:
        first = config.prepare_data_dir(config.get_settings())
        second = config.prepare_data_dir(config.get_settings())
    finally:
        del os.environ["MAILROOM_DATA_DIR"]
    return first == second == WORK / "twice"


check("prepare twice is harmless", prepare_twice)


def command(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(Path(".venv/bin/mailroom")), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "COLUMNS": "200"},
    )


check(
    "the installed command prints the version",
    lambda: command("version").stdout == "mailroom 0.1.0\n",
)
check(
    "the installed command lists version in help",
    lambda: "version" in command("--help").stdout,
)

print(f"FAILURES {FAILURES}")
```

## 5. Searches

Each prints nothing. A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | the keychain is only read, through `keyring.get_password` | `git grep --untracked -n -E 'set_password\|delete_password\|set_keyring\(\|keyring\.core' -- src` |
| Q2 | time and ids only in `clock.py` and `ids.py` | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|uuid[0-9]' -- src ':!src/mailroom/clock.py' ':!src/mailroom/ids.py'` |
| Q3 | time and ids read through the module | `git grep --untracked -n -E 'from mailroom\.(clock\|ids) import' -- src` |
| Q4 | no network code in this phase | `git grep --untracked -n -E 'import (socket\|ssl\|imaplib\|smtplib\|http\|urllib\|requests\|httpx)([^A-Za-z_]\|$)' -- src` |
| Q5 | settings come only from `get_settings()` | `git grep --untracked -n -E 'os\.environ\|getenv\(' -- src ':!src/mailroom/config.py'` |
| Q6 | no output or logging outside the CLI | `git grep --untracked -n -E 'print\(\|logging\|logger' -- src ':!src/mailroom/cli.py'` |
| Q7 | no coverage exclusions | `git grep --untracked -n -E 'pragma: no cover' -- src` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- The default `data_dir` as a `default_factory`, a validator, or a computed default, as long as it is computed when settings are read.
- `~` expanded with `Path.expanduser()` in a validator, or in `get_settings()`.
- The name rule written as one `re.fullmatch`, or as character sets; any form that matches the whole name.
- `os.makedirs` or `Path.mkdir(parents=True, exist_ok=True)`, followed by `chmod(0o700)`.
- `typer.echo` or `print` in `cli.py`; `no_args_is_help=True` or not; a docstring on the callback.
- Exception messages set through `__init__` or passed when raising.
- Private helpers inside the Scope modules, and extra behaviour tests in `tests/unit/test_*_more.py`.

## 7. Verdict

Write `docs/reviews/phase-00-skeleton.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 0`), then run `.venv/bin/python scripts/check_reports.py --phase 0`; it must print `Reports OK.`
