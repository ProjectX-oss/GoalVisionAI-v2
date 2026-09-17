from decimal import Decimal

from .duplicate import DuplicatePublicationChecker
from .models import (
    ProbabilitySource,
    PublicationCandidate,
    QualityGateCheckResult,
    QualityGateContext,
    QualityGateDecision,
    QualityGateStatus,
    RejectionReason,
    ReviewReason,
)
from .policy import QualityGatePolicy
from .rules import DEFAULT_RULES, QualityGateRule


class PublicationQualityGate:
    """Collects every safe independent check and applies fixed precedence."""

    def __init__(
        self,
        policy: QualityGatePolicy,
        duplicates: DuplicatePublicationChecker,
        rules: tuple[QualityGateRule, ...] = DEFAULT_RULES,
    ) -> None:
        checks = tuple(rule.check for rule in rules)
        if len(set(checks)) != len(checks):
            raise ValueError("Quality gate checks must be unique.")
        self._policy = policy
        self._duplicates = duplicates
        self._rules = rules

    def evaluate(
        self,
        candidate: PublicationCandidate,
        context: QualityGateContext,
    ) -> QualityGateDecision:
        checks = tuple(
            rule.evaluate(
                candidate,
                context,
                self._policy,
                self._duplicates,
            )
            for rule in self._rules
        )
        rejections = self._ordered_rejections(checks)
        reviews = self._ordered_reviews(checks)
        if rejections:
            status = QualityGateStatus.REJECTED
        elif reviews:
            status = QualityGateStatus.REVIEW_REQUIRED
        else:
            status = QualityGateStatus.APPROVED
        return QualityGateDecision(
            candidate_id=candidate.prediction_id,
            status=status,
            checks=checks,
            rejection_reasons=rejections,
            review_reasons=reviews,
            evaluated_probability=self._last_value(
                checks,
                "evaluated_probability",
            ),
            probability_source=self._last_value(checks, "probability_source"),
            expected_value=self._last_value(checks, "expected_value"),
            market_disagreement=self._last_value(
                checks,
                "market_disagreement",
            ),
            policy_version=self._policy.version,
            evaluation_timestamp=context.evaluation_timestamp,
        )

    @staticmethod
    def _ordered_rejections(
        checks: tuple[QualityGateCheckResult, ...],
    ) -> tuple[RejectionReason, ...]:
        present = {
            reason
            for check in checks
            for reason in check.rejection_reasons
        }
        return tuple(reason for reason in RejectionReason if reason in present)

    @staticmethod
    def _ordered_reviews(
        checks: tuple[QualityGateCheckResult, ...],
    ) -> tuple[ReviewReason, ...]:
        present = {
            reason
            for check in checks
            for reason in check.review_reasons
        }
        return tuple(reason for reason in ReviewReason if reason in present)

    @staticmethod
    def _last_value(
        checks: tuple[QualityGateCheckResult, ...],
        name: str,
    ) -> Decimal | ProbabilitySource | None:
        values = tuple(
            value
            for check in checks
            if (value := getattr(check, name)) is not None
        )
        return values[-1] if values else None
