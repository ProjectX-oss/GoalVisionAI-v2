import asyncio
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database import Database, MigrationManager
from app.publication_quality_gate import (
    CalibrationQualityFacts,
    ConfidenceLevel,
    ExposureDecision,
    FactStatus,
    GateReason,
    LineupStatus,
    MarketAvailability,
    ModelHealthFacts,
    ModelHealthStatus,
    OfficialPublicationCandidate,
    OfficialPublicationEligibilityBoundary,
    OfficialPublicationQualityGate,
    OfficialQualityGatePolicy,
    PublicationState,
    SQLiteQualityGateEvaluationRepository,
)
from app.quality_gate import QualityGateStatus
from app.risk_management import RiskAssessmentDecision, RiskProductScope


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)


def calibration(**changes) -> CalibrationQualityFacts:
    values = {
        "brier_score": Decimal("0.15"),
        "log_loss": Decimal("0.50"),
        "expected_calibration_error": Decimal("0.03"),
        "maximum_calibration_error": Decimal("0.08"),
        "sample_size": 200,
        "model_version": "model-v1",
    }
    values.update(changes)
    return CalibrationQualityFacts(**values)


def candidate(**changes) -> OfficialPublicationCandidate:
    values = {
        "prediction_id": "prediction-1",
        "model_version": "model-v1",
        "market": "MATCH_WINNER",
        "selection": "HOME",
        "raw_probability": Decimal("0.62"),
        "calibrated_probability": Decimal("0.60"),
        "decimal_odds": Decimal("1.80"),
        "expected_value": Decimal("0.080"),
        "confidence": ConfidenceLevel.HIGH,
        "prediction_timestamp": NOW - timedelta(minutes=10),
        "kickoff_timestamp": NOW + timedelta(hours=1),
        "evaluation_timestamp": NOW,
        "odds_observed_at": NOW - timedelta(minutes=2),
        "core_data_observed_at": NOW - timedelta(minutes=5),
        "supporting_data_status": FactStatus.AVAILABLE,
        "market_availability": MarketAvailability.AVAILABLE,
        "calibration": calibration(),
        "model_health": ModelHealthFacts(
            ModelHealthStatus.HEALTHY,
            "model-v1",
            NOW - timedelta(minutes=1),
        ),
        "risk_result": RiskAssessmentDecision.ELIGIBLE,
        "exposure_result": ExposureDecision.CLEAR,
        "bankroll_scope": RiskProductScope.OFFICIAL,
        "publication_state": PublicationState.UNPUBLISHED,
        "lineup_status": LineupStatus.CONFIRMED,
        "injury_status": FactStatus.AVAILABLE,
        "market_line": None,
    }
    values.update(changes)
    return OfficialPublicationCandidate(**values)


