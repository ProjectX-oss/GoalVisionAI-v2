import shutil
from pathlib import Path
import unittest
from uuid import uuid4

from app.database import Database
from app.model_activation import (
    ActivationRequest,
    ModelActivationPolicy,
    SQLiteModelActivationRepository,
)
from app.model_activation.evidence import build_activation_evidence
from app.model_activation.validation import evaluate_evidence
from app.model_operations_rehearsal import (
    RehearsalSafetyError,
    create_rehearsal_database_copies,
    resolve_database_source,
    seed_lab_fixture,
)
from app.shadow_evaluation import SQLiteShadowEvaluationRepository


class ModelOperationsRehearsalSafetyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("var") / "test_model_operations_rehearsal" / uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_source_resolution_rejects_missing_and_ambiguous_candidates(self):
        with self.assertRaises(RehearsalSafetyError):
            resolve_database_source(explicit=None, discovered=())
        first = self.root / "first.db"
        second = self.root / "second.db"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        with self.assertRaises(RehearsalSafetyError):
            resolve_database_source(
                explicit=None,
                discovered=(first, second),
            )

    def test_copy_is_byte_identical_and_never_overwrites(self):
        source = self.root / "source.db"
        source.write_bytes(b"goalvision-rehearsal-source")
        copies = create_rehearsal_database_copies(
            source,
            self.root / "copies",
            timestamp="20260724T230000Z",
        )
        self.assertEqual(
            copies.source_fingerprint,
            copies.backup_fingerprint,
        )
        self.assertEqual(
            copies.source_fingerprint,
            copies.rehearsal_fingerprint,
        )
        self.assertEqual(source.read_bytes(), b"goalvision-rehearsal-source")
        with self.assertRaises(RehearsalSafetyError):
            create_rehearsal_database_copies(
                source,
                self.root / "copies",
                timestamp="20260724T230000Z",
            )


class ModelOperationsRehearsalFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = Database(":memory:")
        cls.manifest = seed_lab_fixture(cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def test_fixture_is_labeled_complete_and_policy_eligible(self):
        self.assertEqual(
            self.manifest.label,
            "FICTIONAL_LAB_REHEARSAL_ONLY",
        )
        request = ActivationRequest(
            activation_request_id="test-evidence",
            activation_name=self.manifest.label,
            model_scope=self.manifest.model_scope,
            current_champion_generation_id="pending",
            current_champion_generation_fingerprint="pending",
            current_champion=self.manifest.champion,
            challenger=self.manifest.challenger,
            comparison_run_id=self.manifest.comparison_run_id,
            comparison_run_fingerprint=self.manifest.comparison_run_fingerprint,
            challenger_candidate_id=self.manifest.challenger_candidate_id,
            recommendation_id=self.manifest.recommendation_id,
            recommendation_fingerprint=self.manifest.recommendation_fingerprint,
            evidence_cutoff_timestamp_utc=self.manifest.evidence_cutoff_timestamp_utc,
            requested_timestamp_utc=self.manifest.evidence_cutoff_timestamp_utc,
            activation_reason=self.manifest.label,
            operator_identity="test",
        )
        evidence = build_activation_evidence(
            request,
            SQLiteShadowEvaluationRepository(self.database, migrate=False),
        )
        validations = evaluate_evidence(evidence, ModelActivationPolicy())
        self.assertEqual(evidence.settled_count, 30)
        self.assertEqual(str(evidence.observation_days), "14.0")
        self.assertTrue(all(item.status.value == "PASS" for item in validations))

    def test_fixture_never_bootstraps_or_executes_model_operations(self):
        repository = SQLiteModelActivationRepository(
            self.database,
            migrate=False,
        )
        self.assertEqual(repository.list_generations("OFFICIAL_GLOBAL"), ())
        counts = {
            table: self.database.connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in (
                "model_activation_plans",
                "model_activation_executions",
                "model_rollback_plans",
                "model_rollback_executions",
            )
        }
        self.assertEqual(set(counts.values()), {0})

    def test_manifest_contains_fingerprints_not_database_paths(self):
        output = self.manifest.as_json()
        self.assertIn(self.manifest.shadow_evidence_fingerprint, output)
        self.assertNotIn(".db", output)


if __name__ == "__main__":
    unittest.main()
