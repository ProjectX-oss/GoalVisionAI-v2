from app.h2h import H2HEngine
from app.league_strength import LeagueStrengthEngine
from app.models import HistoricalMatch, Match, Prediction, TeamContext
from app.quality_score import QualityScoreResult, QualitySignal, QualitySignals
from app.rest_days import RestDaysEngine

from .config import ExplanationConfig
from .models import PredictionExplanation, SupportingMetric


class PredictionExplanationEngine:
    """Builds concise explanations only from calculated supporting data."""

    SIGNAL_LABELS = {
        QualitySignal.RECENT_FORM: "recent form",
        QualitySignal.LEAGUE_STRENGTH: "league strength",
        QualitySignal.STANDINGS: "standings",
        QualitySignal.H2H: "head-to-head history",
        QualitySignal.REST_DAYS: "rest-days history",
        QualitySignal.HOME_AWAY: "home/away history",
        QualitySignal.ATTACK: "attack data",
        QualitySignal.DEFENSE: "defense data",
    }

    def __init__(
        self,
        config: ExplanationConfig,
        league_strength: LeagueStrengthEngine,
        h2h: H2HEngine,
        rest_days: RestDaysEngine,
    ) -> None:
        if config.component_advantage_margin < 0.0:
            raise ValueError("Component advantage margin cannot be negative.")
        if not 0.0 <= config.normalized_advantage_margin <= 0.5:
            raise ValueError(
                "Normalized advantage margin must be between 0.0 and 0.5."
            )

        self.config = config
        self.league_strength = league_strength
        self.h2h = h2h
        self.rest_days = rest_days

    def explain(
        self,
        match: Match,
        prediction: Prediction,
        quality_score: QualityScoreResult,
        quality_signals: QualitySignals,
        home: TeamContext,
        away: TeamContext,
        h2h_history: tuple[HistoricalMatch, ...] | None,
        rest_history: tuple[HistoricalMatch, ...] | None,
    ) -> PredictionExplanation:
        positives: list[str] = []
        risks: list[str] = []
        reason_codes: list[str] = list(quality_score.reason_codes)
        metrics: list[SupportingMetric] = [
            SupportingMetric("quality_score", quality_score.score, "score"),
            SupportingMetric(
                "quality_completeness",
                quality_score.completeness,
                "ratio",
            ),
            SupportingMetric(
                "quality_consistency",
                quality_score.consistency,
                "ratio",
            ),
        ]

        self._add_component_evidence(
            match,
            prediction,
            quality_signals,
            home,
            away,
            positives,
            risks,
            reason_codes,
            metrics,
        )
        self._add_h2h_evidence(
            match,
            prediction,
            quality_signals,
            h2h_history,
            positives,
            risks,
            reason_codes,
            metrics,
        )
        self._add_rest_evidence(
            match,
            prediction,
            quality_signals,
            rest_history,
            positives,
            risks,
            reason_codes,
            metrics,
        )

        if quality_signals.league_strength is not None:
            positives.append("Configured league-strength data is available.")
            reason_codes.append("LEAGUE_STRENGTH_AVAILABLE")
            metrics.append(SupportingMetric(
                "league_strength",
                self.league_strength.strength_for(match.league_id),
                "ratio",
            ))
        if "SIGNALS_CONFLICT" in quality_score.reason_codes:
            risks.append("Supporting indicators point in different directions.")
        if "CRITICAL_DATA_MISSING" in quality_score.reason_codes:
            risks.append("Critical supporting data is missing.")

        missing_data = tuple(
            self.SIGNAL_LABELS[signal]
            for signal in quality_score.missing_signals
        )
        summary = self._summary(prediction, positives, risks)

        return PredictionExplanation(
            short_summary=summary,
            positive_factors=tuple(positives),
            risk_factors=tuple(risks),
            missing_data=missing_data,
            reason_codes=tuple(reason_codes),
            supporting_metrics=tuple(metrics),
        )

    def _add_component_evidence(
        self,
        match: Match,
        prediction: Prediction,
        signals: QualitySignals,
        home: TeamContext,
        away: TeamContext,
        positives: list[str],
        risks: list[str],
        reason_codes: list[str],
        metrics: list[SupportingMetric],
    ) -> None:
        components = (
            (
                "FORM",
                "recent-form rating",
                signals.recent_form,
                home.rating.form,
                away.rating.form,
                "rating",
            ),
            (
                "ATTACK",
                "attack rating",
                signals.attack,
                home.rating.attack,
                away.rating.attack,
                "rating",
            ),
            (
                "DEFENSE",
                "defense rating",
                signals.defense,
                home.rating.defense,
                away.rating.defense,
                "rating",
            ),
            (
                "VENUE",
                "home/away record",
                signals.home_away,
                home.strength.home,
                away.strength.away,
                "rating",
            ),
            (
                "STANDINGS",
                "standings position",
                signals.standings,
                home.features.league_position,
                away.features.league_position,
                "ratio",
            ),
        )

        for code, label, availability, home_value, away_value, unit in components:
            if availability is None:
                continue
            metrics.extend((
                SupportingMetric(f"home_{code.lower()}", home_value, unit),
                SupportingMetric(f"away_{code.lower()}", away_value, unit),
            ))
            margin = (
                self.config.normalized_advantage_margin
                if unit == "ratio"
                else self.config.component_advantage_margin
            )
            self._add_directional_factor(
                code=code,
                label=label,
                home_value=home_value,
                away_value=away_value,
                margin=margin,
                home_name=match.home_team_name,
                away_name=match.away_team_name,
                predicted_winner=prediction.winner,
                positives=positives,
                risks=risks,
                reason_codes=reason_codes,
            )

    def _add_h2h_evidence(
        self,
        match: Match,
        prediction: Prediction,
        signals: QualitySignals,
        history: tuple[HistoricalMatch, ...] | None,
        positives: list[str],
        risks: list[str],
        reason_codes: list[str],
        metrics: list[SupportingMetric],
    ) -> None:
        if signals.h2h is None or not history:
            return
        strength = self.h2h.strength_for(
            match.home_team_id,
            match.away_team_id,
            history,
        )
        metrics.append(SupportingMetric("h2h_home_strength", strength, "ratio"))
        self._add_directional_factor(
            code="H2H",
            label="head-to-head record",
            home_value=strength,
            away_value=1.0 - strength,
            margin=self.config.normalized_advantage_margin * 2.0,
            home_name=match.home_team_name,
            away_name=match.away_team_name,
            predicted_winner=prediction.winner,
            positives=positives,
            risks=risks,
            reason_codes=reason_codes,
        )

    def _add_rest_evidence(
        self,
        match: Match,
        prediction: Prediction,
        signals: QualitySignals,
        history: tuple[HistoricalMatch, ...] | None,
        positives: list[str],
        risks: list[str],
        reason_codes: list[str],
        metrics: list[SupportingMetric],
    ) -> None:
        if signals.rest_days is None or not history:
            return
        advantage = self.rest_days.advantage_for(
            match.home_team_id,
            match.away_team_id,
            match.kickoff,
            history,
        )
        metrics.append(SupportingMetric("rest_home_advantage", advantage, "ratio"))
        self._add_directional_factor(
            code="REST",
            label="rest period",
            home_value=advantage,
            away_value=1.0 - advantage,
            margin=self.config.normalized_advantage_margin * 2.0,
            home_name=match.home_team_name,
            away_name=match.away_team_name,
            predicted_winner=prediction.winner,
            positives=positives,
            risks=risks,
            reason_codes=reason_codes,
        )

    @staticmethod
    def _add_directional_factor(
        code: str,
        label: str,
        home_value: float,
        away_value: float,
        margin: float,
        home_name: str,
        away_name: str,
        predicted_winner: str,
        positives: list[str],
        risks: list[str],
        reason_codes: list[str],
    ) -> None:
        difference = home_value - away_value
        if abs(difference) <= margin:
            return

        leader = home_name if difference > 0.0 else away_name
        direction = "HOME" if difference > 0.0 else "AWAY"
        reason_codes.append(f"{code}_{direction}_ADVANTAGE")

        if leader == predicted_winner:
            positives.append(f"{leader} has the stronger {label}.")
        else:
            risks.append(
                f"{leader} has the stronger {label} than the predicted winner."
            )

    @staticmethod
    def _summary(
        prediction: Prediction,
        positives: list[str],
        risks: list[str],
    ) -> str:
        directional_positives = sum(
            "available" not in factor for factor in positives
        )
        if directional_positives == 0:
            return (
                f"{prediction.winner} is the prediction, but available data "
                "shows no clear supporting advantage."
            )
        return (
            f"{prediction.winner} is supported by {directional_positives} "
            f"data factor(s); {len(risks)} risk factor(s) remain."
        )
