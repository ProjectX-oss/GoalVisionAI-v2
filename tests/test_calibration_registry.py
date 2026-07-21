import json
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.calibration import (
    CalibrationFitRequest,
    CalibrationFittingPolicy,
    CalibrationObservation,
    CalibrationScope,
    CalibrationTrainingWindow,
    CalibratorSerializer,
    PlattCalibrator,
)
from app.calibration_registry import (
    CalibrationArtifactConflictError,
    CalibrationArtifactStatus,
    CalibrationRegistryQuery,
    CalibrationRegistryService,
    InvalidCalibrationStatusTransition,
)
from app.database import Database
from app.model_monitoring import CalibrationArtifactComparisonService


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def fitted(version: str = "platt-test-v1", fitted_at: datetime = BASE + timedelta(days=3)):
    observations = (
        CalibrationObservation(
            "one", 1, "League", "MATCH_WINNER", "home",
            BASE, BASE + timedelta(days=1), Decimal("0.7"), 1, "model-v1",
        ),
        CalibrationObservation(
            "two", 2, "League", "MATCH_WINNER", "away",
            BASE + timedelta(hours=1), BASE + timedelta(days=1, hours=1),
            Decimal("0.3"), 0, "model-v1",
        ),
    )
    trainer = PlattCalibrator(
        policy=CalibrationFittingPolicy(
            global_minimum=2,
            market_minimum=2,
            competition_minimum=2,
            competition_market_minimum=2,
            odds_band_minimum=2,
            minimum_positive=1,
            minimum_negative=1,
        )
    )
    return trainer.fit(
        observations,
        CalibrationFitRequest(
            fitted_at=fitted_at,
            training_window=CalibrationTrainingWindow(
                BASE, BASE + timedelta(days=2)
            ),
            scope=CalibrationScope.global_scope(),
            version=version,
            model_version="model-v1",
        ),
    )


class CalibrationRegistryTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("tests") / f".calibration-registry-{uuid4().hex}.db"
        self.database = Database(self.path)
        self.registry = CalibrationRegistryService(self.database)
        self.artifact = self.registry.artifact_from_calibrator(
            fitted(), created_at=BASE + timedelta(days=4),
            status_reason="New offline calibration candidate.",
        )

    def tearDown(self):
        self.database.close()
        for suffix in ("", "-journal", "-shm", "-wal"):
            path = Path(f"{self.path}{suffix}")
            if path.exists():
                path.unlink()

    def test_valid_registration_and_safe_deserialization(self):
        result = self.registry.register(self.artifact)
        self.assertTrue(result.inserted)
        restored = self.registry.deserialize(self.artifact.artifact_id)
        self.assertEqual(
            restored.calibrate(Decimal("0.4")),
            fitted().calibrate(Decimal("0.4")),
        )

    def test_duplicate_registration_is_idempotent(self):
        first = self.registry.register(self.artifact)
        second = self.registry.register(self.artifact)
        self.assertTrue(first.inserted)
        self.assertFalse(second.inserted)
        self.assertEqual(first.artifact, second.artifact)

    def test_equivalent_artifact_with_different_id_is_rejected(self):
        self.registry.register(self.artifact)
        conflict = replace(
            self.artifact,
            identity=replace(self.artifact.identity, artifact_id="different-id"),
        )
        with self.assertRaises(CalibrationArtifactConflictError):
            self.registry.register(conflict)

    def test_artifact_fitted_data_is_database_immutable(self):
        self.registry.register(self.artifact)
        with self.assertRaises(sqlite3.DatabaseError):
            self.database.connection.execute(
                "UPDATE calibration_artifacts SET method = 'isotonic'"
            )

    def test_malformed_artifact_is_rejected(self):
        malformed = replace(self.artifact, serialized_calibrator="{bad")
        with self.assertRaises(CalibrationArtifactConflictError):
            self.registry.register(malformed)

    def test_unknown_serialization_version_is_rejected(self):
        payload = json.loads(self.artifact.serialized_calibrator)
        payload["serialization_version"] = "future-version"
        malformed = replace(
            self.artifact,
            serialized_calibrator=json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ),
        )
        validation = self.registry.validate_serialized_artifact(malformed)
        self.assertFalse(validation.valid)
        self.assertIn("Unknown", validation.safe_message)

    def test_latest_is_fitted_cutoff_and_artifact_id_order_not_best(self):
        first = self.artifact
        second_calibrator = fitted("platt-test-v2", BASE + timedelta(days=5))
        second = self.registry.artifact_from_calibrator(
            second_calibrator,
            created_at=BASE + timedelta(days=6),
            status_reason="Second candidate.",
        )
        self.registry.register(second)
        self.registry.register(first)
        self.assertEqual(
            self.registry.latest(CalibrationRegistryQuery(method="platt")),
            second,
        )

    def test_valid_status_transition_history_and_status_query(self):
        self.registry.register(self.artifact)
        transition = self.registry.transition_status(
            self.artifact.artifact_id,
            CalibrationArtifactStatus.VALIDATED,
            reason="Offline validation passed.",
            changed_at=BASE + timedelta(days=5),
            actor_source="unit-test",
        )
        self.assertEqual(transition.previous_status, CalibrationArtifactStatus.CANDIDATE)
        self.assertEqual(self.registry.status_history(self.artifact.artifact_id), (transition,))
        matches = self.registry.query(
            CalibrationRegistryQuery(status=CalibrationArtifactStatus.VALIDATED)
        )
        self.assertEqual(matches[0].status, CalibrationArtifactStatus.VALIDATED)
        self.assertEqual(matches[0].artifact_id, self.artifact.artifact_id)

    def test_all_supported_status_paths(self):
        allowed = (
            (CalibrationArtifactStatus.CANDIDATE, CalibrationArtifactStatus.VALIDATED),
            (CalibrationArtifactStatus.CANDIDATE, CalibrationArtifactStatus.REJECTED),
            (CalibrationArtifactStatus.CANDIDATE, CalibrationArtifactStatus.RETIRED),
        )
        self.assertEqual(len(allowed), 3)
        self.registry.register(self.artifact)
        self.registry.transition_status(
            self.artifact.artifact_id,
            CalibrationArtifactStatus.VALIDATED,
            reason="Validated", changed_at=BASE + timedelta(days=5),
            actor_source="test",
        )
        self.registry.transition_status(
            self.artifact.artifact_id,
            CalibrationArtifactStatus.SHADOW,
            reason="Shadow", changed_at=BASE + timedelta(days=6),
            actor_source="test",
        )
        self.registry.transition_status(
            self.artifact.artifact_id,
            CalibrationArtifactStatus.RETIRED,
            reason="Retired", changed_at=BASE + timedelta(days=7),
            actor_source="test",
        )
        self.assertEqual(
            self.registry.current_status(self.artifact.artifact_id),
            CalibrationArtifactStatus.RETIRED,
        )

    def test_invalid_transition_is_rejected(self):
        self.registry.register(self.artifact)
        with self.assertRaises(InvalidCalibrationStatusTransition):
            self.registry.transition_status(
                self.artifact.artifact_id,
                CalibrationArtifactStatus.SHADOW,
                reason="Skipped validation",
                changed_at=BASE + timedelta(days=5),
                actor_source="test",
            )

    def test_restart_persistence(self):
        self.registry.register(self.artifact)
        self.database.close()
        self.database = Database(self.path)
        restarted = CalibrationRegistryService(self.database)
        self.assertEqual(restarted.get(self.artifact.artifact_id), self.artifact)

    def test_migration_v8_schema_indexes_decimal_text_and_compatibility(self):
        tables = {
            row[0]
            for row in self.database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertTrue(
            {
                "calibration_artifacts",
                "calibration_artifact_status_history",
                "model_monitoring_runs",
                "model_monitoring_alerts",
            }.issubset(tables)
        )
        versions = tuple(
            row[0]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 15)))
        self.registry.register(self.artifact)
        stored = self.database.connection.execute(
            "SELECT training_metrics FROM calibration_artifacts"
        ).fetchone()[0]
        self.assertIn('"brier_score":"', stored)

    def test_artifact_comparison_is_deterministic_and_does_not_change_status(self):
        first = self.artifact
        second = self.registry.artifact_from_calibrator(
            fitted("platt-test-v2", BASE + timedelta(days=5)),
            created_at=BASE + timedelta(days=6),
            status_reason="Second candidate.",
        )
        self.registry.register(first)
        self.registry.register(second)
        validation = (
            CalibrationObservation(
                "validation-1", 10, "League", "MATCH_WINNER", "home",
                BASE + timedelta(days=10), BASE + timedelta(days=11),
                Decimal("0.8"), 1, "model-v1",
            ),
            CalibrationObservation(
                "validation-2", 11, "League", "MATCH_WINNER", "away",
                BASE + timedelta(days=10, hours=1),
                BASE + timedelta(days=11, hours=1),
                Decimal("0.2"), 0, "model-v1",
            ),
        )
        report = CalibrationArtifactComparisonService().compare(
            (second, first), validation
        )
        self.assertEqual(len(report.results), 2)
        self.assertEqual(
            tuple(item.ranking for item in report.results),
            (1, 2),
        )
        self.assertEqual(
            self.registry.current_status(first.artifact_id),
            CalibrationArtifactStatus.CANDIDATE,
        )


if __name__ == "__main__":
    unittest.main()
