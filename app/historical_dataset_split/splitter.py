"""Deterministic explicit, ratio, and expanding-window partition construction."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN

from app.historical_training_dataset import HistoricalTrainingExample

from .chronology import ACTIVE_PARTITIONS, assert_fold_safe, example_order_key, group_equal_kickoffs
from .exceptions import SplitPartitionSizeError
from .fingerprint import sha256_fingerprint
from .models import (
    DatasetSplitFold, NormalizedDatasetSplitCommand, Partition, PartitionAssignment, SplitStrategy,
)
from .policy import HistoricalDatasetSplitPolicy


def construct_split_folds(
    split_id: str,
    command: NormalizedDatasetSplitCommand,
    examples: tuple[HistoricalTrainingExample, ...],
    policy: HistoricalDatasetSplitPolicy,
) -> tuple[DatasetSplitFold, ...]:
    ordered = tuple(sorted(examples, key=example_order_key))
    overrides: dict[str, tuple[Partition, str]] = {}
    eligible_items: list[HistoricalTrainingExample] = []
    for group in group_equal_kickoffs(ordered):
        selected = tuple(_selected(item, command) for item in group)
        if all(selected):
            eligible_items.extend(group)
        elif any(selected):
            for item in group:
                overrides[item.training_example_id] = (
                    Partition.EXCLUDED_BOUNDARY_GROUP,
                    "FILTER_SPLITS_EQUAL_KICKOFF_GROUP",
                )
        else:
            for item in group:
                overrides[item.training_example_id] = (
                    Partition.EXCLUDED_FILTER,
                    "FILTERED_BY_SPLIT_COMMAND",
                )
    eligible = tuple(eligible_items)
    if not eligible:
        return (_finalize_fold(
            split_id, 0, command, ordered,
            lambda item: overrides[item.training_example_id],
            (), (), (), policy,
        ),)
    if command.strategy is SplitStrategy.EXPLICIT_TIME_BOUNDARIES_V1:
        folds = (_explicit_fold(split_id, command, ordered, overrides, policy),)
    elif command.strategy is SplitStrategy.RATIO_BY_CHRONOLOGY_V1:
        folds = (_ratio_fold(split_id, command, ordered, eligible, overrides, policy),)
    else:
        folds = _expanding_folds(split_id, command, ordered, eligible, overrides, policy)
    for fold in folds:
        assert_fold_safe(fold)
        _verify_minimum_sizes(fold, command)
    return folds


def _explicit_fold(split_id, command, ordered, overrides, policy) -> DatasetSplitFold:
    boundaries = dict(command.explicit_boundaries)
    train_end = boundaries["train_end_exclusive"]
    validation_start = boundaries["validation_start_inclusive"]
    validation_end = boundaries["validation_end_exclusive"]
    test_start = boundaries["test_start_inclusive"]
    test_end = boundaries["test_end_exclusive"]

    def classify(item: HistoricalTrainingExample) -> tuple[Partition, str | None]:
        if item.training_example_id in overrides:
            return overrides[item.training_example_id]
        kickoff = item.kickoff_utc
        if kickoff < train_end:
            return Partition.TRAIN, None
        if kickoff < validation_start:
            return Partition.EXCLUDED_GAP, "TRAIN_VALIDATION_GAP"
        if kickoff < validation_end:
            return Partition.VALIDATION, None
        if kickoff < test_start:
            return Partition.EXCLUDED_GAP, "VALIDATION_TEST_GAP"
        if test_end is None or kickoff < test_end:
            return Partition.TEST, None
        return Partition.EXCLUDED_BOUNDARY_GROUP, "OUTSIDE_EXPLICIT_BOUNDARIES"

    return _finalize_fold(
        split_id, 0, command, ordered, classify,
        (("end_exclusive", train_end),),
        (("start_inclusive", validation_start), ("end_exclusive", validation_end)),
        (("start_inclusive", test_start), ("end_exclusive", test_end)),
        policy,
    )


def _ratio_fold(split_id, command, ordered, eligible, overrides, policy) -> DatasetSplitFold:
    groups = group_equal_kickoffs(eligible)
    if len(groups) < 3:
        raise SplitPartitionSizeError("Ratio splitting requires at least three distinct kickoff groups.")
    ratios = dict(command.ratios)
    total = len(eligible)
    best: tuple[Decimal, Decimal, int, int] | None = None
    for first in range(1, len(groups) - 1):
        train_count = sum(len(group) for group in groups[:first])
        for second in range(first + 1, len(groups)):
            validation_count = sum(len(group) for group in groups[first:second])
            score = (
                abs(Decimal(train_count) / Decimal(total) - ratios["TRAIN"]),
                abs(Decimal(validation_count) / Decimal(total) - ratios["VALIDATION"]),
                first,
                second,
            )
            if best is None or score < best:
                best = score
    assert best is not None
    first, second = best[2], best[3]
    train_ids = {item.training_example_id for group in groups[:first] for item in group}
    validation_ids = {item.training_example_id for group in groups[first:second] for item in group}
    test_ids = {item.training_example_id for group in groups[second:] for item in group}
    validation_start = groups[first][0].kickoff_utc
    test_start = groups[second][0].kickoff_utc
    train_gap_start = _iso(_time(validation_start) - timedelta(days=command.gaps.train_to_validation_days))
    validation_gap_start = _iso(_time(test_start) - timedelta(days=command.gaps.validation_to_test_days))

    def classify(item: HistoricalTrainingExample) -> tuple[Partition, str | None]:
        if item.training_example_id in overrides:
            return overrides[item.training_example_id]
        if item.training_example_id in train_ids:
            if item.kickoff_utc >= train_gap_start:
                return Partition.EXCLUDED_GAP, "TRAIN_VALIDATION_GAP"
            return Partition.TRAIN, None
        if item.training_example_id in validation_ids:
            if item.kickoff_utc >= validation_gap_start:
                return Partition.EXCLUDED_GAP, "VALIDATION_TEST_GAP"
            return Partition.VALIDATION, None
        if item.training_example_id in test_ids:
            return Partition.TEST, None
        return Partition.EXCLUDED_BOUNDARY_GROUP, "RATIO_BOUNDARY_GROUP"

    return _finalize_fold(
        split_id, 0, command, ordered, classify,
        (("ratio_target", str(ratios["TRAIN"])), ("boundary_exclusive", validation_start)),
        (("ratio_target", str(ratios["VALIDATION"])), ("start_inclusive", validation_start), ("end_exclusive", test_start)),
        (("ratio_target", str(ratios["TEST"])), ("start_inclusive", test_start)),
        policy,
    )


def _expanding_folds(split_id, command, ordered, eligible, overrides, policy) -> tuple[DatasetSplitFold, ...]:
    config = dict(command.expanding_window)
    initial = _time(str(config["initial_train_end_exclusive"]))
    latest = max(_time(item.kickoff_utc) for item in eligible)
    folds = []
    for index in range(int(config["maximum_folds"])):
        train_end = initial + timedelta(days=int(config["step_days"]) * index)
        validation_start = train_end + timedelta(days=command.gaps.train_to_validation_days)
        validation_end = validation_start + timedelta(days=int(config["validation_window_days"]))
        test_start = validation_end + timedelta(days=command.gaps.validation_to_test_days)
        test_end = test_start + timedelta(days=int(config["test_window_days"]))
        if test_start > latest:
            break

        def classify(item, train_end=train_end, validation_start=validation_start, validation_end=validation_end, test_start=test_start, test_end=test_end):
            if item.training_example_id in overrides:
                return overrides[item.training_example_id]
            kickoff = _time(item.kickoff_utc)
            if kickoff < train_end:
                return Partition.TRAIN, None
            if kickoff < validation_start:
                return Partition.EXCLUDED_GAP, "TRAIN_VALIDATION_GAP"
            if kickoff < validation_end:
                return Partition.VALIDATION, None
            if kickoff < test_start:
                return Partition.EXCLUDED_GAP, "VALIDATION_TEST_GAP"
            if kickoff < test_end:
                return Partition.TEST, None
            return Partition.EXCLUDED_BOUNDARY_GROUP, "OUTSIDE_FOLD_WINDOW"

        folds.append(_finalize_fold(
            split_id, index, command, ordered, classify,
            (("end_exclusive", _iso(train_end)),),
            (("start_inclusive", _iso(validation_start)), ("end_exclusive", _iso(validation_end))),
            (("start_inclusive", _iso(test_start)), ("end_exclusive", _iso(test_end))),
            policy,
        ))
    return tuple(folds)


def _finalize_fold(
    split_id, index, command, ordered, classify,
    train_boundary, validation_boundary, test_boundary, policy,
) -> DatasetSplitFold:
    fold_identity = sha256_fingerprint({"split_id": split_id, "fold_index": index})
    fold_id = f"historical-dataset-split-fold-{fold_identity}"
    assignments = []
    for order, example in enumerate(ordered):
        partition, exclusion = classify(example)
        assignment_fingerprint = sha256_fingerprint({
            "split_id": split_id, "fold_id": fold_id,
            "training_example_id": example.training_example_id,
            "example_fingerprint": example.example_fingerprint,
            "kickoff": example.kickoff_utc, "partition": partition,
            "assignment_order": order, "exclusion_reason": exclusion,
            "policy_version": policy.version,
        })
        assignments.append(PartitionAssignment(
            assignment_id=f"historical-dataset-assignment-{assignment_fingerprint}",
            split_id=split_id, fold_id=fold_id,
            training_example_id=example.training_example_id,
            historical_match_id=example.historical_match_id,
            kickoff_utc=example.kickoff_utc, competition=example.competition, season=example.season,
            partition=partition, assignment_order=order,
            example_fingerprint=example.example_fingerprint,
            assignment_fingerprint=assignment_fingerprint, exclusion_reason=exclusion,
        ))
    assignments_tuple = tuple(assignments)
    counts = tuple((partition.value, sum(item.partition is partition for item in assignments_tuple)) for partition in Partition)
    active_total = sum(dict(counts)[item.value] for item in ACTIVE_PARTITIONS)
    ratios = _ratios(dict(counts), active_total)
    kickoffs = tuple(
        (partition.value, *_range(tuple(item.kickoff_utc for item in assignments_tuple if item.partition is partition)))
        for partition in ACTIVE_PARTITIONS
    )
    fold_fingerprint = sha256_fingerprint({
        "fold_identity": (fold_id, index),
        "ordered_assignment_fingerprints": tuple(item.assignment_fingerprint for item in assignments_tuple),
        "boundaries": (train_boundary, validation_boundary, test_boundary),
        "achieved_counts": counts, "achieved_ratios": ratios,
        "policy_version": policy.version,
    })
    return DatasetSplitFold(
        fold_id=fold_id, split_id=split_id, fold_index=index,
        fold_fingerprint=fold_fingerprint,
        train_boundary=tuple(train_boundary), validation_boundary=tuple(validation_boundary),
        test_boundary=tuple(test_boundary), assignments=assignments_tuple,
        achieved_counts=counts, achieved_ratios=ratios, earliest_latest_kickoffs=kickoffs,
    )


def _verify_minimum_sizes(fold: DatasetSplitFold, command: NormalizedDatasetSplitCommand) -> None:
    counts = dict(fold.achieved_counts)
    minimums = command.minimum_partition_sizes
    failures = []
    for partition, minimum in ((Partition.TRAIN, minimums.train), (Partition.VALIDATION, minimums.validation), (Partition.TEST, minimums.test)):
        if counts[partition.value] < minimum:
            failures.append(f"{partition.value}_BELOW_MINIMUM")
    if failures:
        raise SplitPartitionSizeError("|".join(failures))


def _selected(example: HistoricalTrainingExample, command: NormalizedDatasetSplitCommand) -> bool:
    if command.competition_filters and example.competition.casefold() not in command.competition_filters:
        return False
    if command.season_filters and example.season not in command.season_filters:
        return False
    if command.kickoff_lower_bound is not None and example.kickoff_utc < command.kickoff_lower_bound:
        return False
    if command.kickoff_upper_bound is not None and example.kickoff_utc >= command.kickoff_upper_bound:
        return False
    return True


def _ratio(value: int, total: int) -> Decimal:
    if total == 0:
        return Decimal("0.000000")
    return (Decimal(value) / Decimal(total)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)


def _ratios(counts: dict[str, int], total: int) -> tuple[tuple[str, Decimal], ...]:
    if total == 0:
        return tuple((partition.value, Decimal("0.000000")) for partition in ACTIVE_PARTITIONS)
    train = _ratio(counts["TRAIN"], total)
    validation = _ratio(counts["VALIDATION"], total)
    test = Decimal("1.000000") - train - validation
    return (("TRAIN", train), ("VALIDATION", validation), ("TEST", test))


def _range(values: tuple[str, ...]) -> tuple[str | None, str | None]:
    return (min(values), max(values)) if values else (None, None)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
