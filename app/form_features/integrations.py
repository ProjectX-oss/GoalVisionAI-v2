from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from app.models import Match
from app.pipeline import PredictionAssessment
from app.quality_gate import (
    EvidenceAssessment,
    EvidenceCategory,
    EvidenceStatus,
    ReviewReason,
)
from app.quality_gate_shadow import ShadowObservationFacts, ShadowObservationFactsProvider

from .models import (
    FormEvidenceStatus,
    FormSignal,
    HistoricalFormFeature,
    HistoricalFormWalkForwardInput,
    OpponentAdjustedFormSnapshot,
    OpponentStrengthObservation,
    VenueSplit,
)
from .repository import SQLiteFormFeatureRepository
from .snapshot import FormSnapshotBuilder


@dataclass(frozen=True, slots=True)
class FormQualityGateEvidence:
    status: EvidenceStatus
    sample_size: int
    review_signals: tuple[ReviewReason, ...]


class FormQualityGateAdapter:
    def map(
        self,
        snapshot: OpponentAdjustedFormSnapshot | None,
    ) -> FormQualityGateEvidence:
        if snapshot is None:
            return FormQualityGateEvidence(EvidenceStatus.MISSING, 0, (ReviewReason.OPTIONAL_EVIDENCE_PARTIAL,))
        status = EvidenceStatus(snapshot.form.evidence_status.value)
        reviews = (
            (ReviewReason.OPTIONAL_EVIDENCE_PARTIAL,)
            if status in {EvidenceStatus.MISSING, EvidenceStatus.PARTIAL, EvidenceStatus.STALE}
            or snapshot.form.signals
            else ()
        )
        return FormQualityGateEvidence(status, snapshot.form.sample_size, reviews)


class FormBacktestingAdapter:
    @staticmethod
    def feature(
        snapshot: OpponentAdjustedFormSnapshot,
        prediction_timestamp: datetime,
    ) -> HistoricalFormFeature:
        form = snapshot.form
        if form.calculation_timestamp > prediction_timestamp:
            raise ValueError("Form snapshot would leak future information.")
        if form.latest_source_observed_at and form.latest_source_observed_at > prediction_timestamp:
            raise ValueError("Form source observation would leak future information.")
        return HistoricalFormFeature(
            form.team_id,
            form.calculation_timestamp,
            form.evidence_status,
            form.sample_size,
            snapshot.adjusted_attacking_form,
            snapshot.adjusted_defensive_form,
            form.expected_goals.status,
            form.expected_goals.opponent_adjusted_xg_for,
            form.expected_goals.opponent_adjusted_xg_against,
        )

    @classmethod
    def walk_forward(
        cls,
        target_fixture_id: str,
        cutoff: datetime,
        snapshot: OpponentAdjustedFormSnapshot,
    ) -> HistoricalFormWalkForwardInput:
        return HistoricalFormWalkForwardInput(
            target_fixture_id,
            cutoff,
            cls.feature(snapshot, cutoff),
        )


class FormShadowFactsProvider:
    """Adds past-only team-form evidence to existing real shadow facts."""

    def __init__(
        self,
        base: ShadowObservationFactsProvider,
        repository: SQLiteFormFeatureRepository,
        opponent_strengths: tuple[OpponentStrengthObservation, ...] = (),
        builder: FormSnapshotBuilder | None = None,
    ) -> None:
        self._base = base
        self._repository = repository
        self._opponents = opponent_strengths
        self._builder = builder or FormSnapshotBuilder()
        self._adapter = FormQualityGateAdapter()

    def facts_for(self, match: Match, assessment: PredictionAssessment):
        return self._base.facts_for(match, assessment)

    def facts_for_at(
        self,
        match: Match,
        assessment: PredictionAssessment,
        evaluation_timestamp: datetime,
    ) -> ShadowObservationFacts | None:
        base = (
            self._base.facts_for_at(match, assessment, evaluation_timestamp)
            if hasattr(self._base, "facts_for_at")
            else self._base.facts_for(match, assessment)
        )
        if base is None:
            return None
        home = assessment.prediction.winner == match.home_team_name
        team_id = str(match.home_team_id if home else match.away_team_id)
        snapshot = self._builder.build(
            target_fixture_id=str(match.fixture_id),
            target_kickoff=match.kickoff,
            team_id=team_id,
            venue=VenueSplit.HOME if home else VenueSplit.AWAY,
            evaluation_timestamp=evaluation_timestamp,
            historical_observations=self._repository.history(
                team_id,
                cutoff=evaluation_timestamp,
            ),
            opponent_strengths=self._opponents,
        )
        evidence = self._adapter.map(snapshot)
        mapped = tuple(
            EvidenceAssessment(
                item.category,
                evidence.status if item.category is EvidenceCategory.TEAM_FORM else item.status,
            )
            for item in base.evidence
        )
        return replace(
            base,
            sample_size=evidence.sample_size,
            data_completeness_status=(
                EvidenceStatus.PARTIAL
                if evidence.status is not EvidenceStatus.AVAILABLE
                else base.data_completeness_status
            ),
            evidence=mapped,
        )
