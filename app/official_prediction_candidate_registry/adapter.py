import sqlite3
from datetime import datetime

from app.official_prediction_orchestration import (
    OfficialCandidateAssemblyRequest,
    OfficialPredictionFacts,
    PublicationDeliveryState,
    SQLiteOfficialPublicationStateReader,
)
from app.official_prediction_run_coordinator import (
    OfficialPredictionCandidateReference,
)

from .exceptions import CandidateRegistryPersistenceError
from .models import (
    CandidatePublicationGuardState,
    OfficialCandidateMarket,
    OfficialPredictionCandidateVersion,
)
from .ports import OfficialCandidateAssemblyContextProvider
from .repository import SQLiteOfficialPredictionCandidateRepository


class SQLiteOfficialCandidatePublicationGuard:
    """Reuses durable prediction-level publication state without claiming it."""

    def __init__(self, reader: SQLiteOfficialPublicationStateReader) -> None:
        self._reader = reader

    def state(
        self,
        prediction_id: str,
        match_id: str,
        evaluated_at: datetime,
    ) -> CandidatePublicationGuardState:
        try:
            state = self._reader.get(prediction_id, match_id, evaluated_at).state
        except sqlite3.DatabaseError as exc:
            raise CandidateRegistryPersistenceError(
                "Publication protection could not be read."
            ) from exc
        except (TypeError, ValueError):
            return CandidatePublicationGuardState.UNKNOWN
        return {
            PublicationDeliveryState.NEVER_ATTEMPTED: (
                CandidatePublicationGuardState.UNPUBLISHED
            ),
            PublicationDeliveryState.CONFIRMED_FAILED_RETRYABLE: (
                CandidatePublicationGuardState.UNPUBLISHED
            ),
            PublicationDeliveryState.PUBLISHED: CandidatePublicationGuardState.PUBLISHED,
            PublicationDeliveryState.CLAIMED: (
                CandidatePublicationGuardState.ACTIVE_CLAIM
            ),
            PublicationDeliveryState.ATTEMPTING: (
                CandidatePublicationGuardState.ACTIVE_CLAIM
            ),
            PublicationDeliveryState.INDETERMINATE_FAILURE: (
                CandidatePublicationGuardState.INDETERMINATE
            ),
        }[state]


class RegistryOfficialPredictionCandidateSource:
    """Adapts active registry versions to the coordinator's existing source port."""

    def __init__(
        self,
        repository: SQLiteOfficialPredictionCandidateRepository,
        contexts: OfficialCandidateAssemblyContextProvider,
    ) -> None:
        self._repository = repository
        self._contexts = contexts

    def load_candidates(
        self,
        evaluated_at: datetime,
        normalized_filters: tuple[tuple[str, str], ...],
    ) -> tuple[OfficialPredictionCandidateReference, ...]:
        versions = self._repository.discover_ready_candidates(
            evaluated_at,
            normalized_filters,
        )
        return tuple(self._reference(value, evaluated_at) for value in versions)

    def _reference(
        self,
        candidate: OfficialPredictionCandidateVersion,
        evaluated_at: datetime,
    ) -> OfficialPredictionCandidateReference:
        item = candidate.prepared
        context = self._contexts.load(candidate, evaluated_at)
        prediction = OfficialPredictionFacts(
            prediction_id=item.prediction_id,
            match_id=item.match_id,
            model_version=item.model_version,
            market=_orchestration_market(item.market_identity.market),
            selection=item.market_identity.selection,
            market_line=item.market_identity.market_line,
            raw_probability=item.raw_model_probability,
            decimal_odds=item.decimal_odds,
            odds_timestamp=item.odds_timestamp,
            expected_value=item.supplied_expected_value,
            confidence=item.confidence_level,
            prediction_timestamp=item.prediction_creation_timestamp,
            kickoff_timestamp=item.kickoff_timestamp,
            core_data_timestamp=item.core_match_data_timestamp,
            supporting_data_status=item.supporting_data_status,
            market_availability=item.market_availability,
            lineup_status=item.lineup_status,
            injury_status=item.injury_suspension_status,
            registry_candidate_id=candidate.registry_candidate_id,
            registry_content_fingerprint=item.content_fingerprint,
        )
        request = OfficialCandidateAssemblyRequest(
            prediction=prediction,
            calibration_records=context.calibration_records,
            model_health_records=context.model_health_records,
            risk_evaluations=context.risk_evaluations,
            exposure_evaluations=context.exposure_evaluations,
            bankroll=context.bankroll,
            evaluation_timestamp=evaluated_at,
            dry_run=False,
        )
        return OfficialPredictionCandidateReference(
            prediction_id=item.prediction_id,
            match_id=item.match_id,
            immutable_fingerprint=item.content_fingerprint,
            kickoff_timestamp=item.kickoff_timestamp,
            prediction_created_timestamp=item.prediction_creation_timestamp,
            bankroll_scope=item.bankroll_scope,
            destination_scope=item.destination_scope,
            request=request,
            registry_candidate_id=candidate.registry_candidate_id,
            candidate_version=candidate.candidate_version,
        )


def _orchestration_market(value: OfficialCandidateMarket) -> str:
    return {
        OfficialCandidateMarket.MATCH_WINNER: "MATCH WINNER",
        OfficialCandidateMarket.DOUBLE_CHANCE: "DOUBLE CHANCE",
        OfficialCandidateMarket.TOTALS: "TOTALS",
        OfficialCandidateMarket.BTTS: "BTTS",
    }[value]
