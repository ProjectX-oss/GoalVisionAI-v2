from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from statistics import median

from .models import (
    CLVClassification,
    CLVResult,
    ClosingOddsRecord,
    ConsensusCompleteness,
    MarketDisagreement,
    OddsConsensus,
    OddsMarket,
    OddsMovement,
    OddsObservation,
)


ONE = Decimal("1")
HUNDRED = Decimal("100")


class OddsConsensusService:
    def calculate(
        self,
        observations: tuple[OddsObservation, ...],
        *,
        market_group: tuple[OddsObservation, ...] = (),
        source_weights: dict[str, Decimal] | None = None,
        cutoff: datetime | None = None,
    ) -> OddsConsensus:
        if not observations:
            raise ValueError("Consensus requires at least one observation.")
        ordered = tuple(sorted(
            observations,
            key=lambda item: (item.observed_at, item.source_name, item.observation_id),
        ))
        first = ordered[0]
        if any(
            (
                item.fixture_id,
                item.market,
                item.selection.selection_id,
            )
            != (
                first.fixture_id,
                first.market,
                first.selection.selection_id,
            )
            for item in ordered
        ):
            raise ValueError("Consensus observations must identify one selection.")
        latest_by_source: dict[str, OddsObservation] = {}
        for item in ordered:
            latest_by_source[item.source_name] = item
        values = tuple(item.decimal_odds for item in latest_by_source.values())
        mean_odds = sum(values, Decimal("0")) / Decimal(len(values))
        median_odds = Decimal(str(median(values)))
        weights = source_weights or {}
        weighted = self._weighted_mean(latest_by_source, weights)
        no_vig, completeness = self._no_vig(
            first.market,
            market_group or ordered,
        )
        resolved_cutoff = cutoff or max(item.observed_at for item in ordered)
        return OddsConsensus(
            fixture_id=first.fixture_id,
            market=first.market,
            selection=first.selection,
            source_count=len(values),
            minimum_odds=min(values),
            maximum_odds=max(values),
            mean_odds=mean_odds,
            median_odds=median_odds,
            weighted_mean_odds=weighted,
            source_dispersion=max(values) - min(values),
            implied_probabilities=tuple(sorted(
                (source, ONE / item.decimal_odds)
                for source, item in latest_by_source.items()
            )),
            no_vig_probabilities=no_vig,
            completeness=completeness,
            observation_cutoff=resolved_cutoff,
            consensus_timestamp=max(item.observed_at for item in ordered),
        )

    @staticmethod
    def _weighted_mean(
        observations: dict[str, OddsObservation],
        weights: dict[str, Decimal],
    ) -> Decimal | None:
        pairs = tuple(
            (item.decimal_odds, weights[source])
            for source, item in observations.items()
            if source in weights
        )
        if not pairs:
            return None
        if any(not weight.is_finite() or weight <= 0 for _, weight in pairs):
            raise ValueError("Source weights must be positive finite Decimals.")
        total_weight = sum((weight for _, weight in pairs), Decimal("0"))
        return sum((odds * weight for odds, weight in pairs), Decimal("0")) / total_weight

    @staticmethod
    def _no_vig(
        market: OddsMarket,
        observations: tuple[OddsObservation, ...],
    ) -> tuple[tuple[tuple[str, Decimal], ...], ConsensusCompleteness]:
        if market not in {
            OddsMarket.MATCH_WINNER,
            OddsMarket.BTTS,
            OddsMarket.OVER_UNDER_GOALS,
        }:
            return (), ConsensusCompleteness.NOT_APPLICABLE
        grouped: dict[str, list[Decimal]] = defaultdict(list)
        lines: set[Decimal | None] = set()
        for item in observations:
            if item.market is market:
                grouped[item.selection.selection_id].append(item.decimal_odds)
                lines.add(item.selection.line)
        normalized_ids = {key.split(":", 1)[0] for key in grouped}
        required = {
            OddsMarket.MATCH_WINNER: {"home", "draw", "away"},
            OddsMarket.BTTS: {"yes", "no"},
            OddsMarket.OVER_UNDER_GOALS: {"over", "under"},
        }[market]
        if not required.issubset(normalized_ids):
            return (), ConsensusCompleteness.INCOMPLETE
        if market is OddsMarket.OVER_UNDER_GOALS and len(lines) != 1:
            return (), ConsensusCompleteness.INCOMPLETE
        probabilities: list[tuple[str, Decimal]] = []
        for selection_id, odds in grouped.items():
            probabilities.append((
                selection_id,
                ONE / (sum(odds, Decimal("0")) / Decimal(len(odds))),
            ))
        total = sum((value for _, value in probabilities), Decimal("0"))
        if total <= 0:
            return (), ConsensusCompleteness.INCOMPLETE
        return (
            tuple(sorted((selection, value / total) for selection, value in probabilities)),
            ConsensusCompleteness.COMPLETE,
        )


