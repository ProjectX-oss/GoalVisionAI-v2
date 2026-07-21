from decimal import Decimal

from app.prediction_inference import OFFICIAL_TARGET_ORDER, PredictionInferenceFingerprint, PredictionInferenceResult, PredictionTarget

from .exceptions import InvalidCalibratedOutputError, InvalidInferenceError
from .models import CalibratedTargetResult, CalibratedValidationCheck, CalibratedValidationSummary
from .policy import CalibratedMarketProbabilityPolicy


class CalibratedAssemblyValidator:
    def validate_inference(
        self, supplied: PredictionInferenceResult | None,
        persisted: PredictionInferenceResult | None, calibration_timestamp: object,
        policy: CalibratedMarketProbabilityPolicy,
    ) -> PredictionInferenceResult:
        if not isinstance(supplied, PredictionInferenceResult):
            raise InvalidInferenceError("RAW_INFERENCE_REQUIRED", "A raw inference result is required.")
        if persisted is None or persisted != supplied:
            raise InvalidInferenceError("RAW_INFERENCE_NOT_PERSISTED", "Raw inference provenance is not persisted or differs.")
        if supplied.policy_version not in policy.supported_raw_inference_policy_versions:
            raise InvalidInferenceError("UNSUPPORTED_INFERENCE_POLICY", "Raw inference policy is unsupported.")
        if not hasattr(calibration_timestamp, "tzinfo") or calibration_timestamp.tzinfo is None:
            raise InvalidInferenceError("INVALID_CALIBRATION_TIMESTAMP", "Calibration timestamp must be timezone-aware.")
        if calibration_timestamp < supplied.inference_timestamp:
            raise InvalidInferenceError("CALIBRATION_BEFORE_INFERENCE", "Calibration timestamp precedes inference.")
        probabilities = supplied.raw_probabilities.ordered_probabilities
        if tuple(item.target for item in probabilities) != OFFICIAL_TARGET_ORDER:
            raise InvalidInferenceError("INVALID_RAW_TARGETS", "Raw targets are incomplete, unknown, duplicated, or reordered.")
        if any(not isinstance(item.probability, Decimal) or not item.probability.is_finite() for item in probabilities):
            raise InvalidInferenceError("MALFORMED_RAW_PROBABILITY", "Raw probabilities must be finite Decimals.")
        if any(not Decimal(0) <= item.probability <= Decimal(1) for item in probabilities):
            raise InvalidInferenceError("RAW_PROBABILITY_OUT_OF_RANGE", "Raw probabilities must be within [0, 1].")
        if PredictionInferenceFingerprint().calculate_for_result(supplied) != supplied.inference_fingerprint:
            raise InvalidInferenceError("RAW_INFERENCE_FINGERPRINT_MISMATCH", "Raw inference fingerprint verification failed.")
        return supplied

    def validate_outputs(self, values: tuple[CalibratedTargetResult, ...], policy: CalibratedMarketProbabilityPolicy) -> CalibratedValidationSummary:
        if tuple(item.target for item in values) != policy.target_order:
            raise InvalidCalibratedOutputError("INVALID_CALIBRATED_TARGETS", "Calibrated targets are incomplete or unordered.")
        probabilities = {item.target: item.calibrated_probability for item in values}
        for item in values:
            if not isinstance(item.calibrated_probability, Decimal) or not item.calibrated_probability.is_finite():
                raise InvalidCalibratedOutputError("MALFORMED_CALIBRATED_PROBABILITY", "Calibrated probability is malformed.")
            if not policy.minimum_probability <= item.calibrated_probability <= policy.maximum_probability:
                raise InvalidCalibratedOutputError("CALIBRATED_PROBABILITY_OUT_OF_RANGE", "Calibrated probability is outside allowed bounds.")
        checks = (
            self._sum("MATCH_RESULT_SUM", probabilities, (PredictionTarget.HOME_WIN, PredictionTarget.DRAW, PredictionTarget.AWAY_WIN), policy.match_result_tolerance),
            self._sum("TOTAL_1_5_SUM", probabilities, (PredictionTarget.OVER_1_5, PredictionTarget.UNDER_1_5), policy.complement_tolerance),
            self._sum("TOTAL_2_5_SUM", probabilities, (PredictionTarget.OVER_2_5, PredictionTarget.UNDER_2_5), policy.complement_tolerance),
            self._sum("TOTAL_3_5_SUM", probabilities, (PredictionTarget.OVER_3_5, PredictionTarget.UNDER_3_5), policy.complement_tolerance),
            self._sum("BTTS_SUM", probabilities, (PredictionTarget.BTTS_YES, PredictionTarget.BTTS_NO), policy.complement_tolerance),
            self._monotonic("OVER_TOTALS_MONOTONIC", probabilities[PredictionTarget.OVER_1_5], probabilities[PredictionTarget.OVER_2_5], probabilities[PredictionTarget.OVER_3_5], policy.monotonicity_tolerance, True),
            self._monotonic("UNDER_TOTALS_MONOTONIC", probabilities[PredictionTarget.UNDER_1_5], probabilities[PredictionTarget.UNDER_2_5], probabilities[PredictionTarget.UNDER_3_5], policy.monotonicity_tolerance, False),
        )
        failed = next((item for item in checks if not item.passed), None)
        if failed:
            raise InvalidCalibratedOutputError(failed.code, f"Combined calibrated check {failed.code} failed; output was not normalized.")
        return CalibratedValidationSummary(policy.version, len(values), checks)

    @staticmethod
    def _sum(code: str, values: dict, targets: tuple, tolerance: Decimal) -> CalibratedValidationCheck:
        observed = sum((values[item] for item in targets), Decimal(0))
        return CalibratedValidationCheck(code, abs(observed - Decimal(1)) <= tolerance, observed, tolerance)

    @staticmethod
    def _monotonic(code: str, a: Decimal, b: Decimal, c: Decimal, tolerance: Decimal, descending: bool) -> CalibratedValidationCheck:
        passed = (a + tolerance >= b and b + tolerance >= c) if descending else (a <= b + tolerance and b <= c + tolerance)
        violation = max(b - a, c - b, Decimal(0)) if descending else max(a - b, b - c, Decimal(0))
        return CalibratedValidationCheck(code, passed, violation, tolerance)
