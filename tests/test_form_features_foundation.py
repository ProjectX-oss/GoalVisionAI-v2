import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.database import Database, MigrationManager
from app.form_features import (
    DistortionEvidenceStatus,
    ExistingFootballHistoricalAdapter,
    ExpectedGoalsStatus,
    FormBacktestingAdapter,
    FormEvidenceStatus,
    FormFeatureErrorCode,
    FormFeatureIngestionConfig,
    FormFeaturePolicy,
    MatchDistortionPolicy,
    FormQualityGateAdapter,
    FormShadowFactsProvider,
    FormSignal,
    FormSnapshotBuilder,
    HistoricalMatchIngestionService,
    HistoricalMatchObservation,
    NullHistoricalMatchProvider,
    OpponentStrengthObservation,
    OpponentStrengthSource,
    OpponentStrengthTransform,
    RecencyWeight,
    SQLiteFormFeatureRepository,
    StaticHistoricalMatchProvider,
    VenueSplit,
    build_form_feature_runtime,
)
from app.models import Match
from app.explanations import DEFAULT_EXPLANATION_CONFIG, PredictionExplanationEngine
from app.h2h import H2HEngine
from app.league_strength import LEAGUE_STRENGTH_RATINGS, LeagueStrengthEngine
from app.pipeline import PredictionPipeline
from app.quality_score import DEFAULT_QUALITY_SCORE_CONFIG, QualityScoreEngine
from app.rest_days import RestDaysEngine
from app.quality_gate import EvidenceAssessment, EvidenceCategory, EvidenceStatus
from app.quality_gate_shadow import ShadowObservationFacts
from app.calibration import CalibrationScope


NOW = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
TARGET = NOW + timedelta(days=1)


def observation(
    fixture_id: str,
    *,
    days_ago: int = 1,
    home: str = "1",
    away: str = "2",
    home_goals: int = 2,
    away_goals: int = 1,
    status: str = "FT",
    observed_at: datetime | None = None,
    home_xg: Decimal | None = None,
    away_xg: Decimal | None = None,
    home_shots: int | None = None,
    away_shots: int | None = None,
) -> HistoricalMatchObservation:
    kickoff = NOW - timedelta(days=days_ago)
    return HistoricalMatchObservation(
        fixture_id=fixture_id,
        competition="Premier League",
        kickoff_time=kickoff,
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
        match_status=status,
        observed_at=observed_at or kickoff + timedelta(hours=2),
        home_xg=home_xg,
        away_xg=away_xg,
        home_shots=home_shots,
        away_shots=away_shots,
        home_red_cards=None,
        away_red_cards=None,
        penalties=None,
        source_name="TEST",
        source_reference=f"fixture:{fixture_id}",
        created_at=NOW,
    )


def build(
    observations,
    *,
    venue=VenueSplit.HOME,
    policy=None,
    strengths=(),
    evaluation=NOW,
):
    return FormSnapshotBuilder().build(
        target_fixture_id="target",
        target_kickoff=TARGET,
        team_id="1",
        venue=venue,
        evaluation_timestamp=evaluation,
        historical_observations=tuple(observations),
        opponent_strengths=tuple(strengths),
        policy=policy,
    )


