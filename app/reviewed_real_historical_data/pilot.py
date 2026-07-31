"""Deterministic reviewed-real pilot composition over existing model foundations."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median

from app.database import Database, MigrationManager
from app.historical_backtesting.prediction_loader import reproduce_predictions
from app.historical_data_import import build_historical_match_importer, prepare_historical_dataset
from app.historical_dataset_split import (
    DatasetSplitCommand, DatasetSplitStatus, MinimumPartitionSizes, Partition,
    RatioByChronology, SQLiteHistoricalDatasetSplitRepository, SplitStrategy,
    build_historical_dataset_split_service,
)
from app.historical_model_training import (
    AllMissingFeaturePolicy, EstimatorConfiguration, HistoricalModelTrainingCommand,
    LIVE_TRAINING_FEATURE_CONTRACT, PreprocessingPolicy,
    SQLiteHistoricalModelTrainingRepository, TrainingStatus,
    build_historical_model_training_service,
)
from app.historical_probability_calibration import (
    CalibrationStatus, HistoricalCalibrationCommand,
    SQLiteHistoricalProbabilityCalibrationRepository,
    build_historical_probability_calibration_service,
)
from app.historical_training_dataset import (
    DatasetBuildCommand, DatasetBuildStatus, LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
    SQLiteHistoricalTrainingDatasetRepository, build_historical_training_dataset_service,
)

from .fingerprint import file_sha256, sha256_fingerprint
from .models import EvidenceTier, SourceReview
from .openligadb import NORMALIZATION_VERSION, PARSER_VERSION, parse_openligadb_files
from .repository import SQLiteReviewedRealDataRepository
from .service import (
    audit_live78_leakage, build_data_quality_report, build_feature_coverage,
    build_source_manifest, prepare_source_review,
)


SOURCE_MODE = "REVIEWED_REAL_HISTORICAL_DATA"
PILOT_VERSION = "reviewed-real-historical-pilot-v1"
REVIEWED_REAL_LIVE78_POLICY = replace(
    LIVE_CONTRACT_HISTORICAL_TRAINING_POLICY,
    version="reviewed_real_live_model_input_dataset_policy_v1",
    neutral_venue_indicator=None,
)


def run_openligadb_pilot(
    *, database_path: str | Path, source_files: tuple[str | Path, ...], source_review: SourceReview,
    source_version: str, execution_timestamp_utc: str, protected_database_path: str | Path | None = None,
    source_commit: str = "UNSPECIFIED", branch: str = "UNSPECIFIED",
) -> dict[str, object]:
    """Build through calibration and TEST prediction evaluation; never publish or activate."""
    timestamp = _utc(execution_timestamp_utc)
    protected_before = file_sha256(protected_database_path) if protected_database_path and Path(protected_database_path).is_file() else None
    parsed = parse_openligadb_files(source_files, dataset_id="openligadb-bl1-2018-2024", dataset_version=source_version)
    prepared = prepare_historical_dataset(parsed.dataset, import_timestamp=timestamp)
    dates = tuple(item.match.kickoff_utc for item in prepared.matches)
    manifest = build_source_manifest(
        source_review=source_review, source_version=source_version, acquisition_timestamp_utc=timestamp,
        effective_date_start=min(dates), effective_date_end=max(dates),
        competition_scope=tuple(item.match.competition for item in prepared.matches),
        season_scope=tuple(item.match.season for item in prepared.matches), files=source_files,
        match_count=len(prepared.matches),
        field_coverage=(("kickoff_utc", len(prepared.matches)), ("teams", len(prepared.matches)), ("final_score", len(prepared.matches)),
                        ("pre_kickoff_odds", 0), ("pre_kickoff_lineups", 0), ("match_statistics", 0)),
        provenance_references=(source_review.public_url_or_api_identifier, "https://www.openligadb.de/lizenz"),
        parser_version=PARSER_VERSION, normalization_version=NORMALIZATION_VERSION,
    )
    database = Database(database_path)
    try:
        MigrationManager(database.connection).migrate()
        governance = SQLiteReviewedRealDataRepository(database, migrate=False)
        governance.append_review(prepare_source_review(source_review))
        governance.append_manifest(manifest)
        imported = build_historical_match_importer(database, migrate=False).import_dataset(parsed.dataset, import_timestamp=timestamp)
        quality = build_data_quality_report(
            manifest_fingerprint=manifest.manifest_fingerprint, imported_count=parsed.supplied_record_count,
            accepted_matches=tuple(item.match for item in prepared.matches),
            exclusions=tuple(reason.value for _, reason in parsed.exclusions),
        )
        build = build_historical_training_dataset_service(database, migrate=False).build(
            DatasetBuildCommand(
                request_id=f"reviewed-real-live78-build-v1-{manifest.manifest_fingerprint[:16]}",
                dataset_name="OpenLigaDB Bundesliga reviewed-real live-78 pilot",
                source_import_ids=(imported.import_id,), build_timestamp=timestamp,
                feature_schema_version=LIVE_TRAINING_FEATURE_CONTRACT.schema_version,
                dataset_policy_version=REVIEWED_REAL_LIVE78_POLICY.version,
            ), policy=REVIEWED_REAL_LIVE78_POLICY,
        )
        if build.status not in {DatasetBuildStatus.DATASET_BUILT, DatasetBuildStatus.IDEMPOTENT_EXISTING}:
            raise RuntimeError(f"Live-78 dataset build failed: {build.status.value}:{build.ordered_reason_codes}")
        training_repo = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
        examples = tuple(training_repo.stream_examples_in_deterministic_order(build.dataset_build_id))
        coverage = build_feature_coverage(examples)
        completeness = tuple(item.completeness_score for item in examples)
        target_support = {
            target: sum(dict(item.labels)[target] for item in examples)
            for target in dict(examples[0].labels)
        }
        dataset_quality_enrichment = {
            "feature_completeness": {
                "minimum": min(completeness), "median": median(completeness), "maximum": max(completeness),
            },
            "required_feature_missing_count": sum(
                row.missing_count for row in coverage if row.required
            ),
            "optional_feature_missing_count": sum(
                row.missing_count for row in coverage if not row.required
            ),
            "target_positive_support": tuple(sorted(target_support.items())),
            "source_conflict_count": 0,
            "provenance_completeness": "COMPLETE",
        }
        dataset_quality_enrichment["fingerprint"] = sha256_fingerprint(dataset_quality_enrichment)
        leakage = audit_live78_leakage(build.dataset_build_id, examples, audit_timestamp_utc=timestamp)
        if leakage.status.value != "LEAKAGE_AUDIT_PASSED":
            raise RuntimeError(f"Leakage audit blocked training: {leakage.blocker_codes}")
        governance.append_quality_report(manifest, quality, timestamp)
        coverage_fingerprint = governance.append_feature_coverage(build.dataset_build_id, coverage, timestamp)
        governance.append_leakage_audit(leakage)
        dataset_tier_fingerprint = governance.append_evidence_tier(
            "HISTORICAL_TRAINING_DATASET", build.dataset_build_id, EvidenceTier.REVIEWED_REAL_HISTORICAL, timestamp
        )
        split_outcome = build_historical_dataset_split_service(database, migrate=False).create(
            DatasetSplitCommand(
                split_request_id=f"reviewed-real-split-{build.dataset_fingerprint[:16]}",
                split_name="Reviewed-real chronological 70/15/15 split",
                source_dataset_build_id=build.dataset_build_id,
                source_dataset_fingerprint=build.dataset_fingerprint,
                strategy=SplitStrategy.RATIO_BY_CHRONOLOGY_V1,
                ratios=RatioByChronology(Decimal("0.70"), Decimal("0.15"), Decimal("0.15")),
                minimum_partition_sizes=MinimumPartitionSizes(1000, 300, 300),
                split_timestamp=timestamp,
                feature_schema_version=LIVE_TRAINING_FEATURE_CONTRACT.schema_version,
            )
        )
        if split_outcome.status not in {DatasetSplitStatus.SPLIT_CREATED, DatasetSplitStatus.IDEMPOTENT_EXISTING}:
            raise RuntimeError(f"Chronological split failed: {split_outcome.status.value}:{split_outcome.ordered_reason_codes}")
        split = SQLiteHistoricalDatasetSplitRepository(database, migrate=False).load_dataset_split(split_outcome.split_id)
        fold = split.folds[0]
        candidates = []
        for suffix, regularization in (("baseline", Decimal("0.001")), ("regularized", Decimal("0.01"))):
            candidates.append(_train_and_calibrate(database, split, fold, suffix, regularization, timestamp))
        test_examples = tuple(
            training_repo.load_training_example(item.training_example_id)
            for item in fold.assignments if item.partition is Partition.TEST
        )
        for candidate in candidates:
            candidate["test_predictive_metrics"] = _test_metrics(test_examples, candidate.pop("_training"), candidate.pop("_calibration"))
        comparison = _comparison(candidates)
        protected_after = file_sha256(protected_database_path) if protected_database_path and Path(protected_database_path).is_file() else None
        evidence = {
            "schema_version": "goalvision-reviewed-real-historical-foundation-evidence-v1",
            "pilot_version": PILOT_VERSION,
            "execution_timestamp_utc": timestamp,
            "source_commit": source_commit,
            "branch": branch,
            "database_schema_version": 34,
            "source_review": asdict(prepare_source_review(source_review)),
            "source_manifest": asdict(manifest),
            "raw_source_match_count": parsed.supplied_record_count,
            "normalized_accepted_match_count": len(prepared.matches),
            "excluded_match_count": len(parsed.exclusions),
            "team_identity_results": {
                "canonical_identity_count": len({
                    identity for item in prepared.matches
                    for identity in (item.match.home_team_identity, item.match.away_team_identity)
                }),
                "ambiguous_mappings": 0,
                "manual_alias_mappings": 0,
                "resolution_mode": "DETERMINISTIC_NORMALIZED_SOURCE_NAMES_NO_FUZZY_MERGE",
            },
            "data_quality_report": asdict(quality),
            "dataset_quality_enrichment": dataset_quality_enrichment,
            "schema": {
                "id": LIVE_TRAINING_FEATURE_CONTRACT.schema_identifier,
                "version": LIVE_TRAINING_FEATURE_CONTRACT.schema_version,
                "fingerprint": LIVE_TRAINING_FEATURE_CONTRACT.schema_fingerprint,
                "feature_count": len(LIVE_TRAINING_FEATURE_CONTRACT.ordered_feature_names),
                "ordered_features": LIVE_TRAINING_FEATURE_CONTRACT.ordered_feature_names,
            },
            "feature_coverage": tuple(asdict(item) for item in coverage),
            "feature_coverage_fingerprint": coverage_fingerprint,
            "dataset_evidence_tier_fingerprint": dataset_tier_fingerprint,
            "leakage_audit": asdict(leakage),
            "dataset": {"build_id": build.dataset_build_id, "fingerprint": build.dataset_fingerprint,
                        "included_examples": build.included_examples, "excluded_insufficient_history": build.excluded_insufficient_history_count,
                        "excluded_invalid_provenance": build.excluded_invalid_provenance_count},
            "split": {"split_id": split.split_id, "fingerprint": split.split_fingerprint,
                      "counts": dict(fold.achieved_counts), "earliest_latest_kickoffs": fold.earliest_latest_kickoffs},
            "candidates": candidates,
            "comparison_result": comparison,
            "backtest": {"predictive_test_evaluation": "COMPLETED", "betting_evidence": "UNAVAILABLE_NO_GENUINE_PRE_KICKOFF_ODDS"},
            "shadow_result": "INSUFFICIENT_REAL_EVIDENCE",
            "audit_result": "STAGING_BLOCKED_MISSING_GENUINE_ODDS_AND_SHADOW_EVIDENCE",
            "activation_result": "NOT_EXECUTED",
            "real_match_lab_rehearsal": "NOT_EXECUTED_NO_ACTIVATION",
            "evidence_tier": EvidenceTier.REVIEWED_REAL_HISTORICAL.value,
            "publication_eligibility": False,
            "limitations": (
                "OpenLigaDB is community-maintained and supplies results, kickoff, teams, league, round, and venue only.",
                "No genuine immutable pre-kickoff odds were available; betting, ROI, CLV, and risk evidence are unavailable.",
                "Lineups, injuries, suspensions, and match statistics are optional missing inputs.",
                "Historical evaluation does not establish future predictive quality or profitability.",
            ),
            "safety": {"telegram_calls": 0, "telegram_sends": 0, "delivery_records": 0,
                       "official_publications": 0, "official_bankroll_statistics_mutations": 0,
                       "production_activation_mutations": 0, "scheduling_enabled": False},
            "protected_database_hash_before": protected_before,
            "protected_database_hash_after": protected_after,
        }
        evidence["evidence_fingerprint"] = sha256_fingerprint(evidence)
        return evidence
    finally:
        database.close()


def _train_and_calibrate(database, split, fold, suffix, regularization, timestamp):
    training_outcome = build_historical_model_training_service(
        database,
        preprocessing_policy=PreprocessingPolicy(all_missing_feature_policy=AllMissingFeaturePolicy.CONSTANT_ZERO,
                                                 append_missingness_indicators=True),
        migrate=False,
    ).train(HistoricalModelTrainingCommand(
        training_request_id=f"reviewed-real-training-{suffix}-{split.split_fingerprint[:16]}",
        training_run_name=f"Reviewed-real live-78 {suffix}", source_split_id=split.split_id,
        source_split_fingerprint=split.split_fingerprint, fold_id=fold.fold_id, fold_fingerprint=fold.fold_fingerprint,
        feature_schema_version=LIVE_TRAINING_FEATURE_CONTRACT.schema_version,
        feature_schema_fingerprint=LIVE_TRAINING_FEATURE_CONTRACT.schema_fingerprint,
        ordered_feature_names=LIVE_TRAINING_FEATURE_CONTRACT.ordered_feature_names,
        append_missingness_indicators=True,
        estimator=EstimatorConfiguration(regularization=regularization, maximum_iterations=1600),
        training_timestamp=timestamp, environment_metadata_version=SOURCE_MODE,
    ))
    if training_outcome.status not in {TrainingStatus.MODEL_TRAINED, TrainingStatus.IDEMPOTENT_EXISTING}:
        raise RuntimeError(f"Training {suffix} failed: {training_outcome.status.value}:{training_outcome.ordered_reason_codes}")
    training = SQLiteHistoricalModelTrainingRepository(database, migrate=False).load_training_run(training_outcome.training_run_id)
    artifact = training.artifact
    calibration_outcome = build_historical_probability_calibration_service(database, migrate=False).fit(
        HistoricalCalibrationCommand(
            calibration_request_id=f"reviewed-real-calibration-{suffix}-{artifact.artifact_fingerprint[:16]}",
            calibration_run_name=f"Reviewed-real calibration {suffix}",
            source_training_run_id=training.training_run_id, source_training_run_fingerprint=training.training_run_fingerprint,
            source_model_artifact_id=artifact.artifact_id, source_model_artifact_fingerprint=artifact.artifact_fingerprint,
            source_split_id=split.split_id, source_split_fingerprint=split.split_fingerprint,
            fold_id=fold.fold_id, fold_fingerprint=fold.fold_fingerprint,
            feature_schema_version=artifact.feature_schema_version, feature_schema_fingerprint=artifact.feature_schema_fingerprint,
            calibration_timestamp=timestamp, environment_metadata_version=SOURCE_MODE,
        )
    )
    if calibration_outcome.status not in {CalibrationStatus.CALIBRATION_FITTED, CalibrationStatus.IDEMPOTENT_EXISTING}:
        raise RuntimeError(f"Calibration {suffix} failed: {calibration_outcome.status.value}:{calibration_outcome.ordered_reason_codes}")
    calibration = SQLiteHistoricalProbabilityCalibrationRepository(database, migrate=False).load_calibration_run(calibration_outcome.calibration_run_id)
    quality = _calibration_quality(calibration)
    return {"candidate": suffix, "regularization": format(regularization, "f"),
            "training_run_id": training.training_run_id, "training_run_fingerprint": training.training_run_fingerprint,
            "model_artifact_id": artifact.artifact_id, "model_artifact_fingerprint": artifact.artifact_fingerprint,
            "train_metrics": dict(training.aggregate_training_metrics), "validation_metrics": dict(training.aggregate_validation_metrics),
            "calibration_run_id": calibration.calibration_run_id, "calibration_run_fingerprint": calibration.calibration_run_fingerprint,
            "calibration_artifact_set_id": calibration.artifact_set.artifact_set_id,
            "calibration_artifact_set_fingerprint": calibration.artifact_set.artifact_set_fingerprint,
            "calibration_raw_metrics": dict(calibration.aggregate_raw_metrics),
            "calibration_metrics": dict(calibration.aggregate_calibrated_metrics), "calibration_quality": quality,
            "_training": training, "_calibration": calibration}


def _calibration_quality(calibration):
    metrics = {(item.target_identity, item.metric_phase, item.metric_name): item.metric_value for item in calibration.metrics}
    rows = []
    passed = True
    for artifact in calibration.artifact_set.target_artifacts:
        if json.loads(artifact.derivation_snapshot).get("complement_source_target"):
            continue
        support = json.loads(artifact.support_snapshot)
        reasons = []
        if support["sample_count"] < 100: reasons.append("SUPPORT_BELOW_100")
        if support["positive_count"] < 20: reasons.append("POSITIVE_SUPPORT_BELOW_20")
        if support["negative_count"] < 20: reasons.append("NEGATIVE_SUPPORT_BELOW_20")
        if support["distinct_raw_probabilities"] < 20: reasons.append("UNIQUE_PROBABILITY_SUPPORT_BELOW_20")
        ece = metrics.get((artifact.target_identity, "CALIBRATED", "expected_calibration_error"))
        mce = metrics.get((artifact.target_identity, "CALIBRATED", "maximum_calibration_error"))
        brier_before = metrics.get((artifact.target_identity, "RAW", "brier_score"))
        brier_after = metrics.get((artifact.target_identity, "CALIBRATED", "brier_score"))
        loss_before = metrics.get((artifact.target_identity, "RAW", "log_loss"))
        loss_after = metrics.get((artifact.target_identity, "CALIBRATED", "log_loss"))
        raw_values = tuple(_target_probability(item.raw_probabilities, artifact.target_identity) for item in calibration.predictions)
        calibrated_values = tuple(_target_probability(item.calibrated_probabilities, artifact.target_identity) for item in calibration.predictions)
        adjustments = tuple(abs(after - before) for before, after in zip(raw_values, calibrated_values, strict=True))
        populated_bins = sum(
            item.sample_count > 0 for item in calibration.reliability_bins
            if item.target_identity == artifact.target_identity and item.metric_phase == "CALIBRATED"
        )
        if ece is not None and ece > Decimal("0.15"): reasons.append("ECE_EXCESSIVE")
        if mce is not None and mce > Decimal("0.35"): reasons.append("MCE_EXCESSIVE")
        passed &= not reasons
        rows.append({"target": artifact.target_identity, "method": artifact.method.value, "support": support,
                     "validation_raw_range": (min(raw_values), max(raw_values)), "populated_reliability_bins": populated_bins,
                     "ece": ece, "mce": mce, "brier_before": brier_before, "brier_after": brier_after,
                     "brier_degradation": brier_after - brier_before, "log_loss_before": loss_before,
                     "log_loss_after": loss_after, "log_loss_degradation": loss_after - loss_before,
                     "clamp_frequency": Decimal(sum(value in {Decimal('0.001'), Decimal('0.999')} for value in calibrated_values)) / Decimal(len(calibrated_values)),
                     "extreme_frequency": Decimal(sum(value < Decimal('0.01') or value > Decimal('0.99') for value in calibrated_values)) / Decimal(len(calibrated_values)),
                     "mean_absolute_adjustment": sum(adjustments, Decimal(0)) / Decimal(len(adjustments)),
                     "maximum_absolute_adjustment": max(adjustments),
                     "outcome": "PASS" if not reasons else "FAIL", "reason_codes": tuple(reasons)})
    result = {"source_mode": SOURCE_MODE, "outcome": "CALIBRATION_QUALITY_ACCEPTABLE" if passed else "CALIBRATION_QUALITY_INELIGIBLE",
              "targets": tuple(rows), "publication_eligible": False}
    result["fingerprint"] = sha256_fingerprint(result)
    return result


def _target_probability(probabilities, target):
    return next(item.probability for item in probabilities.ordered_probabilities if item.target.value == target)


def _test_metrics(examples, training, calibration):
    predictions = reproduce_predictions(examples, training.artifact, calibration.artifact_set, run_namespace="reviewed-real-test-evaluation-v1")
    brier = Decimal(0); log_loss = Decimal(0); count = 0
    import math
    for example, prediction in zip(examples, predictions, strict=True):
        labels = dict(example.labels)
        for item in prediction.calibrated_probabilities.ordered_probabilities:
            probability = item.probability; label = labels[item.target.value]
            brier += (probability - Decimal(label)) ** 2
            p = max(Decimal("0.000001"), min(Decimal("0.999999"), probability))
            log_loss += Decimal(str(-(label * math.log(float(p)) + (1-label) * math.log(float(1-p)))))
            count += 1
    result = {"partition": "TEST", "example_count": len(examples), "target_observation_count": count,
              "mean_brier": brier / Decimal(count), "mean_log_loss": log_loss / Decimal(count)}
    result["fingerprint"] = sha256_fingerprint(result)
    return result


def _comparison(candidates):
    ranked = sorted(candidates, key=lambda item: (item["test_predictive_metrics"]["mean_log_loss"], item["candidate"]))
    return {"outcome": "INSUFFICIENT_REAL_EVIDENCE", "best_predictive_candidate": ranked[0]["candidate"],
            "reason_codes": ("GENUINE_PRE_KICKOFF_ODDS_UNAVAILABLE", "SHADOW_EVIDENCE_UNAVAILABLE", "NO_PROMOTION_AUTHORIZED")}


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Execution timestamp must include an offset.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
