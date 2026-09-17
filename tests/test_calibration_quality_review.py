from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import json
from pathlib import Path
import unittest

from app.calibration import CalibrationFitMetadata, CalibrationScope, CalibrationTrainingWindow, IdentityCalibrator
from app.calibration_quality_review import (
    CalibrationQualityPolicy,
    CalibrationQualityStatus,
    DEFAULT_CALIBRATION_QUALITY_POLICY,
)
from app.real_match_lab_analysis.fingerprint import fingerprint


EVIDENCE = Path("docs/rehearsals/live_78_calibration_quality_review_2026-07-31.json")


class CalibrationQualityReviewEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.quality = cls.evidence["quality"]
        cls.targets = {item["target"]: item for item in cls.quality["target_evidence"]}
        cls.traces = {item["target"]: item for item in cls.quality["traces"]}
        cls.markets = {item["market"]: item for item in cls.evidence["markets"]}

    def test_evidence_fingerprint_is_deterministic(self):
        value = dict(self.evidence)
        expected = value.pop("evidence_fingerprint")
        self.assertEqual(fingerprint(value), expected)

    def test_exact_under_2_5_extreme_trace_is_reproduced(self):
        trace = self.traces["UNDER_2_5"]
        self.assertEqual(trace["raw_probability"], "1")
        self.assertEqual(trace["fitted_source_target"], "OVER_2_5")
        self.assertEqual(trace["calibrator_output_before_clamp"], "0.99996875065016451984")
        self.assertEqual(trace["fitted_output_after_clamp"], "0.999")
        self.assertEqual(trace["output_after_final_clamp"], "0.999")

    def test_calibrator_output_is_distinct_from_final_clamp(self):
        trace = self.traces["UNDER_2_5"]
        self.assertTrue(trace["clamp_changed"])
        self.assertNotEqual(trace["calibrator_output_before_clamp"], trace["output_after_final_clamp"])

    def test_under_2_5_is_complement_not_independently_fitted(self):
        target = self.targets["UNDER_2_5"]
        self.assertTrue(target["derived_complement"])
        self.assertEqual(target["fitted_source_target"], "OVER_2_5")
        self.assertTrue(self.traces["UNDER_2_5"]["complement_changed"])

    def test_platt_parameters_and_convergence_are_inspectable(self):
        payload = json.loads(self.traces["UNDER_2_5"]["calibration_parameters_snapshot"])
        self.assertEqual(payload["method"], "platt")
        self.assertTrue(payload["parameters"]["converged"])
        self.assertEqual(payload["parameters"]["iteration_count"], 5)
        self.assertEqual(payload["parameters"]["a"], "0.7465429458251747")

    def test_isotonic_endpoint_risk_has_typed_policy_support(self):
        self.assertEqual(DEFAULT_CALIBRATION_QUALITY_POLICY.extreme_minimum, Decimal("0.001"))
        self.assertEqual(DEFAULT_CALIBRATION_QUALITY_POLICY.extreme_maximum, Decimal("0.999"))

    def test_identity_remains_an_explicit_method(self):
        from datetime import datetime, timezone
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        metadata = CalibrationFitMetadata(at, CalibrationTrainingWindow(at, at), 0, CalibrationScope.identity_scope(), "identity", "v1")
        self.assertEqual(IdentityCalibrator(metadata).calibrate(Decimal("0.42")), Decimal("0.42"))

    def test_every_fitted_target_has_validation_and_class_support(self):
        fitted = [item for item in self.targets.values() if not item["derived_complement"]]
        self.assertEqual(len(fitted), 7)
        self.assertTrue(all(item["validation_count"] == 200 for item in fitted))
        self.assertTrue(all(item["positive_count"] >= 51 for item in fitted))
        self.assertTrue(all(item["negative_count"] >= 92 for item in fitted))
        self.assertTrue(all(item["unique_raw_probability_count"] == 200 for item in fitted))

    def test_reliability_support_and_errors_are_persisted(self):
        for target in self.targets.values():
            self.assertEqual(target["reliability_bin_count"], 10)
            self.assertGreaterEqual(target["populated_bin_count"], 3)
            Decimal(target["expected_calibration_error"])
            Decimal(target["maximum_calibration_error"])

    def test_brier_and_log_loss_before_after_are_persisted(self):
        target = self.targets["OVER_2_5"]
        for name in ("brier_before", "brier_after", "log_loss_before", "log_loss_after"):
            self.assertTrue(Decimal(target[name]).is_finite())

    def test_extreme_and_large_adjustment_frequencies_are_persisted(self):
        for target in self.targets.values():
            for name in (
                "fraction_at_minimum", "fraction_at_maximum", "fraction_below_0_01",
                "fraction_above_0_99", "fraction_adjusted_over_0_10",
                "fraction_adjusted_over_0_25", "maximum_absolute_adjustment",
            ):
                Decimal(target[name])

    def test_totals_and_simplex_corrections_are_traced(self):
        for name in ("OVER_1_5", "OVER_2_5", "OVER_3_5"):
            self.assertIn("monotonicity_correction_count", self.targets[name])
        for name in ("HOME_WIN", "DRAW", "AWAY_WIN"):
            self.assertIn("simplex_correction_count", self.targets[name])

    def test_report_and_78_feature_shift_are_complete(self):
        shift = self.quality["distribution_shift"]
        self.assertEqual(shift["feature_count"], 78)
        self.assertEqual(len(shift["features"]), 78)
        self.assertEqual(shift["required_missing_count"], 0)
        self.assertEqual(shift["optional_missing_count"], 42)
        self.assertEqual(shift["out_of_range_feature_count"], 13)
        self.assertEqual(shift["strongly_shifted_feature_count"], 13)

    def test_each_feature_contains_partition_statistics(self):
        required = {
            "live_value", "missing", "train_median", "validation_median",
            "test_median", "robust_dispersion", "percentile_rank",
            "standardized_distance", "imputed", "absent",
            "outside_historical_range",
        }
        self.assertTrue(all(required <= set(item) for item in self.quality["distribution_shift"]["features"]))

    def test_controlled_synthetic_is_previewable_but_not_send_eligible(self):
        self.assertTrue(self.quality["controlled_synthetic"])
        self.assertTrue(self.quality["analysis_preview_allowed"])
        self.assertFalse(self.quality["send_eligible"])
        self.assertFalse(self.evidence["send_eligible"])

    def test_unsupported_extreme_and_ev_are_non_actionable(self):
        market = self.markets["UNDER_2_5"]
        self.assertEqual(market["extreme_status"], "CALIBRATION_EXTREME_UNSUPPORTED")
        self.assertGreater(Decimal(market["expected_value"]), 1)
        self.assertFalse(market["actionable"])
        self.assertIn("CALIBRATION_EXTREME_UNSUPPORTED", market["rejection_reasons"])

    def test_mathematical_rank_differs_from_actionable_result(self):
        self.assertEqual(self.evidence["mathematical_ranking"][0], "UNDER_2_5")
        self.assertEqual(self.markets["UNDER_2_5"]["mathematical_rank"], 1)
        self.assertEqual(self.evidence["actionable_result"], "NO_SELECTION")

    def test_lab_and_official_fail_closed(self):
        self.assertEqual(self.quality["lab_outcome"], CalibrationQualityStatus.INELIGIBLE.value)
        self.assertEqual(self.quality["official_outcome"], CalibrationQualityStatus.INELIGIBLE.value)
        self.assertFalse(DEFAULT_CALIBRATION_QUALITY_POLICY.official_policy_authorized)

    def test_all_11_markets_remain_inspectable(self):
        self.assertEqual(len(self.evidence["markets"]), 11)
        self.assertEqual(len(self.quality["traces"]), 11)
        self.assertTrue(all("calibration_quality_outcome" in item for item in self.evidence["markets"]))

    def test_replay_outcome_and_reasons_are_honest(self):
        self.assertEqual(self.evidence["analysis_status"], "NO_SELECTION")
        self.assertEqual(self.evidence["rejection_reasons"], [
            "CALIBRATION_EXTREME_UNSUPPORTED",
            "CALIBRATION_DISTRIBUTION_SHIFT",
            "CONTROLLED_SYNTHETIC_CALIBRATION_NOT_PUBLICATION_ELIGIBLE",
        ])

    def test_safety_counters_and_integrity_are_zero(self):
        safety = self.evidence["safety"]
        for name in (
            "telegram_calls", "telegram_sends", "delivery_records",
            "official_publications", "official_result_publications",
            "official_bankroll_accounts", "official_bankroll_transactions",
            "production_activation_mutations", "foreign_key_violations",
        ):
            self.assertEqual(safety[name], 0)
        self.assertEqual(safety["source_database_sha256_before"], safety["source_database_sha256_after"])

    def test_policy_is_frozen_and_cannot_authorize_official(self):
        with self.assertRaises(FrozenInstanceError):
            DEFAULT_CALIBRATION_QUALITY_POLICY.maximum_ece = Decimal("1")
        with self.assertRaises(ValueError):
            replace(CalibrationQualityPolicy(), official_policy_authorized=True)

    def test_report_is_sanitized_and_disclaims_predictive_quality(self):
        text = json.dumps(self.evidence)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", text)
        self.assertIn("controlled synthetic", text.lower())
        self.assertIn("not betting advice", text.lower())


if __name__ == "__main__":
    unittest.main()
