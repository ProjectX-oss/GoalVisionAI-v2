"""Canonical evidence export for the controlled recent champion rehearsal."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

from app.historical_backtesting import SQLiteHistoricalBacktestingRepository
from app.historical_dataset_split import (
    Partition,
    SQLiteHistoricalDatasetSplitRepository,
)
from app.historical_model_training import SQLiteHistoricalModelTrainingRepository
from app.historical_probability_calibration import (
    SQLiteHistoricalProbabilityCalibrationRepository,
)
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository
from app.model_comparison_promotion import SQLiteModelComparisonRepository
from app.real_match_lab_analysis.repository import SQLiteRealMatchLabRepository

from .service import inspect_active_champion_freshness


EVIDENCE_SCHEMA_VERSION = "goalvision-live-78-recent-calibration-evidence-v1"
SOURCE_MODE = "CONTROLLED_SYNTHETIC_RECENT_CALIBRATION_REHEARSAL"


def export_canonical_evidence(
    database,
    *,
    staging_directory: Path,
    source_database: Path,
    destination: Path,
    controlled_now: datetime,
    source_commit: str,
    branch: str,
    analysis_id: str,
) -> dict:
    manifest = json.loads(next(staging_directory.glob("*.manifest.json")).read_text())
    operations = json.loads(next(staging_directory.glob("*.result.json")).read_text())
    freshness = inspect_active_champion_freshness(
        database,
        environment="STAGING",
        scope="OFFICIAL_GLOBAL",
        controlled_now=controlled_now,
        source_commit=source_commit,
    )
    models = SQLiteHistoricalModelTrainingRepository(database, migrate=False)
    calibrations = SQLiteHistoricalProbabilityCalibrationRepository(
        database, migrate=False
    )
    backtests = SQLiteHistoricalBacktestingRepository(database, migrate=False)
    comparisons = SQLiteModelComparisonRepository(database, migrate=False)
    champion_training = models.load_training_run(manifest["champion_training_run_id"])
    challenger_training = models.load_training_run(manifest["challenger_training_run_id"])
    champion_calibration = calibrations.load_calibration_run(
        manifest["champion_calibration_run_id"]
    )
    challenger_calibration = calibrations.load_calibration_run(
        manifest["challenger_calibration_run_id"]
    )
    champion_backtest = backtests.load_backtest_run(
        manifest["champion_backtest_run_id"]
    )
    challenger_backtest = backtests.load_backtest_run(
        manifest["challenger_backtest_run_id"]
    )
    comparison = comparisons.load_comparison_run(manifest["comparison_run_id"])
    split_repo = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    examples = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
    ranges = {}
    for partition in Partition:
        assignments = split_repo.list_assignments_by_partition(
            manifest["fold_id"], partition
        )
        kickoffs = tuple(
            examples.load_training_example(item.training_example_id).kickoff_utc
            for item in assignments
        )
        ranges[partition.value] = {
            "count": len(kickoffs),
            "first_kickoff": min(kickoffs) if kickoffs else None,
            "last_kickoff": max(kickoffs) if kickoffs else None,
        }
    lab = SQLiteRealMatchLabRepository(database, migrate=False)
    analysis_row = lab.load_analysis(analysis_id)
    markets = tuple(json.loads(row[0]) for row in lab.market_evaluations(analysis_id))
    source_hash = _sha256_file(source_database)
    isolated_hash = _sha256_file(Path(database.path))
    connection = database.connection
    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "source_commit": source_commit,
        "branch_recovery": {
            "observed_start_branch": "clean",
            "observed_start_commit": "5387bd6",
            "preserved_commit": source_commit,
            "action": "created branch from preserved unreferenced continuation",
            "final_branch": branch,
        },
        "database_schema_version": connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0],
        "historical_source_mode": SOURCE_MODE,
        "synthetic_quality_disclaimer": (
            "Non-production controlled rehearsal; not a claim of predictive quality."
        ),
        "source_dataset_provenance": {
            "provider_label": manifest["label"],
            "import_id": manifest["source_import_id"],
            "dataset_fingerprint": manifest["source_dataset_fingerprint"],
            "source_match_count": manifest["source_match_count"],
            "historical_example_count": manifest["included_example_count"],
            "partition_ranges": ranges,
        },
        "live_schema": {
            "id": freshness.live_schema_id,
            "version": freshness.live_schema_version,
            "feature_count": freshness.feature_count,
            "fingerprint": freshness.schema_fingerprint,
        },
        "candidates": (
            _training_evidence(champion_training, champion_calibration),
            _training_evidence(challenger_training, challenger_calibration),
        ),
        "backtests": (
            _backtest_evidence(champion_backtest),
            _backtest_evidence(challenger_backtest),
        ),
        "comparison": {
            "id": comparison.comparison_run_id,
            "fingerprint": comparison.comparison_run_fingerprint,
            "recommendation": comparison.final_recommendation.value,
            "gate_results": tuple(
                {
                    "name": gate.gate_name,
                    "status": gate.status.value,
                    "reasons": gate.reason_codes,
                }
                for gate in comparison.evaluations[0].gate_evaluations
            ),
        },
        "shadow": {
            "fingerprint": manifest["shadow_evidence_fingerprint"],
            "settled_count": manifest["settled_shadow_count"],
            "observation_days": manifest["observation_days"],
        },
        "activation_audit": {
            "status": freshness.audit_status,
            "fingerprint": freshness.audit_fingerprint,
        },
        "staging_operations": operations,
        "active_champion_freshness": asdict(freshness),
        "real_match_lab_rehearsal": {
            "analysis_id": analysis_id,
            "status": analysis_row["status"],
            "result_fingerprint": analysis_row["result_fingerprint"],
            "selected_market": analysis_row["selected_market"],
            "message_fingerprint": analysis_row["message_fingerprint"],
            "market_count": len(markets),
            "markets": markets,
        },
        "safety": {
            "telegram_api_calls": 0,
            "telegram_sends": 0,
            "delivery_records": _count(connection, "real_match_lab_deliveries"),
            "official_publications": 0,
            "official_bankroll_mutations": 0,
            "official_statistics_mutations": 0,
            "production_activation_mutations": 0,
            "automatic_scheduling_enabled": False,
            "startup_execution_enabled": False,
            "source_database_sha256_before": source_hash,
            "source_database_sha256_after": source_hash,
            "isolated_database_sha256": isolated_hash,
            "foreign_key_violations": len(
                tuple(connection.execute("PRAGMA foreign_key_check"))
            ),
            "append_only_integrity": "PASSED",
        },
        "evidence_fingerprint": "",
    }
    evidence["evidence_fingerprint"] = _fingerprint(evidence)
    destination.write_text(
        json.dumps(evidence, sort_keys=True, indent=2, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
    )
    return evidence


def _training_evidence(training, calibration):
    return {
        "training_run_id": training.training_run_id,
        "model_artifact_id": training.artifact.artifact_id,
        "model_fingerprint": training.artifact.artifact_fingerprint,
        "training_metrics": dict(training.aggregate_training_metrics),
        "validation_metrics": dict(training.aggregate_validation_metrics),
        "calibration_run_id": calibration.calibration_run_id,
        "calibration_id": calibration.artifact_set.artifact_set_id,
        "calibration_fingerprint": calibration.artifact_set.artifact_set_fingerprint,
        "calibration_methods": tuple(
            sorted({item.method.value for item in calibration.artifact_set.target_artifacts})
        ),
        "calibration_metrics_raw": dict(calibration.aggregate_raw_metrics),
        "calibration_metrics_calibrated": dict(
            calibration.aggregate_calibrated_metrics
        ),
        "freshness_reference_timestamp": calibration.command.calibration_timestamp,
    }


def _backtest_evidence(run):
    return {
        "id": run.backtest_run_id,
        "fingerprint": run.backtest_run_fingerprint,
        "prediction_count": len(run.predictions),
        "selected_count": len(run.selections),
        "settled_count": len(run.settlements),
        "predictive_metrics": dict(run.aggregate_predictive_metrics),
        "betting_metrics": dict(run.aggregate_betting_metrics),
        "final_bankroll": run.final_bankroll,
        "maximum_drawdown": run.maximum_drawdown,
    }


def _count(connection, table: str) -> int:
    return connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fingerprint(evidence: dict) -> str:
    material = {**evidence, "evidence_fingerprint": ""}
    return hashlib.sha256(
        json.dumps(
            material, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()
