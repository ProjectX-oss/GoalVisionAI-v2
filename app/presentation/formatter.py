from html import escape

from app.explanations import PredictionExplanation

from .config import PresentationConfig
from .models import (
    CompactPredictionMessage,
    DetailedExplanationMessage,
    InlineActionMetadata,
    PredictionPresentationData,
    ResultMessage,
    ResultPresentationData,
)


class TelegramPredictionPresenter:
    """Formats deterministic Telegram-safe HTML without sending messages."""

    def __init__(self, config: PresentationConfig) -> None:
        self.config = config

    def compact(
        self,
        data: PredictionPresentationData,
        action: InlineActionMetadata | None = None,
    ) -> CompactPredictionMessage:
        self._validate_prediction(data)
        lines = [
            "<b>GoalVision AI</b>",
            f"🏆 {escape(data.league)}",
            f"⚽ {escape(data.home_team)} vs {escape(data.away_team)}",
            f"🎯 {escape(data.market)}: <b>{escape(data.pick)}</b>",
        ]

        if data.odds is not None:
            lines.append(f"💰 Odds: {data.odds:.2f}")

        lines.extend((
            f"📊 Probability: {data.probability:.1f}%",
            f"🔥 Confidence: {escape(data.confidence)}",
        ))

        if self.config.show_quality_score and data.quality_score is not None:
            lines.append(f"🧠 AI Quality: {data.quality_score}/100")

        actions = (action,) if action is not None else ()
        return CompactPredictionMessage(
            text="\n".join(lines),
            inline_actions=actions,
        )

    def detailed(
        self,
        data: PredictionPresentationData,
    ) -> DetailedExplanationMessage:
        return self.detailed_explanation(data.explanation)

    def detailed_explanation(
        self,
        explanation: PredictionExplanation,
    ) -> DetailedExplanationMessage:
        """Format an already-generated deterministic explanation."""
        lines = [
            "<b>Why this pick?</b>",
            escape(explanation.short_summary),
        ]

        positives = explanation.positive_factors[
            : self.config.maximum_positive_factors
        ]
        risks = explanation.risk_factors[
            : self.config.maximum_risk_factors
        ]

        if positives:
            lines.append("\n<b>Key factors</b>")
            lines.extend(f"• {escape(factor)}" for factor in positives)
        if risks:
            lines.append("\n<b>Key risks</b>")
            lines.extend(f"• {escape(risk)}" for risk in risks)
        if (
            "CRITICAL_DATA_MISSING" in explanation.reason_codes
            and explanation.missing_data
        ):
            lines.append("\n<b>Missing data</b>")
            lines.extend(
                f"• {escape(item)}"
                for item in explanation.missing_data[
                    : self.config.maximum_risk_factors
                ]
            )

        return DetailedExplanationMessage(text="\n".join(lines))

    def result(self, data: ResultPresentationData) -> ResultMessage:
        self._validate_odds(data.odds)
        lines = [
            "<b>GoalVision AI Result</b>",
            f"📋 <b>{data.status.value}</b>",
        ]
        if data.league is not None:
            lines.append(f"🏆 {escape(data.league)}")
        if data.home_team is not None and data.away_team is not None:
            lines.append(
                f"⚽ {escape(data.home_team)} vs {escape(data.away_team)}"
            )
        lines.append(f"🎯 {escape(data.market)}: {escape(data.pick)}")
        if data.odds is not None:
            lines.append(f"💰 Odds: {data.odds:.2f}")
        if data.home_score is not None and data.away_score is not None:
            lines.append(f"Final score: {data.home_score}-{data.away_score}")
        if data.stake_stars is not None and data.stake_amount is not None:
            currency = escape(data.currency or "EUR")
            lines.append(
                f"Stake: {'★' * data.stake_stars} · "
                f"{currency} {data.stake_amount:.2f}"
            )
        if data.profit_loss is not None:
            currency = escape(data.currency or "EUR")
            sign = "+" if data.profit_loss > 0 else "-" if data.profit_loss < 0 else ""
            lines.append(
                f"Profit/Loss: {sign}{currency} {abs(data.profit_loss):.2f}"
            )
        if data.bankroll_balance is not None:
            currency = escape(data.currency or "EUR")
            lines.append(
                f"Official bankroll: {currency} {data.bankroll_balance:.2f}"
            )
        return ResultMessage(text="\n".join(lines))

    @staticmethod
    def _validate_prediction(data: PredictionPresentationData) -> None:
        if not 0.0 <= data.probability <= 100.0:
            raise ValueError("Probability must be between 0 and 100.")
        if data.quality_score is not None and not 0 <= data.quality_score <= 100:
            raise ValueError("AI Quality Score must be between 0 and 100.")
        TelegramPredictionPresenter._validate_odds(data.odds)

    @staticmethod
    def _validate_odds(odds: float | None) -> None:
        if odds is not None and odds <= 0.0:
            raise ValueError("Odds must be greater than zero when provided.")
