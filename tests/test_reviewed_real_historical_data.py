import json
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "reviewed_real"

from app.database import Database, MigrationManager
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT
from app.reviewed_real_historical_data import (
    EvidenceTier, SourceApprovalStatus, SourceReview, TeamAlias, TeamIdentityResolver,
    build_source_manifest, parse_openligadb_files, prepare_source_review,
    validate_manifest_files,
)
from app.reviewed_real_historical_data.fingerprint import sha256_fingerprint


def review(status=SourceApprovalStatus.APPROVED_FOR_INTERNAL_DERIVED_DATA):
    return SourceReview(
        source_id="source", source_name="Source", source_category="OPEN_DATA",
        public_url_or_api_identifier="https://example.test/api", data_owner_provider="Owner",
        access_method="PUBLIC_HTTPS", authentication_requirement="NONE",
        terms_of_use_status="ODbL reviewed", robots_public_access_considerations="API only",
        redistribution_restrictions="Attribution/share-alike", commercial_use_restrictions="Review required",
        rate_limits="Unknown; bounded operator access", data_fields_available=("kickoff", "score"),
        historical_coverage="2018-2025", competition_coverage="League", update_cadence="Community",
        reliability_assessment="Community; verify", raw_data_may_be_stored=True,
        normalized_derived_data_may_be_stored=True, provenance_may_be_committed=True,
        evidence_may_be_published=True, review_timestamp_utc="2026-07-31T12:00:00Z",
        reviewer_operator_note="Controlled research only", approval_status=status,
    )


def match(match_id=1, finished=True, kickoff="2024-08-01T18:30:00Z"):
    return {
        "matchID": match_id, "leagueName": "Bundesliga", "leagueSeason": "2024",
        "matchDateTimeUTC": kickoff, "matchIsFinished": finished,
        "team1": {"teamId": 1, "teamName": "Alpha"}, "team2": {"teamId": 2, "teamName": "Bravo"},
        "group": {"groupOrderID": 1, "groupName": "1. Spieltag"},
        "location": {"locationStadium": "Ground"},
        "matchResults": [{"resultTypeID": 2, "pointsTeam1": 2, "pointsTeam2": 1}],
    }


class ReviewedRealSourceTests(unittest.TestCase):
    def test_review_is_deterministic(self):
        self.assertEqual(prepare_source_review(review()), prepare_source_review(review()))

    def test_review_requires_terms_and_operator_note(self):
        with self.assertRaises(ValueError):
            prepare_source_review(replace(review(), terms_of_use_status=""))

    def test_rejected_and_unclear_sources_fail_closed(self):
        for status in (SourceApprovalStatus.REJECTED, SourceApprovalStatus.TERMS_UNCLEAR,
                       SourceApprovalStatus.REVIEW_REQUIRED, SourceApprovalStatus.ACCESS_UNAVAILABLE):
            with self.subTest(status=status), self.assertRaises(PermissionError):
                build_source_manifest(source_review=review(status), source_version="v1",
                    acquisition_timestamp_utc="2026-07-31T12:00:00Z", effective_date_start="2024-01-01",
                    effective_date_end="2024-12-31", competition_scope=("League",), season_scope=("2024",),
                    files=(FIXTURES / "missing.json",), match_count=0, field_coverage=(), provenance_references=("https://example.test",),
                    parser_version="v1", normalization_version="v1")

    def test_manifest_hash_and_replay_are_deterministic(self):
        path = FIXTURES / "source_a" / "source.json"
        kwargs = dict(source_review=review(), source_version="v1", acquisition_timestamp_utc="2026-07-31T12:00:00Z",
            effective_date_start="2024-01-01", effective_date_end="2024-12-31", competition_scope=("League",),
            season_scope=("2024",), files=(path,), match_count=0, field_coverage=(("score", 0),),
            provenance_references=("https://example.test",), parser_version="v1", normalization_version="v1")
        first = build_source_manifest(**kwargs); second = build_source_manifest(**kwargs)
        self.assertEqual(first, second); validate_manifest_files(first, path.parent)
        with self.assertRaises(ValueError): validate_manifest_files(first, FIXTURES / "source_b")

    def test_openligadb_completed_only_and_utc_preserved(self):
        result = parse_openligadb_files((FIXTURES / "openligadb_sample.json",), dataset_id="dataset", dataset_version="v1")
        self.assertEqual(result.supplied_record_count, 2); self.assertEqual(len(result.dataset.matches), 1)
        self.assertEqual(result.dataset.matches[0].kickoff_utc, "2024-08-01T18:30:00Z")
        self.assertEqual(result.exclusions[0][1].value, "NOT_FINISHED")

    def test_openligadb_duplicate_is_excluded(self):
        result = parse_openligadb_files((FIXTURES / "openligadb_duplicate.json",), dataset_id="dataset", dataset_version="v1")
        self.assertEqual(len(result.dataset.matches), 1); self.assertEqual(result.exclusions[0][1].value, "DUPLICATE")

    def test_team_alias_exact_resolution_and_ambiguity(self):
        alias = TeamAlias("source", "10", "alpha", "team-alpha", "Alpha", "League", "2024", "reviewed")
        resolver = TeamIdentityResolver((alias,))
        self.assertEqual(resolver.resolve(source_id="source", source_team_id="10", normalized_name="alpha",
                                          competition="League", season="2024").canonical_team_id, "team-alpha")
        with self.assertRaises(ValueError):
            resolver.resolve(source_id="source", source_team_id="missing", normalized_name="other",
                             competition="League", season="2024")

    def test_conflicting_team_alias_is_rejected(self):
        first = TeamAlias("source", "10", "alpha", "team-alpha", "Alpha", "League", "2024", "reviewed")
        second = replace(first, canonical_team_id="team-other")
        with self.assertRaises(ValueError): TeamIdentityResolver((first, second))

    def test_live_contract_remains_exact_authority(self):
        self.assertEqual(LIVE_MODEL_INPUT_CONTRACT.schema_identifier, "goalvision_model_input_v1")
        self.assertEqual(LIVE_MODEL_INPUT_CONTRACT.schema_version, "v1")
        self.assertEqual(LIVE_MODEL_INPUT_CONTRACT.feature_count, 78)


class ReviewedRealMigrationTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:"); MigrationManager(self.database.connection).migrate()

    def tearDown(self): self.database.close()

    def test_latest_migration_is_34_and_foreign_keys_hold(self):
        version = self.database.connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
        self.assertEqual(version, 34)
        self.assertEqual(self.database.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_source_review_is_append_only(self):
        self.database.connection.execute(
            "INSERT INTO historical_source_reviews VALUES(?,?,?,?,?,?)",
            ("r", "source", "REVIEW_REQUIRED", "2026-01-01T00:00:00Z", "a"*64, "{}"),
        ); self.database.connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("UPDATE historical_source_reviews SET approval_status='REJECTED' WHERE source_id='source'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("DELETE FROM historical_source_reviews WHERE source_id='source'")

    def test_non_production_tier_cannot_be_publication_eligible(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "INSERT INTO historical_evidence_tiers VALUES(?,?,?,?,?,?,?,?,?)",
                ("id", "DATASET", "d", EvidenceTier.REVIEWED_REAL_HISTORICAL.value, 1, None, "b"*64, "{}", "2026-01-01T00:00:00Z"),
            )

    def test_production_tier_requires_authorization_reference(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "INSERT INTO historical_evidence_tiers VALUES(?,?,?,?,?,?,?,?,?)",
                ("id", "DATASET", "d", EvidenceTier.PRODUCTION_AUTHORIZED.value, 1, None, "c"*64, "{}", "2026-01-01T00:00:00Z"),
            )


class ReviewedRealCanonicalEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parents[1] / "docs" / "rehearsals" / "live_78_reviewed_real_historical_foundation_2026-07-31.json"
        cls.evidence = json.loads(path.read_text(encoding="utf-8"))

    def test_all_78_features_are_reviewed_and_required_features_do_not_block(self):
        rows = self.evidence["feature_coverage"]
        self.assertEqual(len(rows), 78)
        self.assertEqual([row["feature_name"] for row in rows], self.evidence["schema"]["ordered_features"])
        self.assertFalse(any(row["required"] and row["review_status"] == "REQUIRED_BLOCKING" for row in rows))

    def test_leakage_split_calibration_and_test_isolation_evidence(self):
        self.assertEqual(self.evidence["leakage_audit"]["status"], "LEAKAGE_AUDIT_PASSED")
        self.assertGreaterEqual(self.evidence["split"]["counts"]["VALIDATION"], 300)
        self.assertGreaterEqual(self.evidence["split"]["counts"]["TEST"], 300)
        self.assertEqual(len(self.evidence["candidates"]), 2)
        self.assertTrue(all(item["test_predictive_metrics"]["partition"] == "TEST" for item in self.evidence["candidates"]))

    def test_publication_activation_and_production_database_are_unchanged(self):
        self.assertFalse(self.evidence["publication_eligibility"])
        self.assertEqual(self.evidence["safety"]["telegram_calls"], 0)
        self.assertEqual(self.evidence["safety"]["official_publications"], 0)
        self.assertEqual(self.evidence["safety"]["production_activation_mutations"], 0)
        self.assertEqual(self.evidence["protected_database_hash_before"], self.evidence["protected_database_hash_after"])

    def test_evidence_fingerprint_replays_exactly(self):
        material = dict(self.evidence)
        expected = material.pop("evidence_fingerprint")
        self.assertEqual(sha256_fingerprint(material), expected)

if __name__ == "__main__":
    unittest.main()
