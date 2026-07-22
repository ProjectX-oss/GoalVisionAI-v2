"""Typed command and independently loaded source validation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from app.historical_training_dataset import HistoricalTrainingExample, PreparedDatasetBuild

from .exceptions import SourceDatasetVerificationError, SplitRequestValidationError
from .models import (
    DatasetSplitCommand, ExpandingWindow, ExplicitTimeBoundaries, GapConfiguration,
    MinimumPartitionSizes, NormalizedDatasetSplitCommand, RatioByChronology, SplitStrategy,
)
from .policy import HistoricalDatasetSplitPolicy, METADATA_VERSION


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


def normalize_split_command(
    command: DatasetSplitCommand,
    policy: HistoricalDatasetSplitPolicy,
) -> NormalizedDatasetSplitCommand:
    if not isinstance(command, DatasetSplitCommand):
        raise SplitRequestValidationError("A typed DatasetSplitCommand is required.")
    request_id = _identifier(command.split_request_id, "split request ID")
    split_name = _text(command.split_name, "split name")
    source_id = _identifier(command.source_dataset_build_id, "source dataset build ID")
    _fingerprint(command.source_dataset_fingerprint, "source dataset fingerprint")
    try:
        strategy = SplitStrategy(command.strategy)
    except (TypeError, ValueError) as exc:
        raise SplitRequestValidationError("Unsupported split strategy.") from exc
    if strategy.value not in policy.supported_strategies:
        raise SplitRequestValidationError("Unsupported split strategy.")
    if command.split_policy_version != policy.version:
        raise SplitRequestValidationError("Unsupported split policy version.")
    if command.equal_kickoff_policy != policy.equal_kickoff_policy:
        raise SplitRequestValidationError("Unsupported equal-kickoff policy.")
    if command.metadata_version != METADATA_VERSION:
        raise SplitRequestValidationError("Unsupported metadata version.")
    if not command.feature_schema_version or not command.label_schema_version:
        raise SplitRequestValidationError("Feature and label schemas are required.")
    if not isinstance(command.gaps, GapConfiguration) or min(
        command.gaps.train_to_validation_days,
        command.gaps.validation_to_test_days,
    ) < 0:
        raise SplitRequestValidationError("Gap days must be non-negative integers.")
    if any(type(value) is not int for value in asdict(command.gaps).values()):
        raise SplitRequestValidationError("Gap days must be integers.")
    sizes = command.minimum_partition_sizes
    if not isinstance(sizes, MinimumPartitionSizes) or any(type(value) is not int or value < 0 for value in asdict(sizes).values()):
        raise SplitRequestValidationError("Minimum partition sizes must be non-negative integers.")

    explicit: tuple[tuple[str, str | None], ...] = ()
    ratios: tuple[tuple[str, Decimal], ...] = ()
    expanding: tuple[tuple[str, str | int], ...] = ()
    if strategy is SplitStrategy.EXPLICIT_TIME_BOUNDARIES_V1:
        if command.maximum_folds is not None:
            raise SplitRequestValidationError("Maximum folds applies only to expanding-window strategy.")
        if not isinstance(command.explicit_boundaries, ExplicitTimeBoundaries) or command.ratios is not None or command.expanding_window is not None:
            raise SplitRequestValidationError("Explicit strategy requires only explicit boundaries.")
        value = command.explicit_boundaries
        train_end = normalize_utc(value.train_end_exclusive)
        validation_start = normalize_utc(value.validation_start_inclusive)
        validation_end = normalize_utc(value.validation_end_exclusive)
        test_start = normalize_utc(value.test_start_inclusive)
        test_end = normalize_utc(value.test_end_exclusive, optional=True)
        if not train_end <= validation_start < validation_end <= test_start:
            raise SplitRequestValidationError("Explicit boundaries overlap or are unordered.")
        if test_end is not None and test_start >= test_end:
            raise SplitRequestValidationError("Test end must be later than test start.")
        if _time(validation_start) - _time(train_end) != timedelta(days=command.gaps.train_to_validation_days):
            raise SplitRequestValidationError("Train-validation boundaries do not match the explicit gap.")
        if _time(test_start) - _time(validation_end) != timedelta(days=command.gaps.validation_to_test_days):
            raise SplitRequestValidationError("Validation-test boundaries do not match the explicit gap.")
        explicit = (
            ("train_end_exclusive", train_end), ("validation_start_inclusive", validation_start),
            ("validation_end_exclusive", validation_end), ("test_start_inclusive", test_start),
            ("test_end_exclusive", test_end),
        )
    elif strategy is SplitStrategy.RATIO_BY_CHRONOLOGY_V1:
        if command.maximum_folds is not None:
            raise SplitRequestValidationError("Maximum folds applies only to expanding-window strategy.")
        if not isinstance(command.ratios, RatioByChronology) or command.explicit_boundaries is not None or command.expanding_window is not None:
            raise SplitRequestValidationError("Ratio strategy requires only ratio configuration.")
        ratios = (
            ("TRAIN", _decimal(command.ratios.train_ratio, "train ratio")),
            ("VALIDATION", _decimal(command.ratios.validation_ratio, "validation ratio")),
            ("TEST", _decimal(command.ratios.test_ratio, "test ratio")),
        )
        if any(value <= 0 or value >= 1 for _, value in ratios) or sum((value for _, value in ratios), Decimal(0)) != Decimal(1):
            raise SplitRequestValidationError("Ratios must be positive and sum exactly to one.")
    else:
        if not isinstance(command.expanding_window, ExpandingWindow) or command.explicit_boundaries is not None or command.ratios is not None:
            raise SplitRequestValidationError("Expanding strategy requires only expanding-window configuration.")
        value = command.expanding_window
        integers = (value.validation_window_days, value.test_window_days, value.step_days, value.maximum_folds)
        if any(type(item) is not int or item < 1 for item in integers):
            raise SplitRequestValidationError("Expanding-window durations and maximum folds must be positive integers.")
        if command.maximum_folds is not None and command.maximum_folds != value.maximum_folds:
            raise SplitRequestValidationError("Maximum-fold declarations conflict.")
        expanding = (
            ("initial_train_end_exclusive", normalize_utc(value.initial_train_end_exclusive)),
            ("validation_window_days", value.validation_window_days),
            ("test_window_days", value.test_window_days),
            ("step_days", value.step_days),
            ("maximum_folds", value.maximum_folds),
        )
    competitions = tuple(sorted({_text(value, "competition filter").casefold() for value in command.competition_filters}))
    seasons = tuple(sorted({_text(value, "season filter") for value in command.season_filters}))
    lower = normalize_utc(command.kickoff_lower_bound, optional=True)
    upper = normalize_utc(command.kickoff_upper_bound, optional=True)
    if lower is not None and upper is not None and lower >= upper:
        raise SplitRequestValidationError("Kickoff filter bounds are unordered.")
    return NormalizedDatasetSplitCommand(
        split_request_id=request_id, split_name=split_name, source_dataset_build_id=source_id,
        source_dataset_fingerprint=command.source_dataset_fingerprint, strategy=strategy,
        explicit_boundaries=explicit, ratios=ratios, expanding_window=expanding,
        gaps=command.gaps, minimum_partition_sizes=sizes,
        equal_kickoff_policy=command.equal_kickoff_policy,
        maximum_folds=command.maximum_folds,
        split_timestamp=normalize_utc(command.split_timestamp),
        feature_schema_version=command.feature_schema_version,
        label_schema_version=command.label_schema_version,
        split_policy_version=command.split_policy_version, metadata_version=command.metadata_version,
        competition_filters=competitions, season_filters=seasons,
        kickoff_lower_bound=lower, kickoff_upper_bound=upper,
    )


def validate_source_dataset(
    build: PreparedDatasetBuild,
    examples: tuple[HistoricalTrainingExample, ...],
    command: NormalizedDatasetSplitCommand,
) -> None:
    if build.dataset_build_id != command.source_dataset_build_id:
        raise SourceDatasetVerificationError("Source dataset identity mismatch.")
    if build.dataset_fingerprint != command.source_dataset_fingerprint:
        raise SourceDatasetVerificationError("Source dataset fingerprint mismatch.")
    if build.command.feature_schema_version != command.feature_schema_version:
        raise SourceDatasetVerificationError("Source feature schema mismatch.")
    if build.command.label_schema_version != command.label_schema_version:
        raise SourceDatasetVerificationError("Source label schema mismatch.")
    ids: set[str] = set()
    fingerprints: set[str] = set()
    expected_order = tuple(sorted(
        examples,
        key=lambda item: (
            item.kickoff_utc, item.competition, item.historical_match_id,
            item.training_example_id,
        ),
    ))
    if examples != expected_order:
        raise SourceDatasetVerificationError("Source example ordering is not deterministic.")
    for example in examples:
        if example.training_example_id in ids:
            raise SourceDatasetVerificationError("Duplicate training example ID.")
        if example.example_fingerprint in fingerprints:
            raise SourceDatasetVerificationError("Duplicate training example fingerprint.")
        ids.add(example.training_example_id)
        fingerprints.add(example.example_fingerprint)
        kickoff = normalize_utc(example.kickoff_utc)
        if kickoff != example.kickoff_utc:
            raise SourceDatasetVerificationError("Example kickoff is not canonical UTC.")
        if example.dataset_build_id != build.dataset_build_id:
            raise SourceDatasetVerificationError("Example source dataset linkage is invalid.")
        if example.feature_schema_version != command.feature_schema_version:
            raise SourceDatasetVerificationError("Example feature schema mismatch.")
        if example.label_schema_version != command.label_schema_version:
            raise SourceDatasetVerificationError("Example label schema mismatch.")


def normalize_utc(value: datetime | str | None, *, optional: bool = False) -> str | None:
    if value is None:
        if optional:
            return None
        raise SplitRequestValidationError("A timezone-aware timestamp is required.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise SplitRequestValidationError("Timestamp is malformed.") from exc
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SplitRequestValidationError("Timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _decimal(value: Decimal | str | int, label: str) -> Decimal:
    if isinstance(value, float) or isinstance(value, bool):
        raise SplitRequestValidationError(f"{label.title()} must be Decimal-safe.")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SplitRequestValidationError(f"{label.title()} is malformed.") from exc
    if not result.is_finite():
        raise SplitRequestValidationError(f"{label.title()} must be finite.")
    return result


def _identifier(value: object, label: str) -> str:
    text = _text(value, label)
    if not _IDENTIFIER.fullmatch(text):
        raise SplitRequestValidationError(f"{label.title()} is malformed.")
    return text


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SplitRequestValidationError(f"{label.title()} must be text.")
    text = " ".join(unicodedata.normalize("NFKC", value).split())
    if not text or len(text) > 200:
        raise SplitRequestValidationError(f"{label.title()} is empty or too long.")
    return text


def _fingerprint(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise SplitRequestValidationError(f"{label.title()} is malformed.")


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
