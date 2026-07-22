import asyncio
import sqlite3
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.calibration import CalibrationScope
from app.database import Database, MigrationManager
from app.models import Match
from app.quality_gate import (
    EvidenceAssessment,
    EvidenceCategory,
    EvidenceStatus,
)
from app.quality_gate_shadow import (
    ShadowEvaluationOutcome,
    ShadowModeConfig,
    ShadowObservationFacts,
    build_quality_gate_shadow_observer,
)
from app.team_availability import (
    AvailabilityBacktestingAdapter,
    AvailabilityErrorCode,
    AvailabilityEvidenceStatus,
    AvailabilityFreshnessPolicy,
    AvailabilityIngestionService,
    AvailabilityQualityGateAdapter,
    AvailabilityReason,
    AvailabilityReliability,
    AvailabilityShadowFactsProvider,
    AvailabilitySource,
    AvailabilityValidationPolicy,
    AvailabilityValidator,
    ExistingFootballApiAvailabilityAdapter,
    FixtureTeamSide,
    LineupConfirmationPolicy,
    LineupObservation,
    LineupPlayer,
    LineupStatus,
    LineupType,
    NoOpPlayerImpactEstimator,
    NullAvailabilityProvider,
    PlayerAvailabilityObservation,
    PlayerAvailabilityStatus,
    PlayerIdentity,
    PlayerImportanceInput,
    PublicationStage,
    SQLiteTeamAvailabilityRepository,
    StaticAvailabilityProvider,
    TeamAvailabilityIngestionConfig,
    TeamAvailabilityRuntime,
    TeamAvailabilitySnapshotBuilder,
    TeamIdentity,
    normalize_formation,
    normalize_player,
    normalize_position,
    normalize_reason,
    normalize_team,
)


NOW = datetime(2026, 7, 16, 10, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=3)
TEAM = TeamIdentity("1", "Home")
SOURCE = AvailabilitySource(
    "test-source",
    "Test Source",
    1,
    AvailabilityReliability.RELIABLE,
    True,
)


def player(
    player_id: str | None = "10",
    name: str = "Player One",
) -> PlayerIdentity:
    return PlayerIdentity(player_id, name)


def availability(
    observation_id: str = "availability-1",
    *,
    identity: PlayerIdentity | None = None,
    status: PlayerAvailabilityStatus = PlayerAvailabilityStatus.AVAILABLE,
    reason: AvailabilityReason = AvailabilityReason.NONE,
    observed_at: datetime = NOW,
    source_name: str = "Test Source",
    team: TeamIdentity = TEAM,
) -> PlayerAvailabilityObservation:
    return PlayerAvailabilityObservation(
        observation_id=observation_id,
        fixture_id="500",
        competition="Premier League",
        team=team,
        player=identity or player(),
        fixture_team_side=FixtureTeamSide.HOME,
        availability_status=status,
        reason=reason,
        provider_reason_text=None,
        observed_at=observed_at,
        source_name=source_name,
        source_reference=f"ref:{observation_id}",
        expected_return_at=None,
        confidence=Decimal("0.8"),
        created_at=observed_at,
    )


def lineup_player(
    player_id: str,
    *,
    name: str | None = None,
    starting: bool = True,
    position: str = "MIDFIELDER",
    goalkeeper: bool = False,
    captain: bool | None = False,
    order: int = 0,
) -> LineupPlayer:
    return LineupPlayer(
        player=player(player_id, name or f"Player {player_id}"),
        role="PLAYER",
        position=position,
        shirt_number=int(player_id) if player_id.isdigit() else None,
        is_starting=starting,
        is_captain=captain,
        is_goalkeeper=goalkeeper,
        source_order=order,
    )


def lineup(
    observation_id: str = "lineup-1",
    *,
    status: LineupStatus = LineupStatus.PREDICTED,
    lineup_type: LineupType = LineupType.STARTING,
    observed_at: datetime = NOW,
    players: tuple[LineupPlayer, ...] | None = None,
    formation: str | None = "4-3-3",
) -> LineupObservation:
    return LineupObservation(
        lineup_observation_id=observation_id,
        fixture_id="500",
        competition="Premier League",
        team=TEAM,
        fixture_team_side=FixtureTeamSide.HOME,
        lineup_status=status,
        lineup_type=lineup_type,
        observed_at=observed_at,
        source_name="Test Source",
        source_reference=f"ref:{observation_id}",
        formation=formation,
        players=players or (lineup_player("10"),),
        created_at=observed_at,
    )


class AvailabilityDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path("tests") / f".availability-{uuid4().hex}.db"
        self.database = Database(self.path)
        self.repository = SQLiteTeamAvailabilityRepository(self.database)
        self.repository.save_source(SOURCE)
        self.addCleanup(self.cleanup)

    def cleanup(self) -> None:
        try:
            self.database.close()
        except sqlite3.ProgrammingError:
            pass
        for suffix in ("", "-journal", "-shm", "-wal"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                candidate.unlink()


class AvailabilityDomainTests(unittest.TestCase):
    def test_player_availability_statuses_and_unknown_is_not_available(self):
        for status, reason in (
            (PlayerAvailabilityStatus.AVAILABLE, AvailabilityReason.NONE),
            (PlayerAvailabilityStatus.INJURED, AvailabilityReason.INJURY),
            (PlayerAvailabilityStatus.SUSPENDED, AvailabilityReason.SUSPENSION),
            (PlayerAvailabilityStatus.DOUBTFUL, AvailabilityReason.FITNESS),
            (PlayerAvailabilityStatus.UNKNOWN, AvailabilityReason.UNKNOWN),
        ):
            with self.subTest(status=status):
                value = availability(status=status, reason=reason)
                self.assertEqual(value.availability_status, status)
        snapshot = TeamAvailabilitySnapshotBuilder().build(
            fixture_id="500",
            team=TEAM,
            evaluation_timestamp=NOW,
            kickoff=KICKOFF,
            player_observations=(availability(
                status=PlayerAvailabilityStatus.UNKNOWN,
                reason=AvailabilityReason.UNKNOWN,
            ),),
            lineup_observations=(),
            sources=(SOURCE,),
        )
        self.assertEqual(snapshot.unknown_status_players, (player(),))
        self.assertNotIn(player(), snapshot.unavailable_players)

    def test_predicted_confirmed_partial_and_substitutes(self):
        predicted = lineup()
        confirmed = lineup("confirmed", status=LineupStatus.CONFIRMED)
        partial = lineup("partial", status=LineupStatus.PARTIAL)
        substitutes = lineup(
            "subs",
            status=LineupStatus.CONFIRMED,
            lineup_type=LineupType.SUBSTITUTE,
            players=(lineup_player("12", starting=False),),
        )
        self.assertIs(predicted.lineup_status, LineupStatus.PREDICTED)
        self.assertIs(confirmed.lineup_status, LineupStatus.CONFIRMED)
        self.assertIs(partial.lineup_status, LineupStatus.PARTIAL)
        self.assertFalse(substitutes.players[0].is_starting)

    def test_goalkeeper_captain_and_immutability(self):
        value = lineup_player(
            "1",
            position="GOALKEEPER",
            goalkeeper=True,
            captain=True,
        )
        self.assertTrue(value.is_goalkeeper)
        self.assertTrue(value.is_captain)
        with self.assertRaises(FrozenInstanceError):
            value.is_captain = False

    def test_invalid_timezone_and_confirmed_after_kickoff(self):
        with self.assertRaises(ValueError):
            availability(observed_at=NOW.replace(tzinfo=None))
        validator = AvailabilityValidator()
        with self.assertRaises(RuntimeError):
            validator.validate_lineup(
                lineup(
                    status=LineupStatus.CONFIRMED,
                    observed_at=KICKOFF + timedelta(seconds=1),
                ),
                SOURCE,
                kickoff=KICKOFF,
            )
        historical = AvailabilityValidator(AvailabilityValidationPolicy(True))
        self.assertIsNotNone(historical.validate_lineup(
            lineup(
                status=LineupStatus.CONFIRMED,
                observed_at=KICKOFF + timedelta(seconds=1),
            ),
            SOURCE,
            kickoff=KICKOFF,
        ))

    def test_observation_after_historical_cutoff_is_rejected(self):
        with self.assertRaises(RuntimeError):
            AvailabilityValidator().validate_player(
                availability(observed_at=NOW + timedelta(minutes=1)),
                SOURCE,
                evaluation_cutoff=NOW,
            )

    def test_normalization_stability_and_player_id_preference(self):
        self.assertEqual(normalize_team(" 1 ", " Home  Team "), TeamIdentity("1", "Home Team"))
        self.assertEqual(normalize_position("gk"), "GOALKEEPER")
        self.assertEqual(normalize_formation("4 – 3 – 3"), "4-3-3")
        self.assertIs(normalize_reason("injured"), AvailabilityReason.INJURY)
        first = normalize_player("10", "Same Name")
        second = normalize_player("11", "Same Name")
        self.assertNotEqual(first.identity_key, second.identity_key)

    def test_noop_player_impact_does_not_invent_importance(self):
        estimate = NoOpPlayerImpactEstimator().estimate(PlayerImportanceInput(
            player=player(),
            recent_minutes=None,
            recent_starts=None,
            position="MIDFIELDER",
            is_goalkeeper=False,
            is_captain=None,
            provider_rating=None,
            internal_strength=None,
        ))
        self.assertFalse(estimate.available)
        self.assertIsNone(estimate.score)


class AvailabilityPersistenceAndIngestionTests(AvailabilityDatabaseTestCase):
    def test_duplicate_player_and_lineup_observations_are_idempotent(self):
        service = AvailabilityIngestionService(self.repository)
        provider = StaticAvailabilityProvider(
            "Test Source",
            (availability(), lineup()),
        )
        first = service.ingest(
            (provider,),
            kickoff_by_fixture={"500": KICKOFF},
            occurred_at=NOW,
        )
        second = service.ingest(
            (provider,),
            kickoff_by_fixture={"500": KICKOFF},
            occurred_at=NOW,
        )
        self.assertEqual((first.records_inserted, second.duplicate_records), (2, 2))
        self.assertTrue(all(
            item.code is AvailabilityErrorCode.DUPLICATE_OBSERVATION
            for item in second.ordered_errors
        ))

    def test_ingestion_continues_after_malformed_record(self):
        provider = StaticAvailabilityProvider(
            "Test Source",
            (SimpleNamespace(source_name="Test Source"), availability()),
        )
        report = AvailabilityIngestionService(self.repository).ingest(
            (provider,),
            occurred_at=NOW,
        )
        self.assertEqual((report.records_received, report.records_inserted), (2, 1))
        self.assertEqual(
            report.ordered_errors[0].code,
            AvailabilityErrorCode.MALFORMED_PROVIDER_RECORD,
        )

    def test_database_restart_and_latest_before_cutoff(self):
        past = availability("past", observed_at=NOW)
        future = availability(
            "future",
            status=PlayerAvailabilityStatus.INJURED,
            reason=AvailabilityReason.INJURY,
            observed_at=NOW + timedelta(hours=1),
        )
        self.repository.insert_player(past)
        self.repository.insert_player(future)
        self.repository.insert_lineup(lineup())
        latest = self.repository.latest_player_before(
            "500", "1", player().identity_key, NOW + timedelta(minutes=1)
        )
        self.assertEqual(latest, (past,))
        self.database.close()
        self.database = Database(self.path)
        restarted = SQLiteTeamAvailabilityRepository(self.database)
        self.assertEqual(
            restarted.player_observations("500", "1"),
            (past, future),
        )
        self.assertEqual(restarted.lineup_observations("500", "1"), (lineup(),))

    def test_disabled_unknown_sources_and_decimal_text(self):
        unknown = AvailabilityIngestionService(self.repository).ingest(
            (StaticAvailabilityProvider("Unknown", (replace(
                availability(), source_name="Unknown"
            ),)),),
            occurred_at=NOW,
        )
        self.assertEqual(unknown.ordered_errors[0].code, AvailabilityErrorCode.UNKNOWN_SOURCE)
        disabled = replace(SOURCE, source_id="disabled", source_name="Disabled", enabled=False)
        self.repository.save_source(disabled)
        report = AvailabilityIngestionService(self.repository).ingest(
            (StaticAvailabilityProvider("Disabled", (replace(
                availability(), source_name="Disabled"
            ),)),),
            occurred_at=NOW,
        )
        self.assertEqual(report.ordered_errors[0].code, AvailabilityErrorCode.DISABLED_SOURCE)
        self.repository.insert_player(availability())
        row = self.database.connection.execute(
            "SELECT typeof(confidence) kind, confidence FROM player_availability_observations"
        ).fetchone()
        self.assertEqual((row["kind"], row["confidence"]), ("text", "0.8"))

    def test_null_static_and_existing_provider_adapter(self):
        self.assertEqual(NullAvailabilityProvider().observations().records, ())
        records = (availability(),)
        self.assertEqual(
            StaticAvailabilityProvider("Test Source", records).observations().records,
            records,
        )
        adapter = ExistingFootballApiAvailabilityAdapter(({
            "fixture": {"id": 500},
            "teams": {"home": {"id": 1}, "away": {"id": 2}},
        },), occurred_at=NOW)
        self.assertEqual(adapter.observations().records, ())
        self.assertFalse(adapter.capabilities.confirmed_lineups)
        malformed = ExistingFootballApiAvailabilityAdapter(
            ({"bad": "record"},),
            occurred_at=NOW,
        ).observations()
        self.assertEqual(
            malformed.errors[0].code,
            AvailabilityErrorCode.MALFORMED_PROVIDER_RECORD,
        )


class AvailabilitySnapshotTests(unittest.TestCase):
    def build(self, players=(), lineups=(), evaluation=NOW, freshness=None):
        return TeamAvailabilitySnapshotBuilder(freshness).build(
            fixture_id="500",
            team=TEAM,
            evaluation_timestamp=evaluation,
            kickoff=KICKOFF,
            player_observations=players,
            lineup_observations=lineups,
            sources=(SOURCE,),
        )

    def test_future_observations_are_excluded(self):
        result = self.build(
            players=(availability(
                status=PlayerAvailabilityStatus.INJURED,
                reason=AvailabilityReason.INJURY,
                observed_at=NOW + timedelta(minutes=1),
            ),),
        )
        self.assertEqual(result.injured_players, ())
        self.assertIs(result.data_completeness, AvailabilityEvidenceStatus.MISSING)

    def test_fresh_and_stale_injury_evidence(self):
        fresh = self.build(players=(availability(
            status=PlayerAvailabilityStatus.INJURED,
            reason=AvailabilityReason.INJURY,
        ),))
        stale = self.build(
            players=(availability(
                status=PlayerAvailabilityStatus.INJURED,
                reason=AvailabilityReason.INJURY,
                observed_at=NOW - timedelta(days=4),
            ),),
            freshness=AvailabilityFreshnessPolicy(
                injury_max_age=timedelta(days=3),
            ),
        )
        self.assertIs(fresh.data_freshness, AvailabilityEvidenceStatus.AVAILABLE)
        self.assertIs(stale.data_freshness, AvailabilityEvidenceStatus.STALE)

    def test_missing_predicted_and_confirmed_lineup_states(self):
        missing = self.build()
        predicted = self.build(lineups=(lineup(),))
        confirmed = self.build(lineups=(lineup(
            status=LineupStatus.CONFIRMED,
        ),))
        self.assertIs(missing.latest_lineup_status, LineupStatus.NOT_AVAILABLE)
        self.assertEqual(predicted.confirmed_starters, ())
        self.assertEqual(len(predicted.predicted_starters), 1)
        self.assertEqual(len(confirmed.confirmed_starters), 1)

    def test_substitutes_and_formation_are_preserved(self):
        result = self.build(lineups=(
            lineup(status=LineupStatus.CONFIRMED),
            lineup(
                "subs",
                status=LineupStatus.CONFIRMED,
                lineup_type=LineupType.SUBSTITUTE,
                players=(lineup_player("12", starting=False),),
            ),
        ))
        self.assertEqual(result.formation, "4-3-3")
        self.assertEqual(result.substitutes[0].player.player_id, "12")

    def test_conflicting_reliable_statuses_are_preserved_deterministically(self):
        second_source = AvailabilitySource(
            "second", "Second", 2, AvailabilityReliability.RELIABLE, True
        )
        first = availability(
            "available",
            status=PlayerAvailabilityStatus.AVAILABLE,
        )
        second = replace(
            availability(
                "injured",
                status=PlayerAvailabilityStatus.INJURED,
                reason=AvailabilityReason.INJURY,
            ),
            source_name="Second",
        )
        builder = TeamAvailabilitySnapshotBuilder()
        kwargs = dict(
            fixture_id="500",
            team=TEAM,
            evaluation_timestamp=NOW,
            kickoff=KICKOFF,
            player_observations=(second, first),
            lineup_observations=(),
            sources=(SOURCE, second_source),
        )
        result = builder.build(**kwargs)
        repeated = builder.build(**kwargs)
        self.assertEqual(result, repeated)
        self.assertEqual(
            result.conflicts[0].statuses,
            (
                PlayerAvailabilityStatus.AVAILABLE,
                PlayerAvailabilityStatus.INJURED,
            ),
        )
        self.assertIs(result.data_completeness, AvailabilityEvidenceStatus.PARTIAL)

    def test_snapshot_has_no_current_time_dependency(self):
        first = self.build(lineups=(lineup(),))
        second = self.build(lineups=(lineup(),))
        self.assertEqual(first, second)
        self.assertEqual(first.snapshot_timestamp, NOW)


class AvailabilityPolicyAndIntegrationTests(AvailabilityDatabaseTestCase):
    def base_facts(self) -> ShadowObservationFacts:
        return ShadowObservationFacts(
            offered_odds=Decimal("2"),
            odds_timestamp=NOW,
            calibrated_probability=Decimal("0.6"),
            calibration_method="identity",
            calibration_scope=CalibrationScope.global_scope(),
            calibration_sample_size=200,
            calibration_fit_timestamp=NOW - timedelta(days=1),
            calibration_training_cutoff=NOW - timedelta(days=2),
            model_version="v1",
            confidence_score=Decimal("0.8"),
            uncertainty_score=Decimal("0.1"),
            reference_odds=None,
            expected_value=None,
            data_completeness_status=EvidenceStatus.AVAILABLE,
            data_freshness_status=EvidenceStatus.AVAILABLE,
            lineup_status=EvidenceStatus.MISSING,
            injury_data_status=EvidenceStatus.MISSING,
            market_consensus_probability=Decimal("0.55"),
            market_disagreement=Decimal("0.05"),
            current_exposure=Decimal("0"),
            daily_exposure=Decimal("0"),
            competition_exposure=Decimal("0"),
            correlated_exposure=Decimal("0"),
            sample_size=200,
            context_calibration_sample_size=200,
            evidence=tuple(
                EvidenceAssessment(item, EvidenceStatus.MISSING)
                for item in EvidenceCategory
            ),
        )

    def match_assessment(self):
        match = Match(
            500, 39, "Premier League", 2026,
            1, "Home", 2, "Away", KICKOFF, "NS",
        )
        assessment = SimpleNamespace(prediction=SimpleNamespace(
            winner="Home",
            home_probability=60.0,
            away_probability=40.0,
            confidence="HIGH",
            rating_difference=20.0,
        ))
        return match, assessment

    def test_lineup_confirmation_policy_windows(self):
        policy = LineupConfirmationPolicy()
        self.assertIs(
            policy.expected_status(
                PublicationStage.EARLY_PREMATCH,
                time_until_kickoff=timedelta(hours=3),
            ),
            LineupStatus.PREDICTED,
        )
        self.assertIs(
            policy.expected_status(
                PublicationStage.FINAL_PRE_KICKOFF,
                time_until_kickoff=timedelta(minutes=10),
            ),
            LineupStatus.CONFIRMED,
        )

    def test_quality_gate_mapping_and_missing_remains_missing(self):
        adapter = AvailabilityQualityGateAdapter()
        missing = adapter.map(None)
        self.assertIs(missing.lineup_status, EvidenceStatus.MISSING)
        self.assertIs(missing.injury_status, EvidenceStatus.MISSING)
        snapshot = TeamAvailabilitySnapshotBuilder().build(
            fixture_id="500",
            team=TEAM,
            evaluation_timestamp=NOW,
            kickoff=KICKOFF,
            player_observations=(availability(
                status=PlayerAvailabilityStatus.INJURED,
                reason=AvailabilityReason.INJURY,
            ),),
            lineup_observations=(lineup(status=LineupStatus.CONFIRMED),),
            sources=(SOURCE,),
        )
        mapped = adapter.map(snapshot)
        self.assertIs(mapped.lineup_status, EvidenceStatus.AVAILABLE)
        self.assertIs(mapped.injury_status, EvidenceStatus.AVAILABLE)
        lineup_only = TeamAvailabilitySnapshotBuilder().build(
            fixture_id="500",
            team=TEAM,
            evaluation_timestamp=NOW,
            kickoff=KICKOFF,
            player_observations=(),
            lineup_observations=(lineup(status=LineupStatus.CONFIRMED),),
            sources=(SOURCE,),
        )
        self.assertIs(
            adapter.map(lineup_only).injury_status,
            EvidenceStatus.MISSING,
        )
        self.assertIs(
            lineup_only.data_completeness,
            AvailabilityEvidenceStatus.PARTIAL,
        )

    def test_backtesting_leakage_and_state_preservation(self):
        snapshot = TeamAvailabilitySnapshotBuilder().build(
            fixture_id="500",
            team=TEAM,
            evaluation_timestamp=NOW,
            kickoff=KICKOFF,
            player_observations=(),
            lineup_observations=(lineup(),),
            sources=(SOURCE,),
        )
        feature = AvailabilityBacktestingAdapter.feature(snapshot, NOW)
        self.assertFalse(feature.confirmed)
        self.assertIs(feature.lineup_status, LineupStatus.PREDICTED)
        with self.assertRaises(ValueError):
            AvailabilityBacktestingAdapter.feature(
                snapshot,
                NOW - timedelta(seconds=1),
            )

    def test_shadow_adapter_uses_no_future_lineup_or_injury(self):
        self.repository.insert_lineup(lineup(
            status=LineupStatus.CONFIRMED,
            observed_at=NOW + timedelta(minutes=10),
        ))
        self.repository.insert_player(availability(
            status=PlayerAvailabilityStatus.INJURED,
            reason=AvailabilityReason.INJURY,
            observed_at=NOW + timedelta(minutes=10),
        ))
        base = SimpleNamespace(facts_for=lambda match, assessment: self.base_facts())
        provider = AvailabilityShadowFactsProvider(
            base,
            self.repository,
            (SOURCE,),
        )
        match, assessment = self.match_assessment()
        facts = provider.facts_for_at(match, assessment, NOW)
        self.assertIs(facts.lineup_status, EvidenceStatus.MISSING)
        self.assertIs(facts.injury_data_status, EvidenceStatus.MISSING)

    def test_shadow_adapter_uses_synthetic_past_evidence(self):
        self.repository.insert_lineup(lineup(status=LineupStatus.CONFIRMED))
        self.repository.insert_player(availability(
            status=PlayerAvailabilityStatus.INJURED,
            reason=AvailabilityReason.INJURY,
        ))
        base = SimpleNamespace(facts_for=lambda match, assessment: self.base_facts())
        provider = AvailabilityShadowFactsProvider(
            base,
            self.repository,
            (SOURCE,),
        )
        match, assessment = self.match_assessment()
        facts = provider.facts_for_at(match, assessment, NOW)
        self.assertIs(facts.lineup_status, EvidenceStatus.AVAILABLE)
        self.assertIs(facts.injury_data_status, EvidenceStatus.AVAILABLE)

    def test_config_and_null_runtime(self):
        self.assertFalse(TeamAvailabilityIngestionConfig.from_environment({}).enabled)
        self.assertTrue(TeamAvailabilityIngestionConfig.from_environment({
            "TEAM_AVAILABILITY_INGESTION_ENABLED": "true",
        }).enabled)
        with self.assertRaises(ValueError):
            TeamAvailabilityIngestionConfig.from_environment({
                "TEAM_AVAILABILITY_INGESTION_ENABLED": "yes",
            })
        disabled = TeamAvailabilityRuntime(
            TeamAvailabilityIngestionConfig(False),
            NullAvailabilityProvider(),
            self.database,
        )
        self.assertIsNone(disabled.start())
        enabled = TeamAvailabilityRuntime(
            TeamAvailabilityIngestionConfig(True),
            NullAvailabilityProvider(),
            self.database,
        )
        self.assertEqual(enabled.start().records_received, 0)

    def test_no_publication_bankroll_or_scheduling_effects(self):
        with patch("asyncio.create_task") as scheduling:
            report = AvailabilityIngestionService(self.repository).ingest(
                (NullAvailabilityProvider(),),
                occurred_at=NOW,
            )
        self.assertEqual(report.records_received, 0)
        scheduling.assert_not_called()


class AvailabilityMigrationTests(unittest.TestCase):
    def test_migration_v6_is_idempotent_and_preserves_existing_data(self):
        path = Path("tests") / f".availability-migration-{uuid4().hex}.db"
        database = Database(path)
        try:
            database.connection.execute("CREATE TABLE existing (value TEXT)")
            database.connection.execute("INSERT INTO existing VALUES ('keep')")
            database.commit()
            MigrationManager(database.connection).migrate()
            MigrationManager(database.connection).migrate()
            versions = tuple(
                row["version"]
                for row in database.connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            )
            tables = {
                row["name"]
                for row in database.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertEqual(versions, tuple(range(1, 22)))
            self.assertTrue({
                "availability_sources",
                "player_availability_observations",
                "lineup_observations",
                "lineup_players",
            } <= tables)
            self.assertEqual(
                database.connection.execute(
                    "SELECT value FROM existing"
                ).fetchone()["value"],
                "keep",
            )
        finally:
            database.close()
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
