"""Read-only upstream provenance, partition, and compatibility verification."""

from __future__ import annotations

from app.historical_dataset_split import Partition
from app.historical_dataset_split.inspection import (
    verify_equal_kickoff_grouping,
    verify_partition_chronology,
    verify_partition_exclusivity,
    verify_source_dataset_linkage,
    verify_split_fingerprints,
)
from app.historical_model_training.inspection import verify_artifact_fingerprint
from app.historical_probability_calibration.inspection import (
    verify_calibration_artifact_fingerprint,
    verify_target_artifact_fingerprints,
)
from app.historical_training_dataset.inspection import (
    verify_dataset_fingerprints,
    verify_label_consistency,
    verify_no_temporal_leakage,
)

from .exceptions import (
    BacktestPartitionSafetyError,
    BacktestSchemaCompatibilityError,
    BacktestSourceError,
)


def verify_sources(command, training_repository, split_repository, model_repository, calibration_repository):
    split = split_repository.load_dataset_split(command.source_split_id)
    if split is None or split.split_fingerprint != command.source_split_fingerprint:
        raise BacktestSourceError("Source split is missing or its fingerprint differs.")
    fold = split_repository.load_fold(command.fold_id)
    if fold is None or fold.split_id != split.split_id or fold.fold_fingerprint != command.fold_fingerprint:
        raise BacktestSourceError("Source fold is missing, unrelated, or has a different fingerprint.")
    split_failures = (
        verify_split_fingerprints(split_repository, split.split_id)
        + verify_partition_chronology(split_repository, split.split_id)
        + verify_partition_exclusivity(split_repository, split.split_id)
        + verify_equal_kickoff_grouping(split_repository, split.split_id)
        + verify_source_dataset_linkage(split_repository, training_repository, split.split_id)
    )
    if split_failures:
        raise BacktestPartitionSafetyError(";".join(split_failures))
    dataset = training_repository.load_dataset_build(split.command.source_dataset_build_id)
    if dataset is None:
        raise BacktestSourceError("Source training dataset is missing.")
    dataset_failures = (
        verify_dataset_fingerprints(training_repository, dataset.dataset_build_id)
        + verify_label_consistency(training_repository, dataset.dataset_build_id)
        + verify_no_temporal_leakage(training_repository, dataset.dataset_build_id)
    )
    if dataset_failures:
        raise BacktestPartitionSafetyError(";".join(dataset_failures))
    training_run = model_repository.load_training_run(command.source_training_run_id)
    artifact = model_repository.load_model_artifact(command.model_artifact_id)
    if (
        training_run is None
        or training_run.training_run_fingerprint != command.source_training_run_fingerprint
        or artifact is None
        or artifact.artifact_fingerprint != command.model_artifact_fingerprint
        or artifact.training_run_id != training_run.training_run_id
    ):
        raise BacktestSourceError("Historical model source identity or fingerprint mismatch.")
    if verify_artifact_fingerprint(model_repository, artifact.artifact_id):
        raise BacktestSourceError("Historical model artifact failed reproduction.")
    calibration_run = calibration_repository.load_calibration_run(command.calibration_run_id)
    calibration_set = calibration_repository.load_calibration_artifact_set(command.calibration_artifact_set_id)
    if (
        calibration_run is None
        or calibration_run.calibration_run_fingerprint != command.calibration_run_fingerprint
        or calibration_set is None
        or calibration_set.artifact_set_fingerprint != command.calibration_artifact_set_fingerprint
        or calibration_set.calibration_run_id != calibration_run.calibration_run_id
    ):
        raise BacktestSourceError("Historical calibration source identity or fingerprint mismatch.")
    if (
        verify_calibration_artifact_fingerprint(calibration_repository, calibration_set.artifact_set_id)
        or verify_target_artifact_fingerprints(calibration_repository, calibration_set.artifact_set_id)
    ):
        raise BacktestSourceError("Historical calibration artifact set failed reproduction.")
    compatibility = calibration_set.command
    expected = (
        compatibility.source_training_run_id == training_run.training_run_id
        and compatibility.source_training_run_fingerprint == training_run.training_run_fingerprint
        and compatibility.source_model_artifact_id == artifact.artifact_id
        and compatibility.source_model_artifact_fingerprint == artifact.artifact_fingerprint
        and compatibility.source_split_id == split.split_id
        and compatibility.source_split_fingerprint == split.split_fingerprint
        and compatibility.fold_id == fold.fold_id
        and compatibility.fold_fingerprint == fold.fold_fingerprint
        and artifact.feature_schema_version == dataset.command.feature_schema_version
        and artifact.label_schema_version == dataset.command.label_schema_version
    )
    if not expected:
        raise BacktestSchemaCompatibilityError("Split, model, calibration, and dataset are incompatible.")
    assignments = split_repository.list_assignments_by_partition(fold.fold_id, Partition.TEST)
    forbidden = tuple(
        item for item in assignments
        if item.partition is not Partition.TEST or item.exclusion_reason is not None
    )
    if forbidden:
        raise BacktestPartitionSafetyError("Only non-excluded TEST assignments may be evaluated.")
    examples = []
    for assignment in assignments:
        example = training_repository.load_training_example(assignment.training_example_id)
        if example is None or example.example_fingerprint != assignment.example_fingerprint:
            raise BacktestPartitionSafetyError("A TEST example is missing or corrupted.")
        examples.append(example)
    examples.sort(key=lambda item: (item.kickoff_utc, item.competition, item.historical_match_id, item.training_example_id))
    return split, fold, dataset, training_run, artifact, calibration_run, calibration_set, tuple(examples)


def verify_test_partition_only(split_repository, fold_id: str, example_ids: tuple[str, ...]) -> tuple[str, ...]:
    test = {item.training_example_id for item in split_repository.list_assignments_by_partition(fold_id, Partition.TEST)}
    return tuple(f"{identity}:NOT_TEST" for identity in example_ids if identity not in test)