class FormDomainTests(unittest.TestCase):
    def test_completed_match_is_immutable_and_invalid_inputs_are_rejected(self):
        item = observation("1")
        self.assertTrue(item.completed)
        with self.assertRaises(FrozenInstanceError):
            item.home_goals = 3
        with self.assertRaises(ValueError):
            replace(item, kickoff_time=datetime(2026, 1, 1))
        with self.assertRaises(ValueError):
            replace(item, home_goals=-1)

    def test_no_fake_xg_and_goals_fields_remain_distinct(self):
        snapshot = build((observation("1"),))
        xg = snapshot.form.expected_goals
        self.assertEqual(xg.status, ExpectedGoalsStatus.MISSING)
        self.assertIsNone(xg.xg_for)
        self.assertEqual(snapshot.form.overall.average_goals_for, Decimal("2"))

    def test_genuine_xg_is_supported_without_goal_proxying(self):
        snapshot = build(
            (
                observation(
                    "1",
                    home_xg=Decimal("1.40"),
                    away_xg=Decimal("0.70"),
                ),
            )
        )
        xg = snapshot.form.expected_goals
        self.assertEqual(xg.status, ExpectedGoalsStatus.AVAILABLE)
        self.assertEqual(xg.average_xg_for, Decimal("1.40"))
        self.assertEqual(snapshot.form.overall.average_goals_for, Decimal("2"))

    def test_partial_xg_remains_partial_and_never_fills_missing_rows(self):
        snapshot = build(
            (
                observation(
                    "1",
                    home_xg=Decimal("1.20"),
                    away_xg=Decimal("0.80"),
                ),
                observation("2", days_ago=2),
            )
        )
        self.assertEqual(
            snapshot.form.expected_goals.status,
            ExpectedGoalsStatus.PARTIAL,
        )
        self.assertEqual(snapshot.form.expected_goals.sample_size, 1)

    def test_red_card_timing_remains_unavailable(self):
        distortions = build((observation("1"),)).form.distortions
        self.assertEqual(
            distortions.early_red_card,
            DistortionEvidenceStatus.UNAVAILABLE,
        )
        self.assertEqual(
            distortions.late_red_card,
            DistortionEvidenceStatus.UNAVAILABLE,
        )
        self.assertFalse(MatchDistortionPolicy().apply_adjustments)

    def test_policy_rejects_invalid_weights(self):
        with self.assertRaises(ValueError):
            FormFeaturePolicy(explicit_weights=(Decimal("0"),))
        with self.assertRaises(ValueError):
            FormFeaturePolicy(exponential_decay=Decimal("1.1"))
        with self.assertRaises(ValueError):
            FormFeaturePolicy(
                opponent_strength_source=OpponentStrengthSource.STANDINGS_RANK,
                opponent_strength_transform=OpponentStrengthTransform.RATIO_TO_BASELINE,
            )


class FormSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.history = (
            observation("a", days_ago=4, home="1", away="2", home_goals=2, away_goals=0),
            observation("b", days_ago=3, home="3", away="1", home_goals=1, away_goals=1),
            observation("c", days_ago=2, home="1", away="4", home_goals=0, away_goals=1),
            observation("d", days_ago=1, home="5", away="1", home_goals=0, away_goals=3),
        )

    def test_counts_averages_clean_sheets_and_failed_to_score(self):
        metrics = build(self.history).form.overall
        self.assertEqual(
            (metrics.matches_played, metrics.wins, metrics.draws, metrics.losses),
            (4, 2, 1, 1),
        )
        self.assertEqual(metrics.points, 7)
        self.assertEqual(metrics.goals_for, 6)
        self.assertEqual(metrics.goals_against, 2)
        self.assertEqual(metrics.clean_sheets, 2)
        self.assertEqual(metrics.failed_to_score, 1)
        self.assertEqual(metrics.average_goals_for, Decimal("1.5"))

    def test_home_away_and_venue_fallback(self):
        snapshot = build(self.history, venue=VenueSplit.AWAY)
        self.assertEqual(snapshot.form.home.matches_played, 2)
        self.assertEqual(snapshot.form.away.matches_played, 2)
        self.assertFalse(snapshot.form.venue_fallback_used)
        fallback = build(
            self.history,
            policy=FormFeaturePolicy(venue_minimum_sample=3),
        )
        self.assertTrue(fallback.form.venue_fallback_used)
        self.assertEqual(fallback.form.evidence_status, FormEvidenceStatus.PARTIAL)

    def test_unfinished_future_and_after_cutoff_are_excluded(self):
        unfinished = observation("unfinished", status="NS")
        future = replace(observation("future"), kickoff_time=TARGET + timedelta(hours=1))
        late = observation("late", observed_at=NOW + timedelta(minutes=1))
        snapshot = build(self.history + (unfinished, future, late))
        reasons = dict(snapshot.form.excluded_fixtures)
        self.assertEqual(reasons["unfinished"], "INCOMPLETE_MATCH")
        self.assertEqual(reasons["future"], "NOT_BEFORE_TARGET")
        self.assertEqual(reasons["late"], "AFTER_EVALUATION_CUTOFF")

    def test_uniform_exponential_and_explicit_weights(self):
        uniform = build(
            self.history,
            policy=FormFeaturePolicy(recent_window=4),
        ).form.weighted.normalized_weights
        self.assertEqual(uniform, (Decimal("0.25"),) * 4)
        exponential = build(
            self.history,
            policy=FormFeaturePolicy(
                recent_window=4,
                recency_weight=RecencyWeight.EXPONENTIAL,
                exponential_decay=Decimal("0.5"),
            ),
        ).form.weighted.normalized_weights
        self.assertGreater(exponential[-1], exponential[0])
        explicit = build(
            self.history,
            policy=FormFeaturePolicy(
                recent_window=4,
                recency_weight=RecencyWeight.EXPLICIT,
                explicit_weights=(
                    Decimal("1"),
                    Decimal("2"),
                    Decimal("3"),
                    Decimal("4"),
                ),
            ),
        ).form.weighted.normalized_weights
        self.assertEqual(sum(explicit), Decimal("1"))
        self.assertEqual(explicit[-1], Decimal("0.4"))
        with self.assertRaises(ValueError):
            build(
                self.history,
                policy=FormFeaturePolicy(
                    recent_window=4,
                    recency_weight=RecencyWeight.EXPLICIT,
                    explicit_weights=(Decimal("1"), Decimal("2")),
                ),
            )

    def test_equal_timestamps_are_ordered_by_fixture_id(self):
        same = NOW - timedelta(days=2)
        values = (
            replace(observation("z"), kickoff_time=same),
            replace(observation("a"), kickoff_time=same),
        )
        self.assertEqual(build(values).form.selected_fixture_ids, ("a", "z"))

    def test_opponent_adjustment_missing_and_capped(self):
        strengths = tuple(
            OpponentStrengthObservation(
                team,
                OpponentStrengthSource.POINTS_PER_MATCH,
                value,
                NOW - timedelta(days=5),
                "table",
            )
            for team, value in (
                ("2", Decimal("5")),
                ("3", Decimal("0.1")),
                ("4", Decimal("1.5")),
            )
        )
        snapshot = build(self.history, strengths=strengths)
        factors = dict(snapshot.adjustment_factors)
        self.assertEqual(factors["2"], Decimal("1.25"))
        self.assertEqual(factors["3"], Decimal("0.75"))
        self.assertIsNone(factors["5"])
        self.assertEqual(snapshot.missing_opponents, ("5",))

    def test_missing_opponent_strength_can_use_explicit_non_neutral_fallback(self):
        snapshot = build(
            (observation("1", away="9"),),
            policy=FormFeaturePolicy(
                missing_opponent_fallback=Decimal("0.80"),
            ),
        )
        self.assertEqual(dict(snapshot.adjustment_factors)["9"], Decimal("0.80"))
        self.assertEqual(snapshot.missing_opponents, ())

    def test_inverse_rank_transformation_is_explicit_and_capped(self):
        strength = OpponentStrengthObservation(
            "2",
            OpponentStrengthSource.STANDINGS_RANK,
            Decimal("2"),
            NOW - timedelta(days=5),
            "standings",
        )
        snapshot = build(
            (observation("1"),),
            strengths=(strength,),
            policy=FormFeaturePolicy(
                opponent_strength_source=OpponentStrengthSource.STANDINGS_RANK,
                opponent_strength_transform=OpponentStrengthTransform.INVERSE_RANK_RATIO,
                opponent_baseline=Decimal("10"),
            ),
        )
        self.assertEqual(dict(snapshot.adjustment_factors)["2"], Decimal("1.25"))

    def test_genuine_xg_supports_opponent_adjustment_and_venue_splits(self):
        history = (
            observation(
                "home",
                home="1",
                away="2",
                home_xg=Decimal("1.50"),
                away_xg=Decimal("0.50"),
            ),
            observation(
                "away",
                days_ago=2,
                home="3",
                away="1",
                home_xg=Decimal("0.90"),
                away_xg=Decimal("1.10"),
            ),
        )
        strengths = (
            OpponentStrengthObservation(
                "2",
                OpponentStrengthSource.POINTS_PER_MATCH,
                Decimal("1.50"),
                NOW - timedelta(days=3),
                "table",
            ),
            OpponentStrengthObservation(
                "3",
                OpponentStrengthSource.POINTS_PER_MATCH,
                Decimal("1.50"),
                NOW - timedelta(days=3),
                "table",
            ),
        )
        xg = build(history, strengths=strengths).form.expected_goals
        self.assertEqual(xg.opponent_adjusted_xg_for, Decimal("1.30"))
        self.assertEqual(xg.home_average_xg_for, Decimal("1.50"))
        self.assertEqual(xg.away_average_xg_for, Decimal("1.10"))

    def test_same_fixture_conflicts_are_preserved_deterministically(self):
        first = observation("same", home_goals=1, away_goals=0)
        second = replace(
            first,
            home_goals=2,
            source_name="OTHER",
            source_reference="fixture:same:other",
        )
        snapshot = build((second, first))
        self.assertEqual(len(snapshot.conflicts), 1)
        self.assertEqual(
            snapshot.conflicts[0].observation_ids,
            ("OTHER:fixture:same:other", "TEST:fixture:same"),
        )
        self.assertEqual(snapshot.form.selected_fixture_ids, ("same",))

    def test_target_fixture_is_always_excluded(self):
        target = replace(observation("target"), kickoff_time=NOW - timedelta(days=1))
        snapshot = build((target, observation("past", days_ago=2)))
        self.assertEqual(snapshot.form.selected_fixture_ids, ("past",))
        self.assertEqual(
            dict(snapshot.form.excluded_fixtures)["target"],
            "TARGET_FIXTURE",
        )

    def test_evaluation_after_target_kickoff_is_rejected(self):
        with self.assertRaises(ValueError):
            build(
                (observation("past"),),
                evaluation=TARGET + timedelta(seconds=1),
            )

    def test_insufficient_sample_freshness_and_divergence_signals(self):
        small = build(
            (observation("1", home_goals=0, away_goals=0),),
            policy=FormFeaturePolicy(minimum_sample=3, divergence_threshold=Decimal("0.1")),
        )
        self.assertIn(FormSignal.VERY_SMALL_SAMPLE, small.form.signals)
        self.assertIn(FormSignal.RESULTS_GOAL_RATE_DIVERGENCE, small.form.signals)
        stale = build(
            (observation("old", days_ago=20),),
            policy=FormFeaturePolicy(maximum_history_age=timedelta(days=5)),
        )
        self.assertEqual(stale.form.freshness_status, FormEvidenceStatus.STALE)

    def test_snapshot_is_deterministic_and_has_no_current_clock_dependency(self):
        first = build(self.history)
        second = build(tuple(reversed(self.history)))
        self.assertEqual(first, second)
        self.assertEqual(first.form.calculation_timestamp, NOW)


class ProviderPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("tests") / f".form-features-{uuid4().hex}.db"
        self.database = Database(self.path)
        self.repository = SQLiteFormFeatureRepository(self.database)
        self.repository.save_source("test", "TEST")

    def tearDown(self):
        self.database.close()
        self.path.unlink(missing_ok=True)

    def test_provider_maps_only_real_finished_fixture_fields(self):
        payload = {
            "fixture": {"id": 99, "date": "2026-07-10T10:00:00+00:00", "status": {"short": "FT"}},
            "league": {"name": "Premier League"},
            "teams": {"home": {"id": 1}, "away": {"id": 2}},
            "goals": {"home": 2, "away": 1},
            "statistics": {"xg": 9},
        }
        item = ExistingFootballHistoricalAdapter(
            (payload,),
            observed_at=NOW,
        ).historical_matches().observations[0]
        self.assertIsNone(item.home_xg)
        self.assertIsNone(item.home_shots)
        self.assertIsNone(item.home_red_cards)
        self.assertIsNone(item.penalties)

    def test_malformed_provider_record_is_isolated(self):
        batch = ExistingFootballHistoricalAdapter(
            ({"bad": True}, {"fixture": {}}),
            observed_at=NOW,
        ).historical_matches()
        self.assertEqual(len(batch.errors), 2)
        self.assertTrue(
            all(error.code is FormFeatureErrorCode.MALFORMED_PROVIDER_RECORD for error in batch.errors)
        )

    def test_ingestion_is_idempotent_and_persists_across_restart(self):
        provider = StaticHistoricalMatchProvider("TEST", (observation("1"),))
        service = HistoricalMatchIngestionService(self.repository)
        first = service.ingest((provider,), evaluation_timestamp=NOW)
        second = service.ingest((provider,), evaluation_timestamp=NOW)
        self.assertEqual((first.inserted, first.duplicates), (1, 0))
        self.assertEqual((second.inserted, second.duplicates), (0, 1))
        self.database.close()
        self.database = Database(self.path)
        restarted = SQLiteFormFeatureRepository(self.database)
        self.assertEqual(len(restarted.history("1", cutoff=NOW)), 1)

    def test_ingestion_continues_after_incomplete_and_future_records(self):
        provider = StaticHistoricalMatchProvider(
            "TEST",
            (
                observation("ok"),
                observation("incomplete", status="NS"),
                replace(observation("future"), kickoff_time=NOW + timedelta(hours=1)),
            ),
        )
        report = HistoricalMatchIngestionService(self.repository).ingest(
            (provider,),
            evaluation_timestamp=NOW,
        )
        self.assertEqual(report.inserted, 1)
        self.assertEqual(report.rejected, 2)

    def test_migration_v7_is_idempotent_and_decimal_lossless(self):
        item = observation(
            "xg",
            home_xg=Decimal("1.2300"),
            away_xg=Decimal("0.4500"),
        )
        self.repository.insert(item)
        MigrationManager(self.database.connection).migrate()
        versions = tuple(
            row[0]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 33)))
        loaded = self.repository.history("1", cutoff=NOW)[0]
        self.assertEqual(loaded.home_xg, Decimal("1.2300"))

    def test_repository_filters_competition_completion_and_cutoff(self):
        premier = observation("premier")
        cup = replace(observation("cup", days_ago=2), competition="Cup")
        incomplete = observation("pending", days_ago=3, status="NS")
        late = observation("late", observed_at=NOW + timedelta(hours=1))
        for item in (premier, cup, incomplete, late):
            self.repository.insert(item)
        values = self.repository.history(
            "1",
            cutoff=NOW,
            competition="Premier League",
        )
        self.assertEqual(tuple(item.fixture_id for item in values), ("premier",))


