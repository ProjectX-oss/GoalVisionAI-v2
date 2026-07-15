from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.calibration import CalibrationFitMetadata, CalibrationScope


class QualityGateStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class CheckStatus(str, Enum):
    PASSED = "PASSED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class QualityGateCheck(str, Enum):
    STRUCTURAL_VALIDATION = "STRUCTURAL_VALIDATION"
    TIMING_VALIDATION = "TIMING_VALIDATION"
    MARKET_POLICY = "MARKET_POLICY"
    ODDS_VALIDATION = "ODDS_VALIDATION"
    EVIDENCE_COMPLETENESS = "EVIDENCE_COMPLETENESS"
    CALIBRATION_ELIGIBILITY = "CALIBRATION_ELIGIBILITY"
    VALUE_ELIGIBILITY = "VALUE_ELIGIBILITY"
    MARKET_DISAGREEMENT = "MARKET_DISAGREEMENT"
    UNCERTAINTY = "UNCERTAINTY"
    EXPOSURE = "EXPOSURE"
    DUPLICATE_PROTECTION = "DUPLICATE_PROTECTION"


class EvidenceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceCategory(str, Enum):
    ODDS = "ODDS"
    TEAM_FORM = "TEAM_FORM"
    COMPETITION_CONTEXT = "COMPETITION_CONTEXT"
    LINEUP = "LINEUP"
    INJURIES = "INJURIES"
    MODEL_FEATURES = "MODEL_FEATURES"
    MARKET_CONSENSUS = "MARKET_CONSENSUS"
    CALIBRATION = "CALIBRATION"


class PublicationType(str, Enum):
    SINGLE = "SINGLE"
    COMBO = "COMBO"


class ProbabilitySource(str, Enum):
    RAW = "RAW"
    CALIBRATED = "CALIBRATED"


class RejectionReason(str, Enum):
    ODDS_BELOW_MINIMUM = "ODDS_BELOW_MINIMUM"
    ODDS_STALE = "ODDS_STALE"
    PREDICTION_AFTER_KICKOFF = "PREDICTION_AFTER_KICKOFF"
    REQUIRED_DATA_MISSING = "REQUIRED_DATA_MISSING"
    DATA_STALE = "DATA_STALE"
    PROBABILITY_NOT_CALIBRATED = "PROBABILITY_NOT_CALIBRATED"
    CALIBRATION_SAMPLE_TOO_SMALL = "CALIBRATION_SAMPLE_TOO_SMALL"
    MODEL_SAMPLE_TOO_SMALL = "MODEL_SAMPLE_TOO_SMALL"
    EXPECTED_VALUE_TOO_LOW = "EXPECTED_VALUE_TOO_LOW"
    MARKET_CONFLICT = "MARKET_CONFLICT"
    MARKET_CONFLICT_WITH_INCOMPLETE_DATA = (
        "MARKET_CONFLICT_WITH_INCOMPLETE_DATA"
    )
    EXPOSURE_LIMIT_REACHED = "EXPOSURE_LIMIT_REACHED"
    DAILY_EXPOSURE_LIMIT_REACHED = "DAILY_EXPOSURE_LIMIT_REACHED"
    COMPETITION_EXPOSURE_LIMIT_REACHED = (
        "COMPETITION_EXPOSURE_LIMIT_REACHED"
    )
    CORRELATED_EXPOSURE_LIMIT_REACHED = "CORRELATED_EXPOSURE_LIMIT_REACHED"
    DUPLICATE_PUBLICATION = "DUPLICATE_PUBLICATION"
    FORBIDDEN_MARKET = "FORBIDDEN_MARKET"
    FORBIDDEN_PRODUCT_SCOPE = "FORBIDDEN_PRODUCT_SCOPE"
    CORRECT_SCORE_FORBIDDEN = "CORRECT_SCORE_FORBIDDEN"
    COMBO_NOT_ALLOWED = "COMBO_NOT_ALLOWED"
    COMBO_EXCEPTION_REQUIREMENTS_NOT_MET = (
        "COMBO_EXCEPTION_REQUIREMENTS_NOT_MET"
    )
    INVALID_PROBABILITY = "INVALID_PROBABILITY"
    INVALID_ODDS = "INVALID_ODDS"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    EXCESSIVE_UNCERTAINTY = "EXCESSIVE_UNCERTAINTY"


