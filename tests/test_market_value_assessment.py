import sqlite3
import unittest
from dataclasses import replace
from datetime import timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app.calibrated_market_probabilities import (
    generate_calibrated_market_probabilities,
)
from app.database import Database
from app.database.migrations import MIGRATIONS, MigrationManager
from app.market_value_assessment import (
    DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY,
    ActionabilityStatus,
    AssessmentOutcomeStatus,
    FreshnessState,
    MAPPINGS,
    MarketMappingRegistry,
    MarketSelection,
    MarketStatus,
    MarketType,
    MarketValueAssessmentPolicy,
    SQLiteMarketValueAssessmentRepository,
    SuppliedOddsSnapshot,
    ValueClassification,
    assess_market_value,
    build_market_value_assessment_service,
    normalize_odds_snapshot,
    to_future_official_selection_input,
)
from app.market_value_assessment.calculations import (
    calculate,
    classify_calibrated_freshness,
    classify_market_value,
    classify_odds_freshness,
    classify_value,
    worst_freshness,
)
from app.market_value_assessment.exceptions import (
    InvalidOddsError,
    NonActionableMappingError,
)
from app.market_value_assessment.fingerprint import assessment_fingerprint
from app.prediction_inference import PredictionTarget
from tests import test_calibrated_market_probabilities as calibrated_fixture


class MarketValueAssessmentTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = calibrated_fixture.CalibratedMarketProbabilityTests()
        fixture.setUp()
        self.fixture = fixture
        calibrated = generate_calibrated_market_probabilities(
            fixture._service(),
            fixture.inference,
            calibration_set_id="official-calibration-set-v1",
            calibration_effective_timestamp=fixture.timestamp,
        )
        self.assembly = fixture.repository.load_assembly_by_id(
            calibrated.calibrated_assembly_id
        )
        self.database = fixture.database
        self.policy = DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY
        self.repository = SQLiteMarketValueAssessmentRepository(self.database)
        self.service = self._service()
        self.kickoff = self.repository.load_source_kickoff(
            self.assembly.source_snapshot_id
        )
        self.assessed_at = self.assembly.calibration_effective_timestamp + timedelta(
            seconds=60
        )

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def _service(self, policy=None):
        return build_market_value_assessment_service(
            self.repository,
            self.repository,
            MarketMappingRegistry(),
            policy or self.policy,
        )

    def odds(self, **changes) -> SuppliedOddsSnapshot:
        base = SuppliedOddsSnapshot(
            snapshot_id="supplied-1",
            source_provider="Provider One",
            bookmaker_id="Book A",
            source_event_id="event-1",
            match_id=self.assembly.match_id,
            market_type=MarketType.MATCH_WINNER,
            selection=MarketSelection.HOME,
            market_line=None,
            decimal_odds=Decimal("3.00"),
            odds_effective_timestamp=self.assembly.calibration_effective_timestamp,
            source_updated_timestamp=self.assembly.calibration_effective_timestamp,
            registration_timestamp=self.assembly.calibration_effective_timestamp,
            kickoff_timestamp=self.kickoff,
            is_live=False,
            market_status=MarketStatus.OPEN,
            suspended=False,
            available=True,
            currency="EUR",
        )
        return replace(base, **changes)

    def assess(self, odds=None, timestamp=None, service=None):
        return assess_market_value(
            service or self.service,
            self.assembly,
            odds or self.odds(),
            assessment_timestamp=timestamp or self.assessed_at,
        )

    def test_mapping_registry_is_complete_ordered_and_unique(self) -> None:
        expected = (
            (MarketType.MATCH_WINNER, MarketSelection.HOME, None),
            (MarketType.MATCH_WINNER, MarketSelection.DRAW, None),
            (MarketType.MATCH_WINNER, MarketSelection.AWAY, None),
            (MarketType.DOUBLE_CHANCE, MarketSelection.HOME_DRAW, None),
            (MarketType.DOUBLE_CHANCE, MarketSelection.HOME_AWAY, None),
            (MarketType.DOUBLE_CHANCE, MarketSelection.DRAW_AWAY, None),
            (MarketType.TOTALS, MarketSelection.OVER, Decimal("1.5")),
            (MarketType.TOTALS, MarketSelection.UNDER, Decimal("1.5")),
            (MarketType.TOTALS, MarketSelection.OVER, Decimal("2.5")),
            (MarketType.TOTALS, MarketSelection.UNDER, Decimal("2.5")),
            (MarketType.TOTALS, MarketSelection.OVER, Decimal("3.5")),
            (MarketType.TOTALS, MarketSelection.UNDER, Decimal("3.5")),
            (MarketType.BTTS, MarketSelection.YES, None),
            (MarketType.BTTS, MarketSelection.NO, None),
        )
        identities = tuple(
            (item.market_type, item.selection, item.market_line)
            for item in MAPPINGS
        )
        self.assertEqual(identities, expected)
        self.assertEqual(len(identities), len(set(identities)))

    def test_every_direct_market_maps_to_the_expected_target(self) -> None:
        registry = MarketMappingRegistry()
        expected = {
            (MarketType.MATCH_WINNER, MarketSelection.HOME, None): PredictionTarget.HOME_WIN,
            (MarketType.MATCH_WINNER, MarketSelection.DRAW, None): PredictionTarget.DRAW,
            (MarketType.MATCH_WINNER, MarketSelection.AWAY, None): PredictionTarget.AWAY_WIN,
            (MarketType.TOTALS, MarketSelection.OVER, Decimal("1.5")): PredictionTarget.OVER_1_5,
            (MarketType.TOTALS, MarketSelection.UNDER, Decimal("1.5")): PredictionTarget.UNDER_1_5,
            (MarketType.TOTALS, MarketSelection.OVER, Decimal("2.5")): PredictionTarget.OVER_2_5,
            (MarketType.TOTALS, MarketSelection.UNDER, Decimal("2.5")): PredictionTarget.UNDER_2_5,
            (MarketType.TOTALS, MarketSelection.OVER, Decimal("3.5")): PredictionTarget.OVER_3_5,
            (MarketType.TOTALS, MarketSelection.UNDER, Decimal("3.5")): PredictionTarget.UNDER_3_5,
            (MarketType.BTTS, MarketSelection.YES, None): PredictionTarget.BTTS_YES,
            (MarketType.BTTS, MarketSelection.NO, None): PredictionTarget.BTTS_NO,
        }
        for identity, target in expected.items():
            with self.subTest(identity=identity):
                self.assertEqual(
                    registry.resolve(*identity).source_targets,
                    (target,),
                )

    def test_all_double_chance_derivations_preserve_source_targets(self) -> None:
        expected = {
            MarketSelection.HOME_DRAW: (
                PredictionTarget.HOME_WIN,
                PredictionTarget.DRAW,
            ),
            MarketSelection.HOME_AWAY: (
                PredictionTarget.HOME_WIN,
                PredictionTarget.AWAY_WIN,
            ),
            MarketSelection.DRAW_AWAY: (
                PredictionTarget.DRAW,
                PredictionTarget.AWAY_WIN,
            ),
        }
        registry = MarketMappingRegistry()
        for selection, targets in expected.items():
            with self.subTest(selection=selection):
                mapping = registry.resolve(
                    MarketType.DOUBLE_CHANCE, selection, None
                )
                self.assertEqual(mapping.source_targets, targets)
                self.assertEqual(
                    mapping.derivation_formula,
                    " + ".join(target.value for target in targets),
                )

    def test_unsupported_or_inconsistent_market_is_rejected(self) -> None:
        incompatible = self.assess(
            self.odds(selection=MarketSelection.YES, snapshot_id="bad-selection")
        )
        self.assertEqual(
            incompatible.final_status,
            AssessmentOutcomeStatus.REJECTED_INCOMPATIBLE_MARKET,
        )
        with self.assertRaises(InvalidOddsError):
            normalize_odds_snapshot(
                self.odds(market_type="CORRECT_SCORE"), self.policy
            )
        with self.assertRaises(InvalidOddsError):
            normalize_odds_snapshot(
                self.odds(
                    market_type=MarketType.TOTALS,
                    selection=MarketSelection.OVER,
                    market_line=Decimal("2.25"),
                ),
                self.policy,
            )

    def test_odds_normalization_is_unicode_utc_and_registration_independent(self) -> None:
        offset_time = self.assembly.calibration_effective_timestamp.astimezone(
            timezone(timedelta(hours=2))
        )
        value = self.odds(
            source_provider="  Provider\u3000One  ",
            bookmaker_id=" Book   A ",
            odds_effective_timestamp=offset_time,
            source_updated_timestamp=offset_time,
            registration_timestamp=offset_time,
            source_data_version=" v1 ",
        )
        normalized = normalize_odds_snapshot(value, self.policy)
        later_registration = normalize_odds_snapshot(
            replace(
                value,
                registration_timestamp=offset_time + timedelta(seconds=30),
            ),
            self.policy,
        )
        self.assertEqual(normalized.source_provider, "Provider One")
        self.assertEqual(normalized.bookmaker_id, "Book A")
        self.assertEqual(normalized.odds_effective_timestamp.tzinfo, timezone.utc)
        self.assertEqual(
            normalized.odds_fingerprint, later_registration.odds_fingerprint
        )

    def test_odds_validation_rejects_malformed_prices_and_structure(self) -> None:
        cases = (
            self.odds(decimal_odds=Decimal("1.00")),
            self.odds(decimal_odds=Decimal("1000.01")),
            self.odds(decimal_odds=Decimal("NaN")),
            self.odds(decimal_odds=Decimal("Infinity")),
            self.odds(decimal_odds=2.0),
            self.odds(
                market_type=MarketType.TOTALS,
                selection=MarketSelection.OVER,
                market_line=None,
            ),
            self.odds(market_line=Decimal("2.5")),
            self.odds(is_live=True),
            self.odds(suspended=True),
            self.odds(available=False),
            self.odds(is_live="false"),
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(InvalidOddsError):
                normalize_odds_snapshot(value, self.policy)

    def test_odds_validation_rejects_bad_timing_stakes_and_metadata(self) -> None:
        base_time = self.assembly.calibration_effective_timestamp
        cases = (
            self.odds(odds_effective_timestamp=self.kickoff),
            self.odds(source_updated_timestamp=base_time + timedelta(seconds=1)),
            self.odds(odds_effective_timestamp=base_time + timedelta(seconds=1)),
            self.odds(odds_effective_timestamp=base_time.replace(tzinfo=None)),
            self.odds(minimum_stake=Decimal("-1")),
            self.odds(
                minimum_stake=Decimal("20"), maximum_stake=Decimal("10")
            ),
            self.odds(currency="XYZ"),
            self.odds(metadata=(("url", "https://example.com"),)),
            self.odds(metadata=(("affiliate_code", "abc"),)),
            self.odds(metadata=(("api_key", "abc"),)),
            self.odds(metadata={"safe": "value"}),
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(InvalidOddsError):
                normalize_odds_snapshot(value, self.policy)

    def test_valid_markets_and_optional_stakes_normalize(self) -> None:
        cases = (
            self.odds(),
            self.odds(
                market_type=MarketType.TOTALS,
                selection=MarketSelection.OVER,
                market_line=Decimal("2.50"),
            ),
            self.odds(
                market_type=MarketType.BTTS,
                selection=MarketSelection.YES,
            ),
            self.odds(
                market_type=MarketType.DOUBLE_CHANCE,
                selection=MarketSelection.HOME_DRAW,
            ),
            self.odds(minimum_stake=None, maximum_stake=None, currency=None),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertIsInstance(
                    normalize_odds_snapshot(value, self.policy).decimal_odds,
                    Decimal,
                )

    def test_calculations_are_exact_decimal_and_do_not_remove_margin(self) -> None:
        metrics = calculate(Decimal("0.45"), Decimal("3.00"), self.policy)
        self.assertEqual(metrics.fair_probability, Decimal("0.450000"))
        self.assertEqual(metrics.fair_decimal_odds, Decimal("2.222222"))
        self.assertEqual(metrics.implied_probability, Decimal("0.333333"))
        self.assertEqual(metrics.break_even_probability, Decimal("0.333333"))
        self.assertEqual(metrics.absolute_probability_edge, Decimal("0.116667"))
        self.assertEqual(metrics.relative_probability_edge, Decimal("0.350000"))
        self.assertEqual(metrics.expected_value, Decimal("0.350000"))
        self.assertEqual(metrics.expected_return, Decimal("1.350000"))
        self.assertEqual(metrics.potential_profit, Decimal("2.000000"))

    def test_value_classification_boundaries_are_policy_driven(self) -> None:
        cases = (
            (Decimal("-0.000001"), ValueClassification.NEGATIVE_VALUE),
            (Decimal("0"), ValueClassification.NEUTRAL_VALUE),
            (Decimal("0.019999"), ValueClassification.NEUTRAL_VALUE),
            (Decimal("0.02"), ValueClassification.POSITIVE_VALUE),
            (Decimal("0.049999"), ValueClassification.POSITIVE_VALUE),
            (Decimal("0.05"), ValueClassification.STRONG_VALUE),
        )
        for expected_value, classification in cases:
            with self.subTest(expected_value=expected_value):
                self.assertEqual(
                    classify_value(expected_value, self.policy), classification
                )
        self.assertEqual(
            calculate(Decimal("0.5"), Decimal("2"), self.policy).expected_value,
            Decimal("0.000000"),
        )
        self.assertEqual(
            calculate(
                Decimal("0.5"), Decimal("2.0399998"), self.policy
            ).expected_value,
            Decimal("0.020000"),
        )
        self.assertEqual(
            classify_market_value(
                Decimal("0.5"), Decimal("2.0399998"), self.policy
            ),
            ValueClassification.NEUTRAL_VALUE,
        )

    def test_freshness_boundaries_and_worst_state_are_deterministic(self) -> None:
        odds_cases = (
            (300, FreshnessState.FRESH),
            (301, FreshnessState.AGING),
            (901, FreshnessState.STALE),
            (1801, FreshnessState.EXPIRED),
        )
        for age, state in odds_cases:
            self.assertEqual(classify_odds_freshness(age, self.policy), state)
        self.assertEqual(
            classify_calibrated_freshness(7201, self.policy),
            FreshnessState.STALE,
        )
        self.assertEqual(
            worst_freshness(FreshnessState.AGING, FreshnessState.STALE),
            FreshnessState.STALE,
        )

    def test_assessment_calculates_all_metrics_and_below_160_is_valid(self) -> None:
        outcome = self.assess()
        self.assertEqual(outcome.final_status, AssessmentOutcomeStatus.ASSESSED)
        self.assertEqual(outcome.fair_probability, Decimal("0.450000"))
        self.assertEqual(outcome.expected_value, Decimal("0.350000"))
        self.assertEqual(
            outcome.value_classification, ValueClassification.STRONG_VALUE
        )
        below_minimum = self.assess(
            self.odds(decimal_odds=Decimal("1.50"), snapshot_id="below-160")
        )
        self.assertEqual(
            below_minimum.final_status, AssessmentOutcomeStatus.ASSESSED
        )
        self.assertEqual(
            below_minimum.value_classification,
            ValueClassification.NEGATIVE_VALUE,
        )

    def test_all_double_chance_probabilities_are_derived(self) -> None:
        expected = {
            MarketSelection.HOME_DRAW: Decimal("0.700000"),
            MarketSelection.HOME_AWAY: Decimal("0.750000"),
            MarketSelection.DRAW_AWAY: Decimal("0.550000"),
        }
        for selection, probability in expected.items():
            with self.subTest(selection=selection):
                outcome = self.assess(
                    self.odds(
                        snapshot_id=f"dc-{selection.value}",
                        market_type=MarketType.DOUBLE_CHANCE,
                        selection=selection,
                        decimal_odds=Decimal("1.60"),
                    )
                )
                self.assertEqual(outcome.fair_probability, probability)

    def test_expired_stale_and_kickoff_proximity_are_non_actionable(self) -> None:
        expired_at = self.assembly.calibration_effective_timestamp + timedelta(
            seconds=1900
        )
        expired = self.assess(self.odds(snapshot_id="expired"), expired_at)
        self.assertEqual(
            expired.actionability_status,
            ActionabilityStatus.NON_ACTIONABLE_EXPIRED,
        )

        stale_at = self.assembly.calibration_effective_timestamp + timedelta(
            seconds=7201
        )
        stale_odds_time = stale_at - timedelta(seconds=1)
        stale = self.assess(
            self.odds(
                snapshot_id="stale-calibration",
                odds_effective_timestamp=stale_odds_time,
                source_updated_timestamp=stale_odds_time,
                registration_timestamp=stale_odds_time,
            ),
            stale_at,
        )
        self.assertEqual(
            stale.actionability_status,
            ActionabilityStatus.NON_ACTIONABLE_STALE,
        )

        close = self.kickoff - timedelta(seconds=100)
        near_odds_time = close - timedelta(seconds=1)
        near = self.assess(
            self.odds(
                snapshot_id="near",
                registration_timestamp=near_odds_time,
                odds_effective_timestamp=near_odds_time,
                source_updated_timestamp=near_odds_time,
            ),
            close,
        )
        self.assertEqual(
            near.actionability_status,
            ActionabilityStatus.NON_ACTIONABLE_TOO_CLOSE_TO_KICKOFF,
        )

    def test_stale_actionability_follows_explicit_policy(self) -> None:
        policy = replace(
            self.policy,
            version="market-value-assessment-policy-stale-actionable-test",
            stale_is_actionable=True,
        )
        timestamp = self.assembly.calibration_effective_timestamp + timedelta(
            seconds=7201
        )
        odds_time = timestamp - timedelta(seconds=1)
        outcome = self.assess(
            self.odds(
                snapshot_id="stale-allowed",
                odds_effective_timestamp=odds_time,
                source_updated_timestamp=odds_time,
                registration_timestamp=odds_time,
            ),
            timestamp,
            self._service(policy),
        )
        self.assertEqual(outcome.final_status, AssessmentOutcomeStatus.ASSESSED)
        self.assertEqual(outcome.actionability_status, ActionabilityStatus.ACTIONABLE)
        self.assertEqual(outcome.value_classification, ValueClassification.STRONG_VALUE)

    def test_invalid_calibration_fails_before_calculation(self) -> None:
        malformed = replace(
            self.assembly,
            ordered_target_results=self.assembly.ordered_target_results[:-1],
        )
        with patch("app.market_value_assessment.service.calculate") as calculation:
            outcome = assess_market_value(
                self.service,
                malformed,
                self.odds(),
                assessment_timestamp=self.assessed_at,
            )
        self.assertEqual(
            outcome.final_status,
            AssessmentOutcomeStatus.REJECTED_INVALID_CALIBRATION,
        )
        calculation.assert_not_called()
        missing = assess_market_value(
            self.service,
            None,
            self.odds(),
            assessment_timestamp=self.assessed_at,
        )
        self.assertEqual(
            missing.final_status,
            AssessmentOutcomeStatus.REJECTED_INVALID_CALIBRATION,
        )

    def test_provenance_and_timestamp_mismatches_do_not_persist(self) -> None:
        cases = (
            self.assess(self.odds(match_id="other")),
            self.assess(self.odds(kickoff_timestamp=self.kickoff + timedelta(hours=1))),
            self.assess(
                timestamp=self.assembly.calibration_effective_timestamp
                - timedelta(seconds=1)
            ),
            self.assess(timestamp=self.kickoff),
        )
        for outcome in cases:
            self.assertEqual(
                outcome.final_status,
                AssessmentOutcomeStatus.REJECTED_PROVENANCE_MISMATCH,
            )
        count = self.database.connection.execute(
            "SELECT COUNT(*) FROM market_value_assessments"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_fingerprints_change_only_with_material_assessment_inputs(self) -> None:
        first = self.assess()
        identical = self.assess()
        changed_odds = self.assess(
            self.odds(snapshot_id="price-change", decimal_odds=Decimal("3.01"))
        )
        changed_time = self.assess(
            self.odds(snapshot_id="time-change"),
            self.assessed_at + timedelta(seconds=1),
        )
        changed_policy = self.assess(
            self.odds(snapshot_id="policy-change"),
            service=self._service(
                replace(self.policy, version="market-value-assessment-policy-v2-test")
            ),
        )
        self.assertEqual(
            identical.final_status,
            AssessmentOutcomeStatus.IDEMPOTENT_EXISTING,
        )
        self.assertEqual(first.assessment_fingerprint, identical.assessment_fingerprint)
        self.assertEqual(
            len(
                {
                    first.assessment_fingerprint,
                    changed_odds.assessment_fingerprint,
                    changed_time.assessment_fingerprint,
                    changed_policy.assessment_fingerprint,
                }
            ),
            4,
        )

    def test_repository_apis_are_idempotent_and_queryable(self) -> None:
        normalized = normalize_odds_snapshot(self.odds(), self.policy)
        stored_odds, existing = self.repository.append_odds_snapshot(normalized)
        self.assertFalse(existing)
        later_registration = replace(
            normalized,
            registration_timestamp=normalized.registration_timestamp
            + timedelta(seconds=10),
            created_timestamp=normalized.created_timestamp + timedelta(seconds=10),
        )
        same_odds, existing = self.repository.append_odds_snapshot(
            later_registration
        )
        self.assertTrue(existing)
        self.assertEqual(same_odds.odds_fingerprint, stored_odds.odds_fingerprint)
        self.assertEqual(
            self.repository.load_odds_snapshot_by_id(stored_odds.odds_record_id),
            stored_odds,
        )
        self.assertEqual(
            self.repository.find_latest_odds_for_market(
                stored_odds.match_id,
                stored_odds.bookmaker_id,
                stored_odds.market_type,
                stored_odds.selection,
                stored_odds.market_line,
            ),
            stored_odds,
        )
        self.assertEqual(len(self.repository.list_odds_for_match(stored_odds.match_id)), 1)
        self.assertEqual(
            len(
                self.repository.list_odds_by_kickoff_window(
                    self.kickoff - timedelta(seconds=1),
                    self.kickoff + timedelta(seconds=1),
                )
            ),
            1,
        )

    def test_atomic_persistence_queries_and_downstream_mapping(self) -> None:
        outcome = self.assess()
        stored = self.repository.find_assessment_by_fingerprint(
            outcome.assessment_fingerprint
        )
        self.assertEqual(
            self.repository.load_assessment_by_id(outcome.value_assessment_id),
            stored,
        )
        self.assertEqual(
            len(
                self.repository.list_assessments_for_calibrated_assembly(
                    self.assembly.calibrated_assembly_id
                )
            ),
            1,
        )
        self.assertEqual(
            self.repository.find_latest_for_match_bookmaker_market(
                stored.match_id,
                stored.bookmaker_id,
                stored.market_type,
                stored.selection,
                stored.market_line,
            ),
            stored,
        )
        self.assertEqual(self.repository.list_actionable_assessments(), (stored,))
        mapped = to_future_official_selection_input(stored)
        self.assertEqual(mapped.fair_probability, stored.fair_probability)
        self.assertEqual(mapped.expected_value, stored.expected_value)
        self.assertEqual(mapped.bookmaker_id, stored.bookmaker_id)
        self.assertEqual(mapped.source_model_version, stored.source_model_version)
        self.assertEqual(mapped.calibration_set_id, stored.calibration_set_id)
        self.assertEqual(
            mapped.calibration_set_fingerprint,
            stored.calibration_set_fingerprint,
        )
        self.assertEqual(
            mapped.calibrated_assembly_fingerprint,
            stored.calibrated_assembly_fingerprint,
        )
        self.assertFalse(hasattr(mapped, "stake"))
        self.assertFalse(hasattr(mapped, "candidate_status"))

    def test_standalone_assessment_append_and_non_actionable_mapping_guard(self) -> None:
        outcome = self.assess()
        stored = self.repository.load_assessment_by_id(outcome.value_assessment_id)
        new_timestamp = stored.assessment_timestamp + timedelta(seconds=1)
        candidate = replace(
            stored,
            value_assessment_id="standalone-assessment",
            assessment_timestamp=new_timestamp,
            created_timestamp=new_timestamp,
            assessment_fingerprint="",
        )
        fingerprint = assessment_fingerprint(candidate)
        candidate = replace(candidate, assessment_fingerprint=fingerprint)
        appended, existing = self.repository.append_value_assessment(candidate)
        self.assertFalse(existing)
        self.assertEqual(appended, candidate)
        self.assertTrue(self.repository.append_value_assessment(candidate)[1])

        non_actionable_time = self.assembly.calibration_effective_timestamp + timedelta(
            seconds=1901
        )
        non_actionable = self.assess(
            self.odds(snapshot_id="non-actionable-map"), non_actionable_time
        )
        with self.assertRaises(NonActionableMappingError):
            to_future_official_selection_input(
                self.repository.load_assessment_by_id(
                    non_actionable.value_assessment_id
                )
            )

    def test_atomic_insert_rolls_back_odds_when_assessment_insert_fails(self) -> None:
        self.database.connection.execute(
            """CREATE TRIGGER fail_market_value_insert
            BEFORE INSERT ON market_value_assessments
            BEGIN SELECT RAISE(ABORT, 'forced assessment failure'); END"""
        )
        outcome = self.assess(self.odds(snapshot_id="rollback"))
        self.assertIn(
            outcome.final_status,
            (AssessmentOutcomeStatus.CONFLICT, AssessmentOutcomeStatus.PERSISTENCE_FAILURE),
        )
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM market_odds_snapshots"
            ).fetchone()[0],
            0,
        )

    def test_append_only_triggers_prevent_update_and_delete(self) -> None:
        self.assess()
        for table in ("market_odds_snapshots", "market_value_assessments"):
            for statement in (
                f"UPDATE {table} SET created_timestamp = 'changed'",
                f"DELETE FROM {table}",
            ):
                with self.subTest(table=table, statement=statement):
                    with self.assertRaises(sqlite3.IntegrityError):
                        self.database.connection.execute(statement)
                    self.database.connection.rollback()

    def test_factory_rejects_split_transaction_or_mapping_policy(self) -> None:
        other = SQLiteMarketValueAssessmentRepository(Database(":memory:"))
        with self.assertRaises(ValueError):
            build_market_value_assessment_service(
                self.repository,
                other,
                MarketMappingRegistry(),
                self.policy,
            )
        with self.assertRaises(ValueError):
            build_market_value_assessment_service(
                self.repository,
                self.repository,
                MarketMappingRegistry(),
                replace(self.policy, mapping_version="unsupported-mapping"),
            )
        other.connection.close()


class MarketValueMigrationTests(unittest.TestCase):
    def test_fresh_v19_migration_has_tables_indexes_foreign_keys_and_triggers(self) -> None:
        database = Database(":memory:")
        MigrationManager(database.connection).migrate()
        self.assertEqual(
            database.connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0],
            32,
        )
        for table in ("market_odds_snapshots", "market_value_assessments"):
            self.assertIsNotNone(
                database.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
            )
        foreign_keys = database.connection.execute(
            "PRAGMA foreign_key_list(market_value_assessments)"
        ).fetchall()
        self.assertEqual(
            {row[2] for row in foreign_keys},
            {
                "calibrated_market_probability_assemblies",
                "market_odds_snapshots",
            },
        )
        indexes = {
            row[0]
            for row in database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        self.assertTrue(
            {
                "idx_market_odds_match",
                "idx_market_odds_bookmaker",
                "idx_market_odds_identity",
                "idx_market_odds_effective",
                "idx_market_value_match",
                "idx_market_value_identity",
                "idx_market_value_assessed_at",
                "idx_market_value_classification",
                "idx_market_value_actionability",
            }.issubset(indexes)
        )
        database.close()

    def test_v18_database_upgrades_to_v19(self) -> None:
        database = Database(":memory:")
        database.connection.execute(
            "CREATE TABLE schema_migrations("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for migration in MIGRATIONS:
            if migration.version > 18:
                continue
            for statement in migration.statements:
                database.connection.execute(statement)
            database.connection.execute(
                "INSERT INTO schema_migrations VALUES (?, 'existing')",
                (migration.version,),
            )
        MigrationManager(database.connection).migrate()
        self.assertEqual(
            database.connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0],
            32,
        )
        database.close()


if __name__ == "__main__":
    unittest.main()
