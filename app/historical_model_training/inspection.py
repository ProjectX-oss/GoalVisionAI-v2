"""Read-only training summaries and reproducibility checks."""

from __future__ import annotations

import json

from app.historical_dataset_split import Partition

from .artifact import predict_raw_probabilities
from .fingerprint import sha256_fingerprint
from .metrics import calculate_metrics
from .validation import FEATURE_NAMES, FEATURE_SCHEMA_FINGERPRINT, validate_raw_probabilities


def summarize_training_run(repository, training_run_id: str):
    run = repository.load_training_run(training_run_id)
    if run is None:
        return None
    return {
        "training_run_id": run.training_run_id,
        "artifact_id": run.artifact.artifact_id,
        "model_family": run.command.model_family,
        "training_rows": sum(item.partition is Partition.TRAIN for item in run.training_examples),
        "validation_rows": sum(item.partition is Partition.VALIDATION for item in run.training_examples),
        "aggregate_training_metrics": run.aggregate_training_metrics,
        "aggregate_validation_metrics": run.aggregate_validation_metrics,
    }


def inspect_model_artifact(repository, artifact_id: str):
    return repository.load_model_artifact(artifact_id)


def inspect_target_estimator(repository, artifact_id: str, target_identity: str):
    return repository.load_artifact_target(artifact_id, target_identity)


def verify_training_partition_only(repository, training_run_id: str) -> tuple[str, ...]:
    failures = []
    for item in repository.list_training_examples(training_run_id):
        if item.partition not in (Partition.TRAIN, Partition.VALIDATION):
            failures.append(f"{item.training_example_id}:FORBIDDEN_PARTITION")
    return tuple(failures)


def verify_preprocessing_train_only(repository, training_repository, training_run_id: str) -> tuple[str, ...]:
    run = repository.load_training_run(training_run_id)
    if run is None:
        return ("TRAINING_RUN_NOT_FOUND",)
    training_ids = tuple(item.training_example_id for item in run.training_examples if item.partition is Partition.TRAIN)
    examples = tuple(training_repository.load_training_example(item) for item in training_ids)
    if any(item is None for item in examples):
        return ("TRAINING_EXAMPLE_NOT_FOUND",)
    from .policy import PreprocessingPolicy, MissingValuePolicy, ScalingPolicy
    from .preprocessing import fit_preprocessing
    policy = PreprocessingPolicy(
        missing_value_policy=MissingValuePolicy(run.artifact.preprocessing.missing_value_policy),
        scaling_policy=ScalingPolicy(run.artifact.preprocessing.scaling_policy),
        append_missingness_indicators=run.artifact.preprocessing.append_missingness_indicators,
    )
    reproduced = fit_preprocessing(examples, run.artifact.ordered_feature_names, policy)
    return () if reproduced.preprocessing_fingerprint == run.artifact.preprocessing.preprocessing_fingerprint else ("PREPROCESSING_FINGERPRINT_MISMATCH",)


def verify_artifact_fingerprint(repository, artifact_id: str) -> tuple[str, ...]:
    artifact = repository.load_model_artifact(artifact_id)
    if artifact is None:
        return ("ARTIFACT_NOT_FOUND",)
    run = repository.load_training_run(artifact.training_run_id)
    expected = sha256_fingerprint({
        "request_fingerprint": run.request_fingerprint,
        "source_fingerprints": (artifact.source_split_fingerprint, artifact.fold_fingerprint),
        "preprocessing_fingerprint": artifact.preprocessing.preprocessing_fingerprint,
        "estimator_fingerprints": tuple(item.estimator_fingerprint for item in artifact.estimators),
        "canonical_target_order": tuple(item.value for item in artifact.canonical_target_order),
        "metrics": run.metrics, "compatibility": artifact.compatibility_snapshot,
        "artifact_format_version": artifact.artifact_format_version,
    })
    return () if expected == artifact.artifact_fingerprint else ("ARTIFACT_FINGERPRINT_MISMATCH",)


