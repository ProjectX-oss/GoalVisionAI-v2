import sqlite3
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.historical_data_import import (
    HISTORICAL_DATASET_SCHEMA,
    FullTimeResult,
    HistoricalDataset,
    HistoricalDatasetValidationError,
    HistoricalImportConflictError,
    HistoricalImportPersistenceError,
    HistoricalImportStatus,
    HistoricalLineupInput,
    HistoricalMatchInput,
    HistoricalTeamStatisticsInput,
    SQLiteHistoricalMatchRepository,
    TeamSide,
    build_historical_match_importer,
    map_provider_dataset,
    prepare_historical_dataset,
)


IMPORTED_AT = datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc)


def lineup(prefix: str, formation: str = "4-3-3") -> HistoricalLineupInput:
    return HistoricalLineupInput(
        starting_xi=tuple(f"{prefix} Player {index}" for index in range(1, 12)),
        substitutes=tuple(f"{prefix} Substitute {index}" for index in range(1, 6)),
        formation=formation,
    )


def statistics(possession: str, shots: int, on_target: int, xg: str) -> HistoricalTeamStatisticsInput:
    return HistoricalTeamStatisticsInput(
        possession=possession,
        shots=shots,
        shots_on_target=on_target,
        expected_goals=xg,
        corners=5,
        yellow_cards=2,
        red_cards=0,
        fouls=11,
        offsides=2,
    )


def match(
    source_match_id: str = "provider-match-1001",
    *,
    kickoff: str = "2026-05-10T20:00:00+02:00",
    score: tuple[int, int] = (2, 1),
    home: str = "  Northbridge   FC ",
    away: str = "Southport Athletic",
    complete: bool = True,
) -> HistoricalMatchInput:
    return HistoricalMatchInput(
        source_match_id=source_match_id,
        competition=" Fictional  Premier Division ",
        season="2025/26",
        round="Round 30",
        kickoff_utc=kickoff,
        home_team=home,
        away_team=away,
        full_time_home_score=score[0],
        full_time_away_score=score[1],
        half_time_home_score=min(score[0], 1),
        half_time_away_score=0,
        full_time_result="H" if score[0] > score[1] else "D" if score[0] == score[1] else "A",
        venue="Fictional National Stadium",
        referee="Alex Example",
        attendance=21_500,
        home_statistics=statistics("55.0", 14, 7, "1.80") if complete else None,
        away_statistics=statistics("45", 9, 3, "0.70") if complete else None,
        home_lineup=lineup("Home") if complete else None,
        away_lineup=lineup("Away", "4-2-3-1") if complete else None,
    )


def dataset(
    *matches: HistoricalMatchInput,
    dataset_id: str = "fictional-history-2025-26",
    version: str = "v1",
) -> HistoricalDataset:
    return HistoricalDataset(
        schema_version=HISTORICAL_DATASET_SCHEMA,
        provider=" Fictional  Data Provider ",
        dataset_id=dataset_id,
        dataset_version=version,
        matches=tuple(matches or (match(),)),
    )


