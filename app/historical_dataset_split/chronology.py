"""Equal-kickoff grouping and independent partition safety checks."""

from collections import defaultdict

from app.historical_training_dataset import HistoricalTrainingExample

from .exceptions import SplitChronologyError
from .models import DatasetSplitFold, Partition, PartitionAssignment


ACTIVE_PARTITIONS = (Partition.TRAIN, Partition.VALIDATION, Partition.TEST)


def example_order_key(example: HistoricalTrainingExample) -> tuple[str, str, str, str]:
    return (example.kickoff_utc, example.competition, example.historical_match_id, example.training_example_id)


def group_equal_kickoffs(
    examples: tuple[HistoricalTrainingExample, ...],
) -> tuple[tuple[HistoricalTrainingExample, ...], ...]:
    ordered = tuple(sorted(examples, key=example_order_key))
    groups: list[list[HistoricalTrainingExample]] = []
    for example in ordered:
        if not groups or groups[-1][0].kickoff_utc != example.kickoff_utc:
            groups.append([])
        groups[-1].append(example)
    return tuple(tuple(group) for group in groups)


def verify_fold_chronology(fold: DatasetSplitFold) -> tuple[str, ...]:
    failures: list[str] = []
    by_partition = {
        partition: tuple(item for item in fold.assignments if item.partition is partition)
        for partition in ACTIVE_PARTITIONS
    }
    train, validation, test = (by_partition[item] for item in ACTIVE_PARTITIONS)
    if train and validation and max(item.kickoff_utc for item in train) >= min(item.kickoff_utc for item in validation):
        failures.append("TRAIN_NOT_STRICTLY_BEFORE_VALIDATION")
    if validation and test and max(item.kickoff_utc for item in validation) >= min(item.kickoff_utc for item in test):
        failures.append("VALIDATION_NOT_STRICTLY_BEFORE_TEST")
    gaps = tuple(item for item in fold.assignments if item.partition is Partition.EXCLUDED_GAP)
    for gap in gaps:
        between_train_validation = bool(
            train and validation
            and max(item.kickoff_utc for item in train) < gap.kickoff_utc
            < min(item.kickoff_utc for item in validation)
        )
        between_validation_test = bool(
            validation and test
            and max(item.kickoff_utc for item in validation) < gap.kickoff_utc
            < min(item.kickoff_utc for item in test)
        )
        if not (between_train_validation or between_validation_test):
            failures.append(f"GAP_OUTSIDE_PARTITION_BUFFER:{gap.training_example_id}")
    return tuple(failures)


def verify_fold_exclusivity(fold: DatasetSplitFold) -> tuple[str, ...]:
    seen: set[str] = set()
    failures = []
    for item in fold.assignments:
        if item.training_example_id in seen:
            failures.append(f"DUPLICATE_ASSIGNMENT:{item.training_example_id}")
        seen.add(item.training_example_id)
    return tuple(failures)


def verify_equal_kickoff_assignments(fold: DatasetSplitFold) -> tuple[str, ...]:
    partitions: dict[str, set[Partition]] = defaultdict(set)
    for item in fold.assignments:
        partitions[item.kickoff_utc].add(item.partition)
    failures = []
    for kickoff, values in sorted(partitions.items()):
        if len(values) > 1:
            failures.append(f"EQUAL_KICKOFF_SPLIT:{kickoff}")
    return tuple(failures)


def assert_fold_safe(fold: DatasetSplitFold) -> None:
    failures = (*verify_fold_chronology(fold), *verify_fold_exclusivity(fold), *verify_equal_kickoff_assignments(fold))
    if failures:
        raise SplitChronologyError("|".join(failures))