class MarketDisagreementService:
    def compare(
        self,
        model_probability: Decimal,
        consensus: OddsConsensus,
    ) -> MarketDisagreement:
        if not model_probability.is_finite() or not 0 <= model_probability <= 1:
            raise ValueError("Model probability must be in [0, 1].")
        probabilities = dict(consensus.no_vig_probabilities)
        market_probability = probabilities.get(consensus.selection.selection_id)
        signed = (
            model_probability - market_probability
            if market_probability is not None
            else None
        )
        return MarketDisagreement(
            model_probability=model_probability,
            market_probability=market_probability,
            absolute_disagreement=abs(signed) if signed is not None else None,
            signed_disagreement=signed,
            model_edge=signed,
            source_count=consensus.source_count,
            consensus_completeness=consensus.completeness,
            observation_cutoff=consensus.observation_cutoff,
            consensus_timestamp=consensus.consensus_timestamp,
        )


class OddsMovementService:
    def analyze(
        self,
        observations: tuple[OddsObservation, ...],
        *,
        start_observation: OddsObservation | None = None,
        end_observation: OddsObservation | None = None,
        closing: ClosingOddsRecord | None = None,
    ) -> OddsMovement:
        if not observations:
            raise ValueError("Movement requires observations.")
        ordered = tuple(sorted(
            observations,
            key=lambda item: (item.observed_at, item.observation_id),
        ))
        start = start_observation or ordered[0]
        end = end_observation or ordered[-1]
        if (start.fixture_id, start.market, start.selection.selection_id) != (
            end.fixture_id,
            end.market,
            end.selection.selection_id,
        ):
            raise ValueError("Movement observations must identify the same market.")
        absolute = end.decimal_odds - start.decimal_odds
        return OddsMovement(
            fixture_id=start.fixture_id,
            market=start.market,
            selection=start.selection,
            opening_odds=start.decimal_odds,
            latest_odds=end.decimal_odds,
            closing_odds=closing.decimal_odds if closing else None,
            absolute_change=absolute,
            percentage_change=absolute / start.decimal_odds,
            implied_probability_change=(
                ONE / end.decimal_odds
            ) - (ONE / start.decimal_odds),
            observation_count=len(ordered),
            first_observed_at=ordered[0].observed_at,
            latest_observed_at=ordered[-1].observed_at,
        )


class CLVService:
    def calculate(
        self,
        publication: OddsObservation,
        closing: ClosingOddsRecord | None,
    ) -> CLVResult:
        if closing is None:
            return CLVResult(
                classification=CLVClassification.UNAVAILABLE,
                raw_clv=None,
                clv_percentage=None,
                publication_odds=publication.decimal_odds,
                closing_odds=None,
                publication_timestamp=publication.observed_at,
                closing_timestamp=None,
                publication_source=publication.source_name,
                closing_source=None,
            )
        if (
            publication.fixture_id,
            publication.market,
            publication.selection.selection_id,
        ) != (closing.fixture_id, closing.market, closing.selection.selection_id):
            raise ValueError("Publication and closing odds identities must match.")
        if publication.observed_at >= closing.closing_observed_at:
            raise ValueError("Publication timestamp must be before closing timestamp.")
        raw = (publication.decimal_odds / closing.decimal_odds) - ONE
        classification = (
            CLVClassification.POSITIVE
            if raw > 0
            else CLVClassification.NEGATIVE
            if raw < 0
            else CLVClassification.ZERO
        )
        return CLVResult(
            classification=classification,
            raw_clv=raw,
            clv_percentage=raw * HUNDRED,
            publication_odds=publication.decimal_odds,
            closing_odds=closing.decimal_odds,
            publication_timestamp=publication.observed_at,
            closing_timestamp=closing.closing_observed_at,
            publication_source=publication.source_name,
            closing_source=closing.source_name,
        )
