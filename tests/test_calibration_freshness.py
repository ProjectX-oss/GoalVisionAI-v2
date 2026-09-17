from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

from app.calibration_freshness import (
    CalibrationActionabilityStatus,
    CalibrationEvidenceStatus,
    CalibrationFreshnessPolicy,
    CalibrationIntegrityStatus,
    CalibrationReviewStatus,
    assess_calibration_freshness,
)
from app.market_value_assessment import DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY
from app.real_match_lab_analysis.policy import LAB_MARKET_VALUE_ASSESSMENT_POLICY


UTC = timezone.utc
NOW = datetime(2026, 7, 31, 16, tzinfo=UTC)


@dataclass(frozen=True)
class Command:
    calibration_timestamp: str
    source_model_artifact_id: str = "model-1"
    source_model_artifact_fingerprint: str = "model-fp-1"


@dataclass(frozen=True)
class Calibration:
    artifact_set_id: str = "cal-1"
    artifact_set_fingerprint: str = "cal-fp-1"
    calibration_run_id: str = "run-1"
    command: Command = Command("2026-07-31T08:00:00Z")
    provenance_snapshot: str = "CONTROLLED_SYNTHETIC_STAGING_SOURCE"


class Database:
    def __init__(self, evidence="2026-01-01T00:00:00Z"):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE historical_probability_calibration_runs(
          calibration_run_id TEXT,validation_row_count INTEGER,
          source_artifact_id TEXT,source_artifact_fingerprint TEXT);
        CREATE TABLE historical_probability_calibration_predictions(
          calibration_run_id TEXT,training_example_id TEXT,example_fingerprint TEXT);
        CREATE TABLE historical_training_examples(
          training_example_id TEXT,example_fingerprint TEXT,kickoff_timestamp TEXT);
        """)
        self.connection.execute("INSERT INTO historical_probability_calibration_runs VALUES(?,?,?,?)",("run-1",2,"model-1","model-fp-1"))
        for index, timestamp in enumerate((evidence, evidence)):
            self.connection.execute("INSERT INTO historical_training_examples VALUES(?,?,?)",(f"e{index}",f"fp{index}",timestamp))
            self.connection.execute("INSERT INTO historical_probability_calibration_predictions VALUES(?,?,?)",("run-1",f"e{index}",f"fp{index}"))

    def __del__(self):
        self.connection.close()


class CalibrationFreshnessTests(unittest.TestCase):
    def assess(self, database=None, calibration=None, **changes):
        values = dict(environment="LAB", assessment_timestamp=NOW,
                      review_timestamp=NOW-timedelta(minutes=1),
                      policy=CalibrationFreshnessPolicy())
        values.update(changes)
        return assess_calibration_freshness(database or Database(), calibration or Calibration(), **values)

    def test_artifact_creation_age_is_distinct_from_evidence_age(self):
        result = self.assess()
        self.assertEqual(result.artifact_created_timestamp, datetime(2026,7,31,8,tzinfo=UTC))
        self.assertEqual(result.evidence_timestamp, datetime(2026,1,1,tzinfo=UTC))
        self.assertGreater(result.evidence_age_seconds, 7200)
        self.assertEqual(result.actionability_status, CalibrationActionabilityStatus.ACTIONABLE_FOR_LAB)

    def test_original_7200_second_regression(self):
        old_fit = Calibration(command=Command("2026-07-01T00:00:00Z"))
        self.assertEqual(self.assess(calibration=old_fit).evidence_status, CalibrationEvidenceStatus.FRESH)

    def test_activation_or_review_does_not_refresh_evidence(self):
        first = self.assess(review_timestamp=NOW-timedelta(hours=1))
        second = self.assess(review_timestamp=NOW)
        self.assertEqual(first.evidence_timestamp, second.evidence_timestamp)

    def test_refit_unchanged_evidence_cannot_fake_freshness(self):
        stale = Database("2024-01-01T00:00:00Z")
        recent_fit = Calibration(command=Command("2026-07-31T15:59:00Z"))
        self.assertEqual(self.assess(stale, recent_fit).evidence_status, CalibrationEvidenceStatus.STALE)

    def test_copy_cannot_fake_freshness(self):
        stale = Database("2024-01-01T00:00:00Z")
        copied = replace(Calibration(), artifact_set_id="copy", artifact_set_fingerprint="copy-fp")
        self.assertEqual(self.assess(stale, copied).evidence_status, CalibrationEvidenceStatus.STALE)

    def test_missing_evidence_fails_closed(self):
        db = Database(); db.connection.execute("DELETE FROM historical_probability_calibration_predictions")
        result = self.assess(db)
        self.assertEqual(result.evidence_status, CalibrationEvidenceStatus.PROVENANCE_INVALID)
        self.assertEqual(result.actionability_status, CalibrationActionabilityStatus.NON_ACTIONABLE)

    def test_inconsistent_provenance_fails_closed(self):
        db = Database(); db.connection.execute("UPDATE historical_training_examples SET example_fingerprint='changed' WHERE training_example_id='e0'")
        result = self.assess(db)
        self.assertEqual(result.integrity_status, CalibrationIntegrityStatus.INVALID)
        self.assertIn("CALIBRATION_PROVENANCE_INVALID", result.ordered_reason_codes)

    def test_stale_evidence_rejects(self):
        result = self.assess(Database("2024-01-01T00:00:00Z"))
        self.assertIn("CALIBRATION_EVIDENCE_STALE", result.ordered_reason_codes)

    def test_fresh_evidence_permits_further_evaluation(self):
        self.assertEqual(self.assess().actionability_status, CalibrationActionabilityStatus.ACTIONABLE_FOR_LAB)

    def test_expired_review_rejects(self):
        result = self.assess(review_timestamp=NOW-timedelta(days=2))
        self.assertEqual(result.review_status, CalibrationReviewStatus.EXPIRED)

    def test_valid_review_permits(self):
        self.assertEqual(self.assess().review_status, CalibrationReviewStatus.VALID)

    def test_missing_review_rejects(self):
        self.assertEqual(self.assess(review_timestamp=None).review_status, CalibrationReviewStatus.MISSING)

    def test_future_review_fails_closed(self):
        result = self.assess(review_timestamp=NOW+timedelta(seconds=1))
        self.assertEqual(result.review_status, CalibrationReviewStatus.EXPIRED)

    def test_official_policy_is_fail_closed(self):
        result = self.assess(environment="OFFICIAL")
        self.assertEqual(result.actionability_status, CalibrationActionabilityStatus.NON_ACTIONABLE)
        self.assertIn("OFFICIAL_CALIBRATION_POLICY_UNSET", result.ordered_reason_codes)

    def test_deterministic_clock_and_fingerprint(self):
        self.assertEqual(self.assess(), self.assess())

    def test_missing_artifact_timestamp_fails_closed(self):
        result = self.assess(calibration=Calibration(command=Command("")))
        self.assertEqual(result.integrity_status, CalibrationIntegrityStatus.INVALID)

    def test_evidence_after_fit_fails_closed(self):
        result = self.assess(calibration=Calibration(command=Command("2025-01-01T00:00:00Z")))
        self.assertEqual(result.evidence_status, CalibrationEvidenceStatus.PROVENANCE_INVALID)

    def test_policy_is_immutable(self):
        with self.assertRaises(Exception):
            CalibrationFreshnessPolicy().lab_review_validity_seconds = 1

    def test_lab_and_official_market_policies_are_separate(self):
        self.assertEqual(
            DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY.calibrated_aging_seconds,
            7200,
        )
        self.assertEqual(
            LAB_MARKET_VALUE_ASSESSMENT_POLICY.calibrated_aging_seconds,
            CalibrationFreshnessPolicy().lab_evidence_max_age_seconds,
        )
        self.assertNotEqual(
            DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY.version,
            LAB_MARKET_VALUE_ASSESSMENT_POLICY.version,
        )

    def test_genuine_fixture_evidence_is_complete_and_self_verifying(self):
        evidence_path = (
            Path(__file__).parents[1]
            / "docs"
            / "rehearsals"
            / "calibration_freshness_genuine_lab_2026-07-31.json"
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        expected_fingerprint = evidence["evidence_fingerprint"]
        evidence["evidence_fingerprint"] = ""
        canonical = json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), expected_fingerprint)
        self.assertEqual(len(evidence["analysis"]["markets"]), 11)
        self.assertEqual(evidence["analysis"]["persistence_status"], "COMPLETED")
        self.assertEqual(evidence["safety"]["telegram_api_calls"], 0)
        self.assertEqual(evidence["safety"]["delivery_records"], 0)
        self.assertEqual(evidence["safety"]["official_publications"], 0)
        self.assertIn(
            "not proof of real-world predictive quality",
            evidence["limitations"][0],
        )


if __name__ == "__main__":
    unittest.main()
