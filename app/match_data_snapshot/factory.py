from app.database import Database

from .fingerprint import MatchDataSnapshotFingerprint
from .policy import DEFAULT_MATCH_DATA_SNAPSHOT_POLICY, MatchDataSnapshotPolicy
from .repository import SQLiteMatchDataSnapshotRepository
from .service import MatchDataSnapshotService
from .validation import MatchDataSnapshotValidator


def build_match_data_snapshot_service(
    database: Database,
    *,
    policy: MatchDataSnapshotPolicy = DEFAULT_MATCH_DATA_SNAPSHOT_POLICY,
) -> MatchDataSnapshotService:
    """Compose persistence and validation without provider or scheduler work."""
    return MatchDataSnapshotService(
        SQLiteMatchDataSnapshotRepository(database),
        MatchDataSnapshotValidator(policy, MatchDataSnapshotFingerprint()),
    )
