from dataclasses import dataclass
from typing import Sequence

from .calibrators import FittedProbabilityCalibrator, IdentityCalibrator
from .models import CalibrationScope, CalibrationScopeKind


@dataclass(frozen=True, slots=True)
class CalibrationResolverConfig:
    minimum_observations: int = 100
    scope_overrides: tuple[tuple[CalibrationScopeKind, int], ...] = ()

    def __post_init__(self) -> None:
        if self.minimum_observations <= 0:
            raise ValueError("Minimum observations must be positive.")
        kinds = tuple(kind for kind, _ in self.scope_overrides)
        if len(set(kinds)) != len(kinds):
            raise ValueError("Each calibration scope may have one sample override.")
        if any(value <= 0 for _, value in self.scope_overrides):
            raise ValueError("Scope sample overrides must be positive.")

    def minimum_for(self, kind: CalibrationScopeKind) -> int:
        return dict(self.scope_overrides).get(kind, self.minimum_observations)


@dataclass(frozen=True, slots=True)
class CalibrationResolutionRequest:
    competition: str
    market: str
    odds_band: str | None = None

    def __post_init__(self) -> None:
        if not self.competition.strip() or not self.market.strip():
            raise ValueError("Resolution competition and market must not be empty.")
        if self.odds_band is not None and not self.odds_band.strip():
            raise ValueError("Resolution odds band must not be empty.")


@dataclass(frozen=True, slots=True)
class CalibrationResolution:
    calibrator: FittedProbabilityCalibrator
    requested_scope: CalibrationScope
    scope_used: CalibrationScope
    used_fallback: bool


class CalibrationScopeResolver:
    """Resolves the most specific sufficiently supported fitted calibrator."""

    def __init__(
        self,
        calibrators: Sequence[FittedProbabilityCalibrator],
        identity: IdentityCalibrator,
        config: CalibrationResolverConfig | None = None,
    ) -> None:
        self._config = config or CalibrationResolverConfig()
        self._identity = identity
        self._calibrators: dict[CalibrationScope, FittedProbabilityCalibrator] = {}
        for calibrator in calibrators:
            scope = calibrator.metadata.scope
            if scope.kind is CalibrationScopeKind.IDENTITY:
                raise ValueError("Identity fallback must be supplied separately.")
            if scope in self._calibrators:
                raise ValueError("Only one fitted calibrator may exist per scope.")
            self._calibrators[scope] = calibrator

    def resolve(
        self,
        request: CalibrationResolutionRequest,
    ) -> CalibrationResolution:
        candidates = [
            CalibrationScope(
                CalibrationScopeKind.COMPETITION_MARKET,
                competition=request.competition,
                market=request.market,
            ),
            CalibrationScope(CalibrationScopeKind.MARKET, market=request.market),
            CalibrationScope(
                CalibrationScopeKind.COMPETITION,
                competition=request.competition,
            ),
        ]
        if request.odds_band is not None:
            candidates.append(CalibrationScope(
                CalibrationScopeKind.ODDS_BAND,
                odds_band=request.odds_band,
            ))
        candidates.append(CalibrationScope.global_scope())
        requested_scope = candidates[0]
        for scope in candidates:
            calibrator = self._calibrators.get(scope)
            if calibrator is None:
                continue
            if calibrator.metadata.observation_count < self._config.minimum_for(
                scope.kind
            ):
                continue
            return CalibrationResolution(
                calibrator=calibrator,
                requested_scope=requested_scope,
                scope_used=scope,
                used_fallback=(scope != requested_scope),
            )
        return CalibrationResolution(
            calibrator=self._identity,
            requested_scope=requested_scope,
            scope_used=self._identity.metadata.scope,
            used_fallback=True,
        )
