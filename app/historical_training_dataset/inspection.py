"""Read-only dataset inspection and independent integrity verification."""

from __future__ import annotations

from decimal import Decimal

from .chronology import verify_sources_strictly_prior
from .feature_projection import HISTORICAL_TRAINING_FEATURES_V1
from .fingerprint import sha256_fingerprint
from .labels import validate_labels
from .models import DatasetSummary, HistoricalTrainingExample, PreparedDatasetBuild
from .ports import HistoricalTrainingDatasetRepository
from .validation import validate_example


def summarize_dataset(repository: HistoricalTrainingDatasetRepository, dataset_build_id: str) -> DatasetSummary | None:
    build = repository.load_dataset_build(dataset_build_id)
    if build is None:
        return None
    scores = tuple(item.completeness_score for item in build.examples)
    counts = repository.count_examples_by_label(dataset_build_id)
    return DatasetSummary(
        dataset_build_id=dataset_build_id, dataset_name=build.command.dataset_name,
        source_match_count=build.source_match_count, included_count=len(build.examples),
        excluded_count=len(build.exclusions), completeness_minimum=min(scores) if scores else None,
        completeness_average=(sum(scores, Decimal(0)) / Decimal(len(scores))).quantize(Decimal("0.000001")) if scores else None,
        completeness_maximum=max(scores) if scores else None, positive_label_counts=counts,
    )


def inspect_training_example(repository: HistoricalTrainingDatasetRepository, training_example_id: str) -> HistoricalTrainingExample | None:
    return repository.load_training_example(training_example_id)


def verify_no_temporal_leakage(repository: HistoricalTrainingDatasetRepository, dataset_build_id: str) -> tuple[str, ...]:
    reasons = []
    for example in repository.stream_examples_in_deterministic_order(dataset_build_id):
        for reason in verify_sources_strictly_prior(example.historical_match_id, example.kickoff_utc, example.sources):
            reasons.append(f"{example.training_example_id}:{reason}")
    return tuple(reasons)


def verify_label_consistency(repository: HistoricalTrainingDatasetRepository, dataset_build_id: str) -> tuple[str, ...]:
    failures = []
    for example in repository.stream_examples_in_deterministic_order(dataset_build_id):
        try:
            validate_labels(example.labels)
        except Exception as exc:
            failures.append(f"{example.training_example_id}:{exc}")
    return tuple(failures)


def verify_dataset_fingerprints(repository: HistoricalTrainingDatasetRepository, dataset_build_id: str) -> tuple[str, ...]:
    build = repository.load_dataset_build(dataset_build_id)
    if build is None:
        return ("DATASET_BUILD_NOT_FOUND",)
    failures = []
    for example in build.examples:
        try:
            validate_example(example, len(HISTORICAL_TRAINING_FEATURES_V1))
        except Exception as exc:
            failures.append(f"{example.training_example_id}:{exc}")
        expected_example = sha256_fingerprint({
            "dataset_request_fingerprint": build.request_fingerprint,
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
        if expected_example != example.example_fingerprint:
            failures.append(f"{example.training_example_id}:EXAMPLE_FINGERPRINT_MISMATCH")
    expected = sha256_fingerprint({
        "request_fingerprint": build.request_fingerprint,
        "included_example_fingerprints": tuple(item.example_fingerprint for item in build.examples),
        "exclusions": build.exclusions,
        "feature_schema_version": build.command.feature_schema_version,
        "label_schema_version": build.command.label_schema_version,
        "policy_version": build.command.dataset_policy_version,
    })
    if expected != build.dataset_fingerprint:
        failures.append("DATASET_FINGERPRINT_MISMATCH")
    return tuple(failures)
