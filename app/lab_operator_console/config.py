"""Versioned, fail-closed local console configuration."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path


CONSOLE_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class ConsoleConfig:
    database: Path
    allowed_database_roots: tuple[Path, ...]
    environment: str = "LAB"
    host: str = "127.0.0.1"
    port: int = 8765
    read_only: bool = True
    session_secret: bytes = b""
    ephemeral_session: bool = True
    session_ttl_seconds: int = 3600
    csrf_ttl_seconds: int = 1800
    maximum_page_size: int = 100
    maximum_export_bytes: int = 10_000_000
    timezone: str = "Europe/Riga"
    action_timeout_seconds: int = 30
    operator_identifier: str = "local-operator"
    controlled_demo: bool = False

    @classmethod
    def build(cls, database: Path, **changes) -> "ConsoleConfig":
        database = database.resolve()
        roots = tuple(Path(item).resolve() for item in changes.pop("allowed_database_roots", (Path.cwd(),)))
        secret = changes.pop("session_secret", None) or secrets.token_bytes(32)
        value = cls(database=database, allowed_database_roots=roots, session_secret=secret, **changes)
        value.validate()
        return value

    def validate(self) -> None:
        if self.host != "127.0.0.1":
            raise ValueError("EXTERNAL_BINDING_REJECTED: only 127.0.0.1 is supported by this foundation.")
        if not 1024 <= self.port <= 65535:
            raise ValueError("Console port must be between 1024 and 65535.")
        if not any(_within(self.database, root) for root in self.allowed_database_roots):
            raise ValueError("Database is outside the allowed roots.")
        if not self.database.exists():
            raise ValueError("Console database does not exist.")
        if self.environment not in {"DEVELOPMENT", "LAB"}:
            raise ValueError("Console environment must be DEVELOPMENT or LAB.")
        if not 1 <= self.maximum_page_size <= 500:
            raise ValueError("Maximum page size is outside the safe bound.")
        if len(self.session_secret) < 32:
            raise ValueError("Session secret must contain at least 32 bytes.")

    def public_view(self) -> dict[str, object]:
        return {"version":CONSOLE_VERSION,"environment":self.environment,"database":str(self.database),"host":self.host,"port":self.port,"read_only":self.read_only,"ephemeral_session":self.ephemeral_session,"session_ttl_seconds":self.session_ttl_seconds,"timezone":self.timezone,"scheduler_enabled":False,"automatic_publication_enabled":False}


def _within(path: Path, root: Path) -> bool:
    try: path.relative_to(root); return True
    except ValueError: return False