class HistoricalNormalizationTests(unittest.TestCase):
    def test_normalization_is_deterministic_order_independent_and_utc(self):
        first_match = match()
        second_match = match(
            "provider-match-1002",
            kickoff="2026-05-11T18:00:00Z",
            score=(1, 1),
            home="East Town",
            away="West City",
        )
        first = prepare_historical_dataset(
            dataset(first_match, second_match),
            import_timestamp=IMPORTED_AT,
        )
        second = prepare_historical_dataset(
            dataset(second_match, first_match),
            import_timestamp="2026-07-22T18:00:00Z",
        )
        self.assertEqual(first.dataset_fingerprint, second.dataset_fingerprint)
        self.assertEqual(
            tuple(item.match_fingerprint for item in first.matches),
            tuple(item.match_fingerprint for item in second.matches),
        )
        normalized = first.matches[0].match
        self.assertEqual(normalized.kickoff_utc, "2026-05-10T18:00:00Z")
        self.assertEqual(normalized.competition, "Fictional Premier Division")
        self.assertEqual(normalized.home_team, "Northbridge FC")
        self.assertEqual(normalized.home_team_identity, "northbridge fc")
        self.assertEqual(normalized.full_time_result, FullTimeResult.HOME_WIN)

    def test_import_timestamp_does_not_change_dataset_or_match_fingerprints(self):
        first = prepare_historical_dataset(dataset(), import_timestamp=IMPORTED_AT)
        second = prepare_historical_dataset(
            dataset(),
            import_timestamp="2030-01-01T00:00:00Z",
        )
        self.assertEqual(first.dataset_fingerprint, second.dataset_fingerprint)
        self.assertEqual(first.matches[0].match_fingerprint, second.matches[0].match_fingerprint)
        self.assertEqual(len(first.dataset_fingerprint), 64)

    def test_mapping_accepts_strict_versioned_json_compatible_payload(self):
        payload = {
            "schema_version": HISTORICAL_DATASET_SCHEMA,
            "provider": "Provider",
            "dataset_id": "dataset-1",
            "dataset_version": "v1",
            "matches": [{
                "source_match_id": "m-1",
                "competition": "League",
                "season": "2025/26",
                "round": "1",
                "kickoff_utc": "2026-01-01T10:00:00Z",
                "home_team": "Home",
                "away_team": "Away",
                "full_time_home_score": 1,
                "full_time_away_score": 0,
                "venue": "Ground",
                "home_statistics": {"possession": "51.5", "shots": 10},
                "home_lineup": {
                    "starting_xi": [f"Player {index}" for index in range(1, 12)],
                    "substitutes": [],
                    "formation": "4-4-2",
                },
            }],
        }
        mapped = map_provider_dataset(payload)
        prepared = prepare_historical_dataset(mapped, import_timestamp=IMPORTED_AT)
        self.assertEqual(prepared.matches[0].match.home_statistics.possession, Decimal("51.5"))
        self.assertEqual(prepared.matches[0].match.home_lineup.formation, "4-4-2")

    def test_mapping_rejects_missing_unknown_and_non_json_collection_fields(self):
        base = {
            "schema_version": HISTORICAL_DATASET_SCHEMA,
            "provider": "Provider",
            "dataset_id": "dataset-1",
            "dataset_version": "v1",
            "matches": [],
        }
        with self.assertRaises(HistoricalDatasetValidationError):
            map_provider_dataset({**base, "unexpected": True})
        with self.assertRaises(HistoricalDatasetValidationError):
            map_provider_dataset({key: value for key, value in base.items() if key != "provider"})
        with self.assertRaises(HistoricalDatasetValidationError):
            map_provider_dataset({**base, "matches": "not-an-array"})