def verify_estimator_fingerprints(repository, artifact_id: str) -> tuple[str, ...]:
    artifact = repository.load_model_artifact(artifact_id)
    if artifact is None:
        return ("ARTIFACT_NOT_FOUND",)
    run = repository.load_training_run(artifact.training_run_id)
    targets = repository.list_artifact_targets(artifact_id)
    failures = []
    config = run.command.estimator
    for estimator in artifact.estimators:
        expected_core = sha256_fingerprint({
            "identity": estimator.estimator_identity, "model_type": estimator.model_type,
            "classes": estimator.class_order, "coefficients": estimator.coefficients,
            "intercepts": estimator.intercepts, "iterations": estimator.iterations,
            "converged": estimator.converged, "final_delta": estimator.final_delta,
            "solver": config.solver, "regularization": config.regularization,
            "learning_rate": config.learning_rate, "tolerance": config.convergence_tolerance,
            "random_seed": config.random_seed,
        })
        if expected_core != estimator.estimator_fingerprint:
            failures.append(f"{estimator.estimator_identity}:ESTIMATOR_FINGERPRINT_MISMATCH")
    mapping = {
        "HOME_WIN": "MATCH_RESULT", "DRAW": "MATCH_RESULT", "AWAY_WIN": "MATCH_RESULT",
        "OVER_1_5": "TOTAL_GOALS_BUCKET", "UNDER_1_5": "TOTAL_GOALS_BUCKET",
        "OVER_2_5": "TOTAL_GOALS_BUCKET", "UNDER_2_5": "TOTAL_GOALS_BUCKET",
        "OVER_3_5": "TOTAL_GOALS_BUCKET", "UNDER_3_5": "TOTAL_GOALS_BUCKET",
        "BTTS_YES": "BTTS_YES", "BTTS_NO": "BTTS_YES",
    }
    for row in targets:
        estimator = next(item for item in artifact.estimators if item.estimator_identity == mapping[row.target_identity])
        expected_target = sha256_fingerprint({"target": row.target_identity, "estimator_fingerprint": estimator.estimator_fingerprint})
        if row.estimator_fingerprint != expected_target:
            failures.append(f"{row.target_identity}:TARGET_ESTIMATOR_FINGERPRINT_MISMATCH")
    return tuple(failures)


def verify_feature_compatibility(artifact, schema_version, schema_fingerprint, feature_names) -> tuple[str, ...]:
    failures = []
    if schema_version != artifact.feature_schema_version:
        failures.append("FEATURE_SCHEMA_VERSION_MISMATCH")
    if schema_fingerprint != artifact.feature_schema_fingerprint or schema_fingerprint != FEATURE_SCHEMA_FINGERPRINT:
        failures.append("FEATURE_SCHEMA_FINGERPRINT_MISMATCH")
    if tuple(feature_names) != artifact.ordered_feature_names or tuple(feature_names) != FEATURE_NAMES:
        failures.append("FEATURE_ORDER_MISMATCH")
    return tuple(failures)


def verify_probability_contract(probabilities) -> tuple[str, ...]:
    try:
        validate_raw_probabilities(probabilities)
    except Exception as exc:
        return (str(exc),)
    return ()


def reproduce_training_metrics(repository, training_repository, training_run_id: str):
    run = repository.load_training_run(training_run_id)
    if run is None:
        return None
    result = {}
    for partition in (Partition.TRAIN, Partition.VALIDATION):
        links = tuple(item for item in run.training_examples if item.partition is partition)
        examples = tuple(training_repository.load_training_example(item.training_example_id) for item in links)
        predictions = tuple(
            predict_raw_probabilities(
                run.artifact, item.ordered_feature_vector, item.missingness_mask,
                feature_schema_version=item.feature_schema_version,
                feature_schema_fingerprint=run.artifact.feature_schema_fingerprint,
                ordered_feature_names=run.artifact.ordered_feature_names,
            ).raw_probabilities for item in examples
        )
        if examples:
            _, aggregate = calculate_metrics(partition, examples, predictions)
            result[partition.value] = aggregate
    return tuple(sorted(result.items()))


def compare_reproduced_predictions(first, second) -> tuple[str, ...]:
    return () if first == second else ("REPRODUCED_PREDICTIONS_DIFFER",)
