"""Read-only split summaries and independent integrity verification."""

from app.historical_training_dataset import LABEL_ORDER

from .chronology import (
    verify_equal_kickoff_assignments, verify_fold_chronology, verify_fold_exclusivity,
)
from .fingerprint import sha256_fingerprint
from .models import DatasetSplitSummary, Partition, PartitionAssignment
from .ports import HistoricalDatasetSplitRepository, TrainingDatasetSourceRepository


def summarize_dataset_split(repository: HistoricalDatasetSplitRepository, split_id: str) -> DatasetSplitSummary | None:
    split = repository.load_dataset_split(split_id)
    if split is None:
        return None
    return DatasetSplitSummary(
        split_id=split.split_id, split_name=split.command.split_name,
        strategy=split.command.strategy.value, fold_count=len(split.folds),
        aggregate_counts=split.aggregate_counts,
        source_dataset_build_id=split.command.source_dataset_build_id,
        source_dataset_fingerprint=split.command.source_dataset_fingerprint,
    )


def inspect_split_fold(repository: HistoricalDatasetSplitRepository, fold_id: str):
    return repository.load_fold(fold_id)


def inspect_partition_assignment(repository: HistoricalDatasetSplitRepository, assignment_id: str) -> PartitionAssignment | None:
    return repository.load_assignment(assignment_id)


def verify_partition_exclusivity(repository: HistoricalDatasetSplitRepository, split_id: str) -> tuple[str, ...]:
    split = repository.load_dataset_split(split_id)
    if split is None:
        return ("SPLIT_NOT_FOUND",)
    return tuple(f"{fold.fold_id}:{failure}" for fold in split.folds for failure in verify_fold_exclusivity(fold))


def verify_partition_chronology(repository: HistoricalDatasetSplitRepository, split_id: str) -> tuple[str, ...]:
    split = repository.load_dataset_split(split_id)
    if split is None:
        return ("SPLIT_NOT_FOUND",)
    return tuple(f"{fold.fold_id}:{failure}" for fold in split.folds for failure in verify_fold_chronology(fold))


def verify_equal_kickoff_grouping(repository: HistoricalDatasetSplitRepository, split_id: str) -> tuple[str, ...]:
    split = repository.load_dataset_split(split_id)
    if split is None:
        return ("SPLIT_NOT_FOUND",)
    return tuple(f"{fold.fold_id}:{failure}" for fold in split.folds for failure in verify_equal_kickoff_assignments(fold))


def verify_split_fingerprints(repository: HistoricalDatasetSplitRepository, split_id: str) -> tuple[str, ...]:
    split = repository.load_dataset_split(split_id)
    if split is None:
        return ("SPLIT_NOT_FOUND",)
    failures = []
    for fold in split.folds:
        for item in fold.assignments:
            expected = sha256_fingerprint({
                "split_id": item.split_id, "fold_id": item.fold_id,
                "training_example_id": item.training_example_id,
                "example_fingerprint": item.example_fingerprint,
                "kickoff": item.kickoff_utc, "partition": item.partition,
                "assignment_order": item.assignment_order,
                "exclusion_reason": item.exclusion_reason,
                "policy_version": split.command.split_policy_version,
            })
            if expected != item.assignment_fingerprint:
                failures.append(f"{item.assignment_id}:ASSIGNMENT_FINGERPRINT_MISMATCH")
        expected_fold = sha256_fingerprint({
            "fold_identity": (fold.fold_id, fold.fold_index),
            "ordered_assignment_fingerprints": tuple(item.assignment_fingerprint for item in fold.assignments),
            "boundaries": (fold.train_boundary, fold.validation_boundary, fold.test_boundary),
            "achieved_counts": fold.achieved_counts,
            "achieved_ratios": fold.achieved_ratios,
            "policy_version": split.command.split_policy_version,
        })
        if expected_fold != fold.fold_fingerprint:
            failures.append(f"{fold.fold_id}:FOLD_FINGERPRINT_MISMATCH")
    exclusions = tuple(
        item.assignment_fingerprint for fold in split.folds for item in fold.assignments
        if item.partition.value.startswith("EXCLUDED_")
    )
    expected_split = sha256_fingerprint({
        "request_fingerprint": split.request_fingerprint,
        "ordered_fold_fingerprints": tuple(fold.fold_fingerprint for fold in split.folds),
        "aggregate_counts": split.aggregate_counts, "ordered_exclusions": exclusions,
        "source_dataset_fingerprint": split.command.source_dataset_fingerprint,
        "policy_version": split.command.split_policy_version,
    })
    if expected_split != split.split_fingerprint:
        failures.append("SPLIT_FINGERPRINT_MISMATCH")
    return tuple(failures)


def verify_source_dataset_linkage(
    split_repository: HistoricalDatasetSplitRepository,
    training_repository: TrainingDatasetSourceRepository,
    split_id: str,
) -> tuple[str, ...]:
    split = split_repository.load_dataset_split(split_id)
    if split is None:
        return ("SPLIT_NOT_FOUND",)
    source = training_repository.load_dataset_build(split.command.source_dataset_build_id)
    if source is None:
        return ("SOURCE_DATASET_NOT_FOUND",)
    failures = []
    if source.dataset_fingerprint != split.command.source_dataset_fingerprint:
        failures.append("SOURCE_DATASET_FINGERPRINT_MISMATCH")
    examples = {item.training_example_id: item for item in training_repository.stream_examples_in_deterministic_order(source.dataset_build_id)}
    for fold in split.folds:
        for item in fold.assignments:
            source_example = examples.get(item.training_example_id)
            if source_example is None or source_example.example_fingerprint != item.example_fingerprint:
                failures.append(f"{item.assignment_id}:SOURCE_EXAMPLE_MISMATCH")
    return tuple(failures)


def summarize_partition_labels(repository, fold_id: str) -> tuple[tuple[str, tuple[tuple[str, int], ...]], ...]:
    result = []
    for partition in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST):
        supplied = dict(repository.count_partition_labels(fold_id, partition))
        result.append((partition.value, tuple((label, supplied.get(label, 0)) for label in LABEL_ORDER)))
    return tuple(result)
