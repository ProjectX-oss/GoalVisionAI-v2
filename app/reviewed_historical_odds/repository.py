"""Append-only SQLite persistence for reviewed historical odds evidence."""

from __future__ import annotations

import sqlite3

from app.database import Database, MigrationManager

from .fingerprint import canonical_json
from .models import (
    BacktestIntegrityReport, EventLinkDecision, NormalizedOddsQuote,
    OddsAcquisitionWindow, OddsCoverageReport, OddsSourceManifest, OddsSourceReview,
    PartitionCoverageReport,
    QuoteSelectionDecision,
)
from .service import prepare_source_review


class SQLiteReviewedHistoricalOddsRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self.database = database
        if migrate:
            MigrationManager(database.connection).migrate()

    def append_review(self, review: OddsSourceReview) -> None:
        if review.review_fingerprint != prepare_source_review(review).review_fingerprint:
            raise ValueError("Odds source review fingerprint is invalid.")
        review_id = f"odds-source-review-{review.review_fingerprint}"
        legacy = self.database.connection.execute(
            "SELECT review_fingerprint FROM historical_odds_source_reviews WHERE source_id=?", (review.source_id,),
        ).fetchone()
        with self.database.connection:
            if legacy is None:
                self.database.connection.execute(
                    "INSERT INTO historical_odds_source_reviews(odds_source_review_id,source_id,approval_status,review_timestamp_utc,review_fingerprint,review_snapshot) VALUES(?,?,?,?,?,?)",
                    (review_id, review.source_id, review.approval_status.value,
                     review.review_timestamp_utc, review.review_fingerprint, canonical_json(review)),
                )
            prior = self.database.connection.execute(
                "SELECT odds_source_review_id FROM historical_odds_source_review_versions WHERE source_id=? ORDER BY review_timestamp_utc DESC,odds_source_review_id DESC LIMIT 1",
                (review.source_id,),
            ).fetchone()
            existing = self.database.connection.execute(
                "SELECT review_fingerprint FROM historical_odds_source_review_versions WHERE odds_source_review_id=?", (review_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != review.review_fingerprint:
                    raise ValueError("Immutable historical odds source review version conflict.")
                return
            self.database.connection.execute(
                "INSERT INTO historical_odds_source_review_versions(odds_source_review_id,source_id,approval_status,review_timestamp_utc,review_fingerprint,supersedes_review_id,review_snapshot) VALUES(?,?,?,?,?,?,?)",
                (review_id, review.source_id, review.approval_status.value,
                 review.review_timestamp_utc, review.review_fingerprint,
                 prior[0] if prior else None, canonical_json(review)),
            )

    def append_manifest(self, manifest: OddsSourceManifest) -> str:
        row = self.database.connection.execute(
            "SELECT manifest_fingerprint FROM historical_odds_source_manifests WHERE source_id=? AND source_version=?",
            (manifest.source_id, manifest.source_version),
        ).fetchone()
        if row is not None:
            if row[0] != manifest.manifest_fingerprint:
                raise ValueError("Odds source version resolves to different content.")
            return f"historical-odds-manifest-{manifest.manifest_fingerprint}"
        review = self.database.connection.execute(
            "SELECT approval_status FROM historical_odds_source_review_versions WHERE odds_source_review_id=?",
            (manifest.source_review_id,),
        ).fetchone()
        if review is None or review[0] not in {"APPROVED_FOR_CONTROLLED_RESEARCH", "APPROVED_FOR_INTERNAL_DERIVED_DATA"}:
            raise PermissionError("An approved persisted odds source review is required.")
        manifest_id = f"historical-odds-manifest-{manifest.manifest_fingerprint}"
        with self.database.connection:
            self.database.connection.execute(
                "INSERT INTO historical_odds_source_manifests(odds_manifest_id,source_id,source_version,acquisition_timestamp_utc,manifest_fingerprint,manifest_snapshot) VALUES(?,?,?,?,?,?)",
                (manifest_id, manifest.source_id, manifest.source_version,
                 manifest.acquisition_timestamp_utc, manifest.manifest_fingerprint,
                 canonical_json(manifest)),
            )
            for order, item in enumerate(manifest.source_files):
                self.database.connection.execute(
                    "INSERT INTO historical_odds_source_files(odds_source_file_id,odds_manifest_id,deterministic_order,file_name,sha256,byte_count,raw_row_count,file_snapshot) VALUES(?,?,?,?,?,?,?,?)",
                    (f"historical-odds-source-file-{manifest.manifest_fingerprint}-{order}", manifest_id,
                     order, item.file_name, item.sha256, item.byte_count,
                     item.raw_row_count, canonical_json(item)),
                )
        return manifest_id

    def append_acquisition_window(self, window: OddsAcquisitionWindow, timestamp: str) -> str:
        identifier = f"historical-odds-window-{window.window_fingerprint}"
        row = self.database.connection.execute(
            "SELECT window_fingerprint FROM historical_odds_acquisition_windows WHERE split_id=? AND split_fingerprint=?",
            (window.split_id, window.split_fingerprint),
        ).fetchone()
        if row is not None:
            if row[0] != window.window_fingerprint:
                raise ValueError("Immutable odds acquisition window conflict.")
            return identifier
        with self.database.connection:
            self.database.connection.execute(
                "INSERT INTO historical_odds_acquisition_windows(acquisition_window_id,split_id,split_fingerprint,equal_kickoff_grouping_policy,train_start_utc,train_end_utc,validation_start_utc,validation_end_utc,test_start_utc,test_end_utc,train_match_count,validation_match_count,test_match_count,temporal_gap_count,window_fingerprint,window_snapshot,created_timestamp_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (identifier, window.split_id, window.split_fingerprint,
                 window.equal_kickoff_grouping_policy, window.train_start_utc,
                 window.train_end_utc, window.validation_start_utc,
                 window.validation_end_utc, window.test_start_utc, window.test_end_utc,
                 window.train_match_count, window.validation_match_count,
                 window.test_match_count, window.temporal_gap_count,
                 window.window_fingerprint, canonical_json(window), timestamp),
            )
        return identifier

    def append_partition_coverage(self, report: PartitionCoverageReport, timestamp: str) -> str:
        identifier = f"historical-odds-partition-coverage-{report.report_fingerprint}"
        row = self.database.connection.execute(
            "SELECT report_fingerprint FROM historical_odds_partition_coverage_reports WHERE report_fingerprint=?",
            (report.report_fingerprint,),
        ).fetchone()
        if row is None:
            with self.database.connection:
                self.database.connection.execute(
                    "INSERT INTO historical_odds_partition_coverage_reports(partition_coverage_report_id,acquisition_window_id,odds_manifest_id,coverage_status,validation_matches_with_odds,test_matches_with_odds,test_candidate_market_count,ambiguous_event_count,post_kickoff_exclusion_count,report_fingerprint,report_snapshot,created_timestamp_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (identifier, report.acquisition_window_id, report.odds_manifest_id,
                     report.coverage_status.value, report.validation_matches_with_odds,
                     report.test_matches_with_odds, report.test_candidate_market_count,
                     report.ambiguous_event_count, report.post_kickoff_exclusion_count,
                     report.report_fingerprint, canonical_json(report), timestamp),
                )
        return identifier

    def append_links(self, manifest_id: str, links: tuple[EventLinkDecision, ...]) -> None:
        for item in links:
            self._append_identity(
                "historical_odds_event_links", "source_event_id", item.source_event_id,
                "link_fingerprint", item.link_fingerprint,
                "INSERT INTO historical_odds_event_links(event_link_id,odds_manifest_id,source_event_id,historical_match_id,link_status,link_fingerprint,link_snapshot) VALUES(?,?,?,?,?,?,?)",
                (item.event_link_id, manifest_id, item.source_event_id, item.historical_match_id,
                 item.status.value, item.link_fingerprint, canonical_json(item)),
                extra_where=("odds_manifest_id", manifest_id),
            )

    def append_quotes(self, manifest_id: str, quotes: tuple[NormalizedOddsQuote, ...]) -> None:
        link_ids = {
            row["source_event_id"]: row["event_link_id"]
            for row in self.database.connection.execute(
                "SELECT source_event_id,event_link_id FROM historical_odds_event_links WHERE odds_manifest_id=?", (manifest_id,)
            )
        }
        for item in quotes:
            self._append_identity(
                "historical_odds_quotes", "source_quote_id", item.source_quote_id,
                "quote_fingerprint", item.quote_fingerprint,
                "INSERT INTO historical_odds_quotes(quote_id,odds_manifest_id,event_link_id,historical_match_id,source_quote_id,canonical_market,decimal_odds,captured_at_utc,kickoff_utc,quote_fingerprint,quote_snapshot) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (item.quote_id, manifest_id, link_ids[item.source_event_id], item.historical_match_id,
                 item.source_quote_id, item.canonical_market.value, str(item.decimal_odds),
                 item.captured_at_utc, item.linked_kickoff_utc, item.quote_fingerprint,
                 canonical_json(item)), extra_where=("odds_manifest_id", manifest_id),
            )

    def append_selections(self, manifest_id: str, selections: tuple[QuoteSelectionDecision, ...]) -> None:
        for item in selections:
            self._append_identity(
                "historical_odds_quote_selections", "selection_fingerprint", item.selection_fingerprint,
                "selection_fingerprint", item.selection_fingerprint,
                "INSERT INTO historical_odds_quote_selections(quote_selection_id,odds_manifest_id,historical_match_id,canonical_market,selected_quote_id,cutoff_timestamp_utc,policy_version,selection_fingerprint,selection_snapshot) VALUES(?,?,?,?,?,?,?,?,?)",
                (item.quote_selection_id, manifest_id, item.historical_match_id,
                 item.canonical_market.value, item.selected_quote_id,
                 item.cutoff_timestamp_utc, item.policy_version,
                 item.selection_fingerprint, canonical_json(item)),
            )

    def append_coverage(self, manifest_id: str, report: OddsCoverageReport, timestamp: str) -> None:
        self._append_report(
            "historical_odds_coverage_reports", "coverage_report_id", "coverage",
            manifest_id, "report_fingerprint", report.report_fingerprint,
            "report_snapshot", canonical_json(report), timestamp,
        )

    def append_integrity(self, manifest_id: str, report: BacktestIntegrityReport, timestamp: str) -> None:
        identifier = f"historical-odds-integrity-{report.report_fingerprint}"
        row = self.database.connection.execute(
            "SELECT report_fingerprint FROM reviewed_odds_backtest_integrity_reports WHERE report_fingerprint=?", (report.report_fingerprint,),
        ).fetchone()
        if row is None:
            with self.database.connection:
                self.database.connection.execute(
                    "INSERT INTO reviewed_odds_backtest_integrity_reports(integrity_report_id,odds_manifest_id,integrity_status,report_fingerprint,report_snapshot,created_timestamp_utc) VALUES(?,?,?,?,?,?)",
                    (identifier, manifest_id, report.status.value, report.report_fingerprint,
                     canonical_json(report), timestamp),
                )

    def append_summary(self, table: str, manifest_id: str, status: str, fingerprint: str, snapshot: str, timestamp: str) -> None:
        allowed = {
            "historical_betting_evidence_summaries": ("betting_evidence_id", "evidence_status", "evidence_fingerprint", "evidence_snapshot"),
            "historical_odds_shadow_summaries": ("shadow_summary_id", "shadow_status", "summary_fingerprint", "summary_snapshot"),
            "historical_odds_audit_reports": ("odds_audit_id", "audit_status", "audit_fingerprint", "audit_snapshot"),
        }
        if table not in allowed:
            raise ValueError("Unsupported evidence summary table.")
        id_column, status_column, fp_column, snapshot_column = allowed[table]
        row = self.database.connection.execute(f"SELECT {fp_column} FROM {table} WHERE {fp_column}=?", (fingerprint,)).fetchone()
        if row is None:
            with self.database.connection:
                self.database.connection.execute(
                    f"INSERT INTO {table}({id_column},odds_manifest_id,{status_column},{fp_column},{snapshot_column},created_timestamp_utc) VALUES(?,?,?,?,?,?)",
                    (f"{id_column.removesuffix('_id')}-{fingerprint}", manifest_id, status, fingerprint, snapshot, timestamp),
                )

    def _append_report(self, table, id_column, prefix, manifest_id, fp_column, fingerprint, snapshot_column, snapshot, timestamp):
        row = self.database.connection.execute(f"SELECT {fp_column} FROM {table} WHERE {fp_column}=?", (fingerprint,)).fetchone()
        if row is None:
            with self.database.connection:
                self.database.connection.execute(
                    f"INSERT INTO {table}({id_column},odds_manifest_id,{fp_column},{snapshot_column},created_timestamp_utc) VALUES(?,?,?,?,?)",
                    (f"historical-odds-{prefix}-{fingerprint}", manifest_id, fingerprint, snapshot, timestamp),
                )

    def _append_identity(self, table, identity_column, identity, fingerprint_column, fingerprint, statement, values, extra_where=None):
        where, parameters = f"{identity_column}=?", [identity]
        if extra_where:
            where += f" AND {extra_where[0]}=?"; parameters.append(extra_where[1])
        row = self.database.connection.execute(
            f"SELECT {fingerprint_column} FROM {table} WHERE {where}", tuple(parameters),
        ).fetchone()
        if row is not None:
            if row[0] != fingerprint:
                raise ValueError(f"Immutable {table} conflict.")
            return
        try:
            with self.database.connection:
                self.database.connection.execute(statement, values)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Immutable {table} persistence conflict.") from exc
