"""Atomic append-only SQLite repository for safe model artifacts."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from app.database import Database, MigrationManager
from app.historical_dataset_split import Partition

from .exceptions import TrainingConflictError, TrainingPersistenceError
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    ArtifactTarget, EstimatorConfiguration, FittedEstimator, FittedPreprocessing,
    MetricRecord, ModelArtifact, NormalizedTrainingCommand, PreparedTrainingRun,
    PreprocessingFeature, TrainingExampleLink,
)
from .policy import ClassWeightPolicy, MissingValuePolicy, ScalingPolicy


class SQLiteHistoricalModelTrainingRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_training_run(self, run: PreparedTrainingRun) -> None:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT request_fingerprint FROM historical_model_training_runs WHERE training_request_id=?",
                (run.command.training_request_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != run.request_fingerprint:
                    raise TrainingConflictError("Training request ID has different immutable content.")
                self._connection.commit()
                return
            self._insert_run(run)
            self._insert_artifact(run.artifact)
            self._insert_targets(run.artifact)
            self._insert_preprocessing(run.artifact)
            self._insert_examples(run)
            self._insert_metrics(run)
            self._connection.commit()
        except TrainingConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise TrainingPersistenceError("Historical model training transaction failed.") from exc

    def find_by_training_run_fingerprint(self, fingerprint: str):
        row = self._connection.execute(
            "SELECT training_run_id FROM historical_model_training_runs WHERE training_run_fingerprint=?", (fingerprint,),
        ).fetchone()
        return self.load_training_run(row[0]) if row else None

    def find_by_request_id(self, request_id: str):
        row = self._connection.execute(
            "SELECT training_run_id FROM historical_model_training_runs WHERE training_request_id=?", (request_id,),
        ).fetchone()
        return self.load_training_run(row[0]) if row else None

    def load_training_run(self, training_run_id: str):
        row = self._connection.execute(
            "SELECT * FROM historical_model_training_runs WHERE training_run_id=?", (training_run_id,),
        ).fetchone()
        if row is None:
            return None
        artifact_row = self._connection.execute(
            "SELECT artifact_id FROM historical_model_artifacts WHERE training_run_id=?", (training_run_id,),
        ).fetchone()
        artifact = self.load_model_artifact(artifact_row[0])
        snapshot = json.loads(row["deterministic_run_snapshot"])
        command = _load_command(snapshot["command"])
        training_metrics = tuple((name, Decimal(value)) for name, value in snapshot["aggregate_training_metrics"])
        validation_metrics = tuple((name, Decimal(value)) for name, value in snapshot["aggregate_validation_metrics"])
        return PreparedTrainingRun(
            training_run_id=training_run_id, command=command,
            request_fingerprint=row["request_fingerprint"],
            training_run_fingerprint=row["training_run_fingerprint"], artifact=artifact,
            training_examples=self.list_training_examples(training_run_id),
            metrics=self.list_metrics(training_run_id), aggregate_training_metrics=training_metrics,
            aggregate_validation_metrics=validation_metrics,
            deterministic_run_snapshot=row["deterministic_run_snapshot"],
        )

    def load_model_artifact(self, artifact_id: str):
        row = self._connection.execute(
            "SELECT * FROM historical_model_artifacts WHERE artifact_id=?", (artifact_id,),
        ).fetchone()
        if row is None:
            return None
        compatibility = json.loads(row["compatibility_snapshot"])
        provenance = json.loads(row["provenance_snapshot"])
        preprocessing_config = json.loads(row["preprocessing_snapshot"])
        features = self.list_preprocessing_features(artifact_id)
        transformed_names = tuple(preprocessing_config["transformed_feature_names"])
        preprocessing = FittedPreprocessing(
            policy_version=preprocessing_config["policy_version"],
            missing_value_policy=preprocessing_config["missing_value_policy"],
            scaling_policy=preprocessing_config["scaling_policy"],
            append_missingness_indicators=preprocessing_config["append_missingness_indicators"],
            original_feature_names=tuple(compatibility["ordered_feature_names"]),
            transformed_feature_names=transformed_names, features=features,
            preprocessing_fingerprint=row["preprocessing_fingerprint"],
        )
        estimators = tuple(_load_estimator(item) for item in json.loads(row["estimator_snapshot"]))
        from app.prediction_inference.models import PredictionTarget
        return ModelArtifact(
            artifact_id=artifact_id, artifact_fingerprint=row["artifact_fingerprint"],
            training_run_id=row["training_run_id"],
            training_request_fingerprint=provenance["training_request_fingerprint"],
            source_split_id=provenance["source_split_id"],
            source_split_fingerprint=provenance["source_split_fingerprint"],
            fold_id=provenance["fold_id"], fold_fingerprint=provenance["fold_fingerprint"],
            model_family=compatibility["model_family"],
            feature_schema_version=compatibility["feature_schema_version"],
            feature_schema_fingerprint=compatibility["feature_schema_fingerprint"],
            ordered_feature_names=tuple(compatibility["ordered_feature_names"]),
            label_schema_version=compatibility["label_schema_version"],
            target_schema_version=compatibility["target_schema_version"],
            canonical_target_order=tuple(PredictionTarget(item) for item in compatibility["canonical_target_order"]),
            artifact_format_version=row["artifact_format_version"], preprocessing=preprocessing,
            estimators=estimators, training_timestamp=provenance["training_timestamp"],
            compatibility_snapshot=row["compatibility_snapshot"], provenance_snapshot=row["provenance_snapshot"],
        )

    def load_artifact_target(self, artifact_id: str, target_identity: str):
        row = self._connection.execute(
            "SELECT * FROM historical_model_artifact_targets WHERE artifact_id=? AND target_identity=?",
            (artifact_id, target_identity),
        ).fetchone()
        return _target(row) if row else None

    def list_artifact_targets(self, artifact_id: str):
        rows = self._connection.execute(
            "SELECT * FROM historical_model_artifact_targets WHERE artifact_id=? ORDER BY target_order", (artifact_id,),
        ).fetchall()
        return tuple(_target(row) for row in rows)

    def list_preprocessing_features(self, artifact_id: str):
        rows = self._connection.execute(
            "SELECT * FROM historical_model_preprocessing_features WHERE artifact_id=? ORDER BY original_feature_index",
            (artifact_id,),
        ).fetchall()
        return tuple(PreprocessingFeature(
            feature_name=row["feature_name"], original_feature_index=row["original_feature_index"],
            transformed_feature_index=row["transformed_feature_index"],
            imputation_value=float(row["imputation_value"]), missing_training_count=row["missing_training_count"],
            scaling_mean=float(row["scaling_mean"]), scaling_scale=float(row["scaling_scale"]),
            zero_variance=bool(row["zero_variance_flag"]), row_fingerprint=row["preprocessing_row_fingerprint"],
        ) for row in rows)

    def list_training_examples(self, training_run_id: str):
        rows = self._connection.execute(
            "SELECT * FROM historical_model_training_examples WHERE training_run_id=? ORDER BY partition,deterministic_order",
            (training_run_id,),
        ).fetchall()
        return tuple(TrainingExampleLink(
            training_example_id=row["training_example_id"], example_fingerprint=row["example_fingerprint"],
            partition=Partition(row["partition"]), deterministic_order=row["deterministic_order"],
        ) for row in rows)

    def list_metrics(self, training_run_id: str):
        rows = self._connection.execute(
            "SELECT * FROM historical_model_metrics WHERE training_run_id=? ORDER BY deterministic_order", (training_run_id,),
        ).fetchall()
        return tuple(MetricRecord(
            partition=Partition(row["partition"]), target_identity=row["target_identity"],
            metric_name=row["metric_name"], metric_value=Decimal(row["metric_value"]) if row["metric_value"] else None,
            metric_snapshot=row["metric_snapshot"], deterministic_order=row["deterministic_order"],
        ) for row in rows)

    def list_training_runs_for_fold(self, fold_id: str):
        rows = self._connection.execute(
            "SELECT training_run_id FROM historical_model_training_runs WHERE fold_id=? ORDER BY training_timestamp,training_run_id",
            (fold_id,),
        ).fetchall()
        return tuple(self.load_training_run(row[0]) for row in rows)

    def stream_artifact_parameters(self, artifact_id: str):
        cursor = self._connection.execute(
            "SELECT * FROM historical_model_artifact_targets WHERE artifact_id=? ORDER BY target_order", (artifact_id,),
        )
        while True:
            rows = cursor.fetchmany(10)
            if not rows:
                return
            for row in rows:
                yield _target(row)

    def _insert_run(self, run):
        command = run.command
        self._connection.execute(
            """INSERT INTO historical_model_training_runs (
                training_run_id,training_request_id,request_fingerprint,training_run_fingerprint,
                source_split_id,source_split_fingerprint,fold_id,fold_fingerprint,model_family,
                policy_versions_snapshot,feature_schema_version,feature_schema_fingerprint,
                label_schema_version,target_schema_version,training_row_count,validation_row_count,
                target_count,outcome,reason_codes_snapshot,aggregate_metrics_snapshot,
                deterministic_run_snapshot,training_timestamp,created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run.training_run_id, command.training_request_id, run.request_fingerprint,
             run.training_run_fingerprint, command.source_split_id, command.source_split_fingerprint,
             command.fold_id, command.fold_fingerprint, command.model_family,
             canonical_json((command.preprocessing_policy_version, command.model_policy_version, command.metadata_version)),
             command.feature_schema_version, command.feature_schema_fingerprint, command.label_schema_version,
             command.target_schema_version, sum(x.partition is Partition.TRAIN for x in run.training_examples),
             sum(x.partition is Partition.VALIDATION for x in run.training_examples), 11, "MODEL_TRAINED",
             canonical_json(("MODEL_ARTIFACT_PERSISTED",)),
             canonical_json({"TRAIN": run.aggregate_training_metrics, "VALIDATION": run.aggregate_validation_metrics}),
             run.deterministic_run_snapshot, command.training_timestamp, command.training_timestamp),
        )

    def _insert_artifact(self, artifact):
        estimator_snapshot = canonical_json(tuple({
            "estimator_identity": item.estimator_identity, "model_type": item.model_type,
            "class_order": item.class_order, "coefficients": item.coefficients,
            "intercepts": item.intercepts, "iterations": item.iterations,
            "converged": item.converged, "final_delta": item.final_delta,
            "estimator_fingerprint": item.estimator_fingerprint,
        } for item in artifact.estimators))
        preprocessing_snapshot = canonical_json({
            "policy_version": artifact.preprocessing.policy_version,
            "missing_value_policy": artifact.preprocessing.missing_value_policy,
            "scaling_policy": artifact.preprocessing.scaling_policy,
            "append_missingness_indicators": artifact.preprocessing.append_missingness_indicators,
            "transformed_feature_names": artifact.preprocessing.transformed_feature_names,
        })
        bundle_fp = sha256_fingerprint(tuple(item.estimator_fingerprint for item in artifact.estimators))
        self._connection.execute(
            """INSERT INTO historical_model_artifacts (
                artifact_id,training_run_id,artifact_fingerprint,artifact_format_version,
                preprocessing_fingerprint,estimator_bundle_fingerprint,compatibility_snapshot,
                preprocessing_snapshot,estimator_snapshot,provenance_snapshot,created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (artifact.artifact_id, artifact.training_run_id, artifact.artifact_fingerprint,
             artifact.artifact_format_version, artifact.preprocessing.preprocessing_fingerprint,
             bundle_fp, artifact.compatibility_snapshot, preprocessing_snapshot, estimator_snapshot,
             artifact.provenance_snapshot, artifact.training_timestamp),
        )

    def _insert_targets(self, artifact):
        mapping = {
            "HOME_WIN": "MATCH_RESULT", "DRAW": "MATCH_RESULT", "AWAY_WIN": "MATCH_RESULT",
            "OVER_1_5": "TOTAL_GOALS_BUCKET", "UNDER_1_5": "TOTAL_GOALS_BUCKET",
            "OVER_2_5": "TOTAL_GOALS_BUCKET", "UNDER_2_5": "TOTAL_GOALS_BUCKET",
            "OVER_3_5": "TOTAL_GOALS_BUCKET", "UNDER_3_5": "TOTAL_GOALS_BUCKET",
            "BTTS_YES": "BTTS_YES", "BTTS_NO": "BTTS_YES",
        }
        estimators = {item.estimator_identity: item for item in artifact.estimators}
        for order, target in enumerate(artifact.canonical_target_order):
            estimator = estimators[mapping[target.value]]
            target_fp = sha256_fingerprint({"target": target.value, "estimator_fingerprint": estimator.estimator_fingerprint})
            convergence = canonical_json({"iterations": estimator.iterations, "converged": estimator.converged, "final_delta": estimator.final_delta})
            identity = sha256_fingerprint((artifact.artifact_id, target.value))
            self._connection.execute(
                """INSERT INTO historical_model_artifact_targets VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (f"historical-model-target-{identity}", artifact.artifact_id, target.value, order,
                 target_fp, estimator.model_type, canonical_json(estimator.class_order),
                 canonical_json(estimator.coefficients), canonical_json(estimator.intercepts),
                 convergence, artifact.training_timestamp),
            )

    def _insert_preprocessing(self, artifact):
        for feature in artifact.preprocessing.features:
            identity = sha256_fingerprint((artifact.artifact_id, feature.original_feature_index))
            self._connection.execute(
                """INSERT INTO historical_model_preprocessing_features VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"historical-model-preprocessing-{identity}", artifact.artifact_id, feature.feature_name,
                 feature.original_feature_index, feature.transformed_feature_index,
                 str(feature.imputation_value), feature.missing_training_count, str(feature.scaling_mean),
                 str(feature.scaling_scale), int(feature.zero_variance), feature.row_fingerprint,
                 artifact.training_timestamp),
            )

    def _insert_examples(self, run):
        for item in run.training_examples:
            identity = sha256_fingerprint((run.training_run_id, item.training_example_id, item.partition.value))
            self._connection.execute(
                "INSERT INTO historical_model_training_examples VALUES (?,?,?,?,?,?,?)",
                (f"historical-model-example-{identity}", run.training_run_id, item.training_example_id,
                 item.example_fingerprint, item.partition.value, item.deterministic_order, run.command.training_timestamp),
            )

    def _insert_metrics(self, run):
        for item in run.metrics:
            identity = sha256_fingerprint((run.training_run_id, item.deterministic_order))
            self._connection.execute(
                "INSERT INTO historical_model_metrics VALUES (?,?,?,?,?,?,?,?,?)",
                (f"historical-model-metric-{identity}", run.training_run_id, item.partition.value,
                 item.target_identity, item.metric_name, str(item.metric_value) if item.metric_value is not None else None,
                 item.metric_snapshot, item.deterministic_order, run.command.training_timestamp),
            )


def _load_command(value):
    estimator = value["estimator"]
    return NormalizedTrainingCommand(
        **{key: item for key, item in value.items() if key not in {"training_partition", "estimator", "missing_value_policy", "scaling_policy", "ordered_feature_names"}},
        training_partition=Partition(value["training_partition"]),
        ordered_feature_names=tuple(value["ordered_feature_names"]),
        estimator=EstimatorConfiguration(
            regularization=Decimal(estimator["regularization"]), learning_rate=Decimal(estimator["learning_rate"]),
            solver=estimator["solver"], class_weight_policy=ClassWeightPolicy(estimator["class_weight_policy"]),
            maximum_iterations=estimator["maximum_iterations"], convergence_tolerance=Decimal(estimator["convergence_tolerance"]),
            random_seed=estimator["random_seed"],
        ),
        missing_value_policy=MissingValuePolicy(value["missing_value_policy"]),
        scaling_policy=ScalingPolicy(value["scaling_policy"]),
    )


def _load_estimator(value):
    return FittedEstimator(
        estimator_identity=value["estimator_identity"], model_type=value["model_type"],
        class_order=tuple(value["class_order"]),
        coefficients=tuple(tuple(float(item) for item in row) for row in value["coefficients"]),
        intercepts=tuple(float(item) for item in value["intercepts"]), iterations=value["iterations"],
        converged=value["converged"], final_delta=float(value["final_delta"]),
        estimator_fingerprint=value["estimator_fingerprint"],
    )


def _target(row):
    return ArtifactTarget(
        target_identity=row["target_identity"], target_order=row["target_order"],
        estimator_fingerprint=row["estimator_fingerprint"], model_type=row["model_type"],
        class_order=tuple(json.loads(row["class_order_snapshot"])),
        coefficients=tuple(tuple(float(item) for item in values) for values in json.loads(row["coefficients_snapshot"])),
        intercepts=tuple(float(item) for item in json.loads(row["intercept_snapshot"])),
        convergence_snapshot=row["convergence_snapshot"],
    )


def _rollback(connection):
    if connection.in_transaction:
        connection.rollback()
