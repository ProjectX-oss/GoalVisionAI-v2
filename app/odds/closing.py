from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from .analytics import OddsConsensusService
from .models import (
    ClosingOddsRecord,
    ClosingOddsSelection,
    ClosingSelectionPath,
    OddsMarket,
    OddsObservation,
    OddsReliability,
    OddsSource,
    OddsSourceType,
)
from .normalization import deterministic_observation_id


@dataclass(frozen=True, slots=True)
class ClosingOddsPolicy:
    cutoff_before_kickoff: timedelta = timedelta(minutes=1)
    minimum_consensus_sources: int = 2
    preferred_source_ids: tuple[str, ...] = ()
    source_weights: tuple[tuple[str, Decimal], ...] = ()

    def __post_init__(self) -> None:
        if self.cutoff_before_kickoff < timedelta(0):
            raise ValueError("Closing cutoff must not be negative.")
        if (
            type(self.minimum_consensus_sources) is not int
            or self.minimum_consensus_sources <= 0
        ):
            raise ValueError("Minimum consensus sources must be positive.")
        names = tuple(name for name, _ in self.source_weights)
        if len(set(names)) != len(names):
            raise ValueError("Closing source weights must be unique.")


class ClosingOddsSelector:
    def __init__(
        self,
        policy: ClosingOddsPolicy | None = None,
        consensus: OddsConsensusService | None = None,
    ) -> None:
        self._policy = policy or ClosingOddsPolicy()
        self._consensus = consensus or OddsConsensusService()

    def select(
        self,
        observations: tuple[OddsObservation, ...],
        sources: tuple[OddsSource, ...],
        *,
        kickoff: datetime,
        selected_at: datetime,
    ) -> ClosingOddsSelection:
        cutoff = kickoff - self._policy.cutoff_before_kickoff
        valid = tuple(
            item for item in observations
            if item.observed_at < kickoff and item.observed_at <= cutoff
        )
        source_map = {item.source_name: item for item in sources if item.enabled}
        reliable = tuple(
            item for item in valid
            if item.source_name in source_map
            and source_map[item.source_name].reliability is OddsReliability.RELIABLE
        )
        latest = self._latest_by_source(reliable)
        for preferred_id in self._policy.preferred_source_ids:
            source = next(
                (item for item in sources if item.source_id == preferred_id),
                None,
            )
            if (
                source is not None
                and source.source_type is OddsSourceType.EXCHANGE
                and source.source_name in latest
            ):
                return self._from_observation(
                    latest[source.source_name],
                    selected_at,
                    cutoff,
                    ClosingSelectionPath.PREFERRED_EXCHANGE,
                )
        if len(latest) >= self._policy.minimum_consensus_sources:
            selected_observations = tuple(latest.values())
            consensus = self._consensus.calculate(
                selected_observations,
                market_group=selected_observations,
                source_weights=dict(self._policy.source_weights),
                cutoff=cutoff,
            )
            odds = consensus.weighted_mean_odds or consensus.mean_odds
            first = selected_observations[0]
            record = ClosingOddsRecord(
                closing_id=deterministic_observation_id(
                    first.fixture_id,
                    first.market.value,
                    first.selection.selection_id,
                    cutoff.isoformat(),
                    "consensus",
                ),
                fixture_id=first.fixture_id,
                market=first.market,
                selection=first.selection,
                kickoff_time=kickoff,
                selected_at=selected_at,
                closing_observed_at=max(item.observed_at for item in selected_observations),
                decimal_odds=odds,
                source_name="CONSENSUS",
                source_type=OddsSourceType.INTERNAL,
                selection_path=ClosingSelectionPath.WEIGHTED_CONSENSUS,
                source_count=len(latest),
                cutoff=cutoff,
            )
            return ClosingOddsSelection(
                record,
                ClosingSelectionPath.WEIGHTED_CONSENSUS,
                "Sufficient reliable sources produced consensus closing odds.",
            )
        bookmaker_candidates = tuple(
            item for item in latest.values()
            if source_map[item.source_name].source_type is OddsSourceType.BOOKMAKER
        )
        if bookmaker_candidates:
            chosen = min(
                bookmaker_candidates,
                key=lambda item: (
                    source_map[item.source_name].priority,
                    -item.observed_at.timestamp(),
                    item.source_name,
                ),
            )
            return self._from_observation(
                chosen,
                selected_at,
                cutoff,
                ClosingSelectionPath.PRIORITY_BOOKMAKER,
            )
        return ClosingOddsSelection(
            None,
            ClosingSelectionPath.UNAVAILABLE,
            "No valid closing observation satisfied the configured fallback policy.",
        )

    @staticmethod
    def _latest_by_source(
        observations: tuple[OddsObservation, ...],
    ) -> dict[str, OddsObservation]:
        result: dict[str, OddsObservation] = {}
        for item in sorted(observations, key=lambda value: value.observed_at):
            result[item.source_name] = item
        return result

    @staticmethod
    def _from_observation(
        observation: OddsObservation,
        selected_at: datetime,
        cutoff: datetime,
        path: ClosingSelectionPath,
    ) -> ClosingOddsSelection:
        record = ClosingOddsRecord(
            closing_id=deterministic_observation_id(
                observation.fixture_id,
                observation.market.value,
                observation.selection.selection_id,
                cutoff.isoformat(),
                path.value,
            ),
            fixture_id=observation.fixture_id,
            market=observation.market,
            selection=observation.selection,
            kickoff_time=observation.kickoff_time,
            selected_at=selected_at,
            closing_observed_at=observation.observed_at,
            decimal_odds=observation.decimal_odds,
            source_name=observation.source_name,
            source_type=observation.source_type,
            selection_path=path,
            source_count=1,
            cutoff=cutoff,
            observation_id=observation.observation_id,
        )
        return ClosingOddsSelection(record, path, f"Closing odds selected via {path.value}.")
