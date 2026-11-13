import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from mailroom.schema import MIGRATIONS

DB_FILENAME = "mailroom.sqlite3"
SCHEMA_MESSAGE = "unsupported schema version"


class StoreError(Exception):
    pass


class StoreBase:
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA secure_delete = ON")
        path.chmod(0o600)
        self._migrate()

    def _migrate(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version > len(MIGRATIONS):
            self.close()
            raise StoreError(f"{SCHEMA_MESSAGE}: {version}")
        for index in range(version, len(MIGRATIONS)):
            pragma = f"PRAGMA user_version = {index + 1};"
            script = "BEGIN;\n" + MIGRATIONS[index] + "\n" + pragma + "\nCOMMIT;"
            self._connection.executescript(script)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "StoreBase":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @contextmanager
    def _write(self) -> Iterator[None]:
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    @staticmethod
    def _stamp(moment: datetime) -> str:
        return moment.astimezone(UTC).isoformat(timespec="microseconds")

    @staticmethod
    def _read_time(value: str) -> datetime:
        return datetime.fromisoformat(value)