class ReviewReason(str, Enum):
    LINEUP_UNCONFIRMED = "LINEUP_UNCONFIRMED"
    CRITICAL_INJURY_DATA_MISSING = "CRITICAL_INJURY_DATA_MISSING"
    MARKET_CONFLICT = "MARKET_CONFLICT"
    EXCESSIVE_UNCERTAINTY = "EXCESSIVE_UNCERTAINTY"
    OPTIONAL_EVIDENCE_PARTIAL = "OPTIONAL_EVIDENCE_PARTIAL"


@dataclass(frozen=True, slots=True)
class ComboSelection:
    market: str
    selection: str
    offered_odds: Decimal
    confidence_score: Decimal


@dataclass(frozen=True, slots=True)
class PublicationCandidate:
    prediction_id: str
    fixture_id: int
    competition: str
    kickoff_time: datetime
    prediction_timestamp: datetime
    market: str
    selection: str
    raw_probability: Decimal
    offered_odds: Decimal
    odds_timestamp: datetime
    calibrated_probability: Decimal | None = None
    reference_odds: Decimal | None = None
    expected_value: Decimal | None = None
    model_version: str | None = None
    calibration_scope: CalibrationScope | None = None
    calibration_method: str | None = None
    calibration_sample_size: int | None = None
    calibration_fit_timestamp: datetime | None = None
    calibration_training_cutoff: datetime | None = None
    confidence_score: Decimal | None = None
    uncertainty_score: Decimal | None = None
    publication_type: PublicationType = PublicationType.SINGLE
    combo_selections: tuple[ComboSelection, ...] = ()
    product_scope: str = "OFFICIAL"

    @classmethod
    def with_calibration_metadata(
        cls,
        *,
        metadata: CalibrationFitMetadata,
        calibrated_probability: Decimal,
        **candidate_fields: object,
    ) -> "PublicationCandidate":
        """Builds a candidate from the existing typed calibration contract."""

        return cls(
            **candidate_fields,
            calibrated_probability=calibrated_probability,
            calibration_scope=metadata.scope,
            calibration_method=metadata.method_name,
            calibration_sample_size=metadata.observation_count,
            calibration_fit_timestamp=metadata.fitted_at,
            calibration_training_cutoff=metadata.training_window.end,
        )


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    category: EvidenceCategory
    status: EvidenceStatus


@dataclass(frozen=True, slots=True)
class QualityGateContext:
    evaluation_timestamp: datetime
    data_completeness_status: EvidenceStatus
    data_freshness_status: EvidenceStatus
    lineup_status: EvidenceStatus
    injury_data_status: EvidenceStatus
    market_consensus_probability: Decimal | None
    market_disagreement: Decimal | None
    current_exposure: Decimal
    daily_exposure: Decimal
    competition_exposure: Decimal
    correlated_exposure: Decimal
    sample_size: int
    calibration_sample_size: int
    evidence: tuple[EvidenceAssessment, ...]

    def __post_init__(self) -> None:
        categories = tuple(item.category for item in self.evidence)
        if len(set(categories)) != len(categories):
            raise ValueError("Each evidence category may appear only once.")

    def evidence_status(self, category: EvidenceCategory) -> EvidenceStatus:
        if category is EvidenceCategory.LINEUP:
            return self.lineup_status
        if category is EvidenceCategory.INJURIES:
            return self.injury_data_status
        return dict(
            (item.category, item.status) for item in self.evidence
        ).get(category, EvidenceStatus.MISSING)


@dataclass(frozen=True, slots=True)
class QualityGateCheckResult:
    check: QualityGateCheck
    status: CheckStatus
    rejection_reasons: tuple[RejectionReason, ...] = ()
    review_reasons: tuple[ReviewReason, ...] = ()
    evaluated_probability: Decimal | None = None
    probability_source: ProbabilitySource | None = None
    expected_value: Decimal | None = None
    market_disagreement: Decimal | None = None


@dataclass(frozen=True, slots=True)
class QualityGateDecision:
    candidate_id: str
    status: QualityGateStatus
    checks: tuple[QualityGateCheckResult, ...]
    rejection_reasons: tuple[RejectionReason, ...]
    review_reasons: tuple[ReviewReason, ...]
    evaluated_probability: Decimal | None
    probability_source: ProbabilitySource | None
    expected_value: Decimal | None
    market_disagreement: Decimal | None
    policy_version: str
    evaluation_timestamp: datetime

    @property
    def automatic_publication_eligible(self) -> bool:
        return self.status is QualityGateStatus.APPROVED

    @property
    def is_no_bet(self) -> bool:
        return self.status is QualityGateStatus.REJECTED
