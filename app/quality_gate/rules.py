from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.calibration import CalibrationScope

from .duplicate import DuplicatePublicationChecker, PublicationIdentity
from .models import (
    CheckStatus,
    EvidenceCategory,
    EvidenceStatus,
    ProbabilitySource,
    PublicationCandidate,
    PublicationType,
    QualityGateCheck,
    QualityGateCheckResult,
    QualityGateContext,
    RejectionReason,
    ReviewReason,
)
from .policy import QualityGatePolicy


ZERO = Decimal("0")
ONE = Decimal("1")


@runtime_checkable
class QualityGateRule(Protocol):
    check: QualityGateCheck

    def evaluate(
        self,
        candidate: PublicationCandidate,
        context: QualityGateContext,
        policy: QualityGatePolicy,
        duplicates: DuplicatePublicationChecker,
    ) -> QualityGateCheckResult: ...


class ExpectedValueService:
    """Returns decimal odds times accepted probability minus one, unrounded."""

    @staticmethod
    def calculate(decimal_odds: Decimal, probability: Decimal) -> Decimal:
        if not _valid_odds(decimal_odds):
            raise ValueError("Expected value requires valid Decimal odds.")
        if not _valid_probability(probability):
            raise ValueError("Expected value requires a valid Decimal probability.")
        return decimal_odds * probability - ONE


class StructuralValidationRule:
    check = QualityGateCheck.STRUCTURAL_VALIDATION

    def evaluate(self, candidate, context, policy, duplicates):
        reasons: list[RejectionReason] = []
        if (
            not _complete_text(candidate.prediction_id)
            or type(candidate.fixture_id) is not int
            or candidate.fixture_id <= 0
            or not _complete_text(candidate.competition)
            or not _complete_text(candidate.market)
            or not _complete_text(candidate.selection)
        ):
            reasons.append(RejectionReason.REQUIRED_DATA_MISSING)
        if not _complete_text(candidate.product_scope):
            reasons.append(RejectionReason.FORBIDDEN_MARKET)
        if not _valid_probability(candidate.raw_probability):
            reasons.append(RejectionReason.INVALID_PROBABILITY)
        if not _valid_odds(candidate.offered_odds):
            reasons.append(RejectionReason.INVALID_ODDS)
        if candidate.reference_odds is not None and not _valid_odds(
            candidate.reference_odds
        ):
            reasons.append(RejectionReason.INVALID_ODDS)
        timestamps = (
            candidate.kickoff_time,
            candidate.prediction_timestamp,
            candidate.odds_timestamp,
            context.evaluation_timestamp,
        )
        if any(not _aware(value) for value in timestamps):
            reasons.append(RejectionReason.INVALID_TIMESTAMP)
        if not isinstance(candidate.publication_type, PublicationType):
            reasons.append(RejectionReason.FORBIDDEN_MARKET)
        for component in candidate.combo_selections:
            if (
                not _complete_text(component.market)
                or not _complete_text(component.selection)
                or not _valid_odds(component.offered_odds)
            ):
                reasons.append(RejectionReason.INVALID_ODDS)
            if not _valid_probability(component.confidence_score):
                reasons.append(RejectionReason.INVALID_PROBABILITY)
        return _result(self.check, rejection=reasons)


class TimingValidationRule:
    check = QualityGateCheck.TIMING_VALIDATION

    def evaluate(self, candidate, context, policy, duplicates):
        reasons: list[RejectionReason] = []
        if not all((
            _aware(candidate.kickoff_time),
            _aware(candidate.prediction_timestamp),
            _aware(candidate.odds_timestamp),
            _aware(context.evaluation_timestamp),
        )):
            return _result(
                self.check,
                rejection=(RejectionReason.INVALID_TIMESTAMP,),
            )
        if candidate.prediction_timestamp >= candidate.kickoff_time:
            reasons.append(RejectionReason.PREDICTION_AFTER_KICKOFF)
        if (
            candidate.prediction_timestamp > context.evaluation_timestamp
            or candidate.odds_timestamp > context.evaluation_timestamp
        ):
            reasons.append(RejectionReason.INVALID_TIMESTAMP)
        return _result(self.check, rejection=reasons)