class IntegrationRuntimeTests(unittest.TestCase):
    def test_quality_gate_and_backtesting_mapping(self):
        snapshot = build((observation("1"),))
        gate = FormQualityGateAdapter().map(snapshot)
        self.assertEqual(gate.status, EvidenceStatus.PARTIAL)
        feature = FormBacktestingAdapter.feature(snapshot, NOW)
        self.assertEqual(feature.xg_status, ExpectedGoalsStatus.MISSING)
        with self.assertRaises(ValueError):
            FormBacktestingAdapter.feature(snapshot, NOW - timedelta(seconds=1))
        walk = FormBacktestingAdapter.walk_forward("target", NOW, snapshot)
        self.assertEqual(walk.cutoff, NOW)
        self.assertEqual(walk.feature.sample_size, 1)

    def test_shadow_enrichment_uses_only_past_history(self):
        database = Database(":memory:")
        repository = SQLiteFormFeatureRepository(database)
        repository.save_source("test", "TEST")
        repository.insert(observation("past"))
        repository.insert(observation("future-known-late", observed_at=NOW + timedelta(hours=1)))
        base = SimpleNamespace(
            facts_for_at=lambda match, assessment, timestamp: shadow_facts()
        )
        provider = FormShadowFactsProvider(base, repository)
        match = Match(50, 1, "Premier League", 2026, 1, "Home", 2, "Away", TARGET, "NS")
        assessment = SimpleNamespace(
            prediction=SimpleNamespace(winner="Home")
        )
        enriched = provider.facts_for_at(match, assessment, NOW)
        self.assertEqual(enriched.sample_size, 1)
        self.assertEqual(
            dict((x.category, x.status) for x in enriched.evidence)[EvidenceCategory.TEAM_FORM],
            EvidenceStatus.PARTIAL,
        )
        database.close()

    def test_runtime_flags_are_strict_and_do_not_poll(self):
        self.assertFalse(FormFeatureIngestionConfig.from_environment({}).enabled)
        with self.assertRaises(ValueError):
            FormFeatureIngestionConfig.from_environment(
                {"FORM_FEATURE_INGESTION_ENABLED": "1"}
            )
        disabled = build_form_feature_runtime(
            FormFeatureIngestionConfig(False),
            NullHistoricalMatchProvider(),
        )
        self.assertIsNone(disabled.start())
        self.assertIsNone(disabled.database)
        database = Database(":memory:")
        enabled = build_form_feature_runtime(
            FormFeatureIngestionConfig(True),
            NullHistoricalMatchProvider(),
            database,
        )
        report = enabled.start()
        self.assertEqual(report.received, 0)
        enabled.close()

    def test_no_live_product_side_effect_dependencies(self):
        import app.form_features as package

        names = set(package.__dict__)
        self.assertFalse(
            names.intersection(
                {"TelegramService", "BankrollEngine", "Scheduler", "PredictionEngine"}
            )
        )

    def test_enabled_null_runtime_has_zero_telegram_and_bankroll_calls(self):
        database = Database(":memory:")
        runtime = build_form_feature_runtime(
            FormFeatureIngestionConfig(True),
            NullHistoricalMatchProvider(),
            database,
        )
        with (
            patch("telegram.Bot.send_message") as telegram_send,
            patch(
                "app.bankroll.engine.OfficialBankrollSettlementEngine.settle"
            ) as bankroll_settle,
        ):
            report = runtime.start()
        self.assertEqual(report.received, 0)
        telegram_send.assert_not_called()
        bankroll_settle.assert_not_called()
        runtime.close()

    def test_existing_prediction_assessment_is_unchanged_by_form_package(self):
        league = LeagueStrengthEngine(
            ratings=LEAGUE_STRENGTH_RATINGS,
            default_strength=0.5,
        )
        h2h = H2HEngine()
        rest = RestDaysEngine()
        quality = QualityScoreEngine(DEFAULT_QUALITY_SCORE_CONFIG)
        explanations = PredictionExplanationEngine(
            config=DEFAULT_EXPLANATION_CONFIG,
            league_strength=league,
            h2h=h2h,
            rest_days=rest,
        )
        pipeline = PredictionPipeline(league, h2h, rest, quality, explanations)
        home = pipeline.build_team(1, (), {}, True)
        away = pipeline.build_team(2, (), {}, False)
        match = Match(
            50, 1, "Premier League", 2026,
            1, "Home", 2, "Away", TARGET, "NS",
        )
        before = pipeline.assess(match, home, away)
        build((observation("historical"),))
        after = pipeline.assess(match, home, away)
        self.assertEqual(before, after)