class HistoricalValidationTests(unittest.TestCase):
    def test_schema_empty_dataset_and_untyped_items_are_rejected(self):
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(replace(dataset(), schema_version="v2"), import_timestamp=IMPORTED_AT)
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(replace(dataset(), matches=()), import_timestamp=IMPORTED_AT)
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(replace(dataset(), matches=({},)), import_timestamp=IMPORTED_AT)

    def test_duplicate_provider_and_natural_match_identities_are_rejected(self):
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(dataset(match(), match()), import_timestamp=IMPORTED_AT)
        duplicate_natural = match("another-provider-id")
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(dataset(match(), duplicate_natural), import_timestamp=IMPORTED_AT)

    def test_kickoff_requires_timezone_and_normalizes_offsets(self):
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(dataset(match(kickoff="2026-05-10T20:00:00")), import_timestamp=IMPORTED_AT)
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(dataset(), import_timestamp="2026-07-22T18:00:00")

    def test_impossible_scores_half_time_and_result_are_rejected(self):
        cases = (
            replace(match(), full_time_home_score=-1),
            replace(match(), full_time_home_score=31),
            replace(match(), half_time_home_score=3),
            replace(match(), half_time_away_score=None),
            replace(match(), full_time_result="AWAY_WIN"),
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(HistoricalDatasetValidationError):
                prepare_historical_dataset(dataset(value), import_timestamp=IMPORTED_AT)

    def test_impossible_statistics_and_float_decimals_are_rejected(self):
        bad_statistics = (
            HistoricalTeamStatisticsInput(possession="101"),
            HistoricalTeamStatisticsInput(shots=5, shots_on_target=6),
            HistoricalTeamStatisticsInput(expected_goals="21"),
            HistoricalTeamStatisticsInput(red_cards=6),
            HistoricalTeamStatisticsInput(possession=50.5),
            HistoricalTeamStatisticsInput(),
        )
        for stats in bad_statistics:
            with self.subTest(stats=stats), self.assertRaises(HistoricalDatasetValidationError):
                prepare_historical_dataset(
                    dataset(replace(match(), home_statistics=stats)),
                    import_timestamp=IMPORTED_AT,
                )
        possession_conflict = replace(
            match(),
            home_statistics=statistics("70", 10, 5, "1"),
            away_statistics=statistics("40", 8, 3, "1"),
        )
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(dataset(possession_conflict), import_timestamp=IMPORTED_AT)

    def test_team_and_lineup_identity_rules_are_enforced(self):
        with self.assertRaises(HistoricalDatasetValidationError):
            prepare_historical_dataset(
                dataset(match(home="North FC", away=" north  fc ")),
                import_timestamp=IMPORTED_AT,
            )
        invalid_lineups = (
            HistoricalLineupInput(tuple(f"P{i}" for i in range(10))),
            HistoricalLineupInput(tuple("Same" for _ in range(11))),
            HistoricalLineupInput(tuple(f"P{i}" for i in range(11)), formation="4-4-1"),
        )
        for value in invalid_lineups:
            with self.subTest(value=value), self.assertRaises(HistoricalDatasetValidationError):
                prepare_historical_dataset(
                    dataset(replace(match(), home_lineup=value)),
                    import_timestamp=IMPORTED_AT,
                )


class HistoricalPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteHistoricalMatchRepository(self.database)
        self.importer = build_historical_match_importer(self.database, migrate=False)

    def tearDown(self):
        self.database.close()

    def test_complete_dataset_persists_all_four_tables_and_typed_read_models(self):
        result = self.importer.import_dataset(dataset(), import_timestamp=IMPORTED_AT)
        self.assertEqual(result.status, HistoricalImportStatus.IMPORTED)
        self.assertEqual((result.supplied_match_count, result.inserted_match_count, result.reused_match_count), (1, 1, 0))
        counts = tuple(
            self.database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "historical_match_imports",
                "historical_matches",
                "historical_match_statistics",
                "historical_lineups",
            )
        )
        self.assertEqual(counts, (1, 1, 2, 2))
        stored = self.repository.find_match_by_id(result.historical_match_ids[0])
        self.assertEqual((stored.match_version, stored.kickoff_utc), (1, "2026-05-10T18:00:00Z"))
        stats = self.repository.load_statistics(stored.historical_match_id)
        self.assertEqual({item.team_side for item in stats}, {TeamSide.HOME, TeamSide.AWAY})
        self.assertEqual(stats[1].statistics.possession, Decimal("55"))
        lineups = self.repository.load_lineups(stored.historical_match_id)
        self.assertEqual(len(lineups[0].lineup.starting_xi), 11)

    def test_unavailable_optional_statistics_lineups_referee_and_attendance_remain_absent(self):
        incomplete = replace(
            match(complete=False),
            referee=None,
            attendance=None,
        )
        result = self.importer.import_dataset(
            dataset(incomplete),
            import_timestamp=IMPORTED_AT,
        )
        stored = self.repository.find_match_by_id(result.historical_match_ids[0])
        row = self.database.connection.execute(
            "SELECT referee,attendance FROM historical_matches WHERE historical_match_id=?",
            (stored.historical_match_id,),
        ).fetchone()
        self.assertEqual((row["referee"], row["attendance"]), (None, None))
        self.assertEqual(self.repository.load_statistics(stored.historical_match_id), ())
        self.assertEqual(self.repository.load_lineups(stored.historical_match_id), ())

    def test_exact_replay_is_idempotent_and_writes_nothing(self):
        first = self.importer.import_dataset(dataset(), import_timestamp=IMPORTED_AT)
        before_changes = self.database.connection.total_changes
        before_counts = self._counts()
        replay = self.importer.import_dataset(
            dataset(),
            import_timestamp="2030-01-01T00:00:00Z",
        )
        self.assertEqual(replay.status, HistoricalImportStatus.IDEMPOTENT_REPLAY)
        self.assertEqual(first.import_id, replay.import_id)
        self.assertEqual(first.historical_match_ids, replay.historical_match_ids)
        self.assertEqual(replay.import_timestamp, first.import_timestamp)
        self.assertEqual(self.database.connection.total_changes, before_changes)
        self.assertEqual(self._counts(), before_counts)

    def test_new_dataset_version_reuses_identical_match_without_duplication(self):
        first = self.importer.import_dataset(dataset(version="v1"), import_timestamp=IMPORTED_AT)
        second = self.importer.import_dataset(
            dataset(version="v2"),
            import_timestamp="2026-07-23T18:00:00Z",
        )
        self.assertEqual(second.status, HistoricalImportStatus.IMPORTED)
        self.assertEqual((second.inserted_match_count, second.reused_match_count), (0, 1))
        self.assertEqual(first.historical_match_ids, second.historical_match_ids)
        self.assertEqual(self._counts(), (2, 1, 2, 2))

    def test_corrected_provider_record_appends_version_without_mutating_original(self):
        first = self.importer.import_dataset(dataset(version="v1"), import_timestamp=IMPORTED_AT)
        corrected = replace(
            match(),
            full_time_home_score=3,
            full_time_result="HOME_WIN",
        )
        second = self.importer.import_dataset(
            dataset(corrected, version="v2"),
            import_timestamp="2026-07-23T18:00:00Z",
        )
        original = self.repository.find_match_by_id(first.historical_match_ids[0])
        current = self.repository.find_match_by_id(second.historical_match_ids[0])
        self.assertEqual((original.match_version, original.full_time_home_score), (1, 2))
        self.assertEqual((current.match_version, current.full_time_home_score), (2, 3))
        versions = self.repository.list_match_versions(original.logical_identity_fingerprint)
        self.assertEqual(tuple(item.match_version for item in versions), (1, 2))

    def test_dataset_identity_content_conflict_rolls_back(self):
        self.importer.import_dataset(dataset(), import_timestamp=IMPORTED_AT)
        before = self._counts()
        changed = dataset(replace(match(), attendance=22_000))
        with self.assertRaises(HistoricalImportConflictError):
            self.importer.import_dataset(changed, import_timestamp="2026-07-23T18:00:00Z")
        self.assertEqual(self._counts(), before)

    def test_kickoff_change_and_cross_id_natural_duplicate_fail_closed(self):
        self.importer.import_dataset(dataset(), import_timestamp=IMPORTED_AT)
        cases = (
            dataset(match(kickoff="2026-05-10T21:00:00+02:00"), version="v2"),
            dataset(match("replacement-id"), version="v3"),
        )
        for value in cases:
            with self.subTest(version=value.dataset_version), self.assertRaises(HistoricalImportConflictError):
                self.importer.import_dataset(value, import_timestamp="2026-07-23T18:00:00Z")
        self.assertEqual(self._counts(), (1, 1, 2, 2))

    def test_child_failure_rolls_back_the_complete_import(self):
        self.database.connection.execute(
            """
            CREATE TRIGGER force_historical_statistics_failure
            BEFORE INSERT ON historical_match_statistics
            BEGIN SELECT RAISE(ABORT, 'forced test failure'); END
            """
        )
        self.database.connection.commit()
        with self.assertRaises(HistoricalImportPersistenceError):
            self.importer.import_dataset(dataset(), import_timestamp=IMPORTED_AT)
        self.assertEqual(self._counts(), (0, 0, 0, 0))

    def test_all_historical_tables_reject_updates_and_deletes(self):
        result = self.importer.import_dataset(dataset(), import_timestamp=IMPORTED_AT)
        match_id = result.historical_match_ids[0]
        cases = (
            ("historical_match_imports", "import_id", result.import_id),
            ("historical_matches", "historical_match_id", match_id),
            ("historical_match_statistics", "historical_match_id", match_id),
            ("historical_lineups", "historical_match_id", match_id),
        )
        for table, column, identity in cases:
            with self.subTest(table=table, operation="update"), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(
                    f"UPDATE {table} SET {column}={column} WHERE {column}=?",
                    (identity,),
                )
            with self.subTest(table=table, operation="delete"), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(
                    f"DELETE FROM {table} WHERE {column}=?",
                    (identity,),
                )
        self.database.connection.rollback()

    def _counts(self) -> tuple[int, int, int, int]:
        return tuple(
            self.database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "historical_match_imports",
                "historical_matches",
                "historical_match_statistics",
                "historical_lineups",
            )
        )


