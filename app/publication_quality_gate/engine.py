import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Callable

from app.quality_gate import QualityGateStatus
from app.risk_management import RiskAssessmentDecision, RiskProductScope

from .models import (
    ConfidenceLevel,
    ExposureDecision,
    FactStatus,
    FindingSeverity,
    GateFinding,
    GateReason,
    LineupStatus,
    MarketAvailability,
    ModelHealthStatus,
    OfficialPublicationCandidate,
    OfficialQualityGateEvaluation,
    PublicationState,
    SupportedMarket,
)
from .policy import OfficialQualityGatePolicy


REASON_EXPLANATIONS: dict[GateReason, str] = {
    GateReason.INVALID_IDENTITY: "Candidate identity or model version is incomplete.",
    GateReason.INVALID_TIMESTAMP: "One or more supplied timestamps are invalid or future-dated.",
    GateReason.PREDICTION_AT_OR_AFTER_KICKOFF: "Prediction was created at or after kickoff.",
    GateReason.CANDIDATE_EXPIRED: "Candidate exceeded the configured eligibility lifetime.",
    GateReason.INVALID_RAW_PROBABILITY: "Raw model probability is invalid; it is retained only for audit.",
    GateReason.CALIBRATED_PROBABILITY_MISSING: "A calibrated probability is mandatory for Official publication.",
    GateReason.INVALID_CALIBRATED_PROBABILITY: "Calibrated probability is invalid or outside the configured safe range.",
    GateReason.INVALID_ODDS: "Bookmaker decimal odds are missing or invalid.",
    GateReason.ODDS_BELOW_MINIMUM: "Official single-bet odds are below the configured minimum.",
    GateReason.ODDS_STALE: "Bookmaker odds are older than the configured freshness limit.",
    GateReason.CORE_DATA_MISSING: "Required core match data is unavailable.",
    GateReason.CORE_DATA_STALE: "Core match data is older than the configured freshness limit.",
    GateReason.MARKET_UNAVAILABLE: "The supplied market is unavailable for publication.",
    GateReason.MARKET_LIQUIDITY_LIMITED: "Market availability or liquidity requires manual review.",
    GateReason.UNSUPPORTED_MARKET: "The supplied market is not supported by Official policy.",
    GateReason.CORRECT_SCORE_FORBIDDEN: "Correct-score predictions are forbidden.",
    GateReason.INVALID_MARKET_LINE: "The supplied market line is invalid for this market.",
    GateReason.INVALID_SELECTION: "The selection is inconsistent with its market definition.",
    GateReason.INVALID_EXPECTED_VALUE: "Supplied expected value is missing or invalid.",
    GateReason.EXPECTED_VALUE_MISMATCH: "Supplied expected value disagrees with calibrated probability and odds.",
    GateReason.EXPECTED_VALUE_TOO_LOW: "Expected value is below the Official minimum.",
    GateReason.CONSERVATIVE_EXPECTED_VALUE: "Expected value qualifies only for conservative manual treatment.",
    GateReason.LOW_CONFIDENCE: "Low-confidence predictions are not eligible for Official publication.",
    GateReason.MEDIUM_CONFIDENCE_WEAK_DATA: "Medium confidence with weak supporting data requires review.",
    GateReason.CALIBRATION_FACTS_MISSING: "Calibration quality facts are required.",
    GateReason.CALIBRATION_MODEL_VERSION_MISMATCH: "Calibration facts do not match the candidate model version.",
    GateReason.CALIBRATION_SAMPLE_INSUFFICIENT: "Calibration sample size is below the configured minimum.",
    GateReason.CALIBRATION_METRICS_WARNING: "Calibration quality is outside preferred limits.",
    GateReason.CALIBRATION_METRICS_DEGRADED: "Calibration quality exceeds warning limits and requires review.",
    GateReason.CALIBRATION_METRICS_HARD_FAILURE: "Calibration quality exceeds hard safety limits.",
    GateReason.MODEL_HEALTH_VERSION_MISMATCH: "Model health facts do not match the candidate model version.",
    GateReason.MODEL_HEALTH_WARNING: "Current model health requires manual review.",
    GateReason.MODEL_UNHEALTHY: "Current model health is not eligible for publication.",
    GateReason.LINEUP_CONFIRMATION_MISSING: "This market is lineup-sensitive and confirmed lineup data is unavailable.",
    GateReason.INJURY_DATA_INCOMPLETE: "Injury or suspension evidence is incomplete for this lineup-sensitive market.",
    GateReason.RISK_INELIGIBLE: "The supplied risk-management decision is ineligible.",
    GateReason.RISK_REVIEW_REQUIRED: "The supplied risk-management decision requires review.",
    GateReason.WRONG_BANKROLL_SCOPE: "The supplied bankroll scope is not Official.",
    GateReason.EXPOSURE_WARNING: "The supplied exposure assessment contains a warning.",
    GateReason.EXPOSURE_HARD_BREACH: "The supplied exposure assessment breaches a hard Official limit.",
    GateReason.ALREADY_PUBLISHED: "The prediction is already published.",
    GateReason.ACTIVE_PUBLICATION_ATTEMPT: "An active publication claim or attempt creates duplicate-delivery risk.",
}