def shadow_facts() -> ShadowObservationFacts:
    evidence = tuple(
        EvidenceAssessment(category, EvidenceStatus.MISSING)
        for category in EvidenceCategory
    )
    return ShadowObservationFacts(
        offered_odds=Decimal("2"),
        odds_timestamp=NOW,
        calibrated_probability=Decimal("0.55"),
        calibration_method="identity",
        calibration_scope=CalibrationScope.identity_scope(),
        calibration_sample_size=100,
        calibration_fit_timestamp=NOW - timedelta(days=1),
        calibration_training_cutoff=NOW - timedelta(days=2),
        model_version="test",
        confidence_score=None,
        uncertainty_score=None,
        reference_odds=None,
        expected_value=None,
        data_completeness_status=EvidenceStatus.PARTIAL,
        data_freshness_status=EvidenceStatus.AVAILABLE,
        lineup_status=EvidenceStatus.MISSING,
        injury_data_status=EvidenceStatus.MISSING,
        market_consensus_probability=None,
        market_disagreement=None,
        current_exposure=Decimal("0"),
        daily_exposure=Decimal("0"),
        competition_exposure=Decimal("0"),
        correlated_exposure=Decimal("0"),
        sample_size=0,
        context_calibration_sample_size=100,
        evidence=evidence,
    )


if __name__ == "__main__":
    unittest.main()