class HistoricalMigrationAndStartupTests(unittest.TestCase):
    def test_fresh_v23_schema_has_tables_indexes_and_eight_immutable_guards(self):
        database = Database(":memory:")
        MigrationManager(database.connection).migrate()
        self.assertEqual(database.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 40)
        objects = {
            (row[0], row[1])
            for row in database.connection.execute(
                "SELECT name,type FROM sqlite_master WHERE type IN ('table','index','trigger')"
            )
        }
        for table in (
            "historical_match_imports",
            "historical_matches",
            "historical_match_statistics",
            "historical_lineups",
        ):
            self.assertIn((table, "table"), objects)
            self.assertIn((f"{table}_no_update", "trigger"), objects)
            self.assertIn((f"{table}_no_delete", "trigger"), objects)
        database.close()

    def test_v22_to_v23_upgrade_preserves_existing_data(self):
        database = Database(":memory:")
        connection = database.connection
        connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS[:-1]:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute("INSERT INTO schema_migrations VALUES (?, 'existing')", (migration.version,))
        connection.execute("INSERT INTO published_predictions (prediction_id,fixture_id,market,pick,published_at) VALUES ('sentinel',1,'MATCH_WINNER','HOME','2026-01-01T00:00:00Z')")
        connection.commit()
        MigrationManager(connection).migrate()
        self.assertEqual(connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 40)
        self.assertEqual(connection.execute("SELECT prediction_id FROM published_predictions").fetchone()[0], "sentinel")
        database.close()

    def test_importing_package_is_inert_and_has_no_external_runtime_dependencies(self):
        before_threads = tuple(thread.name for thread in threading.enumerate())
        before_default_database = Database.DEFAULT_PATH.exists()
        import app.historical_data_import as historical_data_import
        import app.historical_data_import.factory as historical_factory
        self.assertIsNotNone((historical_data_import, historical_factory))
        self.assertEqual(tuple(thread.name for thread in threading.enumerate()), before_threads)
        self.assertEqual(Database.DEFAULT_PATH.exists(), before_default_database)
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in __import__("pathlib").Path("app/historical_data_import").glob("*.py")
        )
        for forbidden in (
            "import requests",
            "from requests",
            "import aiohttp",
            "from aiohttp",
            "apscheduler",
            "celery",
            "import telegram",
            "from telegram",
        ):
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