class MarketPolicyRule:
    check = QualityGateCheck.MARKET_POLICY
    _CORRECT_SCORE = frozenset({
        "CORRECT SCORE",
        "CORRECT_SCORE",
        "EXACT SCORE",
        "SCORE EXACT",
    })

    def evaluate(self, candidate, context, policy, duplicates):
        reasons: list[RejectionReason] = []
        market = _normalize(candidate.market)
        component_markets = tuple(
            _normalize(component.market) for component in candidate.combo_selections
        )
        if market in self._CORRECT_SCORE or any(
            value in self._CORRECT_SCORE for value in component_markets
        ):
            reasons.append(RejectionReason.CORRECT_SCORE_FORBIDDEN)
        forbidden = frozenset(_normalize(item) for item in policy.forbidden_markets)
        if market in forbidden or any(value in forbidden for value in component_markets):
            reasons.append(RejectionReason.FORBIDDEN_MARKET)
        if _normalize(candidate.product_scope) != _normalize(policy.product_scope):
            reasons.append(RejectionReason.FORBIDDEN_PRODUCT_SCOPE)

        if candidate.publication_type is PublicationType.SINGLE:
            if candidate.combo_selections or market == "COMBO":
                reasons.append(RejectionReason.COMBO_NOT_ALLOWED)
        elif candidate.publication_type is PublicationType.COMBO:
            if not policy.combo_exception_enabled:
                reasons.append(RejectionReason.COMBO_NOT_ALLOWED)
            elif not self._valid_combo_exception(candidate, policy):
                reasons.append(
                    RejectionReason.COMBO_EXCEPTION_REQUIREMENTS_NOT_MET
                )
        return _result(self.check, rejection=reasons)

    @staticmethod
    def _valid_combo_exception(
        candidate: PublicationCandidate,
        policy: QualityGatePolicy,
    ) -> bool:
        selections = candidate.combo_selections
        return (
            len(selections) == 2
            and len(selections) <= policy.maximum_combo_selections
            and _valid_odds(candidate.offered_odds)
            and candidate.offered_odds >= policy.minimum_combo_odds
            and all(
                _valid_odds(item.offered_odds)
                and item.offered_odds < policy.minimum_single_odds
                and _valid_probability(item.confidence_score)
                and item.confidence_score
                >= policy.combo_high_confidence_threshold
                for item in selections
            )
        )


class OddsValidationRule:
    check = QualityGateCheck.ODDS_VALIDATION

    def evaluate(self, candidate, context, policy, duplicates):
        reasons: list[RejectionReason] = []
        if not _valid_odds(candidate.offered_odds):
            reasons.append(RejectionReason.INVALID_ODDS)
        elif (
            candidate.publication_type is PublicationType.SINGLE
            and candidate.offered_odds < policy.minimum_single_odds
        ):
            reasons.append(RejectionReason.ODDS_BELOW_MINIMUM)
        if _aware(candidate.odds_timestamp) and _aware(context.evaluation_timestamp):
            age = context.evaluation_timestamp - candidate.odds_timestamp
            if age > policy.maximum_odds_age:
                reasons.append(RejectionReason.ODDS_STALE)
        return _result(self.check, rejection=reasons)


class EvidenceCompletenessRule:
    check = QualityGateCheck.EVIDENCE_COMPLETENESS

    def evaluate(self, candidate, context, policy, duplicates):
        rejections: list[RejectionReason] = []
        reviews: list[ReviewReason] = []
        if context.data_completeness_status in {
            EvidenceStatus.MISSING,
            EvidenceStatus.NOT_APPLICABLE,
        }:
            rejections.append(RejectionReason.REQUIRED_DATA_MISSING)
        elif context.data_completeness_status is EvidenceStatus.PARTIAL:
            reviews.append(ReviewReason.OPTIONAL_EVIDENCE_PARTIAL)
        elif context.data_completeness_status is EvidenceStatus.STALE:
            rejections.append(RejectionReason.DATA_STALE)
        elif not isinstance(context.data_completeness_status, EvidenceStatus):
            rejections.append(RejectionReason.REQUIRED_DATA_MISSING)
        if context.data_freshness_status is EvidenceStatus.STALE:
            rejections.append(RejectionReason.DATA_STALE)
        elif context.data_freshness_status is EvidenceStatus.PARTIAL:
            reviews.append(ReviewReason.OPTIONAL_EVIDENCE_PARTIAL)
        elif context.data_freshness_status in {
            EvidenceStatus.MISSING,
            EvidenceStatus.NOT_APPLICABLE,
        } or not isinstance(context.data_freshness_status, EvidenceStatus):
            rejections.append(RejectionReason.REQUIRED_DATA_MISSING)

        for requirement in policy.evidence_requirements:
            status = context.evidence_status(requirement.category)
            if status in {EvidenceStatus.MISSING, EvidenceStatus.NOT_APPLICABLE}:
                if requirement.required:
                    rejections.append(RejectionReason.REQUIRED_DATA_MISSING)
                elif requirement.review_when_partial:
                    reviews.append(_evidence_review_reason(requirement.category))
            elif status is EvidenceStatus.STALE:
                if requirement.blocking_when_stale:
                    rejections.append(RejectionReason.DATA_STALE)
                else:
                    reviews.append(_evidence_review_reason(requirement.category))
            elif (
                status is EvidenceStatus.PARTIAL
                and requirement.review_when_partial
            ):
                reviews.append(_evidence_review_reason(requirement.category))
            elif not isinstance(status, EvidenceStatus):
                if requirement.required:
                    rejections.append(RejectionReason.REQUIRED_DATA_MISSING)
                else:
                    reviews.append(_evidence_review_reason(requirement.category))
        return _result(self.check, rejection=rejections, review=reviews)


