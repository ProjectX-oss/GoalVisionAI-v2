"""Explicit database, environment, and scope safety for model operations."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.database import Database

from .models import SUPPORTED_MODEL_SCOPES


SUPPORTED_ENVIRONMENTS = ("lab", "staging", "production")
DATABASE_TIMEOUT_SECONDS = 5.0


class ModelOperationsConfigurationError(ValueError):
    pass


@dataclass
class OpenedOperationsDatabase:
    connection: sqlite3.Connection
    path: Path
    read_only: bool
    _database: Database | None = None

    def close(self) -> None:
        if self._database is not None:
            self._database.close()
        else:
            self.connection.close()


def validate_environment_scope(environment: str, scope: str) -> None:
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ModelOperationsConfigurationError("Unsupported environment.")
    if scope not in SUPPORTED_MODEL_SCOPES:
        raise ModelOperationsConfigurationError(
            "Unsupported model scope; an explicit supported scope is required."
        )


def resolve_database_path(value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ModelOperationsConfigurationError(
            "An explicit database path is required."
        )
    if value.strip() == ":memory:" or value.strip().casefold() in {
        "default",
        "production",
        "prod",
        "goalvision",
        "app",
    }:
        raise ModelOperationsConfigurationError(
            "In-memory databases and ambiguous database aliases are forbidden."
        )
    path = Path(value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ModelOperationsConfigurationError(
            "The explicit model operations database file does not exist."
        )
    return path


def open_operations_database(
    path: Path,
    *,
    read_only: bool,
) -> OpenedOperationsDatabase:
    if read_only:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
            timeout=DATABASE_TIMEOUT_SECONDS,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        opened = OpenedOperationsDatabase(connection, path, True)
    else:
        database = Database(path)
        database.connection.execute(
            f"PRAGMA busy_timeout = {int(DATABASE_TIMEOUT_SECONDS * 1000)}"
        )
        opened = OpenedOperationsDatabase(
            database.connection,
            path,
            False,
            database,
        )
    try:
        row = opened.connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()
        if row is None or row[0] is None or int(row[0]) < 31:
            raise ModelOperationsConfigurationError(
                "Model operations require database migration v31 or later."
            )
    except sqlite3.DatabaseError as exc:
        opened.close()
        raise ModelOperationsConfigurationError(
            "Database schema could not be verified."
        ) from exc
    return opened
