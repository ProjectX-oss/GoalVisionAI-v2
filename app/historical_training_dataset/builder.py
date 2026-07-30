"""Deterministic historical training dataset application service."""

from __future__ import annotations

from dataclasses import asdict, replace

from .chronology import match_order_key, strictly_prior_matches, verify_sources_strictly_prior
from .exceptions import (
    DatasetBuildConflictError,
    DatasetPersistenceError,
    DatasetRequestValidationError,
    SourceProvenanceError,
    TemporalLeakageError,
)
from .feature_projection import HISTORICAL_TRAINING_FEATURES_V1, project_features
from .live_feature_projection import project_live_features
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT
from .fingerprint import canonical_json, sha256_fingerprint
from .labels import generate_labels, validate_labels
from .models import (
    DatasetBuildCommand,
    DatasetBuildOutcome,
    DatasetBuildStatus,
    ExclusionReason,
    HistoricalSourceMatch,
    HistoricalTrainingExample,
    HistoricalTrainingExclusion,
    NormalizedDatasetBuildCommand,
    PreparedDatasetBuild,
)
from .policy import DEFAULT_HISTORICAL_TRAINING_POLICY, HistoricalTrainingDatasetPolicy
from .ports import HistoricalMatchSourceRepository, HistoricalTrainingDatasetRepository
from .validation import normalize_build_command, validate_example, validate_source_matches


