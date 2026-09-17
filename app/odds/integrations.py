from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from app.backtesting import HistoricalEvaluationRecord
from app.models import Match
from app.pipeline import PredictionAssessment
from app.quality_gate import EvidenceAssessment, EvidenceCategory, EvidenceStatus
from app.quality_gate_shadow import ShadowObservationFacts

from .analytics import MarketDisagreementService, OddsConsensusService
from .models import ClosingOddsRecord, OddsMarket, OddsObservation
from .normalization import normalize_selection
from .repository import SQLiteOddsRepository


class BacktestingOddsAdapter:
    @staticmethod
    def build_record(
        *,
        publication: OddsObservation,
        closing: ClosingOddsRecord | None,
        competition: str,
        kickoff: datetime,
        prediction_timestamp: datetime,
        feature_timestamp: datetime,
        model_probability: Decimal,
        result: str,
        outcome,
        profit_loss: Decimal,
    ) -> HistoricalEvaluationRecord:
        if publication.observed_at > prediction_timestamp:
            raise ValueError("Publication odds would leak future information.")
        if closing is not None and closing.closing_observed_at >= kickoff:
            raise ValueError("Closing odds must be before kickoff.")
        return HistoricalEvaluationRecord(
            fixture_id=int(publication.fixture_id),
            competition=competition,
            kickoff_datetime=kickoff,
            prediction_timestamp=prediction_timestamp,
            feature_timestamp=feature_timestamp,
            odds_timestamp=publication.observed_at,
            market=publication.market.value,
            selection=publication.selection.selection_id,
            model_probability=model_probability,
            offered_odds=publication.decimal_odds,
            closing_odds=closing.decimal_odds if closing else None,
            result=result,
            outcome=outcome,
            profit_loss=profit_loss,
        )


@dataclass(frozen=True, slots=True)
class ShadowOddsEnrichment:
    facts: ShadowObservationFacts | None
    unavailable_fields: tuple[str, ...]


class OddsShadowEnrichmentAdapter:
    """Adds only odds visible by evaluation time to already-supplied shadow facts."""

    def __init__(
        self,
        repository: SQLiteOddsRepository,
        *,
        enabled: bool,
    ) -> None:
        self._repository = repository
        self._enabled = enabled
        self._consensus = OddsConsensusService()
        self._disagreement = MarketDisagreementService()

    def enrich(
        self,
        match: Match,
        assessment: PredictionAssessment,
        evaluation_timestamp: datetime,
        base_facts: ShadowObservationFacts | None,
    ) -> ShadowOddsEnrichment:
        if not self._enabled or base_facts is None:
            return ShadowOddsEnrichment(
                base_facts,
                ("offered_odds", "odds_timestamp", "market_consensus_probability", "market_disagreement"),
            )
        selection_name = (
            "home"
            if assessment.prediction.winner == match.home_team_name
            else "away"
            if assessment.prediction.winner == match.away_team_name
            else "draw"
        )
        selection = normalize_selection(selection_name)
        observations = self._repository.observations(
            fixture_id=str(match.fixture_id),
            market=OddsMarket.MATCH_WINNER,
            selection_id=selection.selection_id,
            end_at=evaluation_timestamp,
        )
        if not observations:
            return ShadowOddsEnrichment(
                base_facts,
                ("offered_odds", "odds_timestamp", "market_consensus_probability", "market_disagreement"),
            )
        offered = observations[-1]
        group = self._repository.observations(
            fixture_id=str(match.fixture_id),
            market=OddsMarket.MATCH_WINNER,
            end_at=evaluation_timestamp,
        )
        consensus = self._consensus.calculate(
            observations,
            market_group=group,
            cutoff=evaluation_timestamp,
        )
        probability = (
            Decimal(str(
                assessment.prediction.home_probability
                if selection_name == "home"
                else assessment.prediction.away_probability
                if selection_name == "away"
                else 0
            )) / Decimal("100")
        )
        disagreement = self._disagreement.compare(probability, consensus)
        evidence = tuple(
            EvidenceAssessment(
                item.category,
                EvidenceStatus.AVAILABLE
                if item.category is EvidenceCategory.ODDS
                else item.status,
            )
            for item in base_facts.evidence
        )
        return ShadowOddsEnrichment(
            replace(
                base_facts,
                offered_odds=offered.decimal_odds,
                odds_timestamp=offered.observed_at,
                market_consensus_probability=disagreement.market_probability,
                market_disagreement=disagreement.absolute_disagreement,
                evidence=evidence,
            ),
            (),
        )
