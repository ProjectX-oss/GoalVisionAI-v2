from datetime import datetime

from .exceptions import (
    CandidateRegistrationValidationError,
    CandidateRegistryConflictError,
    CandidateRegistryPersistenceError,
    CandidateScopeValidationError,
)
from .models import (
    CandidateLifecycleOutcome,
    CandidateLifecycleResultStatus,
    CandidateLifecycleState,
    CandidatePublicationGuardState,
    CandidateRegistrationStatus,
    OfficialPredictionCandidateRegistrationCommand,
    OfficialPredictionCandidateRegistrationOutcome,
    OfficialPredictionCandidateVersion,
    PreparedOfficialPredictionCandidate,
)
from .ports import (
    OfficialCandidatePublicationGuard,
    OfficialPredictionCandidateRepository,
)
from .validation import OfficialPredictionCandidateValidator


class OfficialPredictionCandidateRegistryService:
    """Validates and appends supplied pre-match candidate facts only."""

    def __init__(
        self,
        repository: OfficialPredictionCandidateRepository,
        validator: OfficialPredictionCandidateValidator,
        publication_guard: OfficialCandidatePublicationGuard,
    ) -> None:
        self._repository = repository
        self._validator = validator
        self._publication_guard = publication_guard

    def register_candidate(
        self,
        command: OfficialPredictionCandidateRegistrationCommand,
    ) -> OfficialPredictionCandidateRegistrationOutcome:
        try:
            prepared = self._validator.prepare(command)
        except CandidateScopeValidationError as exc:
            return self._rejected(
                command,
                CandidateRegistrationStatus.REJECTED_SCOPE,
                exc,
            )
        except CandidateRegistrationValidationError as exc:
            return self._rejected(
                command,
                CandidateRegistrationStatus.REJECTED_INVALID,
                exc,
            )

        try:
            existing = self._repository.find_by_content_fingerprint(
                prepared.content_fingerprint
            )
            if existing is not None:
                return self._outcome(
                    existing,
                    CandidateRegistrationStatus.IDEMPOTENT_EXISTING,
                    ("IDENTICAL_CANDIDATE_EXISTS",),
                    ("Identical immutable candidate content already exists.",),
                )
            publication = self._publication_guard.state(
                prepared.prediction_id,
                prepared.match_id,
                prepared.registration_timestamp,
            )
            if publication is CandidatePublicationGuardState.PUBLISHED:
                return self._blocked(
                    prepared,
                    CandidateRegistrationStatus.ALREADY_PUBLISHED,
                    "PREDICTION_ALREADY_PUBLISHED",
                    "A terminally published prediction cannot receive a new READY version.",
                )
            if publication in {
                CandidatePublicationGuardState.ACTIVE_CLAIM,
                CandidatePublicationGuardState.INDETERMINATE,
                CandidatePublicationGuardState.UNKNOWN,
            }:
                return self._blocked(
                    prepared,
                    CandidateRegistrationStatus.CORRECTION_REQUIRED,
                    f"PUBLICATION_STATE_{publication.value}",
                    "Unsafe publication state requires explicit correction handling.",
                )
            registration = self._repository.register_candidate_version(prepared)
        except CandidateRegistryConflictError as exc:
            return self._blocked(
                prepared,
                CandidateRegistrationStatus.CONFLICT,
                "REGISTRY_CONFLICT",
                str(exc),
            )
        except CandidateRegistryPersistenceError:
            return self._blocked(
                prepared,
                CandidateRegistrationStatus.PERSISTENCE_FAILURE,
                "REGISTRY_PERSISTENCE_FAILURE",
                "Candidate registry persistence failed safely.",
            )

        if registration.identical_existing:
            return self._outcome(
                registration.candidate,
                CandidateRegistrationStatus.IDEMPOTENT_EXISTING,
                ("IDENTICAL_CANDIDATE_EXISTS",),
                ("Concurrent identical candidate registration was reused.",),
            )
        previous = registration.previous_candidate
        status = (
            CandidateRegistrationStatus.SUPERSEDED_PREVIOUS
            if previous is not None
            else CandidateRegistrationStatus.REGISTERED
        )
        reason = "PREVIOUS_READY_SUPERSEDED" if previous else "CANDIDATE_REGISTERED"
        explanation = (
            "Materially changed candidate content superseded the prior READY version."
            if previous
            else (
                f"Candidate version {registration.candidate.candidate_version} is "
                "structurally READY for coordinator discovery."
            )
        )
        return self._outcome(
            registration.candidate,
            status,
            (reason,),
            (explanation,),
            previous.registry_candidate_id if previous else None,
        )

    def withdraw_candidate(
        self,
        registry_candidate_id: str,
        *,
        reason_code: str,
        event_timestamp: datetime,
    ) -> CandidateLifecycleOutcome:
        return self._transition(
            CandidateLifecycleState.WITHDRAWN,
            registry_candidate_id,
            reason_code,
            event_timestamp,
        )

    def invalidate_candidate(
        self,
        registry_candidate_id: str,
        *,
        reason_code: str,
        event_timestamp: datetime,
    ) -> CandidateLifecycleOutcome:
        return self._transition(
            CandidateLifecycleState.INVALIDATED,
            registry_candidate_id,
            reason_code,
            event_timestamp,
        )

    def _transition(
        self,
        state: CandidateLifecycleState,
        registry_candidate_id: str,
        reason_code: str,
        event_timestamp: datetime,
    ) -> CandidateLifecycleOutcome:
        try:
            reason = self._validator.normalize_reason_code(reason_code)
            timestamp = self._validator.normalize_event_timestamp(event_timestamp)
        except CandidateRegistrationValidationError:
            return CandidateLifecycleOutcome(
                registry_candidate_id,
                None,
                CandidateLifecycleResultStatus.CONFLICT,
                "INVALID_LIFECYCLE_INPUT",
                event_timestamp,
            )
        try:
            event = (
                self._repository.withdraw_candidate(
                    registry_candidate_id,
                    reason,
                    timestamp,
                )
                if state is CandidateLifecycleState.WITHDRAWN
                else self._repository.invalidate_candidate(
                    registry_candidate_id,
                    reason,
                    timestamp,
                )
            )
        except CandidateRegistryConflictError:
            return CandidateLifecycleOutcome(
                registry_candidate_id,
                None,
                CandidateLifecycleResultStatus.CONFLICT,
                reason,
                timestamp,
            )
        except CandidateRegistryPersistenceError:
            return CandidateLifecycleOutcome(
                registry_candidate_id,
                None,
                CandidateLifecycleResultStatus.PERSISTENCE_FAILURE,
                reason,
                timestamp,
            )
        return CandidateLifecycleOutcome(
            registry_candidate_id,
            event.event_type,
            CandidateLifecycleResultStatus.APPLIED,
            event.reason_code,
            event.event_timestamp,
        )

    @staticmethod
    def _rejected(
        command: OfficialPredictionCandidateRegistrationCommand,
        status: CandidateRegistrationStatus,
        error: CandidateRegistrationValidationError,
    ) -> OfficialPredictionCandidateRegistrationOutcome:
        return OfficialPredictionCandidateRegistrationOutcome(
            registry_candidate_id=None,
            prediction_id=str(command.prediction_id),
            match_id=str(command.match_id),
            logical_identity_fingerprint=None,
            candidate_content_fingerprint=None,
            candidate_version=None,
            final_status=status,
            ordered_reason_codes=error.reason_codes,
            explanations=error.explanations,
            previous_candidate_id=None,
            registration_timestamp=command.registration_timestamp,
            model_version=str(command.model_version),
            market_identity=None,
        )

    @staticmethod
    def _blocked(
        prepared: PreparedOfficialPredictionCandidate,
        status: CandidateRegistrationStatus,
        reason: str,
        explanation: str,
    ) -> OfficialPredictionCandidateRegistrationOutcome:
        return OfficialPredictionCandidateRegistrationOutcome(
            registry_candidate_id=None,
            prediction_id=prepared.prediction_id,
            match_id=prepared.match_id,
            logical_identity_fingerprint=prepared.logical_identity_fingerprint,
            candidate_content_fingerprint=prepared.content_fingerprint,
            candidate_version=None,
            final_status=status,
            ordered_reason_codes=(reason,),
            explanations=(explanation,),
            previous_candidate_id=None,
            registration_timestamp=prepared.registration_timestamp,
            model_version=prepared.model_version,
            market_identity=prepared.market_identity,
        )

    @staticmethod
    def _outcome(
        candidate: OfficialPredictionCandidateVersion,
        status: CandidateRegistrationStatus,
        reasons: tuple[str, ...],
        explanations: tuple[str, ...],
        previous_candidate_id: str | None = None,
    ) -> OfficialPredictionCandidateRegistrationOutcome:
        prepared = candidate.prepared
        return OfficialPredictionCandidateRegistrationOutcome(
            registry_candidate_id=candidate.registry_candidate_id,
            prediction_id=prepared.prediction_id,
            match_id=prepared.match_id,
            logical_identity_fingerprint=prepared.logical_identity_fingerprint,
            candidate_content_fingerprint=prepared.content_fingerprint,
            candidate_version=candidate.candidate_version,
            final_status=status,
            ordered_reason_codes=reasons,
            explanations=explanations,
            previous_candidate_id=previous_candidate_id,
            registration_timestamp=prepared.registration_timestamp,
            model_version=prepared.model_version,
            market_identity=prepared.market_identity,
        )


def register_official_prediction_candidate(
    registry: OfficialPredictionCandidateRegistryService,
    command: OfficialPredictionCandidateRegistrationCommand,
) -> OfficialPredictionCandidateRegistrationOutcome:
    """Explicit application boundary; registration never executes publication."""
    return registry.register_candidate(command)
