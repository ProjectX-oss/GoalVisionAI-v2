from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .models import QualitySignal


@dataclass(frozen=True, slots=True)
class QualityScoreConfig:
    signal_weights: Mapping[QualitySignal, float]
    critical_signals: frozenset[QualitySignal]
    conflict_penalty_weight: float
    missing_penalty_weight: float
    critical_missing_penalty_weight: float


DEFAULT_SIGNAL_WEIGHTS: Mapping[QualitySignal, float] = MappingProxyType({
    QualitySignal.RECENT_FORM: 0.15,
    QualitySignal.LEAGUE_STRENGTH: 0.10,
    QualitySignal.STANDINGS: 0.15,
    QualitySignal.H2H: 0.10,
    QualitySignal.REST_DAYS: 0.10,
    QualitySignal.HOME_AWAY: 0.10,
    QualitySignal.ATTACK: 0.15,
    QualitySignal.DEFENSE: 0.15,
})

DEFAULT_QUALITY_SCORE_CONFIG = QualityScoreConfig(
    signal_weights=DEFAULT_SIGNAL_WEIGHTS,
    critical_signals=frozenset({
        QualitySignal.RECENT_FORM,
        QualitySignal.STANDINGS,
        QualitySignal.ATTACK,
        QualitySignal.DEFENSE,
    }),
    conflict_penalty_weight=0.25,
    missing_penalty_weight=0.20,
    critical_missing_penalty_weight=0.25,
)
