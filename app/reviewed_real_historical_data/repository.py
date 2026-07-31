"""SQLite append-only persistence for reviewed real-data governance artifacts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from app.database import Database, MigrationManager

from .fingerprint import canonical_json
from .fingerprint import sha256_fingerprint
from .models import DataQualityReport, EvidenceTier, LeakageAuditReport, SourceManifest, SourceReview


class SQLiteReviewedRealDataRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self.database = database
        if migrate:
            MigrationManager(database.connection).migrate()

    def append_review(self, review: SourceReview) -> SourceReview:
        row = self.database.connection.execute(
            "SELECT review_fingerprint,review_snapshot FROM historical_source_reviews WHERE source_id=?",
            (review.source_id,),
        ).fetchone()
        snapshot = canonical_json(review)
        if row:
            if row["review_fingerprint"] != review.review_fingerprint:
                raise ValueError("Immutable source review conflict.")
            return review
        with self.database.connection:
            self.database.connection.execute(
                "INSERT INTO historical_source_reviews(source_review_id,source_id,approval_status,review_timestamp_utc,review_fingerprint,review_snapshot) VALUES(?,?,?,?,?,?)",
                (f"source-review-{review.review_fingerprint}", review.source_id, review.approval_status.value,
                 review.review_timestamp_utc, review.review_fingerprint, snapshot),
            )
        return review

    def append_manifest(self, manifest: SourceManifest) -> SourceManifest:
        key = (manifest.source_id, manifest.source_version)
        row = self.database.connection.execute(
            "SELECT manifest_fingerprint FROM historical_source_manifests WHERE source_id=? AND source_version=?", key,
        ).fetchone()
        if row:
            if row["manifest_fingerprint"] != manifest.manifest_fingerprint:
                raise ValueError("Source version resolves to different content.")
            return manifest
        review = self.database.connection.execute(
            "SELECT approval_status FROM historical_source_reviews WHERE source_id=?", (manifest.source_id,),
        ).fetchone()
        if review is None:
            raise PermissionError("A persisted source review is required before manifest registration.")
        if review["approval_status"] != manifest.usage_approval_status.value:
            raise PermissionError("Manifest approval status differs from the persisted source review.")
        with self.database.connection:
            self.database.connection.execute(
                "INSERT INTO historical_source_manifests(source_manifest_id,source_id,source_version,acquisition_timestamp_utc,manifest_fingerprint,manifest_snapshot) VALUES(?,?,?,?,?,?)",
                (f"source-manifest-{manifest.manifest_fingerprint}", manifest.source_id, manifest.source_version,
                 manifest.acquisition_timestamp_utc, manifest.manifest_fingerprint, canonical_json(manifest)),
            )
            for position, item in enumerate(manifest.source_files):
                self.database.connection.execute(
                    "INSERT INTO historical_source_files(source_file_id,source_manifest_id,deterministic_order,file_name,sha256,byte_count,row_count,file_snapshot) VALUES(?,?,?,?,?,?,?,?)",
                    (f"source-file-{manifest.manifest_fingerprint}-{position}", f"source-manifest-{manifest.manifest_fingerprint}", position,
                     item.file_name, item.sha256, item.byte_count, item.row_count, canonical_json(item)),
                )
        return manifest

    def load_review(self, source_id: str) -> dict[str, object] | None:
        row = self.database.connection.execute(
            "SELECT review_snapshot FROM historical_source_reviews WHERE source_id=?", (source_id,),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def append_quality_report(self, manifest: SourceManifest, report: DataQualityReport, timestamp: str) -> None:
        self._append_once(
            "historical_data_quality_reports", "report_fingerprint", report.report_fingerprint,
            "INSERT INTO historical_data_quality_reports(data_quality_report_id,source_manifest_id,report_fingerprint,report_snapshot,created_timestamp_utc) VALUES(?,?,?,?,?)",
            (f"data-quality-{report.report_fingerprint}", f"source-manifest-{manifest.manifest_fingerprint}",
             report.report_fingerprint, canonical_json(report), timestamp),
        )

    def append_feature_coverage(self, dataset_build_id: str, rows: tuple[object, ...], timestamp: str) -> str:
        fingerprint = sha256_fingerprint({"dataset_build_id": dataset_build_id, "rows": rows})
        self._append_once(
            "historical_feature_coverage_reports", "report_fingerprint", fingerprint,
            "INSERT INTO historical_feature_coverage_reports(feature_coverage_report_id,dataset_build_id,report_fingerprint,report_snapshot,created_timestamp_utc) VALUES(?,?,?,?,?)",
            (f"feature-coverage-{fingerprint}", dataset_build_id, fingerprint, canonical_json(rows), timestamp),
        )
        return fingerprint

    def append_leakage_audit(self, report: LeakageAuditReport) -> None:
        self._append_once(
            "historical_leakage_audit_reports", "report_fingerprint", report.report_fingerprint,
            "INSERT INTO historical_leakage_audit_reports(leakage_audit_report_id,dataset_build_id,audit_status,report_fingerprint,report_snapshot,audit_timestamp_utc) VALUES(?,?,?,?,?,?)",
            (f"leakage-audit-{report.report_fingerprint}", report.dataset_build_id, report.status.value,
             report.report_fingerprint, canonical_json(report), report.audit_timestamp_utc),
        )

    def append_evidence_tier(self, artifact_type: str, artifact_id: str, tier: EvidenceTier, timestamp: str) -> str:
        publication_eligible = tier.publication_eligible
        material = {"artifact_type": artifact_type, "artifact_id": artifact_id, "evidence_tier": tier.value,
                    "publication_eligible": publication_eligible, "authorization_reference": None, "created_timestamp_utc": timestamp}
        fingerprint = sha256_fingerprint(material)
        row = self.database.connection.execute(
            "SELECT tier_fingerprint FROM historical_evidence_tiers WHERE artifact_type=? AND artifact_id=?",
            (artifact_type, artifact_id),
        ).fetchone()
        if row:
            if row[0] != fingerprint:
                raise ValueError("Immutable evidence-tier conflict.")
            return fingerprint
        with self.database.connection:
            self.database.connection.execute(
                "INSERT INTO historical_evidence_tiers(evidence_tier_record_id,artifact_type,artifact_id,evidence_tier,publication_eligible,authorization_reference,tier_fingerprint,tier_snapshot,created_timestamp_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                (f"evidence-tier-{fingerprint}", artifact_type, artifact_id, tier.value, int(publication_eligible), None,
                 fingerprint, canonical_json(material), timestamp),
            )
        return fingerprint

    def _append_once(self, table: str, identity_column: str, identity: str, statement: str, values: tuple[object, ...]) -> None:
        row = self.database.connection.execute(
            f"SELECT {identity_column} FROM {table} WHERE {identity_column}=?", (identity,),
        ).fetchone()
        if row:
            return
        with self.database.connection:
            self.database.connection.execute(statement, values)
