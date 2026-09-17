"""Application service for verified deterministic dataset splitting."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_EVEN

from app.historical_training_dataset import (
    verify_dataset_fingerprints, verify_label_consistency, verify_no_temporal_leakage,
)

from .exceptions import (
    DatasetSplitConflictError, DatasetSplitPersistenceError, SourceDatasetVerificationError,
    SplitChronologyError, SplitPartitionSizeError, SplitRequestValidationError,
)
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    DatasetSplitCommand, DatasetSplitOutcome, DatasetSplitStatus, Partition,
    PreparedDatasetSplit,
)
from .policy import DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY, HistoricalDatasetSplitPolicy
from .ports import HistoricalDatasetSplitRepository, TrainingDatasetSourceRepository
from .splitter import construct_split_folds
from .validation import normalize_split_command, validate_source_dataset


class HistoricalDatasetSplitter:
    def __init__(
        self,
        training_repository: TrainingDatasetSourceRepository,
        split_repository: HistoricalDatasetSplitRepository,
        default_policy: HistoricalDatasetSplitPolicy = DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY,
    ) -> None:
        self._training = training_repository
        self._splits = split_repository
        self._default_policy = default_policy

    def create(
        self,
        command: DatasetSplitCommand,
        *,
        policy: HistoricalDatasetSplitPolicy | None = None,
    ) -> DatasetSplitOutcome:
        selected_policy = policy or self._default_policy
        try:
            normalized = normalize_split_command(command, selected_policy)
        except (SplitRequestValidationError, ValueError) as exc:
            return _rejected(command, selected_policy, DatasetSplitStatus.REJECTED_INVALID_REQUEST, ("INVALID_SPLIT_REQUEST", str(exc)))
        request_fingerprint = sha256_fingerprint({"command": normalized})
        existing = self._splits.find_by_request_id(normalized.split_request_id)
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                return _outcome(existing, DatasetSplitStatus.CONFLICT, ("SPLIT_REQUEST_ID_CONFLICT",))
            return _outcome(existing, DatasetSplitStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_SPLIT_EXISTS",))

        source = self._training.load_dataset_build(normalized.source_dataset_build_id)
        if source is None:
            return _empty(normalized, DatasetSplitStatus.REJECTED_SOURCE_DATASET, ("SOURCE_DATASET_NOT_FOUND",))
        examples = tuple(self._training.stream_examples_in_deterministic_order(normalized.source_dataset_build_id))
        try:
            validate_source_dataset(source, examples, normalized)
            failures = (
                *verify_dataset_fingerprints(self._training, normalized.source_dataset_build_id),
                *verify_label_consistency(self._training, normalized.source_dataset_build_id),
                *verify_no_temporal_leakage(self._training, normalized.source_dataset_build_id),
            )
            if failures:
                raise SourceDatasetVerificationError("|".join(failures))
        except (SourceDatasetVerificationError, SplitRequestValidationError) as exc:
            return _empty(normalized, DatasetSplitStatus.REJECTED_SOURCE_DATASET, ("SOURCE_DATASET_VERIFICATION_FAILED", str(exc)))

        split_id = f"historical-dataset-split-{request_fingerprint}"
        try:
            folds = construct_split_folds(split_id, normalized, examples, selected_policy)
        except SplitChronologyError as exc:
            return _empty(normalized, DatasetSplitStatus.REJECTED_CHRONOLOGY, ("SPLIT_CHRONOLOGY_REJECTED", str(exc)))
        except SplitPartitionSizeError as exc:
            return _empty(normalized, DatasetSplitStatus.REJECTED_PARTITION_SIZE, ("MINIMUM_PARTITION_SIZE_NOT_MET", str(exc)))

        aggregate = tuple(
            (partition.value, sum(dict(fold.achieved_counts)[partition.value] for fold in folds))
            for partition in Partition
        )
        exclusions = tuple(
            item.assignment_fingerprint
            for fold in folds for item in fold.assignments
            if item.partition.value.startswith("EXCLUDED_")
        )
        split_fingerprint = sha256_fingerprint({
            "request_fingerprint": request_fingerprint,
            "ordered_fold_fingerprints": tuple(fold.fold_fingerprint for fold in folds),
            "aggregate_counts": aggregate, "ordered_exclusions": exclusions,
            "source_dataset_fingerprint": normalized.source_dataset_fingerprint,
            "policy_version": normalized.split_policy_version,
        })
        snapshot = canonical_json({
            "command": asdict(normalized), "request_fingerprint": request_fingerprint,
            "split_fingerprint": split_fingerprint,
            "fold_fingerprints": tuple(fold.fold_fingerprint for fold in folds),
            "aggregate_counts": aggregate, "ordered_exclusions": exclusions,
        })
        prepared = PreparedDatasetSplit(
            split_id=split_id, command=normalized, request_fingerprint=request_fingerprint,
            split_fingerprint=split_fingerprint, folds=folds,
            aggregate_counts=aggregate, deterministic_split_snapshot=snapshot,
        )
        try:
            duplicate = self._splits.find_by_split_fingerprint(split_fingerprint)
            if duplicate is not None:
                return _outcome(duplicate, DatasetSplitStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_SPLIT_EXISTS",))
            self._splits.append_dataset_split(prepared)
        except DatasetSplitConflictError:
            return _outcome(prepared, DatasetSplitStatus.CONFLICT, ("IMMUTABLE_SPLIT_CONFLICT",))
        except DatasetSplitPersistenceError:
            return _outcome(prepared, DatasetSplitStatus.PERSISTENCE_FAILURE, ("ATOMIC_SPLIT_PERSISTENCE_FAILURE",))
        active_count = sum(dict(aggregate).get(name, 0) for name in ("TRAIN", "VALIDATION", "TEST"))
        status = DatasetSplitStatus.SPLIT_CREATED if active_count else DatasetSplitStatus.NO_ELIGIBLE_EXAMPLES
        reason = "SPLIT_PERSISTED" if active_count else "NO_ELIGIBLE_EXAMPLES"
        return _outcome(prepared, status, (reason,))


def create_historical_dataset_split(
    service: HistoricalDatasetSplitter,
    command: DatasetSplitCommand,
    *,
    policy: HistoricalDatasetSplitPolicy = DEFAULT_HISTORICAL_DATASET_SPLIT_POLICY,
) -> DatasetSplitOutcome:
    return service.create(command, policy=policy)


def _outcome(split: PreparedDatasetSplit, status: DatasetSplitStatus, reasons: tuple[str, ...]) -> DatasetSplitOutcome:
    counts = dict(split.aggregate_counts)
    active = counts.get("TRAIN", 0) + counts.get("VALIDATION", 0) + counts.get("TEST", 0)
    if active:
        train_ratio = _ratio(counts.get("TRAIN", 0), active)
        validation_ratio = _ratio(counts.get("VALIDATION", 0), active)
        ratios = (
            ("TRAIN", train_ratio), ("VALIDATION", validation_ratio),
            ("TEST", Decimal("1.000000") - train_ratio - validation_ratio),
        )
    else:
        ratios = tuple((name, Decimal("0.000000")) for name in ("TRAIN", "VALIDATION", "TEST"))
    ranges = []
    for name in ("TRAIN", "VALIDATION", "TEST"):
        values = tuple(
            item.kickoff_utc for fold in split.folds for item in fold.assignments if item.partition.value == name
        )
        ranges.append((name, min(values) if values else None, max(values) if values else None))
    return DatasetSplitOutcome(
        status=status, split_id=split.split_id, split_request_id=split.command.split_request_id,
        split_fingerprint=split.split_fingerprint,
        source_dataset_build_id=split.command.source_dataset_build_id,
        source_dataset_fingerprint=split.command.source_dataset_fingerprint,
        strategy=split.command.strategy.value, fold_count=len(split.folds),
        train_count=counts.get("TRAIN", 0), validation_count=counts.get("VALIDATION", 0),
        test_count=counts.get("TEST", 0), excluded_gap_count=counts.get("EXCLUDED_GAP", 0),
        excluded_filter_count=counts.get("EXCLUDED_FILTER", 0),
        excluded_boundary_count=counts.get("EXCLUDED_BOUNDARY_GROUP", 0),
        excluded_invalid_provenance_count=counts.get("EXCLUDED_INVALID_PROVENANCE", 0),
        actual_achieved_ratios=ratios, earliest_latest_kickoffs=tuple(ranges),
        ordered_reason_codes=reasons, policy_version=split.command.split_policy_version,
        split_timestamp=split.command.split_timestamp,
    )


def _empty(command, status, reasons) -> DatasetSplitOutcome:
    return DatasetSplitOutcome(
        status=status, split_id=None, split_request_id=command.split_request_id,
        split_fingerprint=None, source_dataset_build_id=command.source_dataset_build_id,
        source_dataset_fingerprint=command.source_dataset_fingerprint,
        strategy=command.strategy.value, fold_count=0, train_count=0, validation_count=0,
        test_count=0, excluded_gap_count=0, excluded_filter_count=0,
        excluded_boundary_count=0, excluded_invalid_provenance_count=0,
        actual_achieved_ratios=(), earliest_latest_kickoffs=(),
        ordered_reason_codes=reasons, policy_version=command.split_policy_version,
        split_timestamp=command.split_timestamp,
    )


def _rejected(command, policy, status, reasons) -> DatasetSplitOutcome:
    strategy = getattr(command, "strategy", "")
    strategy_value = strategy.value if hasattr(strategy, "value") else str(strategy)
    return DatasetSplitOutcome(
        status=status, split_id=None, split_request_id=getattr(command, "split_request_id", ""),
        split_fingerprint=None, source_dataset_build_id=getattr(command, "source_dataset_build_id", ""),
        source_dataset_fingerprint=getattr(command, "source_dataset_fingerprint", ""),
        strategy=strategy_value, fold_count=0, train_count=0, validation_count=0, test_count=0,
        excluded_gap_count=0, excluded_filter_count=0, excluded_boundary_count=0,
        excluded_invalid_provenance_count=0, actual_achieved_ratios=(), earliest_latest_kickoffs=(),
        ordered_reason_codes=reasons, policy_version=policy.version, split_timestamp=None,
    )


def _ratio(value: int, total: int) -> Decimal:
    return (Decimal(value) / Decimal(total)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN) if total else Decimal("0.000000")
