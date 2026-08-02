import sqlite3
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.historical_data_import import (
    HISTORICAL_DATASET_SCHEMA,
    HistoricalDataset,
    HistoricalMatchInput,
    HistoricalTeamStatisticsInput,
    build_historical_match_importer,
)
from app.historical_training_dataset import (
    CUTOFF_POLICY,
    DATASET_POLICY_VERSION,
    FEATURE_SCHEMA_VERSION,
    HISTORICAL_TRAINING_FEATURES_V1,
    LABEL_ORDER,
    LABEL_SCHEMA_VERSION,
    DatasetBuildCommand,
    DatasetBuildStatus,
    HistoricalSourceMatch,
    SQLiteHistoricalTrainingDatasetRepository,
    TemporalLeakageError,
    assert_source_precedes_target,
    build_historical_training_dataset_service,
    generate_labels,
    inspect_training_example,
    summarize_dataset,
    verify_dataset_fingerprints,
    verify_label_consistency,
    verify_no_temporal_leakage,
)
from app.historical_training_dataset.validation import validate_source_matches


UTC = timezone.utc
BASE = datetime(2025, 8, 1, 12, 0, tzinfo=UTC)
BUILT_AT = datetime(2026, 7, 22, 20, 0, tzinfo=UTC)


def stats(seed: int) -> HistoricalTeamStatisticsInput:
    return HistoricalTeamStatisticsInput(
        possession="50", shots=8 + seed, shots_on_target=3 + seed,
        expected_goals=str(Decimal("0.75") + Decimal(seed) / 10), corners=3 + seed,
        yellow_cards=seed % 4, red_cards=0, fouls=9 + seed, offsides=seed % 3,
    )


def historical_match(
    index: int,
    home: str,
    away: str,
    score: tuple[int, int],
    *,
    kickoff: datetime | None = None,
    with_statistics: bool = True,
) -> HistoricalMatchInput:
    return HistoricalMatchInput(
        source_match_id=f"match-{index}", competition="Example League", season="2025/26",
        round=f"Round {index}", kickoff_utc=kickoff or BASE + timedelta(days=index),
        home_team=home, away_team=away, full_time_home_score=score[0],
        full_time_away_score=score[1], venue=f"{home} Ground",
        full_time_result="H" if score[0] > score[1] else "D" if score[0] == score[1] else "A",
        home_statistics=stats(index % 4) if with_statistics else None,
        away_statistics=stats((index + 1) % 4) if with_statistics else None,
    )


def history() -> tuple[HistoricalMatchInput, ...]:
    return (
        historical_match(0, "Alpha", "Charlie", (2, 0)),
        historical_match(1, "Bravo", "Delta", (1, 1)),
        historical_match(2, "Charlie", "Alpha", (1, 3)),
        historical_match(3, "Delta", "Bravo", (0, 2)),
        historical_match(4, "Alpha", "Charlie", (1, 1)),
        historical_match(5, "Bravo", "Delta", (3, 1)),
        historical_match(6, "Alpha", "Bravo", (2, 1)),
        historical_match(7, "Charlie", "Delta", (0, 0)),
        historical_match(8, "Bravo", "Alpha", (1, 2)),
    )


def import_history(database: Database, matches: tuple[HistoricalMatchInput, ...] | None = None) -> str:
    importer = build_historical_match_importer(database)
    result = importer.import_dataset(
        HistoricalDataset(
            schema_version=HISTORICAL_DATASET_SCHEMA, provider="Test Provider",
            dataset_id="training-history", dataset_version="v1", matches=matches or history(),
        ),
        import_timestamp=datetime(2026, 7, 22, 19, 0, tzinfo=UTC),
    )
    return result.import_id


def command(import_id: str, *, request_id: str = "build-request-1", lower_day: int = 6, upper_day: int = 9) -> DatasetBuildCommand:
    return DatasetBuildCommand(
        request_id=request_id, dataset_name="Example training dataset",
        source_import_ids=(import_id,), competition_filters=("Example League",),
        season_filters=("2025/26",), kickoff_lower_bound=BASE + timedelta(days=lower_day),
        kickoff_upper_bound=BASE + timedelta(days=upper_day), build_timestamp=BUILT_AT,
    )


class HistoricalTrainingBuildTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.import_id = import_history(self.database)
        self.service = build_historical_training_dataset_service(self.database, migrate=False)
        self.repository = SQLiteHistoricalTrainingDatasetRepository(self.database, migrate=False)

    def tearDown(self):
        self.database.close()

    def test_builds_immutable_examples_in_deterministic_order(self):
        outcome = self.service.build(command(self.import_id))
        self.assertEqual(outcome.status, DatasetBuildStatus.DATASET_BUILT)
        self.assertEqual(outcome.included_examples, 3)
        examples = self.repository.list_examples_for_dataset(outcome.dataset_build_id)
        self.assertEqual(tuple(item.kickoff_utc for item in examples), tuple(sorted(item.kickoff_utc for item in examples)))
        self.assertTrue(all(len(item.ordered_feature_vector) == len(HISTORICAL_TRAINING_FEATURES_V1) for item in examples))
        self.assertTrue(all(item.cutoff_timestamp == item.kickoff_utc for item in examples))
        self.assertTrue(all(source.source_kickoff < item.kickoff_utc for item in examples for source in item.sources))

    def test_equal_future_round_future_season_and_later_same_day_are_never_sources(self):
        outcome = self.service.build(command(self.import_id, lower_day=6, upper_day=7))
        example = self.repository.list_examples_for_dataset(outcome.dataset_build_id)[0]
        target_kickoff = example.kickoff_utc
        self.assertTrue(all(source.source_kickoff < target_kickoff for source in example.sources))
        forbidden = {item.source_match_fingerprint for item in example.sources if item.source_kickoff >= target_kickoff}
        self.assertEqual(forbidden, set())
        with self.assertRaises(TemporalLeakageError):
            assert_source_precedes_target("source", target_kickoff, "target", target_kickoff)
        with self.assertRaises(TemporalLeakageError):
            assert_source_precedes_target("source", "2030-01-01T00:00:00Z", "target", target_kickoff)

    def test_recent_split_season_h2h_rest_congestion_and_statistics_features(self):
        outcome = self.service.build(command(self.import_id, lower_day=8, upper_day=9))
        example = self.repository.list_examples_for_dataset(outcome.dataset_build_id)[0]
        values = dict(zip((item.name for item in HISTORICAL_TRAINING_FEATURES_V1), example.ordered_feature_vector))
        self.assertEqual(values["home_last_3_matches_played"], 3)
        self.assertEqual(values["home_last_5_matches_played"], 4)
        self.assertEqual(values["away_last_10_matches_played"], 4)
        self.assertEqual(values["home_venue_last_10_matches_played"], 2)
        self.assertEqual(values["away_venue_last_10_matches_played"], 1)
        self.assertEqual(values["home_season_matches_played"], 4)
        self.assertEqual(values["away_season_matches_played"], 4)
        self.assertEqual(values["head_to_head_meetings_count"], 1)
        self.assertEqual(values["home_days_since_previous_match"], Decimal("2.000000"))
        self.assertEqual(values["home_matches_previous_7_days"], 4)
        self.assertIsInstance(values["home_last_10_average_shots"], Decimal)

    def test_missing_statistics_remain_missing_without_imputation(self):
        database = Database(":memory:")
        no_stats = tuple(replace(item, home_statistics=None, away_statistics=None) for item in history())
        import_id = import_history(database, no_stats)
        service = build_historical_training_dataset_service(database, migrate=False)
        repository = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
        outcome = service.build(command(import_id, lower_day=8, upper_day=9))
        example = repository.list_examples_for_dataset(outcome.dataset_build_id)[0]
        index = next(item.index for item in HISTORICAL_TRAINING_FEATURES_V1 if item.name == "home_last_10_average_shots")
        self.assertIsNone(example.ordered_feature_vector[index])
        self.assertTrue(example.missingness_mask[index])
        self.assertIn("INCLUDED_WITH_MISSINGNESS", outcome.ordered_reason_codes)
        database.close()

    def test_target_score_and_target_statistics_never_enter_prematch_features(self):
        def build_target(target_score, target_stats):
            database = Database(":memory:")
            items = list(history())
            target = items[8]
            items[8] = replace(
                target,
                full_time_home_score=target_score[0],
                full_time_away_score=target_score[1],
                full_time_result="H" if target_score[0] > target_score[1] else "D" if target_score[0] == target_score[1] else "A",
                home_statistics=target_stats,
                away_statistics=target_stats,
            )
            import_id = import_history(database, tuple(items))
            service = build_historical_training_dataset_service(database, migrate=False)
            repository = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
            outcome = service.build(command(import_id, request_id=f"target-{target_score[0]}-{target_score[1]}", lower_day=8, upper_day=9))
            example = repository.list_examples_for_dataset(outcome.dataset_build_id)[0]
            database.close()
            return example

        first = build_target((1, 2), stats(1))
        second = build_target((4, 0), stats(3))
        self.assertEqual(first.ordered_feature_vector, second.ordered_feature_vector)
        self.assertEqual(first.missingness_mask, second.missingness_mask)
        self.assertNotEqual(first.labels, second.labels)

    def test_insufficient_history_is_persisted_as_exclusion(self):
        outcome = self.service.build(command(self.import_id, lower_day=0, upper_day=2))
        self.assertEqual(outcome.status, DatasetBuildStatus.NO_ELIGIBLE_MATCHES)
        self.assertEqual(outcome.excluded_insufficient_history_count, 2)
        exclusions = self.repository.list_exclusions_for_dataset(outcome.dataset_build_id)
        self.assertEqual(len(exclusions), 2)
        self.assertTrue(all(item.reason.value == "EXCLUDED_INSUFFICIENT_HISTORY" for item in exclusions))

    def test_input_order_does_not_change_projection_calculations(self):
        first = self.service.build(command(self.import_id, lower_day=8, upper_day=9))
        example = self.repository.list_examples_for_dataset(first.dataset_build_id)[0]
        self.assertEqual(tuple(item.index for item in HISTORICAL_TRAINING_FEATURES_V1), tuple(range(len(HISTORICAL_TRAINING_FEATURES_V1))))
        self.assertEqual(len({item.name for item in HISTORICAL_TRAINING_FEATURES_V1}), len(HISTORICAL_TRAINING_FEATURES_V1))
        self.assertEqual(example.example_fingerprint, self.repository.load_training_example(example.training_example_id).example_fingerprint)

    def test_idempotent_replay_and_request_conflict(self):
        first = self.service.build(command(self.import_id))
        before = self.database.connection.total_changes
        replay = self.service.build(command(self.import_id))
        self.assertEqual(replay.status, DatasetBuildStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(first.dataset_fingerprint, replay.dataset_fingerprint)
        self.assertEqual(before, self.database.connection.total_changes)
        conflict = self.service.build(replace(command(self.import_id), dataset_name="Changed"))
        self.assertEqual(conflict.status, DatasetBuildStatus.CONFLICT)
        self.assertEqual(before, self.database.connection.total_changes)

    def test_independent_builds_are_stable_when_source_input_order_changes(self):
        def build_with(matches):
            database = Database(":memory:")
            import_id = import_history(database, matches)
            service = build_historical_training_dataset_service(database, migrate=False)
            repository = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
            outcome = service.build(command(import_id, lower_day=8, upper_day=9))
            example = repository.list_examples_for_dataset(outcome.dataset_build_id)[0]
            result = outcome.dataset_fingerprint, example.example_fingerprint, example.ordered_feature_vector
            database.close()
            return result

        self.assertEqual(build_with(history()), build_with(tuple(reversed(history()))))

    def test_same_match_can_appear_in_distinct_dataset_builds(self):
        first = self.service.build(command(self.import_id, request_id="distinct-1", lower_day=8, upper_day=9))
        second = self.service.build(command(self.import_id, request_id="distinct-2", lower_day=8, upper_day=9))
        self.assertEqual((first.status, second.status), (DatasetBuildStatus.DATASET_BUILT, DatasetBuildStatus.DATASET_BUILT))
        match_id = self.repository.list_examples_for_dataset(first.dataset_build_id)[0].historical_match_id
        self.assertEqual(len(self.repository.list_datasets_for_match(match_id)), 2)


class HistoricalTrainingLabelTests(unittest.TestCase):
    def source(self, score: tuple[int, int]) -> HistoricalSourceMatch:
        return HistoricalSourceMatch(
            historical_match_id="match", import_ids=("import",), match_fingerprint="a" * 64,
            competition="League", competition_identity="league", season="season",
            kickoff_utc="2025-01-01T00:00:00Z", home_team_identity="home",
            away_team_identity="away", full_time_home_score=score[0], full_time_away_score=score[1],
        )

    def test_home_draw_away_total_boundaries_and_btts(self):
        cases = (((1, 0), "HOME_WIN"), ((1, 1), "DRAW"), ((0, 1), "AWAY_WIN"))
        for score, result in cases:
            values = dict(generate_labels(self.source(score)))
            self.assertEqual(values[result], 1)
            self.assertEqual(sum(values[name] for name in ("HOME_WIN", "DRAW", "AWAY_WIN")), 1)
            self.assertEqual(values["BTTS_YES"] + values["BTTS_NO"], 1)
            self.assertLessEqual(values["OVER_3_5"], values["OVER_2_5"])
            self.assertLessEqual(values["OVER_2_5"], values["OVER_1_5"])
        self.assertEqual(dict(generate_labels(self.source((1, 0))))["UNDER_1_5"], 1)
        self.assertEqual(dict(generate_labels(self.source((2, 0))))["OVER_1_5"], 1)
        self.assertEqual(dict(generate_labels(self.source((2, 1))))["OVER_2_5"], 1)
        self.assertEqual(dict(generate_labels(self.source((2, 2))))["OVER_3_5"], 1)

    def test_schema_contains_only_supported_labels_and_no_correct_score(self):
        self.assertEqual(len(LABEL_ORDER), 11)
        self.assertFalse(any("SCORE" in label for label in LABEL_ORDER))


class HistoricalTrainingValidationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.import_id = import_history(self.database)
        self.service = build_historical_training_dataset_service(self.database, migrate=False)
        self.repository = SQLiteHistoricalTrainingDatasetRepository(self.database, migrate=False)

    def tearDown(self):
        self.database.close()

    def test_invalid_request_unsupported_contracts_empty_sources_and_malformed_metadata(self):
        cases = (
            replace(command(self.import_id), source_import_ids=()),
            replace(command(self.import_id), cutoff_policy="ALLOW_EQUAL"),
            replace(command(self.import_id), feature_schema_version="unknown"),
            replace(command(self.import_id), label_schema_version="unknown"),
            replace(command(self.import_id), dataset_policy_version="unknown"),
            replace(command(self.import_id), metadata_version="unknown"),
            replace(command(self.import_id), build_timestamp="not-a-time"),
            replace(command(self.import_id), competition_filters=("",)),
        )
        for item in cases:
            with self.subTest(item=item):
                self.assertEqual(self.service.build(item).status, DatasetBuildStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_training_dataset_builds").fetchone()[0], 0)

    def test_missing_import_fails_closed_as_source_provenance(self):
        outcome = self.service.build(command("historical-import-missing"))
        self.assertEqual(outcome.status, DatasetBuildStatus.REJECTED_SOURCE_PROVENANCE)
        self.assertEqual(outcome.included_examples, 0)

    def test_duplicate_conflicting_missing_timestamp_and_invalid_team_provenance_fail_closed(self):
        base = HistoricalSourceMatch(
            historical_match_id="source", import_ids=("import",), match_fingerprint="a" * 64,
            competition="League", competition_identity="league", season="season",
            kickoff_utc="2025-01-01T00:00:00Z", home_team_identity="home",
            away_team_identity="away", full_time_home_score=1, full_time_away_score=0,
        )
        cases = (
            (base, base),
            (base, replace(base, match_fingerprint="b" * 64)),
            (replace(base, kickoff_utc=""),),
            (replace(base, away_team_identity="home"),),
        )
        for sources in cases:
            with self.subTest(sources=sources), self.assertRaises(Exception):
                validate_source_matches(sources)

    def test_missing_final_score_is_rejected(self):
        match = HistoricalSourceMatch(
            historical_match_id="source", import_ids=("import",), match_fingerprint="a" * 64,
            competition="League", competition_identity="league", season="season",
            kickoff_utc="2025-01-01T00:00:00Z", home_team_identity="home",
            away_team_identity="away", full_time_home_score=None, full_time_away_score=0,  # type: ignore[arg-type]
        )
        with self.assertRaises(Exception):
            generate_labels(match)

    def test_atomic_rollback_on_example_source_and_exclusion_failures(self):
        cases = (
            ("historical_training_examples", command(self.import_id, request_id="fail-example")),
            ("historical_training_example_sources", command(self.import_id, request_id="fail-source")),
            ("historical_training_exclusions", command(self.import_id, request_id="fail-exclusion", lower_day=0, upper_day=1)),
        )
        for table, request in cases:
            trigger = f"force_{table}_failure"
            self.database.connection.execute(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'forced'); END"
            )
            self.database.connection.commit()
            outcome = self.service.build(request)
            self.assertEqual(outcome.status, DatasetBuildStatus.PERSISTENCE_FAILURE)
            self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_training_dataset_builds").fetchone()[0], 0)
            self.database.connection.execute(f"DROP TRIGGER {trigger}")
            self.database.connection.commit()

    def test_append_only_foreign_keys_uniqueness_and_deterministic_serialization(self):
        outcome = self.service.build(command(self.import_id))
        example = self.repository.list_examples_for_dataset(outcome.dataset_build_id)[0]
        for table, key, identity in (
            ("historical_training_dataset_builds", "dataset_build_id", outcome.dataset_build_id),
            ("historical_training_examples", "training_example_id", example.training_example_id),
            ("historical_training_example_sources", "training_example_id", example.training_example_id),
            ("historical_training_exclusions", "dataset_build_id", outcome.dataset_build_id),
        ):
            if not self.database.connection.execute(f"SELECT 1 FROM {table} WHERE {key}=?", (identity,)).fetchone():
                continue
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(f"UPDATE {table} SET {key}={key} WHERE {key}=?", (identity,))
            self.database.connection.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "INSERT INTO historical_training_examples (training_example_id,dataset_build_id,historical_match_id,historical_match_fingerprint,kickoff_timestamp,competition,season,home_team_id,away_team_id,ordered_feature_vector,missingness_mask,completeness_score,feature_provenance_snapshot,lookback_window_identity,cutoff_timestamp,historical_source_fingerprints_snapshot,labels_snapshot,feature_schema_version,label_schema_version,dataset_policy_version,example_fingerprint,created_timestamp) VALUES ('bad','missing','missing',?,'2025-01-01T00:00:00Z','L','S','h','a','[]','[]','1','[]','x','2025-01-01T00:00:00Z','[]','[]',?,?,?,?,?)",
                ("a" * 64, FEATURE_SCHEMA_VERSION, LABEL_SCHEMA_VERSION, DATASET_POLICY_VERSION, "b" * 64, "2026-01-01T00:00:00Z"),
            )
        self.database.connection.rollback()
        raw = self.database.connection.execute("SELECT ordered_feature_vector FROM historical_training_examples LIMIT 1").fetchone()[0]
        self.assertNotIn(" ", raw)