class CalibrationEligibilityRule:
    check = QualityGateCheck.CALIBRATION_ELIGIBILITY

    def evaluate(self, candidate, context, policy, duplicates):
        probability, source, reasons = _accepted_probability(
            candidate,
            context,
            policy,
        )
        return _result(
            self.check,
            rejection=reasons,
            evaluated_probability=probability,
            probability_source=source,
        )


class ValueEligibilityRule:
    check = QualityGateCheck.VALUE_ELIGIBILITY

    def __init__(self, values: ExpectedValueService | None = None) -> None:
        self._values = values or ExpectedValueService()

    def evaluate(self, candidate, context, policy, duplicates):
        probability, _, probability_reasons = _accepted_probability(
            candidate,
            context,
            policy,
        )
        if probability is None or probability_reasons:
            return _result(self.check, not_applicable=True)
        expected_value = candidate.expected_value
        if expected_value is None:
            if not _valid_odds(candidate.offered_odds):
                return _result(self.check, not_applicable=True)
            expected_value = self._values.calculate(
                candidate.offered_odds,
                probability,
            )
        if (
            not isinstance(expected_value, Decimal)
            or not expected_value.is_finite()
            or expected_value < policy.minimum_expected_value
        ):
            return _result(
                self.check,
                rejection=(RejectionReason.EXPECTED_VALUE_TOO_LOW,),
                expected_value=(
                    expected_value
                    if isinstance(expected_value, Decimal)
                    and expected_value.is_finite()
                    else None
                ),
            )
        return _result(self.check, expected_value=expected_value)


class MarketDisagreementRule:
    check = QualityGateCheck.MARKET_DISAGREEMENT

    def evaluate(self, candidate, context, policy, duplicates):
        probability, _, probability_reasons = _accepted_probability(
            candidate,
            context,
            policy,
        )
        disagreement: Decimal | None = None
        if context.market_consensus_probability is not None:
            if not _valid_probability(context.market_consensus_probability):
                return _result(
                    self.check,
                    rejection=(RejectionReason.INVALID_PROBABILITY,),
                )
            if probability is None or probability_reasons:
                return _result(self.check, not_applicable=True)
            disagreement = abs(
                probability - context.market_consensus_probability
            )
        elif context.market_disagreement is not None:
            if not _valid_probability(context.market_disagreement):
                return _result(
                    self.check,
                    rejection=(RejectionReason.INVALID_PROBABILITY,),
                )
            disagreement = context.market_disagreement
        if disagreement is None:
            return _result(self.check, not_applicable=True)
        if disagreement >= policy.market_disagreement_rejection_threshold:
            reasons = [RejectionReason.MARKET_CONFLICT]
            if _critical_evidence_incomplete(context, policy):
                reasons.append(
                    RejectionReason.MARKET_CONFLICT_WITH_INCOMPLETE_DATA
                )
            return _result(
                self.check,
                rejection=reasons,
                market_disagreement=disagreement,
            )
        if disagreement >= policy.market_disagreement_review_threshold:
            return _result(
                self.check,
                review=(ReviewReason.MARKET_CONFLICT,),
                market_disagreement=disagreement,
            )
        return _result(self.check, market_disagreement=disagreement)


