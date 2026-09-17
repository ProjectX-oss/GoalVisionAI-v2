from dataclasses import dataclass, replace
from datetime import datetime

from app.models import Match
from app.pipeline import PredictionAssessment
from app.quality_gate import (
    EvidenceAssessment,
    EvidenceCategory,
    EvidenceStatus,
    ReviewReason,
)
from app.quality_gate_shadow import (
    ShadowObservationFacts,
    ShadowObservationFactsProvider,
)

from .models import (
    AvailabilityEvidenceStatus,
    LineupStatus,
    TeamAvailabilitySnapshot,
    TeamIdentity,
)
from .repository import SQLiteTeamAvailabilityRepository
from .snapshot import TeamAvailabilitySnapshotBuilder


@dataclass(frozen=True, slots=True)
class AvailabilityQualityGateEvidence:
    lineup_status: EvidenceStatus
    injury_status: EvidenceStatus
    required_evidence_status: EvidenceStatus
    review_signals: tuple[ReviewReason, ...]
    critical_missing: tuple[EvidenceCategory, ...]


class AvailabilityQualityGateAdapter:
    def map(
        self,
        snapshot: TeamAvailabilitySnapshot | None,
        *,
        applicable: bool = True,
    ) -> AvailabilityQualityGateEvidence:
        if not applicable:
            status = EvidenceStatus.NOT_APPLICABLE
            return AvailabilityQualityGateEvidence(status, status, status, (), ())
        if snapshot is None:
            return AvailabilityQualityGateEvidence(
                EvidenceStatus.MISSING,
                EvidenceStatus.MISSING,
                EvidenceStatus.MISSING,
                (
                    ReviewReason.LINEUP_UNCONFIRMED,
                    ReviewReason.CRITICAL_INJURY_DATA_MISSING,
                ),
                (EvidenceCategory.LINEUP, EvidenceCategory.INJURIES),
            )
        lineup = self._lineup(snapshot)
        injury = self._status(snapshot.injury_evidence_status)
        completeness = self._status(snapshot.data_completeness)
        reviews: list[ReviewReason] = []
        critical: list[EvidenceCategory] = []
        if lineup is not EvidenceStatus.AVAILABLE:
            reviews.append(ReviewReason.LINEUP_UNCONFIRMED)
            if lineup is EvidenceStatus.MISSING:
                critical.append(EvidenceCategory.LINEUP)
        if injury in {EvidenceStatus.MISSING, EvidenceStatus.STALE}:
            reviews.append(ReviewReason.CRITICAL_INJURY_DATA_MISSING)
            critical.append(EvidenceCategory.INJURIES)
        if snapshot.conflicts:
            reviews.append(ReviewReason.OPTIONAL_EVIDENCE_PARTIAL)
        return AvailabilityQualityGateEvidence(
            lineup,
            injury,
            completeness,
            tuple(dict.fromkeys(reviews)),
            tuple(dict.fromkeys(critical)),
        )

    @staticmethod
    def _lineup(snapshot: TeamAvailabilitySnapshot) -> EvidenceStatus:
        return EvidenceStatus(snapshot.lineup_evidence_status.value)

    @staticmethod
    def _status(status: AvailabilityEvidenceStatus) -> EvidenceStatus:
        return EvidenceStatus(status.value)


@dataclass(frozen=True, slots=True)
class HistoricalAvailabilityFeature:
    fixture_id: str
    team_id: str
    observation_timestamp: datetime
    evidence_status: AvailabilityEvidenceStatus
    lineup_status: LineupStatus
    confirmed: bool
    stale: bool
    missing: bool


class AvailabilityBacktestingAdapter:
    @staticmethod
    def feature(
        snapshot: TeamAvailabilitySnapshot,
        prediction_timestamp: datetime,
    ) -> HistoricalAvailabilityFeature:
        if snapshot.snapshot_timestamp > prediction_timestamp:
            raise ValueError("Availability snapshot would leak future information.")
        return HistoricalAvailabilityFeature(
            fixture_id=snapshot.fixture_id,
            team_id=snapshot.team.team_id,
            observation_timestamp=snapshot.snapshot_timestamp,
            evidence_status=snapshot.data_completeness,
            lineup_status=snapshot.latest_lineup_status,
            confirmed=snapshot.latest_lineup_status is LineupStatus.CONFIRMED,
            stale=snapshot.data_freshness is AvailabilityEvidenceStatus.STALE,
            missing=snapshot.data_completeness is AvailabilityEvidenceStatus.MISSING,
        )


class AvailabilityShadowFactsProvider:
    """Enriches real shadow facts without creating odds/calibration candidates."""

    def __init__(
        self,
        base: ShadowObservationFactsProvider,
        repository: SQLiteTeamAvailabilityRepository,
        sources,
        builder: TeamAvailabilitySnapshotBuilder | None = None,
    ) -> None:
        self._base = base
        self._repository = repository
        self._sources = tuple(sources)
        self._builder = builder or TeamAvailabilitySnapshotBuilder()
        self._quality_gate = AvailabilityQualityGateAdapter()

    def facts_for(
        self,
        match: Match,
        assessment: PredictionAssessment,
    ) -> ShadowObservationFacts | None:
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
        is_home = assessment.prediction.winner == match.home_team_name
        team = TeamIdentity(
            str(match.home_team_id if is_home else match.away_team_id),
            match.home_team_name if is_home else match.away_team_name,
        )
        snapshot = self._builder.build(
            fixture_id=str(match.fixture_id),
            team=team,
            evaluation_timestamp=evaluation_timestamp,
            kickoff=match.kickoff,
            player_observations=self._repository.player_observations(
                str(match.fixture_id),
                team.team_id,
                cutoff=evaluation_timestamp,
            ),
            lineup_observations=self._repository.lineup_observations(
                str(match.fixture_id),
                team.team_id,
                cutoff=evaluation_timestamp,
            ),
            sources=self._sources,
        )
        evidence = self._quality_gate.map(snapshot)
        mapped = tuple(
            EvidenceAssessment(
                item.category,
                evidence.lineup_status
                if item.category is EvidenceCategory.LINEUP
                else evidence.injury_status
                if item.category is EvidenceCategory.INJURIES
                else item.status,
            )
            for item in base.evidence
        )
        return replace(
            base,
            lineup_status=evidence.lineup_status,
            injury_data_status=evidence.injury_status,
            data_completeness_status=(
                EvidenceStatus.PARTIAL
                if evidence.required_evidence_status
                in {EvidenceStatus.MISSING, EvidenceStatus.PARTIAL}
                else base.data_completeness_status
            ),
            evidence=mapped,
        )
