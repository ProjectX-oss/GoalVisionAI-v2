from app.database import Database
from app.official_prediction_orchestration import SQLiteOfficialPublicationStateReader

from .adapter import (
    RegistryOfficialPredictionCandidateSource,
    SQLiteOfficialCandidatePublicationGuard,
)
from .fingerprint import OfficialCandidateRegistryFingerprint
from .policy import (
    DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY,
    OfficialPredictionCandidateRegistryPolicy,
)
from .ports import (
    OfficialCandidateAssemblyContextProvider,
    OfficialCandidatePublicationGuard,
)
from .repository import SQLiteOfficialPredictionCandidateRepository
from .service import OfficialPredictionCandidateRegistryService
from .validation import OfficialPredictionCandidateValidator


def build_official_prediction_candidate_registry(
    database: Database,
    *,
    policy: OfficialPredictionCandidateRegistryPolicy = (
        DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY
    ),
    publication_guard: OfficialCandidatePublicationGuard | None = None,
) -> OfficialPredictionCandidateRegistryService:
    """Compose the registry without ingesting, scheduling, or publishing."""
    repository = SQLiteOfficialPredictionCandidateRepository(database)
    return OfficialPredictionCandidateRegistryService(
        repository=repository,
        validator=OfficialPredictionCandidateValidator(
            policy,
            OfficialCandidateRegistryFingerprint(),
        ),
        publication_guard=(
            publication_guard
            if publication_guard is not None
            else SQLiteOfficialCandidatePublicationGuard(
                SQLiteOfficialPublicationStateReader(database)
            )
        ),
    )


def build_registry_candidate_source(
    database: Database,
    contexts: OfficialCandidateAssemblyContextProvider,
) -> RegistryOfficialPredictionCandidateSource:
    """Build the read-only registry adapter for the existing run coordinator."""
    return RegistryOfficialPredictionCandidateSource(
        SQLiteOfficialPredictionCandidateRepository(database),
        contexts,
    )
