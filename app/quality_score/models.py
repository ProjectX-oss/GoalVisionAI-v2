from dataclasses import dataclass
from enum import Enum


class QualitySignal(str, Enum):
    RECENT_FORM = "recent_form"
    LEAGUE_STRENGTH = "league_strength"
    STANDINGS = "standings"
    H2H = "h2h"
    REST_DAYS = "rest_days"
    HOME_AWAY = "home_away"
    ATTACK = "attack"
    DEFENSE = "defense"


@dataclass(frozen=True, slots=True)
class QualitySignals:
    recent_form: float | None = None
    league_strength: float | None = None
    standings: float | None = None
    h2h: float | None = None
    rest_days: float | None = None
    home_away: float | None = None
    attack: float | None = None
    defense: float | None = None
    conflicting_signal_penalty: float = 0.0
    missing_data_penalty: float = 0.0

    def values(self) -> dict[QualitySignal, float | None]:
        return {
            QualitySignal.RECENT_FORM: self.recent_form,
            QualitySignal.LEAGUE_STRENGTH: self.league_strength,
            QualitySignal.STANDINGS: self.standings,
            QualitySignal.H2H: self.h2h,
            QualitySignal.REST_DAYS: self.rest_days,
            QualitySignal.HOME_AWAY: self.home_away,
            QualitySignal.ATTACK: self.attack,
            QualitySignal.DEFENSE: self.defense,
        }


@dataclass(frozen=True, slots=True)
class QualityScoreResult:
    score: int
    completeness: float
    consistency: float
    available_signals: tuple[QualitySignal, ...]
    missing_signals: tuple[QualitySignal, ...]
    warnings: tuple[str, ...]
    reason_codes: tuple[str, ...]