FindingCollector = Callable[[GateReason, FindingSeverity], None]


class OfficialPublicationQualityGate:
    """Evaluates supplied facts only and returns one deterministic decision."""

    def __init__(self, policy: OfficialQualityGatePolicy) -> None:
        self.policy = policy

    def evaluate(
        self,
        candidate: OfficialPublicationCandidate,
    ) -> OfficialQualityGateEvaluation:
        findings: list[GateFinding] = []
        def add(reason: GateReason, severity: FindingSeverity) -> None:
            findings.append(
                GateFinding(reason, severity, REASON_EXPLANATIONS[reason])
            )
        self._identity_and_timing(candidate, add)
        market = self._market(candidate, add)
        self._probability_odds_value(candidate, add)
        self._freshness_and_availability(candidate, add)
        self._confidence_and_evidence(candidate, market, add)
        self._calibration_and_health(candidate, add)
        self._risk_exposure_duplicates(candidate, add)

        ordered_findings = self._ordered_findings(tuple(findings))
        if any(item.severity is FindingSeverity.REJECTED for item in ordered_findings):
            decision = QualityGateStatus.REJECTED
        elif ordered_findings:
            decision = QualityGateStatus.REVIEW_REQUIRED
        else:
            decision = QualityGateStatus.APPROVED

        normalized = self.normalized_input(candidate)
        fingerprint = self.fingerprint(normalized)
        recomputed = self._recomputed_expected_value(candidate)
        return OfficialQualityGateEvaluation(
            evaluation_id=f"official-gate-{fingerprint}",
            prediction_id=candidate.prediction_id,
            final_decision=decision,
            ordered_reason_codes=tuple(item.reason for item in ordered_findings),
            internal_explanations=tuple(
                item.explanation for item in ordered_findings
            ),
            findings=ordered_findings,
            policy_version=self.policy.version,
            model_version=candidate.model_version,
            raw_probability=candidate.raw_probability,
            calibrated_probability=candidate.calibrated_probability,
            decimal_odds=candidate.decimal_odds,
            supplied_expected_value=candidate.expected_value,
            recomputed_expected_value=recomputed,
            confidence=candidate.confidence,
            prediction_timestamp=candidate.prediction_timestamp,
            kickoff_timestamp=candidate.kickoff_timestamp,
            evaluated_at=candidate.evaluation_timestamp,
            input_fingerprint=fingerprint,
            normalized_input=normalized,
            risk_result=candidate.risk_result,
            exposure_result=candidate.exposure_result,
        )

    def normalized_input(
        self,
        candidate: OfficialPublicationCandidate,
    ) -> tuple[tuple[str, str], ...]:
        calibration = candidate.calibration
        health = candidate.model_health
        values: dict[str, object] = {
            "bankroll_scope": candidate.bankroll_scope,
            "calibrated_probability": candidate.calibrated_probability,
            "calibration_brier": calibration.brier_score if calibration else None,
            "calibration_ece": calibration.expected_calibration_error if calibration else None,
            "calibration_log_loss": calibration.log_loss if calibration else None,
            "calibration_mce": calibration.maximum_calibration_error if calibration else None,
            "calibration_model_version": calibration.model_version if calibration else None,
            "calibration_sample_size": calibration.sample_size if calibration else None,
            "confidence": candidate.confidence,
            "core_data_observed_at": candidate.core_data_observed_at,
            "decimal_odds": candidate.decimal_odds,
            "evaluation_timestamp": candidate.evaluation_timestamp,
            "expected_value": candidate.expected_value,
            "exposure_result": candidate.exposure_result,
            "injury_status": candidate.injury_status,
            "kickoff_timestamp": candidate.kickoff_timestamp,
            "lineup_status": candidate.lineup_status,
            "market": _normalize(candidate.market),
            "market_availability": candidate.market_availability,
            "market_line": candidate.market_line,
            "model_health_checked_at": health.checked_at,
            "model_health_status": health.status,
            "model_health_version": health.model_version,
            "model_version": candidate.model_version,
            "odds_observed_at": candidate.odds_observed_at,
            "prediction_id": candidate.prediction_id,
            "prediction_timestamp": candidate.prediction_timestamp,
            "publication_state": candidate.publication_state,
            "raw_probability": candidate.raw_probability,
            "risk_result": candidate.risk_result,
            "selection": _normalize(candidate.selection),
            "supporting_data_status": candidate.supporting_data_status,
        }
        return tuple(
            (key, _stable_value(value)) for key, value in sorted(values.items())
        )

    def fingerprint(self, normalized: tuple[tuple[str, str], ...]) -> str:
        payload = json.dumps(
            {"policy_version": self.policy.version, "facts": normalized},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _identity_and_timing(
        self,
        candidate: OfficialPublicationCandidate,
        add: FindingCollector,
    ) -> None:
        if not candidate.prediction_id.strip() or not candidate.model_version.strip():
            add(GateReason.INVALID_IDENTITY, FindingSeverity.REJECTED)
        timestamps = (
            candidate.prediction_timestamp,
            candidate.kickoff_timestamp,
            candidate.evaluation_timestamp,
            candidate.odds_observed_at,
            candidate.core_data_observed_at,
            candidate.model_health.checked_at,
        )
        if not all(_aware(value) for value in timestamps):
            add(GateReason.INVALID_TIMESTAMP, FindingSeverity.REJECTED)
            return
        if candidate.prediction_timestamp >= candidate.kickoff_timestamp:
            add(GateReason.PREDICTION_AT_OR_AFTER_KICKOFF, FindingSeverity.REJECTED)
        if any(
            value > candidate.evaluation_timestamp
            for value in (
                candidate.prediction_timestamp,
                candidate.odds_observed_at,
                candidate.core_data_observed_at,
                candidate.model_health.checked_at,
            )
        ):
            add(GateReason.INVALID_TIMESTAMP, FindingSeverity.REJECTED)
        if (
            candidate.evaluation_timestamp - candidate.prediction_timestamp
            > self.policy.maximum_candidate_age
        ):
            add(GateReason.CANDIDATE_EXPIRED, FindingSeverity.REJECTED)

    def _market(
        self,
        candidate: OfficialPublicationCandidate,
        add: FindingCollector,
    ) -> SupportedMarket | None:
        normalized = _normalize(candidate.market)
        if "CORRECT SCORE" in normalized or "EXACT SCORE" in normalized:
            add(GateReason.CORRECT_SCORE_FORBIDDEN, FindingSeverity.REJECTED)
            return None
        market = _parse_market(normalized)
        if market is None or market not in self.policy.supported_markets:
            add(GateReason.UNSUPPORTED_MARKET, FindingSeverity.REJECTED)
            return None
        selection = _normalize(candidate.selection)
        if market is SupportedMarket.MATCH_WINNER:
            valid = selection in {"HOME", "DRAW", "AWAY", "1", "X", "2"}
            line_valid = candidate.market_line is None
        elif market is SupportedMarket.DOUBLE_CHANCE:
            valid = selection in {
                "HOME OR DRAW", "AWAY OR DRAW", "HOME OR AWAY", "1X", "X2", "12",
            }
            line_valid = candidate.market_line is None
        elif market is SupportedMarket.TOTALS:
            valid = selection.startswith("OVER") or selection.startswith("UNDER")
            line_valid = _positive(candidate.market_line)
        else:
            valid = selection in {"YES", "NO"}
            line_valid = candidate.market_line is None
        if not valid:
            add(GateReason.INVALID_SELECTION, FindingSeverity.REJECTED)
        if not line_valid:
            add(GateReason.INVALID_MARKET_LINE, FindingSeverity.REJECTED)
        return market

    def _probability_odds_value(
        self,
        candidate: OfficialPublicationCandidate,
        add: FindingCollector,
    ) -> None:
        if not _probability(candidate.raw_probability, Decimal("0"), Decimal("1")):
            add(GateReason.INVALID_RAW_PROBABILITY, FindingSeverity.REJECTED)
        if candidate.calibrated_probability is None:
            add(GateReason.CALIBRATED_PROBABILITY_MISSING, FindingSeverity.REJECTED)
        elif not _probability(
            candidate.calibrated_probability,
            self.policy.minimum_probability,
            self.policy.maximum_probability,
        ):
            add(GateReason.INVALID_CALIBRATED_PROBABILITY, FindingSeverity.REJECTED)
        if not _valid_odds(candidate.decimal_odds):
            add(GateReason.INVALID_ODDS, FindingSeverity.REJECTED)
        elif candidate.decimal_odds < self.policy.minimum_odds:
            add(GateReason.ODDS_BELOW_MINIMUM, FindingSeverity.REJECTED)
        if not _finite(candidate.expected_value):
            add(GateReason.INVALID_EXPECTED_VALUE, FindingSeverity.REJECTED)
            return
        recomputed = self._recomputed_expected_value(candidate)
        if recomputed is not None and abs(candidate.expected_value - recomputed) > self.policy.expected_value_tolerance:
            add(GateReason.EXPECTED_VALUE_MISMATCH, FindingSeverity.REJECTED)
        if candidate.expected_value < self.policy.minimum_expected_value:
            add(GateReason.EXPECTED_VALUE_TOO_LOW, FindingSeverity.REJECTED)
        elif candidate.expected_value < self.policy.normal_expected_value:
            add(GateReason.CONSERVATIVE_EXPECTED_VALUE, FindingSeverity.REVIEW_REQUIRED)

    def _freshness_and_availability(
        self,
        candidate: OfficialPublicationCandidate,
        add: FindingCollector,
    ) -> None:
        if _aware(candidate.odds_observed_at) and _aware(candidate.evaluation_timestamp):
            if candidate.evaluation_timestamp - candidate.odds_observed_at > self.policy.maximum_odds_age:
                add(GateReason.ODDS_STALE, FindingSeverity.REJECTED)
        if candidate.supporting_data_status is FactStatus.MISSING:
            add(GateReason.CORE_DATA_MISSING, FindingSeverity.REJECTED)
        if _aware(candidate.core_data_observed_at) and _aware(candidate.evaluation_timestamp):
            if candidate.evaluation_timestamp - candidate.core_data_observed_at > self.policy.maximum_core_data_age:
                add(GateReason.CORE_DATA_STALE, FindingSeverity.REJECTED)
        if candidate.market_availability is MarketAvailability.UNAVAILABLE:
            add(GateReason.MARKET_UNAVAILABLE, FindingSeverity.REJECTED)
        elif candidate.market_availability is MarketAvailability.LIMITED:
            add(GateReason.MARKET_LIQUIDITY_LIMITED, FindingSeverity.REVIEW_REQUIRED)

    def _confidence_and_evidence(
        self,
        candidate: OfficialPublicationCandidate,
        market: SupportedMarket | None,
        add: FindingCollector,
    ) -> None:
        if candidate.confidence is ConfidenceLevel.LOW:
            add(GateReason.LOW_CONFIDENCE, FindingSeverity.REJECTED)
        elif (
            candidate.confidence is ConfidenceLevel.MEDIUM
            and candidate.supporting_data_status is not FactStatus.AVAILABLE
        ):
            add(GateReason.MEDIUM_CONFIDENCE_WEAK_DATA, FindingSeverity.REVIEW_REQUIRED)
        if market in self.policy.lineup_sensitive_markets:
            if candidate.lineup_status is not LineupStatus.CONFIRMED:
                add(GateReason.LINEUP_CONFIRMATION_MISSING, FindingSeverity.REVIEW_REQUIRED)
            if candidate.injury_status is not FactStatus.AVAILABLE:
                add(GateReason.INJURY_DATA_INCOMPLETE, FindingSeverity.REVIEW_REQUIRED)

    def _calibration_and_health(
        self,
        candidate: OfficialPublicationCandidate,
        add: FindingCollector,
    ) -> None:
        calibration = candidate.calibration
        if calibration is None:
            add(GateReason.CALIBRATION_FACTS_MISSING, FindingSeverity.REJECTED)
        else:
            if calibration.model_version != candidate.model_version:
                add(GateReason.CALIBRATION_MODEL_VERSION_MISMATCH, FindingSeverity.REJECTED)
            if type(calibration.sample_size) is not int or calibration.sample_size < self.policy.minimum_calibration_sample_size:
                add(GateReason.CALIBRATION_SAMPLE_INSUFFICIENT, FindingSeverity.REVIEW_REQUIRED)
            metric_pairs = (
                (calibration.brier_score, self.policy.brier_limits),
                (calibration.log_loss, self.policy.log_loss_limits),
                (calibration.expected_calibration_error, self.policy.ece_limits),
                (calibration.maximum_calibration_error, self.policy.mce_limits),
            )
            if any(not _nonnegative_finite(value) or value > limits.hard for value, limits in metric_pairs):
                add(GateReason.CALIBRATION_METRICS_HARD_FAILURE, FindingSeverity.REJECTED)
            elif any(value > limits.warning for value, limits in metric_pairs):
                add(GateReason.CALIBRATION_METRICS_DEGRADED, FindingSeverity.REVIEW_REQUIRED)
            elif any(value > limits.preferred for value, limits in metric_pairs):
                add(GateReason.CALIBRATION_METRICS_WARNING, FindingSeverity.REVIEW_REQUIRED)
        health = candidate.model_health
        if health.model_version != candidate.model_version:
            add(GateReason.MODEL_HEALTH_VERSION_MISMATCH, FindingSeverity.REJECTED)
        if health.status is ModelHealthStatus.UNHEALTHY:
            add(GateReason.MODEL_UNHEALTHY, FindingSeverity.REJECTED)
        elif health.status is ModelHealthStatus.WARNING:
            add(GateReason.MODEL_HEALTH_WARNING, FindingSeverity.REVIEW_REQUIRED)

    def _risk_exposure_duplicates(
        self,
        candidate: OfficialPublicationCandidate,
        add: FindingCollector,
    ) -> None:
        if candidate.risk_result is RiskAssessmentDecision.INELIGIBLE:
            add(GateReason.RISK_INELIGIBLE, FindingSeverity.REJECTED)
        elif candidate.risk_result is RiskAssessmentDecision.REVIEW_REQUIRED:
            add(GateReason.RISK_REVIEW_REQUIRED, FindingSeverity.REVIEW_REQUIRED)
        if candidate.bankroll_scope is not RiskProductScope.OFFICIAL:
            add(GateReason.WRONG_BANKROLL_SCOPE, FindingSeverity.REJECTED)
        if candidate.exposure_result is ExposureDecision.HARD_BREACH and self.policy.exposure_hard_breach_rejects:
            add(GateReason.EXPOSURE_HARD_BREACH, FindingSeverity.REJECTED)
        elif candidate.exposure_result is ExposureDecision.WARNING and self.policy.exposure_warning_requires_review:
            add(GateReason.EXPOSURE_WARNING, FindingSeverity.REVIEW_REQUIRED)
        if candidate.publication_state is PublicationState.PUBLISHED:
            add(GateReason.ALREADY_PUBLISHED, FindingSeverity.REJECTED)
        elif candidate.publication_state in {PublicationState.ATTEMPTING, PublicationState.CLAIMED}:
            add(GateReason.ACTIVE_PUBLICATION_ATTEMPT, FindingSeverity.REJECTED)

    def _recomputed_expected_value(
        self,
        candidate: OfficialPublicationCandidate,
    ) -> Decimal | None:
        probability = candidate.calibrated_probability
        if not _probability(probability, self.policy.minimum_probability, self.policy.maximum_probability):
            return None
        if not _valid_odds(candidate.decimal_odds):
            return None
        return probability * candidate.decimal_odds - Decimal("1")

    @staticmethod
    def _ordered_findings(findings: tuple[GateFinding, ...]) -> tuple[GateFinding, ...]:
        by_reason: dict[GateReason, GateFinding] = {}
        for finding in findings:
            existing = by_reason.get(finding.reason)
            if existing is None or finding.severity is FindingSeverity.REJECTED:
                by_reason[finding.reason] = finding
        return tuple(by_reason[reason] for reason in GateReason if reason in by_reason)


def _parse_market(value: str) -> SupportedMarket | None:
    aliases = {
        "MATCH WINNER": SupportedMarket.MATCH_WINNER,
        "MONEYLINE": SupportedMarket.MATCH_WINNER,
        "1X2": SupportedMarket.MATCH_WINNER,
        "DOUBLE CHANCE": SupportedMarket.DOUBLE_CHANCE,
        "TOTALS": SupportedMarket.TOTALS,
        "OVER UNDER": SupportedMarket.TOTALS,
        "BTTS": SupportedMarket.BTTS,
        "BOTH TEAMS TO SCORE": SupportedMarket.BTTS,
    }
    return aliases.get(value)


def _normalize(value: str) -> str:
    return " ".join(value.strip().upper().replace("_", " ").replace("/", " ").split())


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


def _nonnegative_finite(value: object) -> bool:
    return _finite(value) and value >= 0


def _probability(value: object, minimum: Decimal, maximum: Decimal) -> bool:
    return _finite(value) and minimum <= value <= maximum


def _valid_odds(value: object) -> bool:
    return _finite(value) and value > 1


def _positive(value: object) -> bool:
    return _finite(value) and value > 0


def _stable_value(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc).isoformat()
            if _aware(value)
            else value.isoformat()
        )
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    return str(value)
