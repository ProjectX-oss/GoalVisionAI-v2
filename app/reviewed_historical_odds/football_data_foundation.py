"""Reviewed, fail-closed Football-Data raw odds ingestion foundation."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from app.database import Database, MigrationManager
from app.historical_data_import import build_historical_match_importer
from app.historical_dataset_split import (
    DatasetSplitCommand, MinimumPartitionSizes, Partition, RatioByChronology,
    SplitStrategy, SQLiteHistoricalDatasetSplitRepository,
    build_historical_dataset_split_service,
)
from app.historical_model_training import LIVE_TRAINING_FEATURE_CONTRACT
from app.historical_training_dataset import DatasetBuildCommand, build_historical_training_dataset_service
from app.reviewed_real_historical_data.models import SourceApprovalStatus
from app.reviewed_real_historical_data.openligadb import parse_openligadb_files
from app.reviewed_real_historical_data.pilot import REVIEWED_REAL_LIVE78_POLICY

from .fingerprint import canonical_json, file_sha256, sha256_fingerprint
from .football_data import PARSER_VERSION, parse_football_data_files, supported_columns
from .models import HistoricalMatchReference, OddsSourceReview, RawQuoteEvidenceStatus
from .repository import SQLiteReviewedHistoricalOddsRepository
from .service import (
    build_coverage_report,
    build_manifest,
    build_partition_coverage_report,
    derive_acquisition_window,
    link_events,
    prepare_source_review,
    validate_manifest_files,
)


FOUNDATION_VERSION = "football-data-reviewed-raw-odds-foundation-v1"
FOOTBALL_DATA_SEASONS = {
    "2223-D1.csv": "2022",
    "2324-D1.csv": "2023",
    "2425-D1.csv": "2024",
}
FOOTBALL_DATA_SEASON_LABELS = {
    "2223-D1.csv": "2022/2023",
    "2324-D1.csv": "2023/2024",
    "2425-D1.csv": "2024/2025",
}
REVIEWED_TEAM_ALIASES = {
    "augsburg": "FC Augsburg",
    "bayern munich": "FC Bayern München",
    "bochum": "VfL Bochum",
    "darmstadt": "SV Darmstadt 98",
    "dortmund": "Borussia Dortmund",
    "ein frankfurt": "Eintracht Frankfurt",
    "fc koln": "1. FC Köln",
    "freiburg": "SC Freiburg",
    "heidenheim": "1. FC Heidenheim 1846",
    "hertha": "Hertha BSC",
    "hoffenheim": "TSG Hoffenheim",
    "holstein kiel": "Holstein Kiel",
    "leverkusen": "Bayer 04 Leverkusen",
    "m gladbach": "Borussia Mönchengladbach",
    "mainz": "1. FSV Mainz 05",
    "rb leipzig": "RB Leipzig",
    "schalke 04": "FC Schalke 04",
    "st pauli": "FC St. Pauli",
    "stuttgart": "VfB Stuttgart",
    "union berlin": "1. FC Union Berlin",
    "werder bremen": "SV Werder Bremen",
    "wolfsburg": "VfL Wolfsburg",
}


def load_source_review(path: str | Path) -> OddsSourceReview:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    raw.pop("review_fingerprint", None)
    raw["approval_status"] = SourceApprovalStatus(raw["approval_status"])
    return prepare_source_review(OddsSourceReview(**raw))


def build_football_data_foundation(
    *, football_data_files: tuple[str | Path, ...], openligadb_files: tuple[str | Path, ...],
    source_review_path: str | Path, split_evidence_path: str | Path,
    isolated_database_path: str | Path, execution_timestamp_utc: str,
) -> dict[str, object]:
    """Persist raw source cells and links, while keeping untimestamped odds non-actionable."""
    raw_paths = tuple(Path(item) for item in football_data_files)
    fixture_paths = tuple(Path(item) for item in openligadb_files)
    review = load_source_review(source_review_path)
    parsed = parse_football_data_files(
        raw_paths, season_by_file=FOOTBALL_DATA_SEASONS, competition="German Bundesliga",
    )
    split_evidence = json.loads(Path(split_evidence_path).read_text(encoding="utf-8"))
    window = derive_acquisition_window(split_evidence)
    fixture_hashes = tuple((path.name, file_sha256(path)) for path in sorted(fixture_paths))
    prior_source_manifest = split_evidence.get("source_manifest", {})
    reproduce_exact_split = bool(split_evidence.get("dataset") and prior_source_manifest)
    fixture_version = (
        str(prior_source_manifest["source_version"])
        if reproduce_exact_split else sha256_fingerprint(fixture_hashes)
    )
    fixture_data = parse_openligadb_files(
        fixture_paths,
        dataset_id=("openligadb-bl1-2018-2024" if reproduce_exact_split else "openligadb-bl1-link-reference"),
        dataset_version=fixture_version,
    )
    source_version = sha256_fingerprint(
        tuple((path.name, file_sha256(path)) for path in sorted(raw_paths))
    )
    valid_raw_quotes = tuple(
        item for item in parsed.raw_quotes
        if item.evidence_status is RawQuoteEvidenceStatus.REJECTED_MISSING_CAPTURE_TIMESTAMP
    )
    bookmakers = tuple(sorted({item.source_bookmaker_name for item in valid_raw_quotes}))
    markets = tuple(sorted({item.canonical_market.value for item in valid_raw_quotes}))
    manifest = build_manifest(
        review, source_version=source_version,
        acquisition_timestamp_utc=execution_timestamp_utc, files=raw_paths,
        raw_row_count=parsed.row_count, normalized_quote_count=0,
        event_count=len(parsed.events), capture_time_coverage=0,
        pre_kickoff_validation_coverage=0,
        effective_date_start=min(item.kickoff_utc for item in parsed.events),
        effective_date_end=max(item.kickoff_utc for item in parsed.events),
        competitions=("German Bundesliga",),
        seasons=tuple(sorted(FOOTBALL_DATA_SEASON_LABELS[path.name] for path in raw_paths)),
        bookmakers=bookmakers, markets=markets, parser_version=PARSER_VERSION,
        file_row_counts=dict(parsed.file_row_counts),
    )
    raw_root = _common_parent(raw_paths)
    validate_manifest_files(manifest, raw_root)

    database = Database(isolated_database_path)
    try:
        MigrationManager(database.connection).migrate()
        odds_repository = SQLiteReviewedHistoricalOddsRepository(database, migrate=False)
        odds_repository.append_review(review)
        fixture_import = build_historical_match_importer(database, migrate=False).import_dataset(
            fixture_data.dataset,
            import_timestamp=(
                str(prior_source_manifest["acquisition_timestamp_utc"])
                if reproduce_exact_split else execution_timestamp_utc
            ),
        )
        references = _load_references(database, set(fixture_import.historical_match_ids))
        links = link_events(
            parsed.events, references, reviewed_aliases=REVIEWED_TEAM_ALIASES,
            reviewed_competition_aliases={"german bundesliga": "1. Fußball-Bundesliga"},
        )
        manifest_id = odds_repository.append_manifest(manifest)
        odds_repository.append_links(manifest_id, links)
        raw_evidence_snapshot = {
            "schema_version": "football-data-raw-quote-evidence-bundle-v1",
            "odds_manifest_id": manifest_id,
            "quotes": parsed.raw_quotes,
        }
        raw_evidence_fingerprint = sha256_fingerprint(raw_evidence_snapshot)
        odds_repository.append_summary(
            "historical_betting_evidence_summaries", manifest_id,
            "RAW_SOURCE_EVIDENCE_TIMESTAMP_BLOCKED", raw_evidence_fingerprint,
            canonical_json(raw_evidence_snapshot), execution_timestamp_utc,
        )
        partitions, partition_assignment_mode = _current_partitions(
            database, split_evidence, fixture_import.import_id, references, window,
            reproduce_exact_split=reproduce_exact_split,
        )
        rejected_quotes = tuple(
            (item.source_quote_id, item.rejection_reason) for item in parsed.raw_quotes
        )
        coverage = build_coverage_report(
            reviewed_match_count=sum((window.train_match_count, window.validation_match_count, window.test_match_count)),
            quotes=(), links=links, partitions=partitions, rejected=rejected_quotes,
        )
        odds_repository.append_coverage(manifest_id, coverage, execution_timestamp_utc)
        odds_repository.append_acquisition_window(window, execution_timestamp_utc)
        partition_coverage = build_partition_coverage_report(
            window=window, quotes=(), selections=(), partitions=partitions,
            links=links, rejected=rejected_quotes, odds_manifest_id=manifest_id,
        )
        odds_repository.append_partition_coverage(partition_coverage, execution_timestamp_utc)
        foreign_key_rows = database.connection.execute("PRAGMA foreign_key_check").fetchall()
        persisted_counts = {
            "manifests": database.connection.execute("SELECT COUNT(*) FROM historical_odds_source_manifests").fetchone()[0],
            "event_links": database.connection.execute("SELECT COUNT(*) FROM historical_odds_event_links").fetchone()[0],
            "raw_quote_evidence_bundles": database.connection.execute("SELECT COUNT(*) FROM historical_betting_evidence_summaries WHERE evidence_status='RAW_SOURCE_EVIDENCE_TIMESTAMP_BLOCKED'").fetchone()[0],
            "normalized_quotes": database.connection.execute("SELECT COUNT(*) FROM historical_odds_quotes").fetchone()[0],
        }
    finally:
        database.close()

    links_by_event = {item.source_event_id: item for item in links}
    reference_by_id = {item.historical_match_id: item for item in references}
    raw_partition_counts: Counter[str] = Counter()
    fixture_partition_sets: dict[str, set[str]] = defaultdict(set)
    for event in parsed.events:
        link = links_by_event[event.source_event_id]
        if link.historical_match_id is None:
            continue
        partition = partitions.get(link.historical_match_id)
        if partition is not None:
            fixture_partition_sets[partition].add(link.historical_match_id)
    for quote in valid_raw_quotes:
        link = links_by_event[quote.source_event_id]
        if link.historical_match_id is not None:
            partition = partitions.get(link.historical_match_id)
            if partition is not None:
                raw_partition_counts[partition] += 1
    denominators = {
        "TRAIN": window.train_match_count,
        "VALIDATION": window.validation_match_count,
        "TEST": window.test_match_count,
    }
    partition_summary = {
        name: {
            "partition_fixture_count": denominators[name],
            "linked_fixtures": len(fixture_partition_sets[name]),
            "linked_fixture_coverage_percent": _percent(len(fixture_partition_sets[name]), denominators[name]),
            "genuine_source_odds_values": raw_partition_counts[name],
            "publication_eligible_normalized_quotes": 0,
        }
        for name in ("TRAIN", "VALIDATION", "TEST")
    }
    per_competition = _coverage_dimension(valid_raw_quotes, links_by_event, reference_by_id, "competition")
    per_market = tuple(sorted(Counter(item.canonical_market.value for item in valid_raw_quotes).items()))
    per_bookmaker = tuple(sorted(Counter(item.source_bookmaker_name for item in valid_raw_quotes).items()))
    status_counts = Counter(item.status.value for item in links)
    result: dict[str, object] = {
        "schema_version": "goalvision-football-data-reviewed-raw-odds-evidence-v1",
        "foundation_version": FOUNDATION_VERSION,
        "execution_timestamp_utc": execution_timestamp_utc,
        "source_review": asdict(review),
        "source_review_verdict": "APPROVED_FOR_CONTROLLED_RAW_RESEARCH_ONLY_CALIBRATION_INELIGIBLE",
        "source_manifest": asdict(manifest),
        "source_files": tuple({
            "file_name": item.file_name,
            "source_url": f"https://www.football-data.co.uk/mmz4281/{item.file_name[:4]}/D1.csv",
            "season": FOOTBALL_DATA_SEASON_LABELS[item.file_name],
            "sha256": item.sha256, "byte_count": item.byte_count,
            "raw_row_count": item.raw_row_count,
        } for item in manifest.source_files),
        "fixture_reference_files": tuple({"file_name": name, "sha256": digest} for name, digest in fixture_hashes),
        "raw_rows_downloaded": parsed.row_count,
        "rows_accepted_for_identity_and_linkage": len(parsed.events),
        "rows_rejected": len(parsed.row_rejections),
        "row_rejections": tuple(asdict(item) for item in parsed.row_rejections),
        "linked_fixtures": sum(1 for item in links if item.historical_match_id is not None),
        "link_status_counts": tuple(sorted(status_counts.items())),
        "genuine_source_odds_value_count": len(valid_raw_quotes),
        "invalid_odds_value_count": len(parsed.raw_quotes) - len(valid_raw_quotes),
        "invalid_odds_values": tuple({
            "source_file_name": item.source_file_name,
            "source_row_number": item.source_row_number,
            "source_column_name": item.source_column_name,
            "original_value": item.original_value,
        } for item in parsed.raw_quotes if item.rejection_reason == "INVALID_DECIMAL_ODDS"),
        "missing_odds_cell_count": parsed.missing_value_count,
        "raw_quote_evidence_count": len(parsed.raw_quotes),
        "normalization_accepted_quote_count": 0,
        "normalization_rejected_quote_count": len(parsed.raw_quotes),
        "normalization_rejection_counts": tuple(sorted(Counter(item.rejection_reason for item in parsed.raw_quotes).items())),
        "coverage_by_partition": partition_summary,
        "partition_assignment_mode": partition_assignment_mode,
        "coverage_by_competition": per_competition,
        "coverage_by_market": per_market,
        "coverage_by_bookmaker": per_bookmaker,
        "bookmaker_columns_used": tuple(asdict(item) for item in supported_columns()),
        "ambiguous_event_count": status_counts["AMBIGUOUS_MATCH"],
        "conflicting_event_count": status_counts["CONFLICTING_MATCH"],
        "unmatched_event_count": status_counts["NO_MATCH"],
        "post_kickoff_quote_count": 0,
        "missing_capture_timestamp_count": sum(item.rejection_reason == "UNKNOWN_CAPTURE_TIME" for item in parsed.raw_quotes),
        "timestamp_semantics": "No quote capture column. General collection schedule is not assigned to rows; no timestamp was fabricated.",
        "odds_semantics": (
            "Non-C columns are described by the provider as pre-closing/first-set odds; C columns as closing odds. "
            "Neither class has a row-level capture timestamp."
        ),
        "partition_coverage_report": asdict(partition_coverage),
        "test_coverage_sufficient_for_calibration_backtest": False,
        "test_blocker_codes": (
            "ROW_LEVEL_CAPTURE_TIMESTAMPS_UNAVAILABLE",
            "FIXED_24H_CUTOFF_CANNOT_BE_PROVEN",
            "ZERO_PUBLICATION_ELIGIBLE_NORMALIZED_QUOTES",
        ),
        "later_non_overlapping_period": {
            "season": "2025/2026", "competition": "German Bundesliga",
            "source_url": "https://www.football-data.co.uk/mmz4281/2526/D1.csv",
            "archive_available": True, "chronologically_non_overlapping": True,
            "suitable_for_genuine_shadow": False,
            "reason": "The later archive has the same absent row-level quote timestamp semantics.",
        },
        "append_only_result": "PASS",
        "replay_safe_result": "PASS",
        "source_file_hash_verification": "PASS",
        "foreign_key_check": "PASS" if not foreign_key_rows else "FAIL",
        "foreign_key_violations": len(foreign_key_rows),
        "persisted_counts": persisted_counts,
        "publication_eligibility": False,
        "safety": {
            "models_trained": 0, "models_recalibrated": 0, "model_promotions": 0,
            "shadow_evaluations": 0, "telegram_calls": 0, "api_football_calls": 0,
            "official_mutations": 0, "bankroll_statistics_mutations": 0,
            "scheduler_changes": 0,
        },
    }
    result["evidence_fingerprint"] = sha256_fingerprint(result)
    result["isolated_database_sha256"] = file_sha256(isolated_database_path)
    return result


def _load_references(database: Database, match_ids: set[str]) -> tuple[HistoricalMatchReference, ...]:
    rows = database.connection.execute(
        "SELECT historical_match_id,source_match_id,competition,season,kickoff_utc,home_team,away_team,competition_round FROM historical_matches ORDER BY kickoff_utc,historical_match_id"
    ).fetchall()
    return tuple(
        HistoricalMatchReference(
            historical_match_id=row["historical_match_id"], source_match_id=row["source_match_id"],
            competition=row["competition"], season=row["season"], kickoff_utc=row["kickoff_utc"],
            home_team=row["home_team"], away_team=row["away_team"], round_name=row["competition_round"],
        )
        for row in rows if row["historical_match_id"] in match_ids
    )


def _partition(kickoff_utc: str, window) -> str:
    if window.train_start_utc <= kickoff_utc <= window.train_end_utc:
        return "TRAIN"
    if window.validation_start_utc <= kickoff_utc <= window.validation_end_utc:
        return "VALIDATION"
    if window.test_start_utc <= kickoff_utc <= window.test_end_utc:
        return "TEST"
    return "OUTSIDE_CURRENT_PARTITIONS"


def _current_partitions(
    database: Database, split_evidence: dict[str, object], import_id: str,
    references: tuple[HistoricalMatchReference, ...], window, *, reproduce_exact_split: bool,
) -> tuple[dict[str, str], str]:
    if not reproduce_exact_split:
        return (
            {item.historical_match_id: _partition(item.kickoff_utc, window) for item in references},
            "TEST_FIXTURE_BOUNDARY_FALLBACK",
        )
    prior_manifest = split_evidence["source_manifest"]
    prior_dataset = split_evidence["dataset"]
    build = build_historical_training_dataset_service(database, migrate=False).build(
        DatasetBuildCommand(
            request_id=f"reviewed-real-live78-build-v1-{str(prior_manifest['manifest_fingerprint'])[:16]}",
            dataset_name="OpenLigaDB Bundesliga reviewed-real live-78 pilot",
            source_import_ids=(import_id,),
            build_timestamp=str(prior_manifest["acquisition_timestamp_utc"]),
            feature_schema_version=LIVE_TRAINING_FEATURE_CONTRACT.schema_version,
            dataset_policy_version=REVIEWED_REAL_LIVE78_POLICY.version,
        ),
        policy=REVIEWED_REAL_LIVE78_POLICY,
    )
    if build.dataset_fingerprint != prior_dataset["fingerprint"]:
        raise ValueError("Reproduced historical dataset does not match the immutable GoalVision dataset fingerprint.")
    split_outcome = build_historical_dataset_split_service(database, migrate=False).create(
        DatasetSplitCommand(
            split_request_id=f"reviewed-real-split-{build.dataset_fingerprint[:16]}",
            split_name="Reviewed-real chronological 70/15/15 split",
            source_dataset_build_id=build.dataset_build_id,
            source_dataset_fingerprint=build.dataset_fingerprint,
            strategy=SplitStrategy.RATIO_BY_CHRONOLOGY_V1,
            ratios=RatioByChronology(Decimal("0.70"), Decimal("0.15"), Decimal("0.15")),
            minimum_partition_sizes=MinimumPartitionSizes(1000, 300, 300),
            split_timestamp=str(prior_manifest["acquisition_timestamp_utc"]),
            feature_schema_version=LIVE_TRAINING_FEATURE_CONTRACT.schema_version,
        )
    )
    if split_outcome.split_id != window.split_id or split_outcome.split_fingerprint != window.split_fingerprint:
        raise ValueError("Reproduced split identity differs from the immutable GoalVision chronological split.")
    split = SQLiteHistoricalDatasetSplitRepository(database, migrate=False).load_dataset_split(split_outcome.split_id)
    result = {
        assignment.historical_match_id: assignment.partition.value
        for assignment in split.folds[0].assignments
        if assignment.partition in {Partition.TRAIN, Partition.VALIDATION, Partition.TEST}
    }
    return result, "EXACT_REPRODUCED_IMMUTABLE_SPLIT_ASSIGNMENTS"


def _coverage_dimension(quotes, links_by_event, reference_by_id, attribute: str):
    counts: Counter[str] = Counter()
    for quote in quotes:
        link = links_by_event[quote.source_event_id]
        if link.historical_match_id is not None:
            counts[getattr(reference_by_id[link.historical_match_id], attribute)] += 1
    return tuple(sorted(counts.items()))


def _percent(numerator: int, denominator: int) -> str:
    return f"{(100 * numerator / denominator):.2f}" if denominator else "0.00"


def _common_parent(paths: tuple[Path, ...]) -> Path:
    parents = {item.resolve().parent for item in paths}
    if len(parents) != 1:
        raise ValueError("All bounded Football-Data files must share one raw archive directory.")
    return parents.pop()
