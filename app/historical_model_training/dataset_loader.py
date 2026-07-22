"""Verified TRAIN and optional evaluation-only VALIDATION loading."""

from __future__ import annotations

from app.historical_dataset_split import Partition
from app.historical_dataset_split.inspection import (
    verify_equal_kickoff_grouping, verify_partition_chronology, verify_partition_exclusivity,
    verify_split_fingerprints,
)
from app.historical_training_dataset.chronology import verify_sources_strictly_prior
from app.historical_training_dataset.fingerprint import sha256_fingerprint

from .exceptions import PartitionSafetyError, SourceSplitError
from .validation import validate_example


def load_verified_partitions(command, training_repository, split_repository):
    split = split_repository.load_dataset_split(command.source_split_id)
    if split is None:
        raise SourceSplitError("Source split does not exist.")
    if split.split_fingerprint != command.source_split_fingerprint:
        raise SourceSplitError("Source split fingerprint mismatch.")
    fold = split_repository.load_fold(command.fold_id)
    if fold is None or fold.split_id != split.split_id:
        raise SourceSplitError("Fold does not belong to the source split.")
    if fold.fold_fingerprint != command.fold_fingerprint:
        raise SourceSplitError("Fold fingerprint mismatch.")
    identity = training_repository.load_dataset_identity(split.command.source_dataset_build_id)
    if identity is None:
        raise SourceSplitError("Source dataset does not exist.")
    request_fingerprint, dataset_fingerprint, feature_schema_version, label_schema_version = identity
    if dataset_fingerprint != split.command.source_dataset_fingerprint:
        raise SourceSplitError("Source dataset linkage mismatch.")
    if feature_schema_version != command.feature_schema_version or label_schema_version != command.label_schema_version:
        raise SourceSplitError("Source dataset schema linkage mismatch.")
    split_failures = (
        *verify_split_fingerprints(split_repository, split.split_id),
        *verify_partition_chronology(split_repository, split.split_id),
        *verify_partition_exclusivity(split_repository, split.split_id),
        *verify_equal_kickoff_grouping(split_repository, split.split_id),
    )
    if split_failures:
        raise PartitionSafetyError("|".join(split_failures))
    train_assignments = split_repository.list_assignments_by_partition(fold.fold_id, Partition.TRAIN)
    validation_assignments = (
        split_repository.list_assignments_by_partition(fold.fold_id, Partition.VALIDATION)
        if command.evaluate_validation else ()
    )
    train = _load_assignments(train_assignments, training_repository, Partition.TRAIN, request_fingerprint)
    validation = _load_assignments(validation_assignments, training_repository, Partition.VALIDATION, request_fingerprint)
    if set(item.training_example_id for item in train) & set(item.training_example_id for item in validation):
        raise PartitionSafetyError("TRAIN and VALIDATION overlap.")
    return split, fold, train, validation


def _load_assignments(assignments, repository, partition, dataset_request_fingerprint):
    examples = []
    for assignment in assignments:
        if assignment.partition is not partition:
            raise PartitionSafetyError("Unexpected partition assignment.")
        example = repository.load_training_example(assignment.training_example_id)
        if example is None or example.example_fingerprint != assignment.example_fingerprint:
            raise PartitionSafetyError("Assignment example provenance mismatch.")
        validate_example(example)
        expected = sha256_fingerprint({
            "dataset_request_fingerprint": dataset_request_fingerprint,
            "historical_match_fingerprint": example.historical_match_fingerprint,
            "strict_cutoff_timestamp": example.cutoff_timestamp,
            "ordered_sources": tuple(
                (item.source_historical_match_id, item.source_match_fingerprint)
                for item in example.sources
            ),
            "ordered_feature_vector": example.ordered_feature_vector,
            "missingness_mask": example.missingness_mask,
            "completeness_score": example.completeness_score,
            "labels": example.labels,
            "feature_schema_version": example.feature_schema_version,
            "label_schema_version": example.label_schema_version,
            "policy_version": example.policy_version,
        })
        if expected != example.example_fingerprint:
            raise PartitionSafetyError("Loaded example fingerprint mismatch.")
        leakage = verify_sources_strictly_prior(example.historical_match_id, example.kickoff_utc, example.sources)
        if leakage:
            raise PartitionSafetyError("Loaded example has temporal leakage: " + "|".join(leakage))
        examples.append(example)
    expected = tuple(sorted(examples, key=lambda item: (item.kickoff_utc, item.competition, item.historical_match_id, item.training_example_id)))
    if tuple(examples) != expected:
        raise PartitionSafetyError("Partition examples are not in deterministic chronology order.")
    return tuple(examples)
