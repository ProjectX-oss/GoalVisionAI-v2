"""Manual-only Lab rehearsal support for model operations."""

from .fixtures import LabFixtureManifest, seed_lab_fixture
from .execution import (
    CommandCapture,
    ExecutionRehearsalError,
    ExecutionRehearsalReport,
    SubprocessModelOperationsRunner,
    execute_activation_rollback_rehearsal,
    inspect_rehearsal_state,
)
from .safety import (
    RehearsalSafetyError,
    RehearsalDatabaseCopies,
    create_rehearsal_database_copies,
    resolve_database_source,
    sha256_file,
)

__all__ = [
    "LabFixtureManifest",
    "CommandCapture",
    "ExecutionRehearsalError",
    "ExecutionRehearsalReport",
    "RehearsalDatabaseCopies",
    "RehearsalSafetyError",
    "SubprocessModelOperationsRunner",
    "create_rehearsal_database_copies",
    "execute_activation_rollback_rehearsal",
    "inspect_rehearsal_state",
    "resolve_database_source",
    "seed_lab_fixture",
    "sha256_file",
]
