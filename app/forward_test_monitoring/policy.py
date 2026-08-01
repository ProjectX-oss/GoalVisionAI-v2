"""Single versioned policy for manual forward-test monitoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from app.real_match_lab_analysis.fingerprint import fingerprint


@dataclass(frozen=True, slots=True)
class ForwardTestReportingPolicy:
    policy_id: str = "goalvision-forward-test-monitoring"
    version: str = "1.0.0"
    timezone: str = "Europe/Riga"
    week_starts: str = "MONDAY_00_00_LOCAL"
    week_ends: str = "NEXT_MONDAY_EXCLUSIVE"
    cutoff_semantics: str = "INCLUDE_SOURCE_ROWS_WITH_EVENT_TIMESTAMP_LE_CUTOFF"
    accepted_evidence_tiers: tuple[str, ...] = ("FORWARD_TEST_REAL_TIME",)
    flat_stake_units: Decimal = Decimal("1")
    void_stake_returned: bool = True
    roi_formula: str = "NET_PROFIT_UNITS/TOTAL_STAKED_UNITS"
    yield_formula: str = "NET_PROFIT_UNITS/TOTAL_STAKED_UNITS"
    hit_rate_formula: str = "WINS/(WINS+LOSSES)"
    clv_policy: str = "UNAVAILABLE_UNLESS_IMMUTABLE_PRE_KICKOFF_CLOSING_QUOTE_EXISTS"
    drawdown_method: str = "PEAK_TO_SUBSEQUENT_TROUGH_FLAT_STAKE_CHRONOLOGICAL"
    calibration_bins: int = 10
    early_sample: int = 30
    monitoring_sample: int = 100
    reviewable_sample: int = 200
    policy_minimum_sample: int = 300
    minimum_market_sample: int = 30
    minimum_competition_sample: int = 30
    minimum_calibration_sample: int = 100
    minimum_probability_bin_sample: int = 20
    minimum_shadow_sample: int = 100
    odds_minimum: Decimal = Decimal("1.01")
    odds_maximum: Decimal = Decimal("100")
    probability_minimum: Decimal = Decimal("0")
    probability_maximum: Decimal = Decimal("1")
    extreme_probability_low: Decimal = Decimal("0.02")
    extreme_probability_high: Decimal = Decimal("0.98")
    extreme_ev_absolute: Decimal = Decimal("1")
    odds_fresh_seconds: int = 900
    delayed_settlement_hours: int = 24
    missing_result_hours: int = 12
    publication_review_expiry_hours: int = 4
    stale_preview_minutes: int = 15
    model_segmentation: str = "MODEL_ARTIFACT_ID_AND_FINGERPRINT"
    calibration_segmentation: str = "CALIBRATION_ID_AND_FINGERPRINT"

    @property
    def fingerprint(self) -> str:
        return fingerprint(asdict(self))

    def sample_status(self, settled: int) -> str:
        if settled == 0:
            return "NO_SAMPLE"
        if settled < self.early_sample:
            return "FORWARD_TEST_SAMPLE_INSUFFICIENT"
        if settled < self.monitoring_sample:
            return "EARLY_SAMPLE"
        if settled < self.reviewable_sample:
            return "MONITORING_SAMPLE"
        if settled < self.policy_minimum_sample:
            return "REVIEWABLE_SAMPLE"
        return "POLICY_MINIMUM_MET"


DEFAULT_POLICY = ForwardTestReportingPolicy()
