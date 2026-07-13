from dataclasses import dataclass
from enum import Enum

from app.explanations import PredictionExplanation


class ResultStatus(str, Enum):
    WON = "WON"
    LOST = "LOST"
    VOID = "VOID"


@dataclass(frozen=True, slots=True)
class InlineActionMetadata:
    label: str
    callback_data: str


@dataclass(frozen=True, slots=True)
class CompactPredictionMessage:
    text: str
    parse_mode: str = "HTML"
    inline_actions: tuple[InlineActionMetadata, ...] = ()


@dataclass(frozen=True, slots=True)
class DetailedExplanationMessage:
    text: str
    parse_mode: str = "HTML"


@dataclass(frozen=True, slots=True)
class ResultMessage:
    text: str
    parse_mode: str = "HTML"


@dataclass(frozen=True, slots=True)
class PredictionPresentationData:
    league: str
    home_team: str
    away_team: str
    market: str
    pick: str
    probability: float
    confidence: str
    explanation: PredictionExplanation
    odds: float | None = None
    quality_score: int | None = None


@dataclass(frozen=True, slots=True)
class ResultPresentationData:
    league: str
    home_team: str
    away_team: str
    market: str
    pick: str
    status: ResultStatus
    odds: float | None = None
