"""VALIDATION-only source verification and persisted-artifact prediction reproduction."""

from datetime import datetime

from app.historical_dataset_split import Partition
from app.historical_dataset_split.inspection import (
    verify_equal_kickoff_grouping, verify_partition_chronology,
    verify_partition_exclusivity, verify_split_fingerprints,
)
from app.historical_model_training import (
    predict_raw_probabilities, verify_artifact_fingerprint, verify_estimator_fingerprints,
)
from app.historical_training_dataset.chronology import verify_sources_strictly_prior
from app.historical_training_dataset.fingerprint import sha256_fingerprint

from .exceptions import (
    PartitionSafetyError, RawPredictionError, SchemaCompatibilityError,
    SourceArtifactError, SourceSplitError, SourceTrainingRunError,
)
from .models import ValidationPrediction
from .policy import PREDICTION_IMPLEMENTATION_VERSION


def load_validation_predictions(command, model_repository, split_repository, training_repository):
    run = model_repository.load_training_run(command.source_training_run_id)
    if run is None or run.training_run_fingerprint != command.source_training_run_fingerprint:
        raise SourceTrainingRunError("Training run is missing or its fingerprint differs.")
    artifact = model_repository.load_model_artifact(command.source_model_artifact_id)
    if artifact is None or artifact.training_run_id != run.training_run_id:
        raise SourceArtifactError("Model artifact is missing or does not belong to the selected training run.")
    if artifact.artifact_fingerprint != command.source_model_artifact_fingerprint:
        raise SourceArtifactError("Model artifact fingerprint mismatch.")
    if verify_artifact_fingerprint(model_repository, artifact.artifact_id) or verify_estimator_fingerprints(model_repository, artifact.artifact_id):
        raise SourceArtifactError("Model artifact integrity verification failed.")
    if (artifact.feature_schema_version, artifact.feature_schema_fingerprint, artifact.label_schema_version, artifact.target_schema_version) != (
        command.feature_schema_version, command.feature_schema_fingerprint, command.label_schema_version, command.target_schema_version,
    ):
        raise SchemaCompatibilityError("Training artifact schema compatibility failed.")
    split = split_repository.load_dataset_split(command.source_split_id)
    if split is None or split.split_fingerprint != command.source_split_fingerprint:
        raise SourceSplitError("Source split is missing or its fingerprint differs.")
    fold = split_repository.load_fold(command.fold_id)
    if fold is None or fold.split_id != split.split_id or fold.fold_fingerprint != command.fold_fingerprint:
        raise SourceSplitError("Source fold is missing, unlinked, or has a fingerprint mismatch.")
    if (run.command.source_split_id, run.command.fold_id) != (split.split_id, fold.fold_id):
        raise SourceSplitError("Training run source split/fold linkage differs.")
    failures = (
        *verify_split_fingerprints(split_repository, split.split_id),
        *verify_partition_chronology(split_repository, split.split_id),
        *verify_partition_exclusivity(split_repository, split.split_id),
        *verify_equal_kickoff_grouping(split_repository, split.split_id),
    )
    if failures: raise PartitionSafetyError("|".join(failures))
    identity = training_repository.load_dataset_identity(split.command.source_dataset_build_id)
    if identity is None or identity[1] != split.command.source_dataset_fingerprint:
        raise SourceSplitError("Source dataset linkage differs.")
    dataset_request_fingerprint = identity[0]
    validation_links = {item.training_example_id: item for item in model_repository.list_training_examples(run.training_run_id) if item.partition is Partition.VALIDATION}
    assignments = split_repository.list_assignments_by_partition(fold.fold_id, Partition.VALIDATION)
    if set(validation_links) != {item.training_example_id for item in assignments}:
        raise PartitionSafetyError("Persisted training-run VALIDATION provenance differs from the split.")
    predictions = []
    for order, assignment in enumerate(assignments):
        example = training_repository.load_training_example(assignment.training_example_id)
        if example is None or assignment.example_fingerprint != example.example_fingerprint:
            raise PartitionSafetyError("VALIDATION example linkage differs.")
        expected = sha256_fingerprint({
            "dataset_request_fingerprint": dataset_request_fingerprint,
            "historical_match_fingerprint": example.historical_match_fingerprint,
            "strict_cutoff_timestamp": example.cutoff_timestamp,
            "ordered_sources": tuple((item.source_historical_match_id, item.source_match_fingerprint) for item in example.sources),
            "ordered_feature_vector": example.ordered_feature_vector, "missingness_mask": example.missingness_mask,
            "completeness_score": example.completeness_score, "labels": example.labels,
            "feature_schema_version": example.feature_schema_version, "label_schema_version": example.label_schema_version,
            "policy_version": example.policy_version,
        })
        if expected != example.example_fingerprint:
            raise PartitionSafetyError("VALIDATION example fingerprint verification failed.")
        if verify_sources_strictly_prior(example.historical_match_id, example.kickoff_utc, example.sources):
            raise PartitionSafetyError("VALIDATION example temporal leakage detected.")
        try:
            raw = predict_raw_probabilities(
                artifact, example.ordered_feature_vector, example.missingness_mask,
                feature_schema_version=example.feature_schema_version,
                feature_schema_fingerprint=artifact.feature_schema_fingerprint,
                ordered_feature_names=artifact.ordered_feature_names,
            ).raw_probabilities
        except Exception as exc:
            raise RawPredictionError("Persisted-artifact raw prediction reproduction failed.") from exc
        raw_fp = sha256_fingerprint({
            "artifact_fingerprint": artifact.artifact_fingerprint,
            "example_fingerprint": example.example_fingerprint,
            "ordered_raw_target_probabilities": tuple((item.target.value, item.probability) for item in raw.ordered_probabilities),
            "target_schema": command.target_schema_version,
            "prediction_implementation_version": PREDICTION_IMPLEMENTATION_VERSION,
        })
        predictions.append((example, ValidationPrediction(
            training_example_id=example.training_example_id, example_fingerprint=example.example_fingerprint,
            artifact_id=artifact.artifact_id, artifact_fingerprint=artifact.artifact_fingerprint,
            training_run_id=run.training_run_id, split_id=split.split_id, fold_id=fold.fold_id,
            partition=Partition.VALIDATION, raw_probabilities=raw, calibrated_probabilities=None,
            raw_prediction_fingerprint=raw_fp, deterministic_order=order,
        )))
    return run, artifact, split, fold, tuple(predictions)
