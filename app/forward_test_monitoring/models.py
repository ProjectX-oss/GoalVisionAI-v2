"""Immutable monitoring result contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    affected_identifier: str
    provenance: str
    detail: str


@dataclass(frozen=True, slots=True)
class PersistOutcome:
    identifier: str
    replayed: bool
    fingerprint: str


class MonitoringConflictError(RuntimeError):
    """An immutable request identifier was replayed with different content."""