class UncertaintyRule:
    check = QualityGateCheck.UNCERTAINTY

    def evaluate(self, candidate, context, policy, duplicates):
        uncertainty = candidate.uncertainty_score
        if uncertainty is None:
            return _result(self.check, not_applicable=True)
        if not _valid_probability(uncertainty):
            return _result(
                self.check,
                rejection=(RejectionReason.EXCESSIVE_UNCERTAINTY,),
            )
        if uncertainty >= policy.uncertainty_rejection_threshold:
            return _result(
                self.check,
                rejection=(RejectionReason.EXCESSIVE_UNCERTAINTY,),
            )
        if uncertainty >= policy.uncertainty_review_threshold:
            return _result(
                self.check,
                review=(ReviewReason.EXCESSIVE_UNCERTAINTY,),
            )
        return _result(self.check)


class ExposureRule:
    check = QualityGateCheck.EXPOSURE

    def evaluate(self, candidate, context, policy, duplicates):
        values = (
            (context.current_exposure, policy.exposure_limits.per_prediction,
             RejectionReason.EXPOSURE_LIMIT_REACHED),
            (context.daily_exposure, policy.exposure_limits.daily_total,
             RejectionReason.DAILY_EXPOSURE_LIMIT_REACHED),
            (context.competition_exposure,
             policy.exposure_limits.competition_total,
             RejectionReason.COMPETITION_EXPOSURE_LIMIT_REACHED),
            (context.correlated_exposure,
             policy.exposure_limits.correlated_total,
             RejectionReason.CORRELATED_EXPOSURE_LIMIT_REACHED),
        )
        reasons = tuple(
            reason
            for value, limit, reason in values
            if not _valid_exposure(value) or value >= limit
        )
        return _result(self.check, rejection=reasons)


class DuplicateProtectionRule:
    check = QualityGateCheck.DUPLICATE_PROTECTION

    def evaluate(self, candidate, context, policy, duplicates):
        if (
            type(candidate.fixture_id) is not int
            or candidate.fixture_id <= 0
            or not _complete_text(candidate.market)
            or not _complete_text(candidate.selection)
            or not _complete_text(candidate.product_scope)
        ):
            return _result(self.check, not_applicable=True)
        identity = PublicationIdentity.create(
            candidate.fixture_id,
            candidate.market,
            candidate.selection,
            candidate.product_scope,
        )
        reasons = (
            (RejectionReason.DUPLICATE_PUBLICATION,)
            if duplicates.is_active(identity)
            else ()
        )
        return _result(self.check, rejection=reasons)


DEFAULT_RULES: tuple[QualityGateRule, ...] = (
    StructuralValidationRule(),
    TimingValidationRule(),
    MarketPolicyRule(),
    OddsValidationRule(),
    EvidenceCompletenessRule(),
    CalibrationEligibilityRule(),
    ValueEligibilityRule(),
    MarketDisagreementRule(),
    UncertaintyRule(),
    ExposureRule(),
    DuplicateProtectionRule(),
)


