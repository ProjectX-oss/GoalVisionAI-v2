class MatchDataSnapshotError(Exception):
    """Base error for immutable pre-match snapshots."""


class SnapshotValidationError(MatchDataSnapshotError, ValueError):
    def __init__(self, reason_code: str, explanation: str) -> None:
        super().__init__(explanation)
        self.reason_codes = (reason_code,)
        self.explanations = (explanation,)


class SnapshotConflictError(MatchDataSnapshotError):
    """Persisted history conflicts with the requested append."""


class SnapshotPersistenceError(MatchDataSnapshotError):
    """Snapshot history could not be read or appended safely."""