class HistoricalTrainingDatasetBuilder:
    def __init__(
        self,
        historical_repository: HistoricalMatchSourceRepository,
        dataset_repository: HistoricalTrainingDatasetRepository,
        default_policy: HistoricalTrainingDatasetPolicy = DEFAULT_HISTORICAL_TRAINING_POLICY,
    ) -> None:
        self._historical_repository = historical_repository
        self._dataset_repository = dataset_repository
        self._default_policy = default_policy

    def build(
        self,
        command: DatasetBuildCommand,
        *,
        policy: HistoricalTrainingDatasetPolicy | None = None,
    ) -> DatasetBuildOutcome:
        selected_policy = policy or self._default_policy
        try:
            normalized = normalize_build_command(command, selected_policy)
        except (DatasetRequestValidationError, ValueError) as exc:
            return _rejection(command, selected_policy, DatasetBuildStatus.REJECTED_INVALID_REQUEST, "INVALID_BUILD_REQUEST", str(exc))

        request_fingerprint = sha256_fingerprint({"command": normalized})
        existing = self._dataset_repository.find_by_request_id(normalized.request_id)
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                return _outcome(existing, DatasetBuildStatus.CONFLICT, ("REQUEST_ID_CONFLICT",))
            return _outcome(existing, DatasetBuildStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_DATASET_BUILD_EXISTS",))

        try:
            matches = self._historical_repository.load_matches_for_imports(normalized.source_import_ids)
            validate_source_matches(matches)
        except (SourceProvenanceError, DatasetRequestValidationError, TemporalLeakageError) as exc:
            return _empty_outcome(
                normalized, DatasetBuildStatus.REJECTED_SOURCE_PROVENANCE,
                ("SOURCE_PROVENANCE_REJECTED", str(exc)),
            )

        matches = tuple(sorted(matches, key=match_order_key))
        targets = tuple(match for match in matches if _target_selected(match, normalized))
        examples_without_build: list[HistoricalTrainingExample] = []
        exclusions: list[HistoricalTrainingExclusion] = []
        for target in targets:
            prior = strictly_prior_matches(target, matches)
            home_count = sum(_involves(item, target.home_team_identity) for item in prior)
            away_count = sum(_involves(item, target.away_team_identity) for item in prior)
            if min(home_count, away_count) < selected_policy.minimum_prior_matches_per_team:
                exclusions.append(HistoricalTrainingExclusion(
                    historical_match_id=target.historical_match_id,
                    reason=ExclusionReason.INSUFFICIENT_HISTORY,
                    ordered_reason_codes=("MINIMUM_PRIOR_MATCHES_NOT_MET",),
                    detail=(("home_prior_matches", str(home_count)), ("away_prior_matches", str(away_count))),
                ))
                continue
            try:
                is_live_contract = (
                    selected_policy.feature_schema_version
                    == LIVE_MODEL_INPUT_CONTRACT.schema_version
                )
                projection = (
                    project_live_features(target, prior, selected_policy)
                    if is_live_contract
                    else project_features(target, prior, selected_policy)
                )
                leakage = verify_sources_strictly_prior(target.historical_match_id, target.kickoff_utc, projection.sources)
                if leakage:
                    raise TemporalLeakageError("|".join(leakage))
                labels = generate_labels(target)
                example_fingerprint = _example_fingerprint(
                    target, projection.values, projection.missingness_mask,
                    projection.completeness_score, labels, projection.sources,
                    normalized, request_fingerprint,
                )
                example = HistoricalTrainingExample(
                    training_example_id=f"historical-training-example-{example_fingerprint}",
                    dataset_build_id="PENDING",
                    historical_match_id=target.historical_match_id,
                    historical_match_fingerprint=target.match_fingerprint,
                    competition=target.competition,
                    season=target.season,
                    kickoff_utc=target.kickoff_utc,
                    home_team_identity=target.home_team_identity,
                    away_team_identity=target.away_team_identity,
                    ordered_feature_vector=projection.values,
                    missingness_mask=projection.missingness_mask,
                    completeness_score=projection.completeness_score,
                    feature_provenance=projection.provenance,
                    lookback_window_identity="LAST_3|LAST_5|LAST_10|SEASON_TO_DATE|HEAD_TO_HEAD_LAST_5|REST_7_14",
                    cutoff_timestamp=target.kickoff_utc,
                    historical_source_fingerprints=tuple(source.source_match_fingerprint for source in projection.sources),
                    labels=labels,
                    feature_schema_version=normalized.feature_schema_version,
                    label_schema_version=normalized.label_schema_version,
                    policy_version=normalized.dataset_policy_version,
                    example_fingerprint=example_fingerprint,
                    sources=projection.sources,
                )
                validate_example(
                    example,
                    LIVE_MODEL_INPUT_CONTRACT.feature_count
                    if is_live_contract
                    else len(HISTORICAL_TRAINING_FEATURES_V1),
                )
                validate_labels(example.labels)
                examples_without_build.append(example)
            except (SourceProvenanceError, TemporalLeakageError, ValueError) as exc:
                exclusions.append(HistoricalTrainingExclusion(
                    historical_match_id=target.historical_match_id,
                    reason=ExclusionReason.INVALID_PROVENANCE,
                    ordered_reason_codes=("INVALID_PREMATCH_PROVENANCE",),
                    detail=(("reason", str(exc)),),
                ))

        ordered_exclusions = tuple(sorted(exclusions, key=lambda item: (item.historical_match_id, item.reason.value)))
        example_fingerprints = tuple(item.example_fingerprint for item in examples_without_build)
        dataset_fingerprint = sha256_fingerprint({
            "request_fingerprint": request_fingerprint,
            "included_example_fingerprints": example_fingerprints,
            "exclusions": ordered_exclusions,
            "feature_schema_version": normalized.feature_schema_version,
            "label_schema_version": normalized.label_schema_version,
            "policy_version": normalized.dataset_policy_version,
        })
        dataset_build_id = f"historical-training-dataset-{dataset_fingerprint}"
        examples = tuple(replace(item, dataset_build_id=dataset_build_id) for item in examples_without_build)
        snapshot = canonical_json({
            "command": asdict(normalized),
            "request_fingerprint": request_fingerprint,
            "dataset_fingerprint": dataset_fingerprint,
            "source_match_count": len(matches),
            "example_fingerprints": tuple(item.example_fingerprint for item in examples),
            "exclusions": ordered_exclusions,
        })
        prepared = PreparedDatasetBuild(
            dataset_build_id=dataset_build_id,
            command=normalized,
            request_fingerprint=request_fingerprint,
            dataset_fingerprint=dataset_fingerprint,
            source_match_count=len(matches),
            examples=examples,
            exclusions=ordered_exclusions,
            deterministic_build_snapshot=snapshot,
        )
        try:
            duplicate = self._dataset_repository.find_by_dataset_fingerprint(dataset_fingerprint)
            if duplicate is not None:
                return _outcome(duplicate, DatasetBuildStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_DATASET_BUILD_EXISTS",))
            self._dataset_repository.append_dataset_build(prepared)
        except DatasetBuildConflictError:
            return _outcome(prepared, DatasetBuildStatus.CONFLICT, ("IMMUTABLE_DATASET_CONFLICT",))
        except DatasetPersistenceError:
            return _outcome(prepared, DatasetBuildStatus.PERSISTENCE_FAILURE, ("ATOMIC_PERSISTENCE_FAILURE",))
        status = DatasetBuildStatus.DATASET_BUILT if examples else DatasetBuildStatus.NO_ELIGIBLE_MATCHES
        reasons = ["DATASET_BUILD_PERSISTED" if examples else "NO_ELIGIBLE_MATCHES"]
        if any(any(item.missingness_mask) for item in examples):
            reasons.append("INCLUDED_WITH_MISSINGNESS")
        return _outcome(prepared, status, tuple(reasons))


def build_historical_training_dataset(
    service: HistoricalTrainingDatasetBuilder,
    command: DatasetBuildCommand,
    *,
    policy: HistoricalTrainingDatasetPolicy = DEFAULT_HISTORICAL_TRAINING_POLICY,
) -> DatasetBuildOutcome:
    return service.build(command, policy=policy)


def _example_fingerprint(target, values, mask, completeness, labels, sources, command, request_fingerprint) -> str:
    return sha256_fingerprint({
        "dataset_request_fingerprint": request_fingerprint,
        "historical_match_fingerprint": target.match_fingerprint,
        "strict_cutoff_timestamp": target.kickoff_utc,
        "ordered_sources": tuple((item.source_historical_match_id, item.source_match_fingerprint) for item in sources),
        "ordered_feature_vector": values,
        "missingness_mask": mask,
        "completeness_score": completeness,
        "labels": labels,
        "feature_schema_version": command.feature_schema_version,
        "label_schema_version": command.label_schema_version,
        "policy_version": command.dataset_policy_version,
    })


def _target_selected(match: HistoricalSourceMatch, command: NormalizedDatasetBuildCommand) -> bool:
    if command.competition_filters and match.competition_identity not in command.competition_filters:
        return False
    if command.season_filters and match.season not in command.season_filters:
        return False
    if command.kickoff_lower_bound is not None and match.kickoff_utc < command.kickoff_lower_bound:
        return False
    if command.kickoff_upper_bound is not None and match.kickoff_utc >= command.kickoff_upper_bound:
        return False
    return True


def _involves(match: HistoricalSourceMatch, team: str) -> bool:
    return team in (match.home_team_identity, match.away_team_identity)


def _outcome(build: PreparedDatasetBuild, status: DatasetBuildStatus, reasons: tuple[str, ...]) -> DatasetBuildOutcome:
    insufficient = sum(item.reason is ExclusionReason.INSUFFICIENT_HISTORY for item in build.exclusions)
    invalid = sum(item.reason is ExclusionReason.INVALID_PROVENANCE for item in build.exclusions)
    return DatasetBuildOutcome(
        status=status, dataset_build_id=build.dataset_build_id, request_id=build.command.request_id,
        dataset_fingerprint=build.dataset_fingerprint, source_import_ids=build.command.source_import_ids,
        total_source_matches=build.source_match_count, included_examples=len(build.examples),
        excluded_insufficient_history_count=insufficient, excluded_invalid_provenance_count=invalid,
        feature_schema_version=build.command.feature_schema_version,
        label_schema_version=build.command.label_schema_version,
        policy_version=build.command.dataset_policy_version, ordered_reason_codes=reasons,
        build_timestamp=build.command.build_timestamp,
    )


def _empty_outcome(command: NormalizedDatasetBuildCommand, status: DatasetBuildStatus, reasons: tuple[str, ...]) -> DatasetBuildOutcome:
    return DatasetBuildOutcome(
        status=status, dataset_build_id=None, request_id=command.request_id, dataset_fingerprint=None,
        source_import_ids=command.source_import_ids, total_source_matches=0, included_examples=0,
        excluded_insufficient_history_count=0, excluded_invalid_provenance_count=0,
        feature_schema_version=command.feature_schema_version, label_schema_version=command.label_schema_version,
        policy_version=command.dataset_policy_version, ordered_reason_codes=reasons,
        build_timestamp=command.build_timestamp,
    )


def _rejection(command, policy, status, code, explanation) -> DatasetBuildOutcome:
    return DatasetBuildOutcome(
        status=status, dataset_build_id=None,
        request_id=getattr(command, "request_id", ""), dataset_fingerprint=None,
        source_import_ids=tuple(getattr(command, "source_import_ids", ())), total_source_matches=0,
        included_examples=0, excluded_insufficient_history_count=0,
        excluded_invalid_provenance_count=0, feature_schema_version=policy.feature_schema_version,
        label_schema_version=policy.label_schema_version, policy_version=policy.version,
        ordered_reason_codes=(code, explanation), build_timestamp=None,
    )
