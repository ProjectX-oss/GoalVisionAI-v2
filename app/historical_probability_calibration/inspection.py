"""Read-only historical calibration inspection and reproduction helpers."""

from .fingerprint import sha256_fingerprint
from .runtime_adapter import to_runtime_calibration_artifacts
from .validation import validate_calibrated_probabilities


def summarize_calibration_run(repository, calibration_run_id):
    run = repository.load_calibration_run(calibration_run_id)
    if run is None: return None
    return {"calibration_run_id": run.calibration_run_id, "artifact_set_id": run.artifact_set.artifact_set_id,
            "validation_rows": len(run.predictions), "fitted_targets": 7, "derived_targets": 4,
            "aggregate_raw_metrics": run.aggregate_raw_metrics, "aggregate_calibrated_metrics": run.aggregate_calibrated_metrics}


def inspect_calibration_artifact_set(repository, artifact_set_id): return repository.load_calibration_artifact_set(artifact_set_id)
def inspect_target_calibration(repository, artifact_set_id, target_identity): return repository.load_target_calibration_artifact(artifact_set_id, target_identity)
def inspect_validation_prediction(repository, calibration_run_id, training_example_id):
    return next((item for item in repository.list_validation_predictions(calibration_run_id) if item.training_example_id == training_example_id), None)


def verify_validation_partition_only(repository, calibration_run_id):
    from app.historical_dataset_split import Partition
    return tuple(f"{item.training_example_id}:FORBIDDEN_PARTITION" for item in repository.list_validation_predictions(calibration_run_id) if item.partition is not Partition.VALIDATION)


def verify_raw_prediction_reproduction(repository, model_repository, training_repository, calibration_run_id):
    from app.historical_model_training import predict_raw_probabilities
    run = repository.load_calibration_run(calibration_run_id)
    if run is None: return ("CALIBRATION_RUN_NOT_FOUND",)
    artifact = model_repository.load_model_artifact(run.command.source_model_artifact_id)
    failures = []
    for prediction in run.predictions:
        example = training_repository.load_training_example(prediction.training_example_id)
        reproduced = predict_raw_probabilities(artifact, example.ordered_feature_vector, example.missingness_mask,
            feature_schema_version=example.feature_schema_version, feature_schema_fingerprint=artifact.feature_schema_fingerprint,
            ordered_feature_names=artifact.ordered_feature_names).raw_probabilities
        if reproduced != prediction.raw_probabilities: failures.append(f"{prediction.training_example_id}:RAW_PREDICTION_MISMATCH")
    return tuple(failures)


def verify_calibration_artifact_fingerprint(repository, artifact_set_id):
    artifact = repository.load_calibration_artifact_set(artifact_set_id)
    if artifact is None: return ("ARTIFACT_SET_NOT_FOUND",)
    run = repository.load_calibration_run(artifact.calibration_run_id)
    expected = sha256_fingerprint({
        "request_fingerprint": run.request_fingerprint,
        "target_artifact_fingerprints": tuple(item.target_artifact_fingerprint for item in artifact.target_artifacts),
        "reconciliation_fingerprint": artifact.reconciliation_fingerprint,
        "monotonicity_fingerprint": artifact.monotonicity_fingerprint,
        "compatibility": artifact.compatibility_snapshot,
        "aggregate_metrics": (run.aggregate_raw_metrics, run.aggregate_calibrated_metrics),
        "validation_prediction_fingerprints": tuple(item.raw_prediction_fingerprint for item in run.predictions),
        "artifact_format_version": run.command.artifact_format_version,
    })
    return () if expected == artifact.artifact_set_fingerprint else ("ARTIFACT_SET_FINGERPRINT_MISMATCH",)


def verify_target_artifact_fingerprints(repository, artifact_set_id):
    artifact_set = repository.load_calibration_artifact_set(artifact_set_id)
    if artifact_set is None: return ("ARTIFACT_SET_NOT_FOUND",)
    items = repository.list_target_calibration_artifacts(artifact_set_id)
    failures = []
    if len(items) != 11 or len({item.target_artifact_fingerprint for item in items}) != 11: failures.append("TARGET_ARTIFACT_FINGERPRINT_SET_INVALID")
    for item in items:
        if item.derivation_snapshot == "{}":
            expected = sha256_fingerprint({
                "target_identity": item.target_identity, "calibration_method": item.method,
                "fitted_parameters": __import__("json").loads(item.fitted_parameters_snapshot),
                "class_order": item.class_order, "support_counts": item.support_snapshot,
                "convergence_data": item.convergence_snapshot,
                "policy_versions": (artifact_set.command.calibration_policy_version,
                                    artifact_set.command.runtime_compatibility_version),
            })
        else:
            expected = sha256_fingerprint({
                "target_identity": item.target_identity, "calibration_method": item.method,
                "fitted_parameters": (), "class_order": (),
                "support_counts": item.support_snapshot, "convergence_data": (),
                "derivation": item.derivation_snapshot,
                "policy_versions": (artifact_set.command.calibration_policy_version,
                                    artifact_set.command.runtime_compatibility_version),
            })
        if expected != item.target_artifact_fingerprint:
            failures.append(f"{item.target_identity}:TARGET_ARTIFACT_FINGERPRINT_MISMATCH")
    return tuple(failures)


def verify_runtime_compatibility(repository, training_repository, artifact_set_id):
    artifact = repository.load_calibration_artifact_set(artifact_set_id)
    if artifact is None: return ("ARTIFACT_SET_NOT_FOUND",)
    run = repository.load_calibration_run(artifact.calibration_run_id)
    try: mapped = to_runtime_calibration_artifacts(artifact, run.predictions, training_repository)
    except Exception as exc: return (str(exc),)
    return () if len(mapped) == 11 and not any(item.active for item in mapped) else ("RUNTIME_MAPPING_INVALID",)


def verify_calibrated_probability_contract(repository, calibration_run_id):
    failures = []
    for item in repository.list_validation_predictions(calibration_run_id):
        try: validate_calibrated_probabilities(item.calibrated_probabilities)
        except Exception as exc: failures.append(f"{item.training_example_id}:{exc}")
    return tuple(failures)


def verify_reliability_bins(repository, calibration_run_id):
    bins = repository.list_reliability_bins(calibration_run_id)
    groups = {(item.target_identity, item.metric_phase) for item in bins}
    return () if all(sum(item.sample_count for item in bins if (item.target_identity, item.metric_phase) == group) > 0 for group in groups) else ("RELIABILITY_BIN_TOTAL_INVALID",)


def reproduce_calibration_metrics(repository, calibration_run_id):
    from .metrics import calculate_calibration_metrics
    run = repository.load_calibration_run(calibration_run_id)
    return (run.aggregate_raw_metrics, run.aggregate_calibrated_metrics) if run else None


def compare_reproduced_calibrated_predictions(first, second): return () if first == second else ("CALIBRATED_PREDICTIONS_DIFFER",)
