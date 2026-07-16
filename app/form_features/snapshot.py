from datetime import datetime
from decimal import Decimal

from .models import (
    DistortionEvidenceStatus,
    ExpectedGoalsEvidence,
    ExpectedGoalsStatus,
    FormEvidenceStatus,
    FormFeaturePolicy,
    FormMetrics,
    FormSignal,
    HistoricalMatchObservation,
    MatchDistortionEvidence,
    OpponentAdjustedFormSnapshot,
    OpponentStrengthObservation,
    OpponentStrengthTransform,
    RecencyWeight,
    TeamFormSnapshot,
    TeamMatchPerformance,
    VenueSplit,
    WeightedFormMetrics,
)


ZERO = Decimal("0")


class FormSnapshotBuilder:
    def build(
        self,
        *,
        target_fixture_id: str,
        target_kickoff: datetime,
        team_id: str,
        venue: VenueSplit,
        evaluation_timestamp: datetime,
        historical_observations: tuple[HistoricalMatchObservation, ...],
        opponent_strengths: tuple[OpponentStrengthObservation, ...] = (),
        policy: FormFeaturePolicy | None = None,
    ) -> OpponentAdjustedFormSnapshot:
        resolved = policy or FormFeaturePolicy()
        self._aware(target_kickoff)
        self._aware(evaluation_timestamp)
        if evaluation_timestamp > target_kickoff:
            raise ValueError("Evaluation timestamp must not be after target kickoff.")
        selected: list[HistoricalMatchObservation] = []
        excluded: list[tuple[str, str]] = []
        for item in historical_observations:
            reason = self._exclude(
                item, target_fixture_id, target_kickoff, evaluation_timestamp, team_id
            )
            if reason:
                excluded.append((item.fixture_id, reason))
            else:
                selected.append(item)
        selected, conflicts = self._latest_fixture_observations(selected)
        selected.sort(key=lambda item: (item.kickoff_time, item.fixture_id))
        performances = tuple(self._performance(item, team_id) for item in selected)
        recent = performances[-resolved.recent_window :]
        weights = self._weights(recent, resolved, target_kickoff)
        overall = self._metrics(performances)
        home = self._metrics(tuple(x for x in performances if x.venue is VenueSplit.HOME))
        away = self._metrics(tuple(x for x in performances if x.venue is VenueSplit.AWAY))
        recent_metrics = self._metrics(recent)
        weighted = self._weighted(recent, weights)
        venue_values = tuple(x for x in performances if x.venue is venue)
        venue_fallback = len(venue_values) < resolved.venue_minimum_sample
        venue_metrics = self._metrics(venue_values)
        blend = ZERO if venue_fallback else resolved.venue_blend
        venue_attack = (
            venue_metrics.average_goals_for * blend
            + overall.average_goals_for * (Decimal("1") - blend)
        )
        venue_defense = (
            venue_metrics.average_goals_against * blend
            + overall.average_goals_against * (Decimal("1") - blend)
        )
        strength_map = {
            item.team_id: item
            for item in opponent_strengths
            if item.source is resolved.opponent_strength_source
            and item.observed_at <= evaluation_timestamp
        }
        factors: list[tuple[str, Decimal | None]] = []
        raw: list[tuple[str, Decimal | None]] = []
        missing: set[str] = set()
        adjusted_attack: list[Decimal] = []
        adjusted_defense: list[Decimal] = []
        for performance in performances:
            strength = strength_map.get(performance.opponent_team_id)
            raw_value = strength.raw_value if strength else None
            factor = self._factor(raw_value, resolved)
            raw.append((performance.opponent_team_id, raw_value))
            factors.append((performance.opponent_team_id, factor))
            if factor is None:
                missing.add(performance.opponent_team_id)
            else:
                adjusted_attack.append(Decimal(performance.goals_for) * factor)
                adjusted_defense.append(Decimal(performance.goals_against) / factor)
        status = (
            FormEvidenceStatus.MISSING
            if not performances
            else FormEvidenceStatus.PARTIAL
            if (
                len(performances) < resolved.minimum_sample
                or missing
                or venue_fallback
                or conflicts
            )
            else FormEvidenceStatus.AVAILABLE
        )
        latest = max((item.observed_at for item in selected), default=None)
        freshness = (
            FormEvidenceStatus.MISSING
            if latest is None
            else FormEvidenceStatus.STALE
            if evaluation_timestamp - latest > resolved.maximum_history_age
            else FormEvidenceStatus.AVAILABLE
        )
        signals: list[FormSignal] = []
        if len(performances) < resolved.minimum_sample:
            signals.append(FormSignal.VERY_SMALL_SAMPLE)
        if performances and abs(
            overall.result_form_score
            - self._goal_rate_score(overall.average_goals_for, overall.average_goals_against)
        ) >= resolved.divergence_threshold:
            signals.append(FormSignal.RESULTS_GOAL_RATE_DIVERGENCE)
        factor_values = tuple(factor for _, factor in factors)
        xg = self._xg(performances, weights, factor_values)
        distortions = self._distortions(selected)
        form = TeamFormSnapshot(
            team_id=team_id,
            venue=venue,
            selected_fixture_ids=tuple(item.fixture_id for item in selected),
            excluded_fixtures=tuple(sorted(excluded)),
            overall=overall,
            home=home,
            away=away,
            recent=recent_metrics,
            weighted=weighted,
            venue_weighted_goals_for=venue_attack,
            venue_weighted_goals_against=venue_defense,
            venue_fallback_used=venue_fallback,
            expected_goals=xg,
            evidence_status=status,
            freshness_status=freshness,
            sample_size=len(performances),
            signals=tuple(signals),
            distortions=distortions,
            calculation_timestamp=evaluation_timestamp,
            latest_source_observed_at=latest,
        )
        return OpponentAdjustedFormSnapshot(
            form=form,
            opponent_strengths=tuple(raw),
            adjustment_factors=tuple(factors),
            adjusted_attacking_form=self._average(adjusted_attack),
            adjusted_defensive_form=self._average(adjusted_defense),
            missing_opponents=tuple(sorted(missing)),
            conflicts=conflicts,
        )

    @staticmethod
    def _latest_fixture_observations(items):
        grouped = {}
        for item in items:
            grouped.setdefault(item.fixture_id, []).append(item)
        selected = []
        conflicts = []
        for fixture_id in sorted(grouped):
            values = grouped[fixture_id]
            latest_at = max(item.observed_at for item in values)
            current = sorted(
                (item for item in values if item.observed_at == latest_at),
                key=lambda item: (item.source_name, item.source_reference),
            )
            facts = {
                (
                    item.home_team_id,
                    item.away_team_id,
                    item.home_goals,
                    item.away_goals,
                    item.match_status,
                    item.home_xg,
                    item.away_xg,
                )
                for item in current
            }
            if len(facts) > 1:
                from .models import FormConflict

                conflicts.append(
                    FormConflict(
                        fixture_id,
                        tuple(
                            f"{item.source_name}:{item.source_reference}"
                            for item in current
                        ),
                        "Latest historical observations disagree.",
                    )
                )
            selected.append(current[0])
        return selected, tuple(conflicts)

    @staticmethod
    def _exclude(item, target_id, target_kickoff, evaluation, team_id):
        if item.fixture_id == target_id:
            return "TARGET_FIXTURE"
        if team_id not in {item.home_team_id, item.away_team_id}:
            return "OTHER_TEAM"
        if not item.completed:
            return "INCOMPLETE_MATCH"
        if item.kickoff_time >= target_kickoff:
            return "NOT_BEFORE_TARGET"
        if item.observed_at > evaluation:
            return "AFTER_EVALUATION_CUTOFF"
        return ""

    @staticmethod
    def _performance(item, team_id):
        home = item.home_team_id == team_id
        goals_for = item.home_goals if home else item.away_goals
        goals_against = item.away_goals if home else item.home_goals
        return TeamMatchPerformance(
            item.fixture_id,
            item.away_team_id if home else item.home_team_id,
            VenueSplit.HOME if home else VenueSplit.AWAY,
            item.kickoff_time,
            item.observed_at,
            goals_for,
            goals_against,
            3 if goals_for > goals_against else 1 if goals_for == goals_against else 0,
            item.home_xg if home else item.away_xg,
            item.away_xg if home else item.home_xg,
            item.home_shots if home else item.away_shots,
            item.away_shots if home else item.home_shots,
        )

    def _metrics(self, items):
        count = len(items)
        wins = sum(x.points == 3 for x in items)
        draws = sum(x.points == 1 for x in items)
        losses = count - wins - draws
        goals_for = sum(x.goals_for for x in items)
        goals_against = sum(x.goals_against for x in items)
        return FormMetrics(
            count,
            wins,
            draws,
            losses,
            sum(x.points for x in items),
            goals_for,
            goals_against,
            goals_for - goals_against,
            sum(x.goals_against == 0 for x in items),
            sum(x.goals_for == 0 for x in items),
            self._ratio(goals_for, count),
            self._ratio(goals_against, count),
            self._ratio(sum(x.points for x in items), count * 3),
        )

    def _weights(self, items, policy, target_kickoff):
        count = len(items)
        if not count:
            return ()
        if policy.recency_weight is RecencyWeight.UNIFORM:
            raw = [Decimal("1")] * count
        elif policy.recency_weight is RecencyWeight.EXPONENTIAL:
            raw = [
                policy.exponential_decay
                ** max(
                    0,
                    int(
                        (target_kickoff - item.kickoff_time).total_seconds()
                        // 86400
                    ),
                )
                for item in items
            ]
        else:
            if len(policy.explicit_weights) < count:
                raise ValueError("Explicit recency weights do not cover selected history.")
            raw = list(policy.explicit_weights[-count:])
        total = sum(raw, ZERO)
        return tuple(value / total for value in raw)

    def _weighted(self, items, weights):
        return WeightedFormMetrics(
            weights,
            sum((weight * Decimal(item.points) for item, weight in zip(items, weights)), ZERO),
            sum((weight * Decimal(item.goals_for) for item, weight in zip(items, weights)), ZERO),
            sum((weight * Decimal(item.goals_against) for item, weight in zip(items, weights)), ZERO),
        )

    def _factor(self, raw, policy):
        if raw is None:
            return policy.missing_opponent_fallback
        if (
            policy.opponent_strength_transform
            is OpponentStrengthTransform.INVERSE_RANK_RATIO
            and raw <= 0
        ):
            raise ValueError("Standings rank must be positive.")
        factor = (
            policy.opponent_baseline / raw
            if policy.opponent_strength_transform
            is OpponentStrengthTransform.INVERSE_RANK_RATIO
            else raw / policy.opponent_baseline
        )
        return min(policy.opponent_adjustment_max, max(policy.opponent_adjustment_min, factor))

    def _xg(self, items, weights, factors):
        genuine = tuple(x for x in items if x.xg_for is not None and x.xg_against is not None)
        if not genuine:
            return ExpectedGoalsEvidence(
                ExpectedGoalsStatus.MISSING, 0, None, None, None, None, None,
                None, None, None, None, None, None,
            )
        xgf = sum((x.xg_for for x in genuine), ZERO)
        xga = sum((x.xg_against for x in genuine), ZERO)
        status = ExpectedGoalsStatus.AVAILABLE if len(genuine) == len(items) else ExpectedGoalsStatus.PARTIAL
        recent = items[-len(weights):]
        paired = tuple((item, weight) for item, weight in zip(recent, weights) if item.xg_for is not None and item.xg_against is not None)
        weight_total = sum((weight for _, weight in paired), ZERO)
        weighted_for = sum((item.xg_for * weight for item, weight in paired), ZERO) / weight_total if weight_total else None
        weighted_against = sum((item.xg_against * weight for item, weight in paired), ZERO) / weight_total if weight_total else None
        home = tuple(x.xg_for for x in genuine if x.venue is VenueSplit.HOME)
        away = tuple(x.xg_for for x in genuine if x.venue is VenueSplit.AWAY)
        adjusted_for = tuple(
            item.xg_for * factor
            for item, factor in zip(items, factors)
            if item.xg_for is not None and factor is not None
        )
        adjusted_against = tuple(
            item.xg_against / factor
            for item, factor in zip(items, factors)
            if item.xg_against is not None and factor is not None
        )
        return ExpectedGoalsEvidence(
            status, len(genuine), xgf, xga, xgf - xga,
            xgf / len(genuine), xga / len(genuine),
            weighted_for, weighted_against,
            self._average(adjusted_for), self._average(adjusted_against),
            self._average(home), self._average(away),
        )

    @staticmethod
    def _distortions(items):
        has_penalties = any(x.penalties is not None for x in items)
        unavailable = DistortionEvidenceStatus.UNAVAILABLE
        return MatchDistortionEvidence(
            unavailable,
            unavailable,
            DistortionEvidenceStatus.AVAILABLE if has_penalties else unavailable,
            DistortionEvidenceStatus.AVAILABLE if items else DistortionEvidenceStatus.NOT_APPLICABLE,
            DistortionEvidenceStatus.AVAILABLE if any(x.match_status == "ABD" for x in items) else unavailable,
            DistortionEvidenceStatus.AVAILABLE if any(x.match_status == "AET" for x in items) else unavailable,
            DistortionEvidenceStatus.AVAILABLE if any(x.match_status == "PEN" for x in items) else unavailable,
        )

    @staticmethod
    def _goal_rate_score(goals_for, goals_against):
        total = goals_for + goals_against
        return Decimal("0.5") if total == 0 else goals_for / total

    @staticmethod
    def _ratio(numerator, denominator):
        return ZERO if denominator == 0 else Decimal(numerator) / Decimal(denominator)

    @staticmethod
    def _average(values):
        return None if not values else sum(values, ZERO) / Decimal(len(values))

    @staticmethod
    def _aware(value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Snapshot timestamps must be timezone-aware.")
