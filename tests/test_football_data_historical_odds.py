import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.database import Database
from app.reviewed_historical_odds.football_data import (
    SOURCE_TIMESTAMP_SEMANTICS,
    parse_football_data_files,
)
from app.reviewed_historical_odds.football_data_foundation import (
    build_football_data_foundation,
    load_source_review,
)
from app.reviewed_historical_odds.models import (
    EventLinkStatus,
    HistoricalMatchReference,
    RawQuoteEvidenceStatus,
    SourceOddsEvent,
    SourceOddsQuote,
)
from app.reviewed_historical_odds.service import (
    build_manifest,
    link_events,
    normalize_quotes,
    validate_manifest_files,
)


ROOT = Path(__file__).parent.parent
REVIEW = ROOT / "docs" / "data_sources" / "football_data_co_uk_csv_review_v1.json"


class FootballDataHistoricalOddsTests(unittest.TestCase):
    def test_source_review_authorizes_raw_research_but_discloses_timestamp_blocker(self):
        review = load_source_review(REVIEW)
        self.assertTrue(review.approval_status.permits_import)
        self.assertFalse(review.capture_time_available)
        self.assertIn("fixed 24-hour", review.reliability_assessment)
        self.assertIn("raw-data redistribution", review.redistribution_permission)

    def test_parser_normalizes_only_existing_markets_and_preserves_cell_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2425-D1.csv"
            self._write_csv(path)
            first = parse_football_data_files(
                (path,), season_by_file={path.name: "2024"}, competition="German Bundesliga",
            )
            second = parse_football_data_files(
                (path,), season_by_file={path.name: "2024"}, competition="German Bundesliga",
            )
        self.assertEqual(first, second)
        self.assertEqual(first.row_count, 1)
        self.assertEqual(len(first.raw_quotes), 5)
        self.assertEqual(
            {item.canonical_market.value for item in first.raw_quotes},
            {"HOME_WIN", "DRAW", "AWAY_WIN", "OVER_2_5", "UNDER_2_5"},
        )
        self.assertTrue(all(item.source_row_number == 2 for item in first.raw_quotes))
        self.assertTrue(all(item.captured_at_utc is None for item in first.raw_quotes))
        self.assertTrue(all(item.source_timestamp_semantics == SOURCE_TIMESTAMP_SEMANTICS for item in first.raw_quotes))
        self.assertTrue(all(item.evidence_status is RawQuoteEvidenceStatus.REJECTED_MISSING_CAPTURE_TIMESTAMP for item in first.raw_quotes))
        self.assertEqual(len({item.provenance_fingerprint for item in first.raw_quotes}), 5)

    def test_exact_alias_link_and_ambiguous_rejection_are_deterministic(self):
        event = SourceOddsEvent(
            "event", "German Bundesliga", "2024-08-23T18:30:00Z",
            "M'gladbach", "Leverkusen", season="2024",
        )
        match = HistoricalMatchReference(
            "match", "1", "1. Fußball-Bundesliga 2024/2025", "2024",
            "2024-08-23T18:30:00Z", "Borussia Mönchengladbach", "Bayer 04 Leverkusen",
        )
        aliases = {"m gladbach": "Borussia Mönchengladbach", "leverkusen": "Bayer 04 Leverkusen"}
        competition_aliases = {"german bundesliga": "1. Fußball-Bundesliga"}
        linked = link_events(
            (event,), (match,), reviewed_aliases=aliases,
            reviewed_competition_aliases=competition_aliases,
        )[0]
        ambiguous = link_events(
            (event,), (match, replace(match, historical_match_id="other")),
            reviewed_aliases=aliases, reviewed_competition_aliases=competition_aliases,
        )[0]
        self.assertIs(linked.status, EventLinkStatus.REVIEWED_ALIAS_MATCH)
        self.assertIs(ambiguous.status, EventLinkStatus.AMBIGUOUS_MATCH)
        self.assertIsNone(ambiguous.historical_match_id)

    def test_missing_capture_time_and_post_kickoff_are_never_normalized(self):
        event = SourceOddsEvent("event", "Bundesliga", "2024-08-23T18:30:00Z", "Home", "Away")
        match = HistoricalMatchReference("match", "1", "Bundesliga", "2024", event.kickoff_utc, "Home", "Away")
        link = link_events((event,), (match,), reviewed_aliases={})
        base = SourceOddsQuote(
            "quote", "event", "bet365", "Bet365", "h2h", "Home", "2.0",
            "DECIMAL", None, "2024-08-23T18:00:00Z",
        )
        post = replace(base, source_quote_id="post", captured_at_utc=event.kickoff_utc)
        normalized, rejected = normalize_quotes(
            (base, post), (event,), link, manifest_id="manifest",
            acquisition_timestamp_utc="2026-09-13T11:43:36Z",
        )
        self.assertFalse(normalized)
        self.assertEqual({reason for _, reason in rejected}, {"UNKNOWN_CAPTURE_TIME", "POST_KICKOFF_ODDS"})

    def test_manifest_hash_verification_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2425-D1.csv"
            self._write_csv(path)
            review = load_source_review(REVIEW)
            manifest = build_manifest(
                review, source_version="fixture-v1", acquisition_timestamp_utc="2026-09-13T11:43:36Z",
                files=(path,), raw_row_count=1, normalized_quote_count=0, event_count=1,
                capture_time_coverage=0, pre_kickoff_validation_coverage=0,
                effective_date_start="2024-08-23T18:30:00Z", effective_date_end="2024-08-23T18:30:00Z",
                competitions=("German Bundesliga",), seasons=("2024/2025",),
                bookmakers=("Bet365",), markets=("HOME_WIN",), parser_version="test-v1",
                file_row_counts={path.name: 1},
            )
            validate_manifest_files(manifest, path.parent)
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_manifest_files(manifest, path.parent)

    def test_foundation_import_is_replay_safe_and_reports_test_as_ineligible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            odds = root / "2425-D1.csv"
            fixtures = root / "bl1-2024.json"
            split = root / "split.json"
            database = root / "foundation.db"
            self._write_csv(odds)
            fixtures.write_text(json.dumps([self._openliga_fixture()]), encoding="utf-8")
            split.write_text(json.dumps(self._split_evidence()), encoding="utf-8")
            kwargs = dict(
                football_data_files=(odds,), openligadb_files=(fixtures,),
                source_review_path=REVIEW, split_evidence_path=split,
                isolated_database_path=database,
                execution_timestamp_utc="2026-09-13T11:43:36Z",
            )
            first = build_football_data_foundation(**kwargs)
            second = build_football_data_foundation(**kwargs)
            connection = sqlite3.connect(database)
            counts = (
                connection.execute("SELECT COUNT(*) FROM historical_odds_source_manifests").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM historical_odds_event_links").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM historical_betting_evidence_summaries").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM historical_odds_quotes").fetchone()[0],
            )
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            connection.close()
        self.assertEqual(first["evidence_fingerprint"], second["evidence_fingerprint"])
        self.assertEqual(counts, (1, 1, 1, 0))
        self.assertFalse(first["test_coverage_sufficient_for_calibration_backtest"])
        self.assertEqual(first["coverage_by_partition"]["TEST"]["linked_fixtures"], 1)
        self.assertEqual(first["coverage_by_partition"]["TEST"]["publication_eligible_normalized_quotes"], 0)
        self.assertEqual(first["ambiguous_event_count"], 0)
        self.assertEqual(first["foreign_key_check"], "PASS")
        self.assertFalse(foreign_keys)

    @staticmethod
    def _write_csv(path: Path) -> None:
        path.write_text(
            "Div,Date,Time,HomeTeam,AwayTeam,B365H,B365D,B365A,B365>2.5,B365<2.5,MaxH\n"
            "D1,23/08/2024,19:30,M'gladbach,Leverkusen,5.25,4.5,1.55,1.44,2.75,5.5\n",
            encoding="utf-8",
        )

    @staticmethod
    def _openliga_fixture() -> dict:
        return {
            "matchID": 1, "matchIsFinished": True,
            "matchDateTimeUTC": "2024-08-23T18:30:00Z",
            "leagueSeason": 2024, "leagueName": "1. Fußball-Bundesliga 2024/2025",
            "team1": {"teamName": "Borussia Mönchengladbach"},
            "team2": {"teamName": "Bayer 04 Leverkusen"},
            "group": {"groupName": "1. Spieltag"},
            "location": {"locationStadium": "Test"},
            "matchResults": [{"resultTypeID": 2, "pointsTeam1": 2, "pointsTeam2": 3}],
        }

    @staticmethod
    def _split_evidence() -> dict:
        return {"split": {
            "split_id": "immutable-split", "fingerprint": "a" * 64,
            "counts": {"TRAIN": 1, "VALIDATION": 1, "TEST": 1, "EXCLUDED_GAP": 0},
            "earliest_latest_kickoffs": [
                ["TRAIN", "2022-01-01T00:00:00Z", "2022-12-31T23:59:59Z"],
                ["VALIDATION", "2023-01-01T00:00:00Z", "2023-12-31T23:59:59Z"],
                ["TEST", "2024-01-01T00:00:00Z", "2024-12-31T23:59:59Z"],
            ],
        }}


if __name__ == "__main__":
    unittest.main()