def _accepted_probability(
    candidate: PublicationCandidate,
    context: QualityGateContext,
    policy: QualityGatePolicy,
) -> tuple[
    Decimal | None,
    ProbabilitySource | None,
    tuple[RejectionReason, ...],
]:
    reasons: list[RejectionReason] = []
    if not _valid_probability(candidate.raw_probability):
        reasons.append(RejectionReason.INVALID_PROBABILITY)
    if type(context.sample_size) is not int or (
        context.sample_size < policy.minimum_model_sample_size
    ):
        reasons.append(RejectionReason.MODEL_SAMPLE_TOO_SMALL)

    if candidate.calibrated_probability is None:
        if policy.calibration_required or not policy.raw_probability_allowed:
            reasons.append(RejectionReason.PROBABILITY_NOT_CALIBRATED)
            return None, None, tuple(reasons)
        probability = (
            candidate.raw_probability
            if _valid_probability(candidate.raw_probability)
            else None
        )
        return probability, ProbabilitySource.RAW if probability is not None else None, (
            tuple(reasons)
        )

    if not _valid_probability(candidate.calibrated_probability):
        reasons.append(RejectionReason.INVALID_PROBABILITY)
    metadata_complete = (
        _complete_text(candidate.calibration_method)
        and isinstance(candidate.calibration_scope, CalibrationScope)
        and type(candidate.calibration_sample_size) is int
        and _aware(candidate.calibration_fit_timestamp)
        and _aware(candidate.calibration_training_cutoff)
    )
    if not metadata_complete:
        reasons.append(RejectionReason.PROBABILITY_NOT_CALIBRATED)
    else:
        if (
            candidate.calibration_method.strip().lower() == "identity"
            and not policy.identity_calibration_allowed
        ):
            reasons.append(RejectionReason.PROBABILITY_NOT_CALIBRATED)
        if _aware(candidate.prediction_timestamp):
            if candidate.calibration_fit_timestamp > candidate.prediction_timestamp:
                reasons.append(RejectionReason.PROBABILITY_NOT_CALIBRATED)
            if (
                candidate.calibration_training_cutoff
                >= candidate.prediction_timestamp
            ):
                reasons.append(RejectionReason.PROBABILITY_NOT_CALIBRATED)
        if (
            _aware(candidate.calibration_fit_timestamp)
            and _aware(candidate.calibration_training_cutoff)
            and candidate.calibration_fit_timestamp
            < candidate.calibration_training_cutoff
        ):
            reasons.append(RejectionReason.PROBABILITY_NOT_CALIBRATED)

    sample_sizes = tuple(
        value
        for value in (
            candidate.calibration_sample_size,
            context.calibration_sample_size,
        )
        if type(value) is int
    )
    if (
        len(sample_sizes) < 2
        or min(sample_sizes) < policy.minimum_calibration_sample_size
    ):
        reasons.append(RejectionReason.CALIBRATION_SAMPLE_TOO_SMALL)
    probability = (
        candidate.calibrated_probability
        if _valid_probability(candidate.calibrated_probability)
        and not reasons
        else None
    )
    return (
        probability,
        ProbabilitySource.CALIBRATED if probability is not None else None,
        tuple(reasons),
    )


def _result(
    check: QualityGateCheck,
    *,
    rejection=(),
    review=(),
    not_applicable: bool = False,
    evaluated_probability: Decimal | None = None,
    probability_source: ProbabilitySource | None = None,
    expected_value: Decimal | None = None,
    market_disagreement: Decimal | None = None,
) -> QualityGateCheckResult:
    rejections = _ordered_unique(tuple(rejection), RejectionReason)
    reviews = _ordered_unique(tuple(review), ReviewReason)
    if rejections:
        status = CheckStatus.REJECTED
    elif reviews:
        status = CheckStatus.REVIEW_REQUIRED
    elif not_applicable:
        status = CheckStatus.NOT_APPLICABLE
    else:
        status = CheckStatus.PASSED
    return QualityGateCheckResult(
        check=check,
        status=status,
        rejection_reasons=rejections,
        review_reasons=reviews,
        evaluated_probability=evaluated_probability,
        probability_source=probability_source,
        expected_value=expected_value,
        market_disagreement=market_disagreement,
    )


def _ordered_unique(values: tuple, enum_type: type) -> tuple:
    present = set(values)
    return tuple(item for item in enum_type if item in present)


def _valid_probability(value: object) -> bool:
    return (
        isinstance(value, Decimal)
        and value.is_finite()
        and ZERO <= value <= ONE
    )


def _valid_odds(value: object) -> bool:
    return (
        isinstance(value, Decimal)
        and value.is_finite()
        and value > ONE
    )


def _valid_exposure(value: object) -> bool:
    return (
        isinstance(value, Decimal)
        and value.is_finite()
        and value >= ZERO
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _complete_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize(value: object) -> str:
    return " ".join(value.strip().upper().split()) if isinstance(value, str) else ""


def _evidence_review_reason(category: EvidenceCategory) -> ReviewReason:
    if category is EvidenceCategory.LINEUP:
        return ReviewReason.LINEUP_UNCONFIRMED
    if category is EvidenceCategory.INJURIES:
        return ReviewReason.CRITICAL_INJURY_DATA_MISSING
    return ReviewReason.OPTIONAL_EVIDENCE_PARTIAL


def _critical_evidence_incomplete(
    context: QualityGateContext,
    policy: QualityGatePolicy,
) -> bool:
    if context.data_completeness_status is not EvidenceStatus.AVAILABLE:
        return True
    return any(
        requirement.required
        and context.evidence_status(requirement.category)
        is not EvidenceStatus.AVAILABLE
        for requirement in policy.evidence_requirements
    )