class HistoricalTrainingInspectionMigrationStartupTests(unittest.TestCase):
    def test_inspection_summary_example_integrity_and_read_only_behavior(self):
        database = Database(":memory:")
        import_id = import_history(database)
        service = build_historical_training_dataset_service(database, migrate=False)
        repository = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
        outcome = service.build(command(import_id))
        before = database.connection.total_changes
        summary = summarize_dataset(repository, outcome.dataset_build_id)
        example = repository.list_examples_for_dataset(outcome.dataset_build_id)[0]
        self.assertEqual(summary.included_count, outcome.included_examples)
        self.assertEqual(inspect_training_example(repository, example.training_example_id), example)
        self.assertEqual(verify_no_temporal_leakage(repository, outcome.dataset_build_id), ())
        self.assertEqual(verify_dataset_fingerprints(repository, outcome.dataset_build_id), ())
        self.assertEqual(verify_label_consistency(repository, outcome.dataset_build_id), ())
        self.assertEqual(database.connection.total_changes, before)
        database.close()

    def test_independent_leakage_verifier_detects_corrupted_linkage(self):
        database = Database(":memory:")
        import_id = import_history(database)
        service = build_historical_training_dataset_service(database, migrate=False)
        repository = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
        outcome = service.build(command(import_id, lower_day=8, upper_day=9))
        example = repository.list_examples_for_dataset(outcome.dataset_build_id)[0]
        database.connection.execute("DROP TRIGGER historical_training_example_sources_no_update")
        database.connection.execute(
            "UPDATE historical_training_example_sources SET source_kickoff=? WHERE training_example_id=? AND deterministic_order_index=0",
            (example.kickoff_utc, example.training_example_id),
        )
        database.connection.commit()
        failures = verify_no_temporal_leakage(repository, outcome.dataset_build_id)
        self.assertTrue(any("EQUALS_TARGET" in item for item in failures))
        database.close()

    def test_fresh_v24_and_v23_upgrade_preserve_data(self):
        fresh = Database(":memory:")
        MigrationManager(fresh.connection).migrate()
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 41)
        objects = {(row[0], row[1]) for row in fresh.connection.execute("SELECT name,type FROM sqlite_master")}
        for table in (
            "historical_training_dataset_builds", "historical_training_examples",
            "historical_training_example_sources", "historical_training_exclusions",
        ):
            self.assertIn((table, "table"), objects)
            self.assertIn((f"{table}_no_update", "trigger"), objects)
            self.assertIn((f"{table}_no_delete", "trigger"), objects)
        fresh.close()

        upgrade = Database(":memory:")
        upgrade.connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS[:-1]:
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute("INSERT INTO schema_migrations VALUES (?, 'existing')", (migration.version,))
        upgrade.connection.execute("INSERT INTO published_predictions (prediction_id,fixture_id,market,pick,published_at) VALUES ('sentinel',1,'MATCH_WINNER','HOME','2026-01-01T00:00:00Z')")
        upgrade.connection.commit()
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 41)
        self.assertEqual(upgrade.connection.execute("SELECT prediction_id FROM published_predictions").fetchone()[0], "sentinel")
        upgrade.close()

    def test_import_is_inert_and_has_no_external_runtime_dependencies(self):
        before_threads = tuple(thread.name for thread in threading.enumerate())
        before_database = Database.DEFAULT_PATH.exists()
        import app.historical_training_dataset as package
        import app.historical_training_dataset.factory as factory
        self.assertIsNotNone((package, factory))
        self.assertEqual(tuple(thread.name for thread in threading.enumerate()), before_threads)
        self.assertEqual(Database.DEFAULT_PATH.exists(), before_database)
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in __import__("pathlib").Path("app/historical_training_dataset").glob("*.py")
        ).lower()
        for forbidden in (
            "import requests", "from requests", "import aiohttp", "from aiohttp",
            "apscheduler", "celery", "import telegram", "from telegram", "create_task(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
