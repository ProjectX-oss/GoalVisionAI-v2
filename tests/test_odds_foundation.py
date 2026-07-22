import sqlite3
import sys
import unittest
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.backtesting import EvaluationOutcome
from app.calibration import CalibrationScope
from app.database import Database, MigrationManager
from app.models import Match
from app.odds import (
    BacktestingOddsAdapter,
    CLVClassification,
    CLVService,
    ClosingOddsPolicy,
    ClosingOddsRecord,
    ClosingOddsSelector,
    ClosingSelectionPath,
    ConsensusCompleteness,
    MarketDisagreementService,
    NullOddsProvider,
    OddsConsensusService,
    OddsErrorCode,
    OddsIngestionConfig,
    OddsIngestionService,
    OddsIngestionRuntime,
    OddsMarket,
    OddsMovementService,
    OddsObservation,
    OddsObservationValidator,
    OddsReliability,
    OddsRoleAssignment,
    OddsSelection,
    OddsShadowEnrichmentAdapter,
    OddsSource,
    OddsSourceType,
    OddsObservationRole,
    OddsValidationPolicy,
    SQLiteOddsRepository,
    StaticOddsProvider,
    exchange_odds_after_commission,
    normalize_decimal_odds,
    normalize_market,
    normalize_percentage_commission,
    normalize_selection,
    quantize_decimal,
)
from app.quality_gate import (
    EvidenceAssessment,
    EvidenceCategory,
    EvidenceStatus,
)
from app.quality_gate_shadow import ShadowObservationFacts


NOW = datetime(2026, 7, 16, 10, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=2)


def source(
    name: str = "Book A",
    *,
    source_type: OddsSourceType = OddsSourceType.BOOKMAKER,
    priority: int = 10,
    reliability: OddsReliability = OddsReliability.RELIABLE,
    commission_applies: bool = False,
    commission: Decimal | None = None,
    enabled: bool = True,
) -> OddsSource:
    return OddsSource(
        source_id=name.lower().replace(" ", "-"),
        source_name=name,
        source_type=source_type,
        priority=priority,
        reliability=reliability,
        commission_applies=commission_applies,
        default_commission=commission,
        enabled=enabled,
    )


def observation(
    observation_id: str = "obs-1",
    *,
    source_name: str = "Book A",
    source_type: OddsSourceType = OddsSourceType.BOOKMAKER,
    observed_at: datetime = NOW,
    kickoff: datetime = KICKOFF,
    odds: Decimal = Decimal("2.10"),
    market: OddsMarket = OddsMarket.MATCH_WINNER,
    selection: OddsSelection | None = None,
    commission: Decimal | None = None,
) -> OddsObservation:
    return OddsObservation(
        observation_id=observation_id,
        fixture_id="500",
        competition="Premier League",
        kickoff_time=kickoff,
        observed_at=observed_at,
        source_name=source_name,
        source_type=source_type,
        bookmaker_or_exchange=source_name,
        market=market,
        selection=selection or normalize_selection("home"),
        decimal_odds=odds,
        is_exchange=source_type is OddsSourceType.EXCHANGE,
        commission_rate=commission,
        created_at=observed_at,
    )


def closing(
    odds: Decimal = Decimal("2.00"),
    *,
    fixture_id: str = "500",
    market: OddsMarket = OddsMarket.MATCH_WINNER,
    selection: OddsSelection | None = None,
    observed_at: datetime = KICKOFF - timedelta(minutes=2),
) -> ClosingOddsRecord:
    return ClosingOddsRecord(
        closing_id="close-1",
        fixture_id=fixture_id,
        market=market,
        selection=selection or normalize_selection("home"),
        kickoff_time=KICKOFF,
        selected_at=KICKOFF,
        closing_observed_at=observed_at,
        decimal_odds=odds,
        source_name="Book A",
        source_type=OddsSourceType.BOOKMAKER,
        selection_path=ClosingSelectionPath.PRIORITY_BOOKMAKER,
        source_count=1,
        cutoff=KICKOFF - timedelta(minutes=1),
        observation_id="obs-closing",
    )


class OddsDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path("tests") / f".odds-{uuid4().hex}.db"
        self.database = Database(self.path)
        self.repository = SQLiteOddsRepository(self.database)
        self.repository.save_source(source())
        self.addCleanup(self.cleanup_database)

    def cleanup_database(self) -> None:
        try:
            self.database.close()
        except sqlite3.ProgrammingError:
            pass
        for suffix in ("", "-journal", "-shm", "-wal"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                candidate.unlink()


class OddsDomainAndValidationTests(unittest.TestCase):
    def test_valid_bookmaker_observation_is_immutable(self):
        value = OddsObservationValidator().validate(observation(), source())
        self.assertEqual(value.decimal_odds, Decimal("2.10"))
        with self.assertRaises(FrozenInstanceError):
            value.decimal_odds = Decimal("2")

    def test_valid_exchange_and_commission_adjustment(self):
        exchange = source(
            "Exchange A",
            source_type=OddsSourceType.EXCHANGE,
            commission_applies=True,
            commission=Decimal("0.05"),
        )
        value = observation(
            source_name="Exchange A",
            source_type=OddsSourceType.EXCHANGE,
            odds=Decimal("3"),
        )
        adjusted = OddsObservationValidator().validate(value, exchange)
        self.assertEqual(adjusted.decimal_odds, Decimal("2.90"))
        self.assertEqual(
            exchange_odds_after_commission(Decimal("3"), Decimal("5")),
            Decimal("2.90"),
        )

    def test_invalid_odds_nan_and_infinity_are_rejected(self):
        for value in (Decimal("1"), Decimal("0.9"), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_decimal_odds(value)

    def test_missing_timezone_is_rejected(self):
        with self.assertRaises(ValueError):
            observation(observed_at=NOW.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            observation(kickoff=KICKOFF.replace(tzinfo=None))

    def test_after_and_exact_kickoff_policy(self):
        validator = OddsObservationValidator()
        with self.assertRaises(RuntimeError):
            validator.validate(observation(observed_at=KICKOFF + timedelta(seconds=1)), source())
        with self.assertRaises(RuntimeError):
            validator.validate(observation(observed_at=KICKOFF), source())
        accepted = OddsObservationValidator(OddsValidationPolicy(True)).validate(
            observation(observed_at=KICKOFF),
            source(),
        )
        self.assertEqual(accepted.observed_at, KICKOFF)

    def test_unknown_disabled_and_missing_exchange_commission(self):
        with self.assertRaises(LookupError):
            OddsObservationValidator().validate(observation(), None)
        with self.assertRaises(PermissionError):
            OddsObservationValidator().validate(observation(), source(enabled=False))
        exchange = source(
            "Exchange A",
            source_type=OddsSourceType.EXCHANGE,
            commission_applies=True,
        )
        with self.assertRaises(ValueError):
            OddsObservationValidator().validate(
                observation(
                    source_name="Exchange A",
                    source_type=OddsSourceType.EXCHANGE,
                ),
                exchange,
            )

    def test_invalid_commission_and_explicit_quantization(self):
        for value in (Decimal("-0.1"), Decimal("100"), Decimal("Infinity")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_percentage_commission(value)
        self.assertEqual(normalize_percentage_commission(Decimal("5")), Decimal("0.05"))
        self.assertEqual(quantize_decimal(Decimal("1.234"), Decimal("0.01")), Decimal("1.23"))

    def test_market_and_selection_normalization_is_deterministic(self):
        self.assertIs(normalize_market("Match Winner"), OddsMarket.MATCH_WINNER)
        first = normalize_selection(" Over ", line=Decimal("2.5"))
        second = normalize_selection("Over", line=Decimal("2.5"))
        self.assertEqual(first, second)

    def test_observation_roles_are_separate_immutable_assignments(self):
        assignment = OddsRoleAssignment(
            assignment_id="role-1",
            observation_id="obs-1",
            role=OddsObservationRole.PUBLICATION,
            assigned_at=NOW,
        )
        self.assertEqual(assignment.role, OddsObservationRole.PUBLICATION)
        with self.assertRaises(FrozenInstanceError):
            assignment.role = OddsObservationRole.CLOSING


class OddsPersistenceAndIngestionTests(OddsDatabaseTestCase):
    def test_duplicate_is_idempotent_and_decimal_is_text(self):
        service = OddsIngestionService(self.repository)
        provider = StaticOddsProvider("Book A", (observation(),))
        first = service.ingest((provider,), occurred_at=NOW)
        second = service.ingest((provider,), occurred_at=NOW)
        self.assertEqual((first.inserted_count, second.duplicate_count), (1, 1))
        row = self.database.connection.execute(
            "SELECT typeof(decimal_odds) kind, decimal_odds FROM odds_observations"
        ).fetchone()
        self.assertEqual((row["kind"], row["decimal_odds"]), ("text", "2.10"))

    def test_batch_continues_after_invalid_observation(self):
        invalid = SimpleNamespace(
            source_name="Book A",
            fixture_id="bad",
            market="MATCH_WINNER",
            selection="home",
        )
        provider = StaticOddsProvider("Book A", (invalid, observation()))
        report = OddsIngestionService(self.repository).ingest((provider,), occurred_at=NOW)
        self.assertEqual((report.received_count, report.inserted_count, report.rejected_count), (2, 1, 1))
        self.assertEqual(report.ordered_errors[0].code, OddsErrorCode.INVALID_ODDS)

    def test_unknown_and_disabled_sources_are_audited(self):
        unknown = OddsIngestionService(self.repository).ingest(
            (StaticOddsProvider("Unknown", (replace(observation(), source_name="Unknown"),)),),
            occurred_at=NOW,
        )
        self.assertEqual(unknown.ordered_errors[0].code, OddsErrorCode.UNKNOWN_SOURCE)
        self.repository.save_source(source("Disabled", enabled=False))
        disabled = OddsIngestionService(self.repository).ingest(
            (StaticOddsProvider("Disabled", (replace(observation(), source_name="Disabled"),)),),
            occurred_at=NOW,
        )
        self.assertEqual(disabled.ordered_errors[0].code, OddsErrorCode.DISABLED_SOURCE)

    def test_database_restart_opening_latest_and_closing_persistence(self):
        earlier = observation("earlier", observed_at=NOW - timedelta(hours=1), odds=Decimal("2.20"))
        later = observation("later", observed_at=NOW + timedelta(minutes=10), odds=Decimal("2.00"))
        for item in (later, earlier):
            self.assertTrue(self.repository.insert_observation(item))
        self.assertEqual(self.repository.opening("500", OddsMarket.MATCH_WINNER, "home"), earlier)
        self.assertEqual(
            self.repository.latest_before("500", OddsMarket.MATCH_WINNER, "home", NOW + timedelta(minutes=5)),
            earlier,
        )
        record = replace(closing(), observation_id="later")
        self.assertTrue(self.repository.save_closing(record))
        self.database.close()
        self.database = Database(self.path)
        restarted = SQLiteOddsRepository(self.database)
        self.assertEqual(restarted.get_observation("later"), later)
        self.assertEqual(restarted.get_closing("500", OddsMarket.MATCH_WINNER, "home"), record)

    def test_source_and_time_range_lookups(self):
        self.repository.insert_observation(observation("one", observed_at=NOW))
        self.repository.insert_observation(observation("two", observed_at=NOW + timedelta(minutes=5)))
        rows = self.repository.observations(
            source_name="Book A",
            start_at=NOW + timedelta(minutes=1),
            end_at=NOW + timedelta(minutes=6),
        )
        self.assertEqual(tuple(item.observation_id for item in rows), ("two",))

    def test_null_and_static_provider_behaviour(self):
        self.assertEqual(NullOddsProvider().observations(), ())
        values = (observation(),)
        self.assertEqual(StaticOddsProvider("Book A", values).observations(), values)


class OddsConsensusMovementAndCLVTests(unittest.TestCase):
    def test_consensus_count_mean_median_weighted_and_dispersion(self):
        values = (
            observation("a", source_name="A", odds=Decimal("2.0")),
            observation("b", source_name="B", odds=Decimal("2.2")),
            observation("c", source_name="C", odds=Decimal("2.4")),
        )
        result = OddsConsensusService().calculate(
            values,
            source_weights={"A": Decimal("2"), "B": Decimal("1"), "C": Decimal("1")},
        )
        self.assertEqual(result.source_count, 3)
        self.assertEqual((result.mean_odds, result.median_odds), (Decimal("2.2"), Decimal("2.2")))
        self.assertEqual(result.weighted_mean_odds, Decimal("2.15"))
        self.assertEqual(result.source_dispersion, Decimal("0.4"))

    def test_complete_and_incomplete_match_winner_no_vig(self):
        group = (
            observation("h", selection=normalize_selection("home"), odds=Decimal("2")),
            observation("d", selection=normalize_selection("draw"), odds=Decimal("4")),
            observation("a", selection=normalize_selection("away"), odds=Decimal("4")),
        )
        complete = OddsConsensusService().calculate((group[0],), market_group=group)
        self.assertIs(complete.completeness, ConsensusCompleteness.COMPLETE)
        self.assertEqual(dict(complete.no_vig_probabilities)["home"], Decimal("0.5"))
        incomplete = OddsConsensusService().calculate((group[0],), market_group=group[:2])
        self.assertIs(incomplete.completeness, ConsensusCompleteness.INCOMPLETE)
        self.assertEqual(incomplete.no_vig_probabilities, ())

    def test_btts_and_over_under_same_line_no_vig(self):
        btts = (
            observation("yes", market=OddsMarket.BTTS, selection=normalize_selection("yes"), odds=Decimal("2")),
            observation("no", market=OddsMarket.BTTS, selection=normalize_selection("no"), odds=Decimal("2")),
        )
        self.assertIs(
            OddsConsensusService().calculate((btts[0],), market_group=btts).completeness,
            ConsensusCompleteness.COMPLETE,
        )
        totals = (
            observation("over", market=OddsMarket.OVER_UNDER_GOALS, selection=normalize_selection("over", line=Decimal("2.5"))),
            observation("under", market=OddsMarket.OVER_UNDER_GOALS, selection=normalize_selection("under", line=Decimal("3.5"))),
        )
        self.assertIs(
            OddsConsensusService().calculate((totals[0],), market_group=totals).completeness,
            ConsensusCompleteness.INCOMPLETE,
        )

    def test_disagreement_formula(self):
        group = (
            observation("h", selection=normalize_selection("home"), odds=Decimal("2")),
            observation("d", selection=normalize_selection("draw"), odds=Decimal("4")),
            observation("a", selection=normalize_selection("away"), odds=Decimal("4")),
        )
        consensus = OddsConsensusService().calculate((group[0],), market_group=group)
        result = MarketDisagreementService().compare(Decimal("0.60"), consensus)
        self.assertEqual(result.signed_disagreement, Decimal("0.10"))
        self.assertEqual(result.absolute_disagreement, Decimal("0.10"))
        self.assertEqual(result.model_edge, Decimal("0.10"))

    def test_opening_current_and_publication_closing_movement(self):
        opening = observation("open", observed_at=NOW, odds=Decimal("2.20"))
        current = observation("current", observed_at=NOW + timedelta(minutes=30), odds=Decimal("2.00"))
        service = OddsMovementService()
        first = service.analyze((opening, current))
        second = service.analyze((opening, current), start_observation=current, end_observation=observation(
            "close-obs", observed_at=KICKOFF - timedelta(minutes=2), odds=Decimal("1.90")
        ), closing=closing(Decimal("1.90")))
        self.assertEqual(first.absolute_change, Decimal("-0.20"))
        self.assertEqual(second.opening_odds, Decimal("2.00"))
        self.assertEqual(second.closing_odds, Decimal("1.90"))

    def test_positive_zero_negative_and_missing_clv(self):
        publication = observation(odds=Decimal("2.10"))
        service = CLVService()
        cases = (
            (Decimal("2.00"), CLVClassification.POSITIVE),
            (Decimal("2.10"), CLVClassification.ZERO),
            (Decimal("2.20"), CLVClassification.NEGATIVE),
        )
        for odds, expected in cases:
            with self.subTest(odds=odds):
                self.assertIs(service.calculate(publication, closing(odds)).classification, expected)
        self.assertIs(service.calculate(publication, None).classification, CLVClassification.UNAVAILABLE)

    def test_clv_identity_and_timestamp_mismatches_are_rejected(self):
        service = CLVService()
        with self.assertRaises(ValueError):
            service.calculate(observation(), closing(fixture_id="501"))
        with self.assertRaises(ValueError):
            service.calculate(observation(), closing(market=OddsMarket.BTTS))
        with self.assertRaises(ValueError):
            service.calculate(
                observation(),
                closing(selection=normalize_selection("away")),
            )
        with self.assertRaises(ValueError):
            service.calculate(
                observation(observed_at=KICKOFF - timedelta(seconds=30)),
                closing(observed_at=KICKOFF - timedelta(minutes=1)),
            )

    def test_repeated_calculations_and_decimal_stability(self):
        publication = observation(odds=Decimal("1.333333333333333333"))
        value = closing(Decimal("1.111111111111111111"))
        first = CLVService().calculate(publication, value)
        second = CLVService().calculate(publication, value)
        self.assertEqual(first, second)
        self.assertIsInstance(first.raw_clv, Decimal)


class ClosingSelectionTests(unittest.TestCase):
    def test_preferred_exchange_then_consensus_then_priority_bookmaker(self):
        exchange_source = source(
            "Exchange A",
            source_type=OddsSourceType.EXCHANGE,
            priority=1,
            commission_applies=True,
            commission=Decimal("0.02"),
        )
        book_a = source("Book A", priority=5)
        book_b = source("Book B", priority=10)
        observations = (
            observation("ex", source_name="Exchange A", source_type=OddsSourceType.EXCHANGE, observed_at=KICKOFF - timedelta(minutes=3)),
            observation("a", source_name="Book A", observed_at=KICKOFF - timedelta(minutes=4)),
            observation("b", source_name="Book B", observed_at=KICKOFF - timedelta(minutes=2)),
        )
        preferred = ClosingOddsSelector(ClosingOddsPolicy(
            preferred_source_ids=("exchange-a",),
        )).select(observations, (exchange_source, book_a, book_b), kickoff=KICKOFF, selected_at=KICKOFF)
        self.assertIs(preferred.path, ClosingSelectionPath.PREFERRED_EXCHANGE)
        consensus = ClosingOddsSelector().select(
            observations[1:],
            (book_a, book_b),
            kickoff=KICKOFF,
            selected_at=KICKOFF,
        )
        self.assertIs(consensus.path, ClosingSelectionPath.WEIGHTED_CONSENSUS)
        priority = ClosingOddsSelector(ClosingOddsPolicy(minimum_consensus_sources=3)).select(
            observations[1:],
            (book_a, book_b),
            kickoff=KICKOFF,
            selected_at=KICKOFF,
        )
        self.assertEqual((priority.path, priority.record.source_name), (ClosingSelectionPath.PRIORITY_BOOKMAKER, "Book A"))

    def test_after_cutoff_is_never_selected_and_unavailable_is_explicit(self):
        result = ClosingOddsSelector().select(
            (observation(observed_at=KICKOFF),),
            (source(),),
            kickoff=KICKOFF,
            selected_at=KICKOFF,
        )
        self.assertIs(result.path, ClosingSelectionPath.UNAVAILABLE)
        self.assertIsNone(result.record)
        zero_cutoff = ClosingOddsSelector(ClosingOddsPolicy(
            cutoff_before_kickoff=timedelta(0),
        )).select(
            (observation(observed_at=KICKOFF),),
            (source(),),
            kickoff=KICKOFF,
            selected_at=KICKOFF,
        )
        self.assertIs(zero_cutoff.path, ClosingSelectionPath.UNAVAILABLE)


class OddsIntegrationAndConfigurationTests(OddsDatabaseTestCase):
    def facts(self) -> ShadowObservationFacts:
        return ShadowObservationFacts(
            offered_odds=Decimal("9"),
            odds_timestamp=NOW - timedelta(days=1),
            calibrated_probability=Decimal("0.60"),
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
            market_consensus_probability=None,
            market_disagreement=None,
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

    def test_backtesting_adapter_validates_leakage(self):
        publication = observation(observed_at=NOW)
        record = BacktestingOddsAdapter.build_record(
            publication=publication,
            closing=closing(),
            competition="Premier League",
            kickoff=KICKOFF,
            prediction_timestamp=NOW,
            feature_timestamp=NOW,
            model_probability=Decimal("0.6"),
            result="2-0",
            outcome=EvaluationOutcome.WON,
            profit_loss=Decimal("1.1"),
        )
        self.assertEqual(record.offered_odds, Decimal("2.10"))
        with self.assertRaises(ValueError):
            BacktestingOddsAdapter.build_record(
                publication=replace(publication, observed_at=NOW + timedelta(seconds=1)),
                closing=closing(),
                competition="Premier League",
                kickoff=KICKOFF,
                prediction_timestamp=NOW,
                feature_timestamp=NOW,
                model_probability=Decimal("0.6"),
                result="2-0",
                outcome=EvaluationOutcome.WON,
                profit_loss=Decimal("1.1"),
            )

    def test_shadow_enrichment_uses_only_past_observations(self):
        past = observation("past", observed_at=NOW, odds=Decimal("2"))
        future = observation("future", observed_at=NOW + timedelta(minutes=20), odds=Decimal("5"))
        self.repository.insert_observation(past)
        self.repository.insert_observation(future)
        match = Match(500, 39, "Premier League", 2026, 1, "Home", 2, "Away", KICKOFF, "NS")
        assessment = SimpleNamespace(prediction=SimpleNamespace(
            winner="Home",
            home_probability=60.0,
            away_probability=40.0,
        ))
        result = OddsShadowEnrichmentAdapter(
            self.repository,
            enabled=True,
        ).enrich(match, assessment, NOW + timedelta(minutes=5), self.facts())
        self.assertEqual(result.facts.offered_odds, Decimal("2"))
        self.assertLessEqual(result.facts.odds_timestamp, NOW + timedelta(minutes=5))

    def test_shadow_missing_and_disabled_data_remain_explicit(self):
        match = Match(500, 39, "Premier League", 2026, 1, "Home", 2, "Away", KICKOFF, "NS")
        assessment = SimpleNamespace(prediction=SimpleNamespace(
            winner="Home",
            home_probability=60.0,
            away_probability=40.0,
        ))
        missing = OddsShadowEnrichmentAdapter(self.repository, enabled=True).enrich(
            match, assessment, NOW, self.facts()
        )
        disabled = OddsShadowEnrichmentAdapter(self.repository, enabled=False).enrich(
            match, assessment, NOW, self.facts()
        )
        self.assertIn("offered_odds", missing.unavailable_fields)
        self.assertEqual(disabled.facts.offered_odds, Decimal("9"))

    def test_config_is_strict_disabled_by_default(self):
        self.assertFalse(OddsIngestionConfig.from_environment({}).enabled)
        self.assertTrue(OddsIngestionConfig.from_environment({"ODDS_INGESTION_ENABLED": "true"}).enabled)
        with self.assertRaises(ValueError):
            OddsIngestionConfig.from_environment({"ODDS_INGESTION_ENABLED": "yes"})

    def test_disabled_and_enabled_null_provider_runtime_startup(self):
        disabled = OddsIngestionRuntime(
            OddsIngestionConfig(False),
            NullOddsProvider(),
            self.database,
        )
        self.assertIsNone(disabled.start())
        enabled = OddsIngestionRuntime(
            OddsIngestionConfig(True),
            NullOddsProvider(),
            self.database,
        )
        report = enabled.start()
        self.assertEqual((report.received_count, report.inserted_count), (0, 0))

    def test_no_telegram_bankroll_scheduling_or_scraping_side_effects(self):
        bankroll_engine = sys.modules["app.bankroll.engine"]
        with ExitStack() as stack:
            bankroll = stack.enter_context(patch.object(
                bankroll_engine.OfficialBankrollSettlementEngine,
                "settle",
            ))
            scheduling = stack.enter_context(patch("asyncio.create_task"))
            telegram = None
            if "app.services.telegram_service" in sys.modules:
                telegram = stack.enter_context(patch.object(
                    sys.modules[
                        "app.services.telegram_service"
                    ].TelegramService,
                    "send_message",
                ))
            network = None
            if "httpx" in sys.modules:
                network = stack.enter_context(patch.object(
                    sys.modules["httpx"].AsyncClient,
                    "get",
                ))
            report = OddsIngestionService(self.repository).ingest(
                (NullOddsProvider(),),
                occurred_at=NOW,
            )
        self.assertEqual(report.received_count, 0)
        bankroll.assert_not_called()
        scheduling.assert_not_called()
        if telegram is not None:
            telegram.assert_not_called()
        if network is not None:
            network.assert_not_called()


class OddsMigrationTests(unittest.TestCase):
    def test_migration_v5_is_idempotent_and_preserves_existing_data(self):
        path = Path("tests") / f".odds-migration-{uuid4().hex}.db"
        database = Database(path)
        try:
            database.connection.execute("CREATE TABLE existing (value TEXT)")
            database.connection.execute("INSERT INTO existing VALUES ('keep')")
            database.commit()
            MigrationManager(database.connection).migrate()
            MigrationManager(database.connection).migrate()
            versions = tuple(
                row["version"] for row in database.connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            )
            tables = {
                row["name"] for row in database.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertEqual(versions, tuple(range(1, 22)))
            self.assertTrue({"odds_sources", "odds_observations", "closing_odds"} <= tables)
            self.assertEqual(
                database.connection.execute("SELECT value FROM existing").fetchone()["value"],
                "keep",
            )
        finally:
            database.close()
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
