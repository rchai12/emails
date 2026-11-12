"""Helpers shared by tests: running a command, and fixed times and ids.

New tests import these instead of copying them.
"""

from datetime import datetime

import pytest
from typer.testing import CliRunner

from mailroom import clock, ids
from mailroom.cli import app

runner = CliRunner(env={"COLUMNS": "200"})


def run(*args: object):
    """Run `mailroom` with these arguments, each turned into text."""
    return runner.invoke(app, [str(arg) for arg in args])


def fixed_times(monkeypatch: pytest.MonkeyPatch, *moments: str) -> None:
    """Make `clock.now()` return these ISO moments, one per call, in order."""
    times = iter([datetime.fromisoformat(moment) for moment in moments])
    monkeypatch.setattr(clock, "now", lambda: next(times))


def fixed_ids(monkeypatch: pytest.MonkeyPatch, *values: str) -> None:
    """Make `ids.new_id()` return these values, one per call, in order."""
    found = iter(values)
    monkeypatch.setattr(ids, "new_id", lambda: next(found))
