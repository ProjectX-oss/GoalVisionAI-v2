import hashlib
from decimal import Decimal, ROUND_HALF_UP

from app.quality_gate import QualityGateStatus

from .models import (
    DrawdownState,
    ExposureAssessment,
    ExposureType,
    LossStreakState,
    RiskAssessmentContext,
    RiskAssessmentDecision,
    RiskAssessmentRequest,
    RiskAuditRecord,
    RiskProductScope,
    RiskReason,
    RiskWarning,
    StakeBand,
    StakeRecommendation,
    StakeStars,
)
from .policy import RiskPolicy


ZERO = Decimal("0")
ONE = Decimal("1")


class RiskAssessmentService:
    """Pure deterministic recommendation service with no mutation boundary."""

    def __init__(self, policy: RiskPolicy) -> None:
        self._policy = policy

    def assess(
        self,
        request: RiskAssessmentRequest,
        context: RiskAssessmentContext,
    ) -> RiskAuditRecord:
        reasons: set[RiskReason] = set()
        warnings: set[RiskWarning] = {
            RiskWarning.INITIAL_THRESHOLDS_NOT_STATISTICALLY_OPTIMIZED
        }
        reductions: list[tuple[RiskReason, Decimal, Decimal]] = []
        bankroll = context.bankroll
        exposure = context.exposure
        if (
            request.product_scope is not self._policy.product_scope
            or bankroll.product_scope is not request.product_scope
            or exposure.product_scope is not request.product_scope
        ):
            reasons.add(RiskReason.PRODUCT_SCOPE_MISMATCH)
        if (
            not bankroll.current_bankroll.is_finite()
            or bankroll.current_bankroll <= ZERO
            or bankroll.opening_bankroll <= ZERO
            or bankroll.peak_bankroll <= ZERO
            or bankroll.current_bankroll > bankroll.peak_bankroll
            or bankroll.currency != self._policy.currency
            or any(
                item.currency != self._policy.currency
                for item in exposure.positions
            )
            or exposure.snapshot_timestamp > context.assessed_at
        ):
            reasons.add(RiskReason.INVALID_BANKROLL)
        if (
            not request.accepted_probability.is_finite()
            or not ZERO <= request.accepted_probability <= ONE
        ):
            reasons.add(RiskReason.INVALID_PROBABILITY)
        if (
            not request.offered_odds.is_finite()
            or request.offered_odds <= ONE
        ):
            reasons.add(RiskReason.INVALID_ODDS)
        if (
            not request.expected_value.is_finite()
            or request.expected_value < self._policy.minimum_expected_value
        ):
            reasons.add(RiskReason.EXPECTED_VALUE_TOO_LOW)
        if request.quality_gate_status is QualityGateStatus.REJECTED:
            reasons.add(RiskReason.QUALITY_GATE_REJECTED)
        review = request.quality_gate_status in {
            None,
            QualityGateStatus.REVIEW_REQUIRED,
        }
        if review:
            reasons.add(RiskReason.QUALITY_GATE_REVIEW_REQUIRED)
            warnings.add(RiskWarning.MANUAL_REVIEW_REQUIRED)
        drawdown_state = self._drawdown_state(
            bankroll.current_drawdown_percentage
        )
        loss_state = self._loss_streak_state(bankroll.consecutive_losses)
        if drawdown_state is DrawdownState.HALTED:
            reasons.add(RiskReason.DRAWDOWN_HALTED)
        if loss_state is LossStreakState.REVIEW_REQUIRED:
            reasons.add(RiskReason.LOSS_STREAK_HALTED)
            warnings.add(RiskWarning.MANUAL_REVIEW_REQUIRED)
            review = True

        hard_ineligible = any(
            reason in reasons
            for reason in (
                RiskReason.INVALID_BANKROLL,
                RiskReason.PRODUCT_SCOPE_MISMATCH,
                RiskReason.INVALID_PROBABILITY,
                RiskReason.INVALID_ODDS,
                RiskReason.EXPECTED_VALUE_TOO_LOW,
                RiskReason.QUALITY_GATE_REJECTED,
                RiskReason.DRAWDOWN_HALTED,
            )
        )
        base_percentage = self._base_percentage(request, reasons)
        base_stake = (
            bankroll.current_bankroll * base_percentage
            if bankroll.current_bankroll.is_finite()
            else ZERO
        )
        working = max(base_stake, ZERO)
        minimum_stake = (
            bankroll.current_bankroll * self._policy.minimum_stake_percentage
            if bankroll.current_bankroll.is_finite()
            else ZERO
        )
        maximum_stake = (
            bankroll.current_bankroll * self._policy.maximum_stake_percentage
            if bankroll.current_bankroll.is_finite()
            else ZERO
        )
        if request.requested_stake is not None:
            requested = request.requested_stake
            if not requested.is_finite() or requested < ZERO:
                reasons.add(RiskReason.STAKE_BELOW_MINIMUM)
                hard_ineligible = True
            else:
                allowed = min(requested, maximum_stake)
                if requested > maximum_stake:
                    reasons.add(RiskReason.REQUESTED_STAKE_REDUCED)
                    reductions.append(
                        (RiskReason.REQUESTED_STAKE_REDUCED, working, min(working, allowed))
                    )
                working = min(working, allowed)
        if review and self._policy.review_required_minimum_stake_only:
            working = self._reduce(
                working,
                minimum_stake,
                RiskReason.QUALITY_GATE_REVIEW_REQUIRED,
                reductions,
            )
        if drawdown_state is DrawdownState.CAUTION:
            reasons.add(RiskReason.DRAWDOWN_CAUTION)
            working = self._reduce(
                working,
                bankroll.current_bankroll
                * self._policy.standard_stake_percentage,
                RiskReason.DRAWDOWN_CAUTION,
                reductions,
            )
        elif drawdown_state is DrawdownState.DEFENSIVE:
            reasons.add(RiskReason.DRAWDOWN_DEFENSIVE)
            working = self._reduce(
                working,
                minimum_stake,
                RiskReason.DRAWDOWN_DEFENSIVE,
                reductions,
            )
        if loss_state is LossStreakState.MINIMUM_CAP:
            reasons.add(RiskReason.LOSS_STREAK_REDUCTION)
            working = self._reduce(
                working,
                minimum_stake,
                RiskReason.LOSS_STREAK_REDUCTION,
                reductions,
            )
        exposure_assessments = self._exposure_assessments(
            request, context, working
        )
        limiting = tuple(
            item for item in exposure_assessments if item.limiting
        )
        for item in limiting:
            reasons.add(item.reason)
        if limiting:
            primary_limit = min(
                limiting,
                key=lambda item: (
                    item.remaining_capacity,
                    list(ExposureType).index(item.exposure_type),
                    item.scope_key,
                ),
            )
            cap = primary_limit.remaining_capacity
            working = self._reduce(
                working,
                max(cap, ZERO),
                primary_limit.reason,
                reductions,
            )
        if working > maximum_stake:
            reasons.add(RiskReason.SINGLE_STAKE_LIMIT)
            working = self._reduce(
                working,
                maximum_stake,
                RiskReason.SINGLE_STAKE_LIMIT,
                reductions,
            )
        if not hard_ineligible and working < minimum_stake:
            reasons.add(RiskReason.STAKE_BELOW_MINIMUM)
            hard_ineligible = True
        if hard_ineligible:
            recommendation = None
            decision = RiskAssessmentDecision.INELIGIBLE
        else:
            percentage = working / bankroll.current_bankroll
            recommendation = StakeRecommendation(
                band=self._band(percentage),
                unquantized_stake=working,
                final_stake=working.quantize(
                    self._policy.currency_quantum,
                    rounding=ROUND_HALF_UP,
                ),
                internal_stake_percentage=percentage,
                public_stars=self._stars(percentage),
                currency=self._policy.currency,
                currency_quantum=self._policy.currency_quantum,
            )
            if review:
                decision = RiskAssessmentDecision.REVIEW_REQUIRED
            elif reductions or working < base_stake:
                decision = RiskAssessmentDecision.REDUCED_STAKE
            else:
                decision = RiskAssessmentDecision.ELIGIBLE
        ordered_reasons = tuple(reason for reason in RiskReason if reason in reasons)
        ordered_warnings = tuple(
            warning for warning in RiskWarning if warning in warnings
        )
        assessment_id = self._assessment_id(request, context)
        return RiskAuditRecord(
            assessment_id=assessment_id,
            prediction_id=request.prediction_id,
            product_scope=request.product_scope,
            policy_version=self._policy.version,
            bankroll_snapshot=bankroll,
            exposure_snapshot=exposure,
            quality_gate_status=request.quality_gate_status,
            base_stake=base_stake,
            reductions=tuple(reductions),
            recommendation=recommendation,
            final_decision=decision,
            ordered_reasons=ordered_reasons,
            ordered_warnings=ordered_warnings,
            drawdown_state=drawdown_state,
            loss_streak_state=loss_state,
            limiting_exposure=primary_limit if limiting else None,
            exposure_assessments=exposure_assessments,
            assessed_at=context.assessed_at,
        )

    def _base_percentage(
        self, request: RiskAssessmentRequest, reasons: set[RiskReason]
    ) -> Decimal:
        sufficient_calibration = (
            request.calibrated_probability_available
            and request.calibration_sample_size
            >= self._policy.minimum_calibration_sample
        )
        sufficient_model = (
            request.model_sample_size >= self._policy.minimum_model_sample
        )
        if not sufficient_calibration:
            reasons.add(RiskReason.CALIBRATION_SAMPLE_TOO_SMALL)
        if not sufficient_model:
            reasons.add(RiskReason.MODEL_SAMPLE_TOO_SMALL)
        uncertainty_strong = (
            request.uncertainty is not None
            and request.uncertainty.is_finite()
            and request.uncertainty <= self._policy.strong_uncertainty_maximum
        )
        if not uncertainty_strong:
            reasons.add(RiskReason.UNCERTAINTY_TOO_HIGH)
        confidence = request.model_confidence
        approved = request.quality_gate_status is QualityGateStatus.APPROVED
        strong = (
            approved
            and sufficient_calibration
            and sufficient_model
            and uncertainty_strong
            and confidence is not None
            and confidence.is_finite()
            and confidence >= self._policy.strong_confidence_threshold
            and request.expected_value >= self._policy.strong_expected_value
        )
        exceptional = (
            strong
            and confidence >= self._policy.exceptional_confidence_threshold
            and request.uncertainty
            <= self._policy.exceptional_uncertainty_maximum
            and request.expected_value
            >= self._policy.exceptional_expected_value
        )
        if exceptional:
            return self._policy.maximum_stake_percentage
        if strong:
            return self._policy.standard_stake_percentage
        return self._policy.minimum_stake_percentage

    def _exposure_assessments(
        self,
        request: RiskAssessmentRequest,
        context: RiskAssessmentContext,
        proposed: Decimal,
    ) -> tuple[ExposureAssessment, ...]:
        bankroll = context.bankroll.current_bankroll
        exposure = context.exposure
        scopes = {
            ExposureType.SINGLE_PREDICTION: (request.prediction_id,),
            ExposureType.DAILY_TOTAL: (request.prediction_timestamp.date().isoformat(),),
            ExposureType.COMPETITION_TOTAL: (request.competition,),
            ExposureType.FIXTURE_TOTAL: (str(request.fixture_id),),
            ExposureType.TEAM_TOTAL: request.team_ids,
            ExposureType.MARKET_TOTAL: (request.market_family or request.market,),
            ExposureType.CORRELATED_GROUP_TOTAL: request.correlation_group_ids,
            ExposureType.UNSETTLED_TOTAL: ("ALL",),
        }
        assessments = []
        for limit in self._policy.exposure_limits:
            for scope_key in scopes.get(limit.exposure_type, ()):
                current = exposure.amount_for(limit.exposure_type, scope_key)
                if limit.exposure_type is ExposureType.UNSETTLED_TOTAL:
                    current = max(current, context.bankroll.unsettled_exposure)
                maximum = bankroll * limit.maximum_percentage
                remaining = max(maximum - current, ZERO)
                assessments.append(
                    ExposureAssessment(
                        limit.exposure_type,
                        scope_key,
                        current,
                        proposed,
                        maximum,
                        self._policy.currency,
                        ((current + proposed) / bankroll if bankroll > ZERO else ZERO),
                        exposure.snapshot_timestamp,
                        remaining,
                        proposed > remaining,
                        limit.reason,
                    )
                )
        return tuple(
            sorted(
                assessments,
                key=lambda item: (
                    list(ExposureType).index(item.exposure_type),
                    item.scope_key,
                ),
            )
        )

    def _drawdown_state(self, value: Decimal) -> DrawdownState:
        if value >= self._policy.halted_drawdown_threshold:
            return DrawdownState.HALTED
        if value >= self._policy.defensive_drawdown_threshold:
            return DrawdownState.DEFENSIVE
        if value >= self._policy.caution_drawdown_threshold:
            return DrawdownState.CAUTION
        return DrawdownState.NORMAL

    def _loss_streak_state(self, losses: int) -> LossStreakState:
        if losses >= self._policy.loss_streak_review:
            return LossStreakState.REVIEW_REQUIRED
        if losses >= self._policy.loss_streak_minimum_cap:
            return LossStreakState.MINIMUM_CAP
        return LossStreakState.NORMAL

    @staticmethod
    def _reduce(
        current: Decimal,
        cap: Decimal,
        reason: RiskReason,
        reductions: list[tuple[RiskReason, Decimal, Decimal]],
    ) -> Decimal:
        reduced = min(current, cap)
        if reduced < current:
            reductions.append((reason, current, reduced))
        return reduced

    def _band(self, percentage: Decimal) -> StakeBand:
        if percentage <= self._policy.minimum_stake_percentage:
            return StakeBand.MINIMUM
        if percentage <= self._policy.standard_stake_percentage:
            return StakeBand.STANDARD
        return StakeBand.MAXIMUM

    def _stars(self, percentage: Decimal) -> StakeStars:
        for maximum, stars in self._policy.star_mapping:
            if percentage <= maximum:
                return stars
        return StakeStars.THREE

    def _assessment_id(
        self, request: RiskAssessmentRequest, context: RiskAssessmentContext
    ) -> str:
        seed = "|".join(
            (
                request.prediction_id,
                str(request.fixture_id),
                request.product_scope.value,
                self._policy.version,
                context.assessed_at.isoformat(),
                context.bankroll.authoritative_source_reference,
                context.exposure.authoritative_source_reference,
            )
        )
        return "risk-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()
