from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OfficialStakeRatingPolicy:
    conservative_percentage: Decimal = Decimal("0.01")
    standard_percentage: Decimal = Decimal("0.02")
    maximum_percentage: Decimal = Decimal("0.03")
    filled_star: str = "★"
    empty_star: str = "☆"

    def __post_init__(self) -> None:
        if not (
            Decimal("0")
            < self.conservative_percentage
            < self.standard_percentage
            < self.maximum_percentage
            <= Decimal("1")
        ):
            raise ValueError("Public stake thresholds must increase within (0, 1].")
        if not self.filled_star or not self.empty_star:
            raise ValueError("Public stake glyphs must not be empty.")


@dataclass(frozen=True, slots=True)
class OfficialPredictionMessagePolicy:
    version: str = "official-prediction-message-v1"
    minimum_odds: Decimal = Decimal("1.60")
    maximum_message_length: int = 4096
    maximum_reasoning_length: int = 700
    maximum_reasoning_facts: int = 4
    reasoning_required: bool = True
    parse_mode: str = "HTML"
    stake_rating: OfficialStakeRatingPolicy = OfficialStakeRatingPolicy()

    def __post_init__(self) -> None:
        if not self.version.strip() or self.parse_mode != "HTML":
            raise ValueError("Message policy requires a version and HTML parse mode.")
        if not self.minimum_odds.is_finite() or self.minimum_odds <= 1:
            raise ValueError("Minimum message odds must exceed one.")
        if self.maximum_message_length <= 0 or self.maximum_reasoning_length <= 0:
            raise ValueError("Message and reasoning limits must be positive.")
        if self.maximum_reasoning_facts <= 0:
            raise ValueError("At least one reasoning fact must be allowed.")


DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY = OfficialPredictionMessagePolicy()
