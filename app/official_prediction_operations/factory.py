"""Side-effect-free safety factories and injected transport boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS

from .exceptions import DatabaseSafetyError, DestinationVerificationError


class OperationsEnvironment(str, Enum):
    FIXTURE = "fixture"
    STAGING = "staging"
    PRODUCTION = "production"


class DestinationVerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"
    INDETERMINATE = "INDETERMINATE"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class DestinationVerification:
    state: DestinationVerificationState
    destination_identity: str | None
    destination_type: str | None
    environment: OperationsEnvironment | None
    enabled: bool
    display_name: str | None = None


@runtime_checkable
class DestinationVerificationPort(Protocol):
    def verify(self) -> DestinationVerification: ...


@dataclass(frozen=True, slots=True)
class StaticDestinationVerifier:
    verification: DestinationVerification

    def verify(self) -> DestinationVerification:
        return self.verification


class NoSendTelegramTransport:
    """Dry-run sentinel. Any invocation is a safety violation."""

    is_no_send_transport = True

    def __init__(self) -> None:
        self.calls = 0

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> int | None:
        self.calls += 1
        raise AssertionError("Dry-run no-send transport was invoked.")


def resolve_database_path(
    value: str,
    *,
    create_database: bool,
    publish: bool,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise DatabaseSafetyError("An explicit non-empty database path is required.")
    if value.strip() == ":memory:":
        if publish:
            raise DatabaseSafetyError("publish-fixture refuses an in-memory database.")
        return Path(":memory:")
    if value.strip().lower() in {"production", "prod", "default", "goalvision", "app"}:
        raise DatabaseSafetyError("Ambiguous database aliases are forbidden.")
    path = Path(value).expanduser().resolve()
    if path.exists() and path.is_dir():
        raise DatabaseSafetyError("Database path resolves to a directory.")
    if not path.exists():
        if not create_database:
            raise DatabaseSafetyError("Database file is missing; use --create-database explicitly.")
        if not path.parent.exists() or not path.parent.is_dir():
            raise DatabaseSafetyError("Database parent directory must already exist.")
    return path


def open_operations_database(path: Path) -> Database:
    database = Database(":memory:" if str(path) == ":memory:" else path)
    MigrationManager(database.connection).migrate()
    latest = database.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    if latest != MIGRATIONS[-1].version:
        database.close()
        raise DatabaseSafetyError("Database migration verification failed.")
    return database


def verify_publish_destination(
    verifier: DestinationVerificationPort,
    *,
    expected_identity: str,
    expected_type: str,
    environment: OperationsEnvironment,
) -> DestinationVerification:
    value = verifier.verify()
    if (
        value.state is not DestinationVerificationState.VERIFIED
        or not value.enabled
        or value.destination_identity != expected_identity
        or value.destination_type != expected_type
        or value.environment is not environment
    ):
        raise DestinationVerificationError("Destination is disabled, indeterminate, unknown, or mismatched.")
    return value
