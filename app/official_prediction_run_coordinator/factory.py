from app.database import Database

from .coordinator import OfficialPredictionRunCoordinator
from .discovery import DeterministicOfficialPredictionCandidateDiscovery
from .policy import (
    DEFAULT_OFFICIAL_PREDICTION_RUN_POLICY,
    OfficialPredictionRunPolicy,
)
from .ports import (
    OfficialSinglePredictionOrchestrator,
    PersistedOfficialPredictionCandidateSource,
)
from .repository import (
    SQLiteOfficialCandidateHistoricalStateReader,
    SQLiteOfficialPredictionRunRepository,
)


def build_official_prediction_run_coordinator(
    database: Database,
    candidate_source: PersistedOfficialPredictionCandidateSource,
    orchestration: OfficialSinglePredictionOrchestrator,
    *,
    policy: OfficialPredictionRunPolicy = DEFAULT_OFFICIAL_PREDICTION_RUN_POLICY,
) -> OfficialPredictionRunCoordinator:
    """Compose the manual coordinator without executing or scheduling a run."""
    states = SQLiteOfficialCandidateHistoricalStateReader(database)
    discovery = DeterministicOfficialPredictionCandidateDiscovery(
        candidate_source,
        states,
    )
    return OfficialPredictionRunCoordinator(
        discovery=discovery,
        orchestration=orchestration,
        runs=SQLiteOfficialPredictionRunRepository(database, migrate=False),
        policy=policy,
    )
