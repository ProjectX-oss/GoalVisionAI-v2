from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.results import PublishedPredictionReference
from app.risk_management import (
    RiskAssessmentDecision,
    StakeRecommendation,
)

from .config import OfficialStakeRatingPolicy
from .exceptions import OfficialPredictionPublicationValidationError
from .models import (
    OfficialPredictionPublicationPayload,
    PublicStakeRating,
)


class OfficialStakeRatingMapper:
    """Maps actual internal stake percentage downward to 1-3 public stars."""

    def __init__(self, policy: OfficialStakeRatingPolicy) -> None:
        self._policy = policy

    def map(
        self,
        recommendation: StakeRecommendation | None,
        decision: RiskAssessmentDecision,
    ) -> PublicStakeRating:
        if (
            recommendation is None
            or decision
            not in {
                RiskAssessmentDecision.ELIGIBLE,
                RiskAssessmentDecision.REDUCED_STAKE,
            }
        ):
            raise OfficialPredictionPublicationValidationError(
                "A positive eligible Official stake recommendation is required."
            )
        percentage = recommendation.internal_stake_percentage
        if (
            not isinstance(percentage, Decimal)
            or not percentage.is_finite()
            or percentage < self._policy.conservative_percentage
            or percentage > self._policy.maximum_percentage
            or recommendation.final_stake <= 0
        ):
            raise OfficialPredictionPublicationValidationError(
                "Zero, sub-minimum, excessive, or malformed stakes are not publishable."
            )
        if percentage >= self._policy.maximum_percentage:
            stars = 3
        elif percentage >= self._policy.standard_percentage:
            stars = 2
        else:
            stars = 1
        return PublicStakeRating(
            stars=stars,
            rendered=(
                self._policy.filled_star * stars
                + self._policy.empty_star * (3 - stars)
            ),
        )


class OfficialMarketPresentationMapper:
    def format(
        self,
        market: str,
        selection: str,
        line: Decimal | None,
        home_team: str,
        away_team: str,
    ) -> str:
        normalized_market = _normalize(market)
        normalized_selection = _normalize(selection)
        if "CORRECT SCORE" in normalized_market or "EXACT SCORE" in normalized_market:
            raise OfficialPredictionPublicationValidationError(
                "Correct-score predictions cannot be published."
            )
        if normalized_market in {"MATCH WINNER", "MONEYLINE", "1X2"}:
            if line is not None:
                self._invalid()
            values = {
                "HOME": f"{home_team} to win",
                "1": f"{home_team} to win",
                "DRAW": "Draw",
                "X": "Draw",
                "AWAY": f"{away_team} to win",
                "2": f"{away_team} to win",
            }
            return self._require(values, normalized_selection)
        if normalized_market == "DOUBLE CHANCE":
            if line is not None:
                self._invalid()
            values = {
                "HOME OR DRAW": f"{home_team} or draw",
                "1X": f"{home_team} or draw",
                "AWAY OR DRAW": f"{away_team} or draw",
                "X2": f"{away_team} or draw",
                "HOME OR AWAY": f"{home_team} or {away_team}",
                "12": f"{home_team} or {away_team}",
            }
            return self._require(values, normalized_selection)
        if normalized_market in {"TOTALS", "OVER UNDER"}:
            if not isinstance(line, Decimal) or not line.is_finite() or line <= 0:
                self._invalid()
            direction = normalized_selection.split(" ", 1)[0]
            if direction not in {"OVER", "UNDER"}:
                self._invalid()
            if " " in normalized_selection:
                supplied_line = normalized_selection.split(" ", 1)[1]
                try:
                    selected_line = Decimal(supplied_line)
                except (InvalidOperation, ValueError) as exc:
                    raise OfficialPredictionPublicationValidationError(
                        "Totals selection line is malformed."
                    ) from exc
                if selected_line != line:
                    self._invalid()
            return f"{direction.title()} {_decimal_text(line)} goals"
        if normalized_market in {"BTTS", "BOTH TEAMS TO SCORE"}:
            if line is not None:
                self._invalid()
            values = {
                "YES": "Both teams to score — Yes",
                "NO": "Both teams to score — No",
            }
            return self._require(values, normalized_selection)
        raise OfficialPredictionPublicationValidationError(
            "Unsupported Official market cannot be published."
        )

    @staticmethod
    def _require(values: dict[str, str], key: str) -> str:
        try:
            return values[key]
        except KeyError as exc:
            raise OfficialPredictionPublicationValidationError(
                "Selection is inconsistent with its market."
            ) from exc

    @staticmethod
    def _invalid() -> None:
        raise OfficialPredictionPublicationValidationError(
            "Market, selection, and line are inconsistent."
        )


def published_prediction_reference(
    payload: OfficialPredictionPublicationPayload,
    market: str,
    selection: str,
    published_at: datetime,
) -> PublishedPredictionReference:
    try:
        fixture_id = int(payload.match_id)
    except (TypeError, ValueError) as exc:
        raise OfficialPredictionPublicationValidationError(
            "Published prediction match ID must be a positive integer."
        ) from exc
    return PublishedPredictionReference(
        prediction_id=payload.prediction_id,
        fixture_id=fixture_id,
        market=market,
        selection=selection,
        odds=float(payload.approved_odds),
        stake=None,
        published_at=published_at,
    )


def _normalize(value: str) -> str:
    return " ".join(value.strip().upper().replace("_", " ").replace("/", " ").split())


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")
