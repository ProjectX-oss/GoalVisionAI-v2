"""Fail-closed database copying for a manual Lab-only rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import shutil


class RehearsalSafetyError(RuntimeError):
    """Raised before any copy when the source or destination is ambiguous."""


@dataclass(frozen=True, slots=True)
class RehearsalDatabaseCopies:
    source: Path
    backup: Path
    rehearsal: Path
    source_fingerprint: str
    backup_fingerprint: str
    rehearsal_fingerprint: str


def resolve_database_source(
    *,
    explicit: Path | None,
    discovered: tuple[Path, ...] = (),
) -> Path:
    """Resolve exactly one existing source, never guessing among candidates."""
    candidates = (explicit,) if explicit is not None else discovered
    normalized = tuple(
        dict.fromkeys(path.resolve() for path in candidates if path is not None)
    )
    existing = tuple(path for path in normalized if path.is_file())
    if len(existing) != 1:
        raise RehearsalSafetyError(
            "Exactly one existing database source is required; "
            f"found {len(existing)}."
        )
    return existing[0]


def create_rehearsal_database_copies(
    source: Path,
    destination_directory: Path,
    *,
    timestamp: str,
) -> RehearsalDatabaseCopies:
    """Create a byte-identical backup and an isolated working copy."""
    source = source.resolve()
    destination_directory = destination_directory.resolve()
    if not source.is_file():
        raise RehearsalSafetyError("The database source does not exist.")
    if not timestamp or any(character not in "0123456789TZ" for character in timestamp):
        raise RehearsalSafetyError("A compact UTC timestamp is required.")
    backup = destination_directory / f"goalvision_backup_{timestamp}.db"
    rehearsal = destination_directory / f"goalvision_lab_rehearsal_{timestamp}.db"
    if source in {backup, rehearsal}:
        raise RehearsalSafetyError("The source cannot be a rehearsal destination.")
    if backup.exists() or rehearsal.exists():
        raise RehearsalSafetyError("A rehearsal destination already exists.")

    destination_directory.mkdir(parents=True, exist_ok=True)
    source_fingerprint = sha256_file(source)
    try:
        shutil.copy2(source, backup)
        shutil.copy2(source, rehearsal)
    except Exception:
        backup.unlink(missing_ok=True)
        rehearsal.unlink(missing_ok=True)
        raise
    backup_fingerprint = sha256_file(backup)
    rehearsal_fingerprint = sha256_file(rehearsal)
    if not (
        source_fingerprint
        == backup_fingerprint
        == rehearsal_fingerprint
    ):
        backup.unlink(missing_ok=True)
        rehearsal.unlink(missing_ok=True)
        raise RehearsalSafetyError("A copied database fingerprint differs.")
    return RehearsalDatabaseCopies(
        source=source,
        backup=backup,
        rehearsal=rehearsal,
        source_fingerprint=source_fingerprint,
        backup_fingerprint=backup_fingerprint,
        rehearsal_fingerprint=rehearsal_fingerprint,
    )


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
