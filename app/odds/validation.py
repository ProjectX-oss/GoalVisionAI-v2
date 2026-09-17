from dataclasses import dataclass, replace

from .models import OddsObservation, OddsSource, OddsSourceType
from .normalization import (
    exchange_odds_after_commission,
    normalize_fixture_id,
    normalize_source_name,
)


@dataclass(frozen=True, slots=True)
class OddsValidationPolicy:
    accept_at_kickoff: bool = False


class OddsObservationValidator:
    def __init__(self, policy: OddsValidationPolicy | None = None) -> None:
        self._policy = policy or OddsValidationPolicy()

    def validate(
        self,
        observation: OddsObservation,
        source: OddsSource | None,
    ) -> OddsObservation:
        if source is None:
            raise LookupError("Unknown odds source.")
        if not source.enabled:
            raise PermissionError("Odds source is disabled.")
        if observation.source_type is not source.source_type:
            raise ValueError("Observation source type does not match source metadata.")
        if observation.observed_at > observation.kickoff_time or (
            observation.observed_at == observation.kickoff_time
            and not self._policy.accept_at_kickoff
        ):
            raise RuntimeError("Observation is not before the accepted kickoff cutoff.")
        commission = observation.commission_rate
        if source.source_type is OddsSourceType.EXCHANGE and source.commission_applies:
            commission = commission if commission is not None else source.default_commission
            if commission is None:
                raise ValueError("Exchange observation requires commission.")
        adjusted = (
            exchange_odds_after_commission(observation.decimal_odds, commission)
            if source.source_type is OddsSourceType.EXCHANGE and commission is not None
            else observation.decimal_odds
        )
        return replace(
            observation,
            fixture_id=normalize_fixture_id(observation.fixture_id),
            source_name=normalize_source_name(source.source_name),
            decimal_odds=adjusted,
            commission_rate=commission,
            is_exchange=source.source_type is OddsSourceType.EXCHANGE,
        )
