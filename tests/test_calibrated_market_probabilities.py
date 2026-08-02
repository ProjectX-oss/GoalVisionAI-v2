import sqlite3
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from app.calibrated_market_probabilities import (
    DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY,
    CalibratedAssemblyStatus, CalibrationArtifact, CalibrationRegistry,
    CalibrationRegistryError, CalibrationTargetMapping,
    ExistingProbabilityCalibrationEngineFactory,
    SQLiteCalibratedMarketProbabilityRepository,
    build_calibrated_market_probability_service,
    generate_calibrated_market_probabilities,
    to_future_market_probability_input,
)
from app.database import Database
from app.database.migrations import MIGRATIONS, MigrationManager
from app.feature_store import SCHEMA_IDENTIFIER, build_feature_store_service, generate_match_feature_set
from app.match_data_snapshot import build_match_data_snapshot_service
from app.model_input_builder import build_model_input_builder, generate_model_input
from app.prediction_inference import (
    OFFICIAL_TARGET_ORDER, PredictionInferenceFingerprint,
    PredictionModelRegistry, SQLitePredictionInferenceRepository,
    build_prediction_inference_service, generate_raw_prediction,
)
from app.probability_calibration import (
    CalibrationMethod, ProbabilityCalibrationConfig,
    ProbabilityCalibrationEngine,
)
from tests.test_match_data_snapshot import EFFECTIVE, command
from tests.test_prediction_inference import ReferenceAdapter
from tests.test_probability_calibration_engine import config, request


class CountingFactory(ExistingProbabilityCalibrationEngineFactory):
    def __init__(self, *, fail_version: str | None = None, shift_version: str | None = None) -> None:
        self.calls = 0
        self.fail_version = fail_version
        self.shift_version = shift_version

    def build(self, config):
        base = super().build(config)
        parent = self

        class Engine:
            def calibrate(self, request):
                parent.calls += 1
                if config.calibration_version == parent.fail_version:
                    raise ValueError("declared calibration failure")
                report = base.calibrate(request)
                if config.calibration_version == parent.shift_version:
                    calibrated = report.calibrated_probability + Decimal("0.010000")
                    return replace(report, calibrated_probability=calibrated, delta=calibrated-report.raw_probability)
                return report
        return Engine()


class CalibratedMarketProbabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = Database(":memory:")
        snapshots = build_match_data_snapshot_service(self.database)
        registered = snapshots.register_match_data_snapshot(command())
        snapshot = snapshots.repository.find_snapshot_by_id(registered.snapshot_id)
        feature = generate_match_feature_set(
            build_feature_store_service(self.database), snapshot,
            schema_version=SCHEMA_IDENTIFIER, feature_timestamp=EFFECTIVE,
        ).feature_set
        vector = generate_model_input(build_model_input_builder(self.database), feature).model_input
        adapter = ReferenceAdapter()
        inference_policy = __import__("app.prediction_inference", fromlist=["DEFAULT_PREDICTION_INFERENCE_POLICY"]).DEFAULT_PREDICTION_INFERENCE_POLICY
        inference_repository = SQLitePredictionInferenceRepository(self.database)
        inference_service = build_prediction_inference_service(
            inference_repository,
            PredictionModelRegistry(inference_policy).register(adapter),
            inference_policy,
        )
        outcome = generate_raw_prediction(
            inference_service, vector, model_artifact_id=adapter.model_artifact_id,
            inference_timestamp=vector.created_timestamp + timedelta(minutes=1),
        )
        self.inference_repository = inference_repository
        self.inference = inference_repository.load_inference_by_id(outcome.inference_id)
        self.timestamp = self.inference.inference_timestamp + timedelta(minutes=1)
        self.policy = DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY
        self.registry = self._registry()
        self.mappings = tuple(CalibrationTargetMapping(target, f"identity-{target.value}") for target in OFFICIAL_TARGET_ORDER)
        self.registry = self.registry.define_set(
            calibration_set_id="official-calibration-set-v1", set_name="Official identity test set",
            set_version="1", source_model_artifact_id=self.inference.model_artifact_id,
            compatible_source_model_versions=(self.inference.model_version,), mappings=self.mappings,
            policy_version="probability-calibration-v1", active=True,
            created_timestamp=self.timestamp, effective_timestamp=self.timestamp,
        )
        self.repository = SQLiteCalibratedMarketProbabilityRepository(self.database)

    def tearDown(self) -> None:
        self.database.close()

    def _registry(self) -> CalibrationRegistry:
        registry = CalibrationRegistry(self.policy)
        for target in OFFICIAL_TARGET_ORDER:
            registry = registry.register_artifact(CalibrationArtifact(
                artifact_id=f"identity-{target.value}", target=target,
                method=CalibrationMethod.IDENTITY,
                calibration_model_version="identity-v1",
                source_model_artifact_id=self.inference.model_artifact_id,
                compatible_source_model_versions=(self.inference.model_version,),
                input_probability_schema=self.policy.input_probability_schema,
                input_probability_schema_version=self.policy.input_probability_schema_version,
                calibration_policy_version="probability-calibration-v1",
                config=ProbabilityCalibrationConfig(method=CalibrationMethod.IDENTITY),
                historical_data=(), active=True,
            ))
        return registry

    def _service(self, factory=None):
        return build_calibrated_market_probability_service(
            self.inference_repository, self.registry, self.repository,
            self.repository, factory or ExistingProbabilityCalibrationEngineFactory(), self.policy,
        )

    def test_registry_supports_explicit_identity_platt_and_isotonic_artifacts(self) -> None:
        registry = CalibrationRegistry(self.policy)
        for index, method in enumerate((CalibrationMethod.IDENTITY, CalibrationMethod.PLATT, CalibrationMethod.ISOTONIC)):
            registry = registry.register_artifact(CalibrationArtifact(
                f"artifact-{method.value}", OFFICIAL_TARGET_ORDER[index], method, "v1",
                self.inference.model_artifact_id, (self.inference.model_version,),
                self.policy.input_probability_schema, self.policy.input_probability_schema_version,
                "probability-calibration-v1", ProbabilityCalibrationConfig(method=method), (), False,
            ))
        self.assertEqual(tuple(x.method for x in registry.artifacts), (CalibrationMethod.IDENTITY, CalibrationMethod.PLATT, CalibrationMethod.ISOTONIC))
        with self.assertRaises(CalibrationRegistryError):
            registry.register_artifact(registry.artifacts[0])

    def test_existing_platt_and_isotonic_execution_results_are_propagatable(self) -> None:
        factory = ExistingProbabilityCalibrationEngineFactory()
        for method in (CalibrationMethod.PLATT, CalibrationMethod.ISOTONIC):
            with self.subTest(method=method):
                report = factory.build(config(method)).calibrate(
                    request(run_id=f"assembly-{method.value}")
                )
                self.assertEqual(report.calibration_method, method)
                self.assertTrue(Decimal("0.001") <= report.calibrated_probability <= Decimal("0.999"))

    def test_registry_rejects_conflicting_active_mapping_and_method_metadata(self) -> None:
        artifact = self.registry.artifacts[0]
        with self.assertRaises(CalibrationRegistryError):
            self.registry.register_artifact(replace(artifact, artifact_id="conflict"))
        with self.assertRaises(CalibrationRegistryError):
            CalibrationRegistry(self.policy).register_artifact(
                replace(artifact, artifact_id="bad-method", method=CalibrationMethod.PLATT)
            )

    def test_set_and_explicit_resolution_are_deterministic_and_unambiguous(self) -> None:
        set_plan = self.registry.resolve(self.inference, calibration_set_id="official-calibration-set-v1", explicit_map=None)
        explicit = self.registry.resolve(self.inference, calibration_set_id=None, explicit_map=self.mappings)
        self.assertEqual(tuple(x.target for x in set_plan.ordered_artifacts), OFFICIAL_TARGET_ORDER)
        self.assertNotEqual(set_plan.calibration_set_fingerprint, explicit.calibration_set_fingerprint)
        self.assertEqual(set_plan.calibration_set_fingerprint, self.registry.resolve(self.inference, calibration_set_id="official-calibration-set-v1", explicit_map=None).calibration_set_fingerprint)
        with self.assertRaises(Exception):
            self.registry.resolve(self.inference, calibration_set_id="official-calibration-set-v1", explicit_map=self.mappings)
        with self.assertRaises(Exception):
            self.registry.resolve(self.inference, calibration_set_id=None, explicit_map=self.mappings[:-1])

    def test_identity_assembly_preserves_raw_values_and_calibrates_each_target_once(self) -> None:
        factory = CountingFactory()
        outcome = generate_calibrated_market_probabilities(
            self._service(factory), self.inference,
            calibration_set_id="official-calibration-set-v1",
            calibration_effective_timestamp=self.timestamp,
        )
        self.assertEqual(outcome.final_status, CalibratedAssemblyStatus.GENERATED)
        self.assertEqual(factory.calls, 11)
        self.assertEqual(tuple(x.target for x in outcome.ordered_calibrated_target_results), OFFICIAL_TARGET_ORDER)
        for item in outcome.ordered_calibrated_target_results:
            self.assertEqual(item.raw_probability, item.calibrated_probability)
            self.assertEqual(item.calibration_method, CalibrationMethod.IDENTITY)

    def test_explicit_map_generation_and_idempotency(self) -> None:
        service = self._service()
        first = generate_calibrated_market_probabilities(service, self.inference, explicit_calibration_map=self.mappings, calibration_effective_timestamp=self.timestamp)
        second = generate_calibrated_market_probabilities(service, self.inference, explicit_calibration_map=self.mappings, calibration_effective_timestamp=self.timestamp)
        self.assertEqual(first.final_status, CalibratedAssemblyStatus.GENERATED)
        self.assertEqual(second.final_status, CalibratedAssemblyStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(first.calibrated_assembly_fingerprint, second.calibrated_assembly_fingerprint)

    def test_missing_inference_fingerprint_and_timestamp_fail_before_execution(self) -> None:
        cases = (
            (None, self.timestamp, "RAW_INFERENCE_REQUIRED"),
            (replace(self.inference, inference_fingerprint="0"*64), self.timestamp, "RAW_INFERENCE_NOT_PERSISTED"),
            (self.inference, self.inference.inference_timestamp-timedelta(seconds=1), "CALIBRATION_BEFORE_INFERENCE"),
        )
        for inference, timestamp, code in cases:
            factory = CountingFactory()
            outcome = generate_calibrated_market_probabilities(self._service(factory), inference, calibration_set_id="official-calibration-set-v1", calibration_effective_timestamp=timestamp)
            self.assertEqual(outcome.final_status, CalibratedAssemblyStatus.REJECTED_INVALID_INFERENCE)
            self.assertEqual(outcome.ordered_reason_codes, (code,))
            self.assertEqual(factory.calls, 0)

    def test_incomplete_and_incompatible_configuration_fail_before_execution(self) -> None:
        factory = CountingFactory()
        incomplete = generate_calibrated_market_probabilities(self._service(factory), self.inference, explicit_calibration_map=self.mappings[:-1], calibration_effective_timestamp=self.timestamp)
        self.assertEqual(incomplete.final_status, CalibratedAssemblyStatus.REJECTED_INCOMPLETE_CALIBRATION_SET)
        self.assertEqual(factory.calls, 0)
        bad_registry = CalibrationRegistry(self.policy)
        bad_artifact = replace(self.registry.artifacts[0], source_model_artifact_id="other", active=False)
        bad_registry = bad_registry.register_artifact(bad_artifact)
        self.assertEqual(bad_registry.artifacts[0].source_model_artifact_id, "other")

    def test_one_calibration_failure_has_no_partial_assembly(self) -> None:
        failing_version = self.registry.artifacts[5].config.calibration_version
        # Give the selected target a unique execution version.
        artifacts = list(self.registry.artifacts)
        artifacts[5] = replace(artifacts[5], config=replace(artifacts[5].config, calibration_version="fail-this-target"), calibration_model_version="fail-this-target")
        registry = CalibrationRegistry(self.policy, tuple(artifacts), self.registry.calibration_sets)
        service = build_calibrated_market_probability_service(self.inference_repository, registry, self.repository, self.repository, CountingFactory(fail_version="fail-this-target"), self.policy)
        outcome = generate_calibrated_market_probabilities(service, self.inference, calibration_set_id="official-calibration-set-v1", calibration_effective_timestamp=self.timestamp)
        self.assertEqual(outcome.final_status, CalibratedAssemblyStatus.CALIBRATION_EXECUTION_FAILED)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM calibrated_market_probability_assemblies").fetchone()[0], 0)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM calibrated_market_probability_targets").fetchone()[0], 0)

    def test_invalid_combined_output_is_not_normalized_or_persisted(self) -> None:
        version = self.registry.artifacts[0].config.calibration_version
        artifacts = list(self.registry.artifacts)
        artifacts[0] = replace(artifacts[0], config=replace(artifacts[0].config, calibration_version="shift-home"))
        registry = CalibrationRegistry(self.policy, tuple(artifacts), self.registry.calibration_sets)
        factory = CountingFactory(shift_version="shift-home")
        service = build_calibrated_market_probability_service(self.inference_repository, registry, self.repository, self.repository, factory, self.policy)
        outcome = generate_calibrated_market_probabilities(service, self.inference, calibration_set_id="official-calibration-set-v1", calibration_effective_timestamp=self.timestamp)
        self.assertEqual(outcome.final_status, CalibratedAssemblyStatus.REJECTED_INVALID_CALIBRATED_OUTPUT)
        self.assertEqual(outcome.ordered_reason_codes, ("MATCH_RESULT_SUM",))
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM calibrated_market_probability_assemblies").fetchone()[0], 0)

    def test_persistence_queries_atomic_rows_and_append_only_triggers(self) -> None:
        outcome = generate_calibrated_market_probabilities(self._service(), self.inference, calibration_set_id="official-calibration-set-v1", calibration_effective_timestamp=self.timestamp)
        assembly = self.repository.load_assembly_by_id(outcome.calibrated_assembly_id)
        self.assertEqual(len(assembly.ordered_target_results), 11)
        self.assertEqual(self.repository.find_by_assembly_fingerprint(outcome.calibrated_assembly_fingerprint), assembly)
        self.assertEqual(len(self.repository.list_assemblies_for_inference(self.inference.inference_id)), 1)
        self.assertEqual(self.repository.find_latest_for_match_and_model(self.inference.match_id, self.inference.model_artifact_id), assembly)
        for table in ("probability_calibration_sets", "calibrated_market_probability_assemblies", "calibrated_market_probability_targets"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(f"UPDATE {table} SET created_timestamp='changed'")
            self.database.connection.rollback()

    def test_downstream_mapping_preserves_probability_and_provenance_only(self) -> None:
        outcome = generate_calibrated_market_probabilities(self._service(), self.inference, calibration_set_id="official-calibration-set-v1", calibration_effective_timestamp=self.timestamp)
        assembly = self.repository.load_assembly_by_id(outcome.calibrated_assembly_id)
        mapped = to_future_market_probability_input(assembly)
        self.assertEqual(mapped.ordered_targets, assembly.ordered_target_results)
        self.assertEqual(mapped.raw_inference_fingerprint, self.inference.inference_fingerprint)
        self.assertFalse(hasattr(mapped, "odds"))
        self.assertFalse(hasattr(mapped, "expected_value"))

    def test_fingerprint_changes_with_set_policy_timestamp_and_output(self) -> None:
        first = generate_calibrated_market_probabilities(self._service(), self.inference, explicit_calibration_map=self.mappings, calibration_effective_timestamp=self.timestamp)
        later = generate_calibrated_market_probabilities(self._service(), self.inference, explicit_calibration_map=self.mappings, calibration_effective_timestamp=self.timestamp+timedelta(seconds=1))
        changed_policy = replace(self.policy, version="calibrated-market-probability-policy-v2")
        registry = CalibrationRegistry(changed_policy, self.registry.artifacts, self.registry.calibration_sets)
        service = build_calibrated_market_probability_service(self.inference_repository, registry, self.repository, self.repository, ExistingProbabilityCalibrationEngineFactory(), changed_policy)
        policy_result = generate_calibrated_market_probabilities(service, self.inference, explicit_calibration_map=self.mappings, calibration_effective_timestamp=self.timestamp)
        self.assertEqual(len({first.calibrated_assembly_fingerprint, later.calibrated_assembly_fingerprint, policy_result.calibrated_assembly_fingerprint}), 3)


class CalibratedMarketProbabilityMigrationTests(unittest.TestCase):
    def test_fresh_v18_and_v17_upgrade(self) -> None:
        fresh = Database(":memory:")
        MigrationManager(fresh.connection).migrate()
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 41)
        fresh.close()
        upgrade = Database(":memory:")
        upgrade.connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS:
            if migration.version > 17:
                continue
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute("INSERT INTO schema_migrations VALUES (?, 'existing')", (migration.version,))
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 41)
        tables = {x[0] for x in upgrade.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"probability_calibration_sets", "calibrated_market_probability_assemblies", "calibrated_market_probability_targets"} <= tables)
        upgrade.close()


if __name__ == "__main__":
    unittest.main()
