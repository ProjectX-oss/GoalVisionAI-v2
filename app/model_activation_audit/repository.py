"""Bounded read-only SQLite inspection boundary."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class AuditConfigurationError(ValueError):
    """Known, safely reportable audit configuration failure."""


class ReadOnlyAuditRepository:
    def __init__(self, database: str, timeout_seconds: float = 5.0):
        if not database or database.strip() == ":memory:":
            raise AuditConfigurationError(
                "An explicit existing database file is required."
            )
        if not 0.1 <= timeout_seconds <= 10.0:
            raise AuditConfigurationError(
                "Read-only timeout must be between 0.1 and 10 seconds."
            )
        self.path = Path(database).expanduser().resolve()
        if not self.path.is_file():
            raise AuditConfigurationError(
                "The explicit audit database file does not exist."
            )
        try:
            self.connection = sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro",
                uri=True,
                timeout=timeout_seconds,
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute(
                f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}"
            )
            self.connection.execute("PRAGMA query_only = ON")
        except sqlite3.Error as exc:
            raise AuditConfigurationError(
                "The audit database could not be opened read-only."
            ) from exc

    def close(self) -> None:
        self.connection.close()

    def scalar(self, sql: str, parameters: tuple = ()):
        row = self.connection.execute(sql, parameters).fetchone()
        return None if row is None else row[0]

    def rows(self, sql: str, parameters: tuple = ()) -> tuple[sqlite3.Row, ...]:
        return tuple(self.connection.execute(sql, parameters).fetchall())

    def object_names(self, kind: str) -> set[str]:
        return {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type=?", (kind,)
            )
        }

    def object_sql(self, kind: str, name: str) -> str:
        row = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type=? AND name=?",
            (kind, name),
        ).fetchone()
        return "" if row is None or row[0] is None else row[0]

    def foreign_keys(self, table: str) -> set[tuple[str, str]]:
        return {
            (row["from"], row["table"])
            for row in self.connection.execute(
                f'PRAGMA foreign_key_list("{table}")'
            )
        }

    def foreign_key_failures(self) -> tuple[sqlite3.Row, ...]:
        return tuple(self.connection.execute("PRAGMA foreign_key_check"))
