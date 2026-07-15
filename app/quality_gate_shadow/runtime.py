from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from app.database import Database
from app.models import Match
from app.pipeline import PredictionAssessment
from app.quality_gate import (
    DEFAULT_OFFICIAL_QUALITY_GATE_POLICY,
    InMemoryDuplicatePublicationChecker,
    PublicationQualityGate,
)

from .adapter import (
    PredictionShadowContextAdapter,
    ShadowObservationFacts,
)
from .config import ShadowModeConfig
from .models import (
    ShadowEvaluationError,
    ShadowEvaluationOutcome,
    ShadowEvaluationResult,
    ShadowEvaluationStage,
)
from .repository import SQLiteShadowEvaluationRepository
from .service import QualityGateShadowEvaluationService


@runtime_checkable
class ShadowObservationFactsProvider(Protocol):
    def facts_for(
        self,
        match: Match,
        assessment: PredictionAssessment,
    ) -> ShadowObservationFacts | None: ...


class MissingShadowObservationFactsProvider:
    def facts_for(
        self,
        match: Match,
        assessment: PredictionAssessment,
    ) -> ShadowObservationFacts | None:
        return None


@runtime_checkable
class QualityGateShadowObserver(Protocol):
    def observe(
        self,
        match: Match,
        assessment: PredictionAssessment,
    ) -> ShadowEvaluationResult: ...

    def close(self) -> None: ...


class DisabledQualityGateShadowObserver:
    def observe(
        self,
        match: Match,
        assessment: PredictionAssessment,
    ) -> ShadowEvaluationResult:
        return ShadowEvaluationResult(outcome=ShadowEvaluationOutcome.DISABLED)

    def close(self) -> None:
        return None


class EnabledQualityGateShadowObserver:
    def __init__(
        self,
        adapter: PredictionShadowContextAdapter,
        service: QualityGateShadowEvaluationService,
        facts: ShadowObservationFactsProvider,
        clock: Callable[[], datetime],
        database: Database | None = None,
    ) -> None:
        self._adapter = adapter
        self._service = service
        self._facts = facts
        self._clock = clock
        self._database = database

    def observe(
        self,
        match: Match,
        assessment: PredictionAssessment,
    ) -> ShadowEvaluationResult:
        observed_at = self._clock()
        try:
            adaptation = self._adapter.adapt(
                match,
                assessment,
                observed_at,
                self._facts.facts_for(match, assessment),
                ShadowEvaluationStage.INITIAL_CANDIDATE,
            )
            if adaptation.request is None:
                return ShadowEvaluationResult(
                    outcome=ShadowEvaluationOutcome.INELIGIBLE,
                    unavailable_fields=adaptation.unavailable_fields,
                )
            return self._service.evaluate(adaptation.request)
        except Exception as exc:
            prediction_id = f"official-{match.fixture_id}-adapter-error"
            error_type = type(exc).__name__
            if not error_type.isidentifier():
                error_type = "ShadowObservationFailure"
            error = ShadowEvaluationError(
                shadow_evaluation_id=(
                    f"shadow:{prediction_id}:"
                    f"{DEFAULT_OFFICIAL_QUALITY_GATE_POLICY.version}:"
                    f"{ShadowEvaluationStage.INITIAL_CANDIDATE.value}"
                ),
                prediction_id=prediction_id,
                stage=ShadowEvaluationStage.INITIAL_CANDIDATE,
                policy_version=DEFAULT_OFFICIAL_QUALITY_GATE_POLICY.version,
                error_type=error_type,
                safe_message="Quality gate shadow observation failed safely.",
                occurred_at=observed_at,
            )
            return self._service.record_error(error)

    def close(self) -> None:
        if self._database is not None:
            self._database.close()


def build_quality_gate_shadow_observer(
    config: ShadowModeConfig | None = None,
    facts: ShadowObservationFactsProvider | None = None,
    clock: Callable[[], datetime] | None = None,
) -> QualityGateShadowObserver:
    resolved = config or ShadowModeConfig.from_environment()
    if not resolved.enabled:
        return DisabledQualityGateShadowObserver()
    database = Database(resolved.database_path)
    repository = SQLiteShadowEvaluationRepository(database)
    policy = DEFAULT_OFFICIAL_QUALITY_GATE_POLICY
    gate = PublicationQualityGate(
        policy=policy,
        duplicates=InMemoryDuplicatePublicationChecker(),
    )
    service = QualityGateShadowEvaluationService(gate, repository)
    adapter = PredictionShadowContextAdapter(policy.version)
    return EnabledQualityGateShadowObserver(
        adapter=adapter,
        service=service,
        facts=facts or MissingShadowObservationFactsProvider(),
        clock=clock or (lambda: datetime.now(timezone.utc)),
        database=database,
    )
