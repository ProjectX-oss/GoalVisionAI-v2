import sqlite3
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from app.database import Database
from app.database.migrations import MIGRATIONS, MigrationManager
from app.feature_store import SCHEMA_IDENTIFIER, build_feature_store_service, generate_match_feature_set
from app.match_data_snapshot import build_match_data_snapshot_service
from app.model_input_builder import build_model_input_builder, generate_model_input
from app.prediction_inference import (
    DEFAULT_PREDICTION_INFERENCE_POLICY,
    OFFICIAL_TARGET_ORDER,
    InferenceConflictError,
    InferenceGenerationStatus,
    InferencePersistenceError,
    InvalidModelOutputError,
    MissingValueSupport,
    ModelAdapterCompatibilityError,
    ModelAdapterExecutionError,
    ModelAdapterOutput,
    ModelRegistryError,
    PredictionModelRegistry,
    PredictionTarget,
    RawProbabilityValidator,
    SQLitePredictionInferenceRepository,
    build_prediction_inference_service,
    generate_raw_prediction,
    to_calibration_input,
)
from tests.test_match_data_snapshot import EFFECTIVE, command


VALID_VALUES = {
    PredictionTarget.HOME_WIN: Decimal("0.450000"),
    PredictionTarget.DRAW: Decimal("0.250000"),
    PredictionTarget.AWAY_WIN: Decimal("0.300000"),
    PredictionTarget.OVER_1_5: Decimal("0.800000"),
    PredictionTarget.UNDER_1_5: Decimal("0.200000"),
    PredictionTarget.OVER_2_5: Decimal("0.550000"),
    PredictionTarget.UNDER_2_5: Decimal("0.450000"),
    PredictionTarget.OVER_3_5: Decimal("0.300000"),
    PredictionTarget.UNDER_3_5: Decimal("0.700000"),
    PredictionTarget.BTTS_YES: Decimal("0.580000"),
    PredictionTarget.BTTS_NO: Decimal("0.420000"),
}


class ReferenceAdapter:
    """Deterministic test double; it is not a production football model."""

    def __init__(
        self,
        *,
        artifact_id: str = "reference-artifact-v1",
        version: str = "1.0.0",
        values: dict[PredictionTarget, Decimal] | None = None,
        targets: tuple[PredictionTarget, ...] = OFFICIAL_TARGET_ORDER,
        missing_support: MissingValueSupport = MissingValueSupport.OPTIONAL_FEATURES,
    ) -> None:
        self.model_artifact_id = artifact_id
        self.model_name = "reference-deterministic-test-model"
        self.model_version = version
        self.model_family = "test-only"
        self.input_schema_name = "goalvision_model_input"
        self.input_schema_version = "v1"
        self.compatibility_version = "official_prediction_model_input_v1"
        self.supported_targets = targets
        self.missing_value_support = missing_support
        self.values = dict(values or VALID_VALUES)
        self.infer_calls = 0
        self.compatibility_error: Exception | None = None
        self.execution_error: Exception | None = None
        self.custom_outputs: tuple[ModelAdapterOutput, ...] | None = None

    def validate_compatibility(self, model_input: object) -> None:
        if self.compatibility_error is not None:
            raise self.compatibility_error

    def infer(self, model_input: object) -> tuple[ModelAdapterOutput, ...]:
        self.infer_calls += 1
        if self.execution_error is not None:
            raise self.execution_error
        if self.custom_outputs is not None:
            return self.custom_outputs
        return tuple(ModelAdapterOutput(target, self.values[target]) for target in self.supported_targets)


class FailingRepository:
    def __init__(self, delegate: SQLitePredictionInferenceRepository, *, conflict: bool) -> None:
        self.delegate = delegate
        self.conflict = conflict

    def load_model_input_identity(self, model_input_id: str):
        return self.delegate.load_model_input_identity(model_input_id)

    def find_by_inference_fingerprint(self, fingerprint: str):
        if self.conflict:
            return None
        raise InferencePersistenceError("deliberate test failure")

    def append_inference_result(self, result: object):
        raise InferenceConflictError("deliberate test conflict")


class PredictionInferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = Database(":memory:")
        snapshots = build_match_data_snapshot_service(self.database)
        registration = snapshots.register_match_data_snapshot(command())
        snapshot = snapshots.repository.find_snapshot_by_id(registration.snapshot_id)
        feature_service = build_feature_store_service(self.database)
        feature_outcome = generate_match_feature_set(
            feature_service,
            snapshot,
            schema_version=SCHEMA_IDENTIFIER,
            feature_timestamp=EFFECTIVE,
        )
        builder = build_model_input_builder(self.database)
        self.model_input = generate_model_input(builder, feature_outcome.feature_set).model_input
        self.timestamp = self.model_input.created_timestamp + timedelta(minutes=1)
        self.adapter = ReferenceAdapter()
        self.policy = DEFAULT_PREDICTION_INFERENCE_POLICY
        self.registry = PredictionModelRegistry(self.policy).register(self.adapter, active_official=True)
        self.repository = SQLitePredictionInferenceRepository(self.database)
        self.service = build_prediction_inference_service(self.repository, self.registry, self.policy)

    def tearDown(self) -> None:
        self.database.close()

    def generate(self, model_input=None, artifact_id="reference-artifact-v1", timestamp=None):
        return generate_raw_prediction(
            self.service,
            self.model_input if model_input is None else model_input,
            model_artifact_id=artifact_id,
            inference_timestamp=timestamp or self.timestamp,
        )

    def test_registry_is_immutable_and_selects_only_explicit_or_configured_model(self) -> None:
        empty = PredictionModelRegistry(self.policy)
        registered = empty.register(self.adapter)
        self.assertEqual(empty.registered_models, ())
        self.assertIs(registered.select(self.adapter.model_artifact_id).adapter, self.adapter)
        with self.assertRaises(ModelRegistryError):
            registered.select()
        active = registered.with_active_official(self.adapter.model_artifact_id)
        self.assertIs(active.select().adapter, self.adapter)
        inactive = ReferenceAdapter(artifact_id="inactive", version="2.0.0")
        both = active.register(inactive)
        self.assertIs(both.select().adapter, self.adapter)
        self.assertEqual(len(both.registered_models), 2)

    def test_registry_rejects_duplicate_identity_schema_and_incomplete_targets(self) -> None:
        registered = PredictionModelRegistry(self.policy).register(self.adapter)
        with self.assertRaises(ModelRegistryError):
            registered.register(ReferenceAdapter())
        duplicate_name = ReferenceAdapter(artifact_id="different-artifact")
        with self.assertRaises(ModelRegistryError):
            registered.register(duplicate_name)
        unsupported = ReferenceAdapter(artifact_id="unsupported", version="2")
        unsupported.input_schema_name = "unknown"
        with self.assertRaises(ModelRegistryError):
            PredictionModelRegistry(self.policy).register(unsupported)
        incomplete = ReferenceAdapter(artifact_id="incomplete", version="3", targets=OFFICIAL_TARGET_ORDER[:-1])
        with self.assertRaises(ModelRegistryError):
            PredictionModelRegistry(self.policy).register(incomplete)

    def test_success_is_deterministic_ordered_and_adapter_called_once(self) -> None:
        result = self.generate()
        self.assertEqual(result.final_status, InferenceGenerationStatus.GENERATED)
        self.assertEqual(self.adapter.infer_calls, 1)
        self.assertEqual(
            tuple(item.target for item in result.raw_probability_set.ordered_probabilities),
            OFFICIAL_TARGET_ORDER,
        )
        self.assertEqual(result.inference_timestamp, self.timestamp)
        stored = self.repository.load_inference_by_id(result.inference_id)
        self.assertEqual(stored.raw_probabilities, result.raw_probability_set)
        self.assertEqual(stored.inference_fingerprint, result.inference_fingerprint)

    def test_identical_inference_is_idempotent(self) -> None:
        first = self.generate()
        second = self.generate()
        self.assertEqual(second.final_status, InferenceGenerationStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(first.inference_id, second.inference_id)
        self.assertEqual(first.inference_fingerprint, second.inference_fingerprint)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM prediction_inference_results").fetchone()[0], 1)

    def test_input_validation_prevents_adapter_execution(self) -> None:
        cases = (
            (None, "MODEL_INPUT_REQUIRED"),
            (replace(self.model_input, model_input_fingerprint="0" * 64), "PERSISTED_FINGERPRINT_MISMATCH"),
            (replace(self.model_input, schema_name="unknown"), "UNSUPPORTED_INPUT_SCHEMA"),
            (replace(self.model_input, compatibility_version="v2"), "UNSUPPORTED_COMPATIBILITY_VERSION"),
            (replace(self.model_input, ordered_feature_names=tuple(reversed(self.model_input.ordered_feature_names))), "INVALID_FEATURE_ORDER"),
        )
        for value, reason in cases:
            with self.subTest(reason=reason):
                before = self.adapter.infer_calls
                outcome = generate_raw_prediction(self.service, value, model_artifact_id=self.adapter.model_artifact_id, inference_timestamp=self.timestamp)
                self.assertEqual(outcome.final_status, InferenceGenerationStatus.REJECTED_INVALID_INPUT)
                self.assertEqual(outcome.ordered_reason_codes, (reason,))
                self.assertEqual(self.adapter.infer_calls, before)

    def test_required_missing_timestamp_and_unknown_artifact_rejections(self) -> None:
        names = self.model_input.ordered_feature_names
        required = next(name for name in self.policy.required_feature_names)
        index = names.index(required)
        values = list(self.model_input.ordered_feature_values)
        mask = list(self.model_input.missingness_mask)
        values[index] = None
        mask[index] = True
        changed = replace(
            self.model_input,
            ordered_feature_values=tuple(values),
            missingness_mask=tuple(mask),
            missing_feature_names=(required,),
        )
        missing = self.generate(changed)
        self.assertEqual(missing.ordered_reason_codes, ("REQUIRED_BASELINE_FEATURE_MISSING",))
        early = self.generate(timestamp=self.model_input.created_timestamp - timedelta(seconds=1))
        self.assertEqual(early.ordered_reason_codes, ("INFERENCE_TIMESTAMP_BEFORE_INPUT",))
        unknown = self.generate(artifact_id="unknown")
        self.assertEqual(unknown.final_status, InferenceGenerationStatus.REJECTED_INCOMPATIBLE_MODEL)
        self.assertEqual(unknown.ordered_reason_codes, ("UNKNOWN_MODEL_ARTIFACT",))

    def test_adapter_metadata_and_missingness_support_rejections(self) -> None:
        self.adapter.model_version = "mutated"
        metadata = self.generate()
        self.assertEqual(metadata.ordered_reason_codes, ("MODEL_ADAPTER_METADATA_CONFLICT",))
        self.assertEqual(self.adapter.infer_calls, 0)
        self.adapter.model_version = "1.0.0"

        snapshots = build_match_data_snapshot_service(self.database)
        registration = snapshots.register_match_data_snapshot(command(
            match_id="optional-missing", source_event_id="optional-missing", source_snapshot_id="optional-missing",
            home_venue_split=None, away_venue_split=None, home_season_aggregate=None,
            away_season_aggregate=None, head_to_head=None, home_availability=None,
            away_availability=None, context=None, odds_snapshot=None,
        ))
        snapshot = snapshots.repository.find_snapshot_by_id(registration.snapshot_id)
        feature = generate_match_feature_set(build_feature_store_service(self.database), snapshot, schema_version=SCHEMA_IDENTIFIER, feature_timestamp=EFFECTIVE).feature_set
        partial = generate_model_input(build_model_input_builder(self.database), feature).model_input
        no_missing = ReferenceAdapter(artifact_id="no-missing", version="2", missing_support=MissingValueSupport.NONE)
        registry = PredictionModelRegistry(self.policy).register(no_missing)
        service = build_prediction_inference_service(self.repository, registry, self.policy)
        outcome = generate_raw_prediction(service, partial, model_artifact_id="no-missing", inference_timestamp=partial.created_timestamp + timedelta(minutes=1))
        self.assertEqual(outcome.ordered_reason_codes, ("MODEL_MISSINGNESS_UNSUPPORTED",))
        self.assertEqual(no_missing.infer_calls, 0)

    def test_adapter_declared_failures_and_programmer_defects(self) -> None:
        self.adapter.compatibility_error = ModelAdapterCompatibilityError("incompatible")
        incompatible = self.generate()
        self.assertEqual(incompatible.final_status, InferenceGenerationStatus.REJECTED_INCOMPATIBLE_MODEL)
        self.assertEqual(self.adapter.infer_calls, 0)
        self.adapter.compatibility_error = None
        self.adapter.execution_error = ModelAdapterExecutionError("declared failure")
        outcome = self.generate()
        self.assertEqual(outcome.final_status, InferenceGenerationStatus.MODEL_EXECUTION_FAILED)
        self.adapter.execution_error = None
        self.adapter.custom_outputs = (
            ModelAdapterOutput(PredictionTarget.HOME_WIN, Decimal("0.45")),
        )
        malformed = self.generate()
        self.assertEqual(malformed.final_status, InferenceGenerationStatus.REJECTED_INVALID_OUTPUT)
        self.assertEqual(malformed.ordered_reason_codes, ("MISSING_TARGET",))
        self.adapter.custom_outputs = None
        self.adapter.execution_error = RuntimeError("programmer defect")
        with self.assertRaises(RuntimeError):
            self.generate()

    def test_persistence_and_conflict_outcomes_and_exact_status_contract(self) -> None:
        expected = {
            "GENERATED", "IDEMPOTENT_EXISTING", "REJECTED_INVALID_INPUT",
            "REJECTED_INCOMPATIBLE_MODEL", "REJECTED_INVALID_OUTPUT",
            "MODEL_EXECUTION_FAILED", "CONFLICT", "PERSISTENCE_FAILURE",
        }
        self.assertEqual({item.value for item in InferenceGenerationStatus}, expected)
        persistence_service = build_prediction_inference_service(
            FailingRepository(self.repository, conflict=False), self.registry, self.policy
        )
        persistence = generate_raw_prediction(
            persistence_service, self.model_input,
            model_artifact_id=self.adapter.model_artifact_id,
            inference_timestamp=self.timestamp,
        )
        self.assertEqual(persistence.final_status, InferenceGenerationStatus.PERSISTENCE_FAILURE)
        conflict_service = build_prediction_inference_service(
            FailingRepository(self.repository, conflict=True), self.registry, self.policy
        )
        conflict = generate_raw_prediction(
            conflict_service, self.model_input,
            model_artifact_id=self.adapter.model_artifact_id,
            inference_timestamp=self.timestamp,
        )
        self.assertEqual(conflict.final_status, InferenceGenerationStatus.CONFLICT)

    def test_output_validation_rejections_and_no_normalization(self) -> None:
        validator = RawProbabilityValidator()
        valid = tuple(ModelAdapterOutput(target, VALID_VALUES[target]) for target in OFFICIAL_TARGET_ORDER)
        invalid_cases = (
            (valid[:-1], "MISSING_TARGET"),
            (valid + (valid[0],), "DUPLICATE_TARGET"),
            ((ModelAdapterOutput("UNKNOWN", Decimal("0.1")),) + valid, "UNKNOWN_TARGET"),
            ((ModelAdapterOutput(PredictionTarget.HOME_WIN, 0.45),) + valid[1:], "MALFORMED_DECIMAL"),
            ((ModelAdapterOutput(PredictionTarget.HOME_WIN, Decimal("NaN")),) + valid[1:], "NON_FINITE_PROBABILITY"),
            ((ModelAdapterOutput(PredictionTarget.HOME_WIN, Decimal("Infinity")),) + valid[1:], "NON_FINITE_PROBABILITY"),
            ((ModelAdapterOutput(PredictionTarget.HOME_WIN, Decimal("-0.1")),) + valid[1:], "PROBABILITY_OUT_OF_RANGE"),
            ((ModelAdapterOutput(PredictionTarget.HOME_WIN, Decimal("1.1")),) + valid[1:], "PROBABILITY_OUT_OF_RANGE"),
        )
        for outputs, reason in invalid_cases:
            with self.subTest(reason=reason):
                with self.assertRaises(InvalidModelOutputError) as captured:
                    validator.validate(outputs, self.policy)
                self.assertEqual(captured.exception.reason_code, reason)

        consistency_cases = (
            ({PredictionTarget.HOME_WIN: Decimal("0.46")}, "MATCH_RESULT_SUM"),
            ({PredictionTarget.UNDER_1_5: Decimal("0.21")}, "TOTAL_1_5_SUM"),
            ({PredictionTarget.UNDER_2_5: Decimal("0.46")}, "TOTAL_2_5_SUM"),
            ({PredictionTarget.UNDER_3_5: Decimal("0.71")}, "TOTAL_3_5_SUM"),
            ({PredictionTarget.BTTS_NO: Decimal("0.43")}, "BTTS_SUM"),
            ({PredictionTarget.OVER_2_5: Decimal("0.85"), PredictionTarget.UNDER_2_5: Decimal("0.15")}, "OVER_TOTALS_MONOTONIC"),
        )
        for changes, reason in consistency_cases:
            with self.subTest(reason=reason):
                values = {**VALID_VALUES, **changes}
                outputs = tuple(ModelAdapterOutput(target, values[target]) for target in OFFICIAL_TARGET_ORDER)
                with self.assertRaises(InvalidModelOutputError) as captured:
                    validator.validate(outputs, self.policy)
                self.assertEqual(captured.exception.reason_code, reason)

    def test_tolerance_boundary_is_accepted(self) -> None:
        values = dict(VALID_VALUES)
        values[PredictionTarget.HOME_WIN] = Decimal("0.450001")
        probabilities, summary = RawProbabilityValidator().validate(
            tuple(ModelAdapterOutput(target, values[target]) for target in OFFICIAL_TARGET_ORDER),
            self.policy,
        )
        self.assertEqual(probabilities.probability_for(PredictionTarget.HOME_WIN), Decimal("0.450001"))
        self.assertTrue(all(check.passed for check in summary.ordered_checks))

    def test_identity_changes_with_model_output_policy_input_and_timestamp(self) -> None:
        base = self.generate()
        changed_values = dict(VALID_VALUES)
        changed_values[PredictionTarget.HOME_WIN] = Decimal("0.440000")
        changed_values[PredictionTarget.DRAW] = Decimal("0.260000")
        output_adapter = ReferenceAdapter(values=changed_values)
        output_service = build_prediction_inference_service(self.repository, PredictionModelRegistry(self.policy).register(output_adapter), self.policy)
        output = generate_raw_prediction(output_service, self.model_input, model_artifact_id=output_adapter.model_artifact_id, inference_timestamp=self.timestamp)

        version_adapter = ReferenceAdapter(version="2.0.0")
        version_service = build_prediction_inference_service(self.repository, PredictionModelRegistry(self.policy).register(version_adapter), self.policy)
        version = generate_raw_prediction(version_service, self.model_input, model_artifact_id=version_adapter.model_artifact_id, inference_timestamp=self.timestamp)

        policy = replace(self.policy, version="prediction-inference-policy-v2")
        policy_adapter = ReferenceAdapter()
        policy_service = build_prediction_inference_service(self.repository, PredictionModelRegistry(policy).register(policy_adapter), policy)
        policy_result = generate_raw_prediction(policy_service, self.model_input, model_artifact_id=policy_adapter.model_artifact_id, inference_timestamp=self.timestamp)
        timestamp = self.generate(timestamp=self.timestamp + timedelta(seconds=1))

        snapshots = build_match_data_snapshot_service(self.database)
        registration = snapshots.register_match_data_snapshot(command(
            match_id="different-inference-input",
            source_event_id="different-inference-input",
            source_snapshot_id="different-inference-input",
        ))
        snapshot = snapshots.repository.find_snapshot_by_id(registration.snapshot_id)
        feature = generate_match_feature_set(build_feature_store_service(self.database), snapshot, schema_version=SCHEMA_IDENTIFIER, feature_timestamp=EFFECTIVE).feature_set
        different_input = generate_model_input(build_model_input_builder(self.database), feature).model_input
        input_result = generate_raw_prediction(self.service, different_input, model_artifact_id=self.adapter.model_artifact_id, inference_timestamp=different_input.created_timestamp + timedelta(minutes=1))
        self.assertEqual(len({base.inference_fingerprint, output.inference_fingerprint, version.inference_fingerprint, policy_result.inference_fingerprint, timestamp.inference_fingerprint, input_result.inference_fingerprint}), 6)

    def test_repository_queries_serialization_triggers_and_foreign_key(self) -> None:
        outcome = self.generate()
        stored_json = self.database.connection.execute(
            "SELECT ordered_raw_probability_snapshot FROM prediction_inference_results"
        ).fetchone()[0]
        self.assertNotIn("0.45000000000000001", stored_json)
        self.assertEqual(self.repository.find_by_inference_fingerprint(outcome.inference_fingerprint).inference_id, outcome.inference_id)
        self.assertEqual(self.repository.find_for_model_input_and_artifact(self.model_input.model_input_id, self.adapter.model_artifact_id).inference_id, outcome.inference_id)
        self.assertEqual(self.repository.find_latest_for_match_and_model(self.model_input.match_id, self.adapter.model_artifact_id).inference_id, outcome.inference_id)
        self.assertEqual(len(self.repository.list_inferences_for_model_input(self.model_input.model_input_id)), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("UPDATE prediction_inference_results SET match_id='changed'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("DELETE FROM prediction_inference_results")
        self.database.connection.rollback()
        row = self.database.connection.execute("SELECT * FROM prediction_inference_results").fetchone()
        columns = tuple(item[0] for item in self.database.connection.execute("SELECT * FROM prediction_inference_results").description)
        values = list(row)
        values[columns.index("inference_id")] = "bad-foreign-key"
        values[columns.index("inference_fingerprint")] = "f" * 64
        values[columns.index("model_input_id")] = "missing-input"
        placeholders = ",".join("?" for _ in columns)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(f"INSERT INTO prediction_inference_results ({','.join(columns)}) VALUES ({placeholders})", values)

    def test_calibration_mapping_preserves_raw_provenance_without_execution(self) -> None:
        outcome = self.generate()
        result = self.repository.load_inference_by_id(outcome.inference_id)
        mapped = to_calibration_input(result, PredictionTarget.BTTS_YES)
        self.assertEqual(mapped.raw_probability, Decimal("0.580000"))
        self.assertEqual(mapped.target, PredictionTarget.BTTS_YES)
        self.assertEqual(mapped.inference_id, result.inference_id)
        self.assertEqual(mapped.model_version, result.model_version)
        self.assertEqual(mapped.inference_fingerprint, result.inference_fingerprint)


class PredictionInferenceMigrationTests(unittest.TestCase):
    def test_fresh_v17_and_v16_upgrade(self) -> None:
        fresh = Database(":memory:")
        MigrationManager(fresh.connection).migrate()
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 37)
        self.assertIsNotNone(fresh.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_inference_results'").fetchone())
        fresh.close()

        upgrade = Database(":memory:")
        upgrade.connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS:
            if migration.version > 16:
                continue
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute("INSERT INTO schema_migrations VALUES (?, 'existing')", (migration.version,))
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 37)
        self.assertIsNotNone(upgrade.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_inference_results'").fetchone())
        upgrade.close()


if __name__ == "__main__":
    unittest.main()