class OfficialPublicationQualityGateRuleTests(unittest.TestCase):
    def setUp(self):
        self.gate = OfficialPublicationQualityGate(OfficialQualityGatePolicy())

    def evaluate(self, **changes):
        return self.gate.evaluate(candidate(**changes))

    def assert_reason(self, reason: GateReason, **changes):
        result = self.evaluate(**changes)
        self.assertIn(reason, result.ordered_reason_codes)
        return result

    def test_approved_high_quality_candidate(self):
        result = self.evaluate()

        self.assertEqual(result.final_decision, QualityGateStatus.APPROVED)
        self.assertEqual(result.ordered_reason_codes, ())
        self.assertEqual(result.recomputed_expected_value, Decimal("0.0800"))
        self.assertTrue(result.automatic_publication_eligible)

    def test_odds_below_official_minimum(self):
        result = self.assert_reason(
            GateReason.ODDS_BELOW_MINIMUM,
            decimal_odds=Decimal("1.59"),
            expected_value=Decimal("-0.046"),
        )
        self.assertEqual(result.final_decision, QualityGateStatus.REJECTED)

    def test_expected_value_below_minimum(self):
        self.assert_reason(
            GateReason.EXPECTED_VALUE_TOO_LOW,
            decimal_odds=Decimal("1.68"),
            expected_value=Decimal("0.008"),
        )

    def test_expected_value_verification_mismatch(self):
        self.assert_reason(
            GateReason.EXPECTED_VALUE_MISMATCH,
            expected_value=Decimal("0.10"),
        )

    def test_medium_expected_value_requires_conservative_review(self):
        result = self.assert_reason(
            GateReason.CONSERVATIVE_EXPECTED_VALUE,
            decimal_odds=Decimal("1.72"),
            expected_value=Decimal("0.032"),
        )
        self.assertEqual(result.final_decision, QualityGateStatus.REVIEW_REQUIRED)

    def test_invalid_calibrated_probability(self):
        self.assert_reason(
            GateReason.INVALID_CALIBRATED_PROBABILITY,
            calibrated_probability=Decimal("NaN"),
        )
        self.assert_reason(
            GateReason.INVALID_CALIBRATED_PROBABILITY,
            calibrated_probability=Decimal("1"),
        )

    def test_raw_probability_never_overrides_calibrated_probability(self):
        result = self.evaluate(raw_probability=Decimal("0.99"))

        self.assertEqual(result.final_decision, QualityGateStatus.APPROVED)
        self.assertEqual(result.recomputed_expected_value, Decimal("0.0800"))

    def test_missing_calibrated_probability_and_quality_facts(self):
        result = self.evaluate(calibrated_probability=None, calibration=None)

        self.assertIn(
            GateReason.CALIBRATED_PROBABILITY_MISSING,
            result.ordered_reason_codes,
        )
        self.assertIn(GateReason.CALIBRATION_FACTS_MISSING, result.ordered_reason_codes)
        self.assertEqual(result.final_decision, QualityGateStatus.REJECTED)

    def test_calibration_model_version_mismatch(self):
        self.assert_reason(
            GateReason.CALIBRATION_MODEL_VERSION_MISMATCH,
            calibration=calibration(model_version="model-v2"),
        )

    def test_insufficient_calibration_sample_requires_review(self):
        result = self.assert_reason(
            GateReason.CALIBRATION_SAMPLE_INSUFFICIENT,
            calibration=calibration(sample_size=99),
        )
        self.assertEqual(result.final_decision, QualityGateStatus.REVIEW_REQUIRED)

    def test_calibration_warning_threshold_requires_review(self):
        result = self.assert_reason(
            GateReason.CALIBRATION_METRICS_WARNING,
            calibration=calibration(brier_score=Decimal("0.21")),
        )
        self.assertEqual(result.final_decision, QualityGateStatus.REVIEW_REQUIRED)

    def test_calibration_degraded_threshold_requires_review(self):
        result = self.assert_reason(
            GateReason.CALIBRATION_METRICS_DEGRADED,
            calibration=calibration(brier_score=Decimal("0.26")),
        )
        self.assertEqual(result.final_decision, QualityGateStatus.REVIEW_REQUIRED)

    def test_calibration_hard_threshold_rejects(self):
        result = self.assert_reason(
            GateReason.CALIBRATION_METRICS_HARD_FAILURE,
            calibration=calibration(brier_score=Decimal("0.31")),
        )
        self.assertEqual(result.final_decision, QualityGateStatus.REJECTED)

    def test_prediction_at_or_after_kickoff_rejects(self):
        self.assert_reason(
            GateReason.PREDICTION_AT_OR_AFTER_KICKOFF,
            prediction_timestamp=NOW + timedelta(hours=1),
        )

    def test_expired_candidate_rejects(self):
        self.assert_reason(
            GateReason.CANDIDATE_EXPIRED,
            prediction_timestamp=NOW - timedelta(minutes=31),
        )

    def test_stale_odds_reject(self):
        self.assert_reason(
            GateReason.ODDS_STALE,
            odds_observed_at=NOW - timedelta(minutes=16),
        )

    def test_stale_and_missing_core_data_reject(self):
        self.assert_reason(
            GateReason.CORE_DATA_STALE,
            core_data_observed_at=NOW - timedelta(minutes=61),
        )
        self.assert_reason(
            GateReason.CORE_DATA_MISSING,
            supporting_data_status=FactStatus.MISSING,
        )

    def test_lineup_sensitive_market_without_confirmation_reviews(self):
        result = self.assert_reason(
            GateReason.LINEUP_CONFIRMATION_MISSING,
            lineup_status=LineupStatus.UNCONFIRMED,
        )
        self.assertEqual(result.final_decision, QualityGateStatus.REVIEW_REQUIRED)

    def test_non_lineup_sensitive_market_does_not_require_lineup(self):
        result = self.evaluate(
            market="TOTALS",
            selection="OVER",
            market_line=Decimal("2.5"),
            lineup_status=LineupStatus.MISSING,
            injury_status=FactStatus.MISSING,
        )

        self.assertEqual(result.final_decision, QualityGateStatus.APPROVED)

    def test_unsupported_market_and_correct_score_reject(self):
        self.assert_reason(GateReason.UNSUPPORTED_MARKET, market="CORNERS")
        self.assert_reason(
            GateReason.CORRECT_SCORE_FORBIDDEN,
            market="CORRECT_SCORE",
            selection="2-1",
        )

    def test_invalid_market_line_and_selection_reject(self):
        self.assert_reason(
            GateReason.INVALID_MARKET_LINE,
            market="TOTALS",
            selection="OVER",
            market_line=Decimal("-2.5"),
        )
        self.assert_reason(GateReason.INVALID_SELECTION, selection="ARBITRARY")

    def test_low_and_medium_weak_confidence_rules(self):
        self.assert_reason(GateReason.LOW_CONFIDENCE, confidence=ConfidenceLevel.LOW)
        result = self.assert_reason(
            GateReason.MEDIUM_CONFIDENCE_WEAK_DATA,
            confidence=ConfidenceLevel.MEDIUM,
            supporting_data_status=FactStatus.PARTIAL,
        )
        self.assertEqual(result.final_decision, QualityGateStatus.REVIEW_REQUIRED)

    def test_model_health_warning_mismatch_and_unhealthy(self):
        warning = ModelHealthFacts(ModelHealthStatus.WARNING, "model-v1", NOW)
        self.assert_reason(GateReason.MODEL_HEALTH_WARNING, model_health=warning)
        mismatch = ModelHealthFacts(ModelHealthStatus.HEALTHY, "model-v2", NOW)
        self.assert_reason(GateReason.MODEL_HEALTH_VERSION_MISMATCH, model_health=mismatch)
        unhealthy = ModelHealthFacts(ModelHealthStatus.UNHEALTHY, "model-v1", NOW)
        self.assert_reason(GateReason.MODEL_UNHEALTHY, model_health=unhealthy)

    def test_risk_decisions(self):
        self.assert_reason(
            GateReason.RISK_INELIGIBLE,
            risk_result=RiskAssessmentDecision.INELIGIBLE,
        )
        review = self.assert_reason(
            GateReason.RISK_REVIEW_REQUIRED,
            risk_result=RiskAssessmentDecision.REVIEW_REQUIRED,
        )
        self.assertEqual(review.final_decision, QualityGateStatus.REVIEW_REQUIRED)
        reduced = self.evaluate(risk_result=RiskAssessmentDecision.REDUCED_STAKE)
        self.assertEqual(reduced.final_decision, QualityGateStatus.APPROVED)

    def test_exposure_warning_hard_breach_and_wrong_bankroll(self):
        warning = self.assert_reason(
            GateReason.EXPOSURE_WARNING,
            exposure_result=ExposureDecision.WARNING,
        )
        self.assertEqual(warning.final_decision, QualityGateStatus.REVIEW_REQUIRED)
        self.assert_reason(
            GateReason.EXPOSURE_HARD_BREACH,
            exposure_result=ExposureDecision.HARD_BREACH,
        )
        self.assert_reason(
            GateReason.WRONG_BANKROLL_SCOPE,
            bankroll_scope=RiskProductScope.COMBO,
        )

    def test_market_availability_rules(self):
        self.assert_reason(
            GateReason.MARKET_UNAVAILABLE,
            market_availability=MarketAvailability.UNAVAILABLE,
        )
        review = self.assert_reason(
            GateReason.MARKET_LIQUIDITY_LIMITED,
            market_availability=MarketAvailability.LIMITED,
        )
        self.assertEqual(review.final_decision, QualityGateStatus.REVIEW_REQUIRED)

    def test_duplicate_publication_state(self):
        self.assert_reason(
            GateReason.ALREADY_PUBLISHED,
            publication_state=PublicationState.PUBLISHED,
        )
        for state in (PublicationState.ATTEMPTING, PublicationState.CLAIMED):
            with self.subTest(state=state):
                self.assert_reason(
                    GateReason.ACTIVE_PUBLICATION_ATTEMPT,
                    publication_state=state,
                )

    def test_reason_ordering_and_fingerprint_are_deterministic(self):
        broken = candidate(
            calibrated_probability=None,
            decimal_odds=Decimal("1.50"),
            expected_value=Decimal("-0.10"),
            risk_result=RiskAssessmentDecision.INELIGIBLE,
            publication_state=PublicationState.PUBLISHED,
        )
        first = self.gate.evaluate(broken)
        second = self.gate.evaluate(broken)

        self.assertEqual(first, second)
        self.assertEqual(
            first.ordered_reason_codes,
            tuple(
                reason
                for reason in GateReason
                if reason in set(first.ordered_reason_codes)
            ),
        )
        self.assertEqual(first.input_fingerprint, second.input_fingerprint)
        numerically_equivalent = self.gate.evaluate(
            replace(broken, raw_probability=Decimal("0.6200"))
        )
        self.assertEqual(first.input_fingerprint, numerically_equivalent.input_fingerprint)
        self.assertNotEqual(
            first.input_fingerprint,
            self.gate.evaluate(replace(broken, decimal_odds=Decimal("1.49"))).input_fingerprint,
        )


class OfficialQualityGatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteQualityGateEvaluationRepository(self.database)
        self.gate = OfficialPublicationQualityGate(OfficialQualityGatePolicy())
        self.evaluation = self.gate.evaluate(candidate())

    def tearDown(self):
        self.database.close()

    def test_fresh_database_migration_ten_and_schema(self):
        versions = tuple(
            row[0]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 18)))
        table = self.database.connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='official_quality_gate_evaluations'
            """
        ).fetchone()
        self.assertIsNotNone(table)

    def test_append_only_round_trip_and_database_guards(self):
        stored = self.repository.append(self.evaluation)

        self.assertEqual(stored, self.evaluation)
        self.assertEqual(self.repository.get(stored.evaluation_id), stored)
        for statement in (
            "UPDATE official_quality_gate_evaluations SET final_decision='REJECTED'",
            "DELETE FROM official_quality_gate_evaluations",
        ):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(statement)

    def test_repeated_identical_evaluation_is_idempotent(self):
        self.repository.append(self.evaluation)
        self.repository.append(self.evaluation)

        count = self.database.connection.execute(
            "SELECT COUNT(*) FROM official_quality_gate_evaluations"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_changed_candidate_creates_append_only_evaluation(self):
        changed = self.gate.evaluate(
            candidate(
                decimal_odds=Decimal("1.81"),
                expected_value=Decimal("0.086"),
            )
        )
        self.repository.append(self.evaluation)
        self.repository.append(changed)

        history = self.repository.history_for_prediction("prediction-1")
        self.assertEqual(len(history), 2)
        self.assertNotEqual(history[0].input_fingerprint, history[1].input_fingerprint)

    def test_upgrade_from_existing_v9_schema(self):
        database = Database(":memory:")
        database.connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        database.connection.executemany(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 'existing')",
            [(version,) for version in range(1, 10)],
        )

        MigrationManager(database.connection).migrate()

        versions = tuple(
            row[0]
            for row in database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 18)))
        self.assertIsNotNone(
            database.connection.execute(
                "SELECT name FROM sqlite_master WHERE name='official_quality_gate_evaluations'"
            ).fetchone()
        )
        database.close()


class FakePublisher:
    def __init__(self, fail_first: bool = False):
        self.calls = []
        self.fail_first = fail_first

    async def publish(self, value):
        self.calls.append(value)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("confirmed downstream failure")
        return "published"


class BrokenGate:
    def evaluate(self, value):
        raise RuntimeError("gate failed")


class OfficialQualityGateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteQualityGateEvaluationRepository(self.database)
        self.gate = OfficialPublicationQualityGate(OfficialQualityGatePolicy())

    def tearDown(self):
        self.database.close()

    def boundary(self, publisher, gate=None):
        return OfficialPublicationEligibilityBoundary(
            gate or self.gate,
            self.repository,
            publisher,
        )

    def test_only_approved_reaches_publication_boundary(self):
        publisher = FakePublisher()
        boundary = self.boundary(publisher)

        approved = asyncio.run(boundary.process(candidate()))
        rejected = asyncio.run(
            boundary.process(candidate(prediction_id="rejected", decimal_odds=Decimal("1.50"), expected_value=Decimal("-0.10")))
        )
        review = asyncio.run(
            boundary.process(candidate(prediction_id="review", risk_result=RiskAssessmentDecision.REVIEW_REQUIRED))
        )

        self.assertTrue(approved.publication_attempted)
        self.assertFalse(rejected.publication_attempted)
        self.assertFalse(review.publication_attempted)
        self.assertEqual(len(publisher.calls), 1)

    def test_gate_or_persistence_failure_fails_closed(self):
        publisher = FakePublisher()
        broken_gate = self.boundary(publisher, BrokenGate())
        outcome = asyncio.run(broken_gate.process(candidate()))

        self.assertFalse(outcome.publication_attempted)
        self.assertEqual(outcome.fail_closed_reason, "RuntimeError")
        self.assertEqual(publisher.calls, [])

        self.database.close()
        persistence_failure = asyncio.run(self.boundary(publisher).process(candidate()))
        self.database = Database(":memory:")
        self.repository = SQLiteQualityGateEvaluationRepository(self.database)
        self.assertFalse(persistence_failure.publication_attempted)
        self.assertIsNotNone(persistence_failure.fail_closed_reason)
        self.assertEqual(publisher.calls, [])

    def test_downstream_retry_and_claim_ownership_are_unchanged(self):
        publisher = FakePublisher(fail_first=True)
        boundary = self.boundary(publisher)

        with self.assertRaises(RuntimeError):
            asyncio.run(boundary.process(candidate()))
        second = asyncio.run(boundary.process(candidate()))

        self.assertTrue(second.publication_attempted)
        self.assertEqual(len(publisher.calls), 2)
        count = self.database.connection.execute(
            "SELECT COUNT(*) FROM official_quality_gate_evaluations"
        ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
