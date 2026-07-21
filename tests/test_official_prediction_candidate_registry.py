import asyncio
import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.official_prediction_candidate_registry import (
    CandidateLifecycleResultStatus,
    CandidateLifecycleState,
    CandidatePublicationGuardState,
    CandidateRegistrationValidationError,
    CandidateRegistrationStatus,
    CandidateRegistryConflictError,
    OfficialCandidateAssemblyContext,
    OfficialCandidateRegistryFingerprint,
    OfficialPredictionCandidateRegistrationCommand,
    OfficialPredictionCandidateValidator,
    OfficialPredictionReasoningFact,
    ReasoningFactType,
    RegistryOfficialPredictionCandidateSource,
    SQLiteOfficialPredictionCandidateRepository,
    build_official_prediction_candidate_registry,
    build_registry_candidate_source,
    canonical_decimal,
    canonical_timestamp,
    register_official_prediction_candidate,
)
from app.official_prediction_orchestration import (
    OfficialPredictionCandidateAssembler,
    OrchestrationStatus,
    build_official_prediction_orchestration_service,
)
from app.official_prediction_run_coordinator import (
    CandidateDiscoveryStatus,
    CandidateHistoricalState,
    DeterministicOfficialPredictionCandidateDiscovery,
    OfficialPredictionRunPolicy,
    OfficialPredictionRunRequest,
    OfficialPredictionRunStatus,
    build_official_prediction_run_coordinator,
    run_official_prediction_batch,
)
from app.publication_quality_gate import (
    ConfidenceLevel,
    FactStatus,
    LineupStatus,
    MarketAvailability,
)
from app.risk_management import RiskProductScope
from tests.test_official_prediction_orchestration import (
    NOW,
    Publisher,
    publication,
    request,
)


def command(**changes) -> OfficialPredictionCandidateRegistrationCommand:
    values = {
        "source_event_id": "prediction-engine-event-1",
        "prediction_id": "prediction-1",
        "match_id": "101",
        "competition_id": "premier-league",
        "competition_name": "Premier League",
        "home_team_id": "team-home",
        "home_team_name": "Home FC",
        "away_team_id": "team-away",
        "away_team_name": "Away FC",
        "kickoff_timestamp": NOW + timedelta(hours=1),
        "prediction_creation_timestamp": NOW - timedelta(minutes=10),
        "model_version": "model-v1",
        "market_type": "match winner",
        "selection": "home",
        "market_line": None,
        "raw_model_probability": Decimal("0.62"),
        "supplied_expected_value": Decimal("0.080"),
        "decimal_odds": Decimal("1.80"),
        "odds_timestamp": NOW - timedelta(minutes=2),
        "odds_source_id": "bookmaker-a",
        "core_match_data_timestamp": NOW - timedelta(minutes=5),
        "lineup_status": LineupStatus.CONFIRMED,
        "lineup_data_timestamp": NOW - timedelta(minutes=1),
        "injury_suspension_status": FactStatus.AVAILABLE,
        "injury_suspension_data_timestamp": NOW - timedelta(minutes=1),
        "confidence_level": ConfidenceLevel.HIGH,
        "public_reasoning_facts": (
            OfficialPredictionReasoningFact(
                ReasoningFactType.HOME_STRENGTH,
                "Home side has won four of its last five home matches.",
                "form-snapshot-1",
            ),
            OfficialPredictionReasoningFact(
                ReasoningFactType.MARKET_STATISTICAL_EVIDENCE,
                "The supplied model probability exceeds the market baseline.",
                "model-snapshot-1",
            ),
        ),
        "source_data_version": "snapshot-v1",
        "supporting_data_status": FactStatus.AVAILABLE,
        "market_availability": MarketAvailability.AVAILABLE,
        "bankroll_scope": RiskProductScope.OFFICIAL,
        "destination_scope": RiskProductScope.OFFICIAL,
        "registration_timestamp": NOW,
        "is_live": False,
        "is_accumulator": False,
    }
    values.update(changes)
    return OfficialPredictionCandidateRegistrationCommand(**values)


class Guard:
    def __init__(
        self,
        value: CandidatePublicationGuardState = (
            CandidatePublicationGuardState.UNPUBLISHED
        ),
    ) -> None:
        self.value = value
        self.calls: list[tuple[str, str, object]] = []

    def state(self, prediction_id, match_id, evaluated_at):
        self.calls.append((prediction_id, match_id, evaluated_at))
        return self.value


class Contexts:
    def __init__(self) -> None:
        supplied = request()
        self.context = OfficialCandidateAssemblyContext(
            calibration_records=supplied.calibration_records,
            model_health_records=supplied.model_health_records,
            risk_evaluations=supplied.risk_evaluations,
            exposure_evaluations=supplied.exposure_evaluations,
            bankroll=supplied.bankroll,
        )
        self.calls = []

    def load(self, candidate, evaluated_at):
        self.calls.append((candidate.registry_candidate_id, evaluated_at))
        return self.context


class States:
    def __init__(self, status=CandidateDiscoveryStatus.READY):
        self.status = status

    def get(self, candidate, evaluated_at):
        return CandidateHistoricalState(self.status)


class Orchestrator:
    def __init__(self):
        self.calls = []

    async def prepare_and_publish_official_prediction(self, supplied):
        self.calls.append(supplied)
        raise AssertionError("Blocked candidates must not reach orchestration.")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        from app.official_prediction_candidate_registry import (
            DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY,
        )

        self.validator = OfficialPredictionCandidateValidator(
            DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY
        )

    def test_all_supported_markets_normalize(self):
        cases = (
            ({"market_type": "moneyline", "selection": "1"}, "MATCH_WINNER", "HOME"),
            ({"market_type": "double chance", "selection": "X2"}, "DOUBLE_CHANCE", "AWAY OR DRAW"),
            (
                {
                    "market_type": "over/under",
                    "selection": "over",
                    "market_line": Decimal("2.5"),
                },
                "TOTALS",
                "OVER",
            ),
            ({"market_type": "both teams to score", "selection": "yes"}, "BTTS", "YES"),
        )
        for changes, market, selection in cases:
            with self.subTest(market=market):
                prepared = self.validator.prepare(command(**changes))
                self.assertEqual(prepared.market_identity.market.value, market)
                self.assertEqual(prepared.market_identity.selection, selection)

    def test_invalid_market_and_selection_inputs_are_rejected(self):
        cases = (
            ({"market_type": "correct score"}, "CORRECT_SCORE_FORBIDDEN"),
            ({"market_type": "asian handicap"}, "UNSUPPORTED_MARKET"),
            ({"selection": "arbitrary words"}, "INCONSISTENT_MARKET_SELECTION"),
            ({"market_type": "totals", "selection": "over", "market_line": None}, "INVALID_MARKET_LINE"),
            (
                {
                    "market_type": "totals",
                    "selection": "under",
                    "market_line": Decimal("-0.5"),
                },
                "INVALID_MARKET_LINE",
            ),
            ({"market_line": Decimal("1.5")}, "INVALID_MARKET_LINE"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(
                CandidateRegistrationValidationError
            ) as caught:
                self.validator.prepare(command(**changes))
            self.assertEqual(caught.exception.reason_codes, (reason,))

    def test_required_identity_and_decimal_validation(self):
        cases = (
            ({"model_version": ""}, "INVALID_MODEL_VERSION"),
            ({"source_data_version": ""}, "INVALID_SOURCE_DATA_VERSION"),
            ({"prediction_id": "bad id"}, "INVALID_PREDICTION_ID"),
            ({"raw_model_probability": Decimal("0.0009")}, "INVALID_RAW_PROBABILITY"),
            ({"raw_model_probability": Decimal("1")}, "INVALID_RAW_PROBABILITY"),
            ({"decimal_odds": Decimal("1")}, "INVALID_DECIMAL_ODDS"),
            ({"supplied_expected_value": Decimal("NaN")}, "INVALID_SUPPLIED_EXPECTED_VALUE"),
            ({"supplied_expected_value": "bad"}, "INVALID_SUPPLIED_EXPECTED_VALUE"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(
                CandidateRegistrationValidationError
            ) as caught:
                self.validator.prepare(command(**changes))
            self.assertEqual(caught.exception.reason_codes, (reason,))

    def test_timestamp_and_team_validation(self):
        cases = (
            ({"prediction_creation_timestamp": NOW + timedelta(hours=2)}, "PREDICTION_AT_OR_AFTER_KICKOFF"),
            ({"odds_timestamp": NOW + timedelta(seconds=1)}, "FUTURE_ODDS_TIMESTAMP"),
            ({"core_match_data_timestamp": NOW + timedelta(seconds=1)}, "FUTURE_CORE_DATA_TIMESTAMP"),
            ({"home_team_id": "same", "away_team_id": "same"}, "IDENTICAL_TEAMS"),
            ({"home_team_name": "Same FC", "away_team_name": "  Same   FC "}, "IDENTICAL_TEAMS"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(
                CandidateRegistrationValidationError
            ) as caught:
                self.validator.prepare(command(**changes))
            self.assertEqual(caught.exception.reason_codes, (reason,))

    def test_scope_live_and_accumulator_rejections(self):
        cases = (
            ({"bankroll_scope": RiskProductScope.LIVE}, "NON_OFFICIAL_SCOPE"),
            ({"destination_scope": RiskProductScope.COMBO}, "NON_OFFICIAL_SCOPE"),
            ({"is_live": True}, "LIVE_CANDIDATE_FORBIDDEN"),
            ({"is_accumulator": True}, "ACCUMULATOR_CANDIDATE_FORBIDDEN"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(
                CandidateRegistrationValidationError
            ) as caught:
                self.validator.prepare(command(**changes))
            self.assertEqual(caught.exception.reason_codes, (reason,))

    def test_unsafe_reasoning_is_rejected(self):
        cases = (
            ("See https://example.com/value", "REASONING_URL_FORBIDDEN"),
            ("Use affiliate promo code WIN", "AFFILIATE_CONTENT_FORBIDDEN"),
            ("Guaranteed risk-free winner", "PROMOTIONAL_CLAIM_FORBIDDEN"),
            ("The exact score should land", "CORRECT_SCORE_REASONING_FORBIDDEN"),
            ("Paste the bot token here", "CREDENTIAL_CONTENT_FORBIDDEN"),
            ("<b>Strong form</b>", "INVALID_REASONING_FACT"),
        )
        for text, reason in cases:
            facts = (OfficialPredictionReasoningFact(ReasoningFactType.RECENT_FORM, text),)
            with self.subTest(reason=reason), self.assertRaises(
                CandidateRegistrationValidationError
            ) as caught:
                self.validator.prepare(command(public_reasoning_facts=facts))
            self.assertEqual(caught.exception.reason_codes, (reason,))


class NormalizationAndFingerprintTests(unittest.TestCase):
    def setUp(self):
        from app.official_prediction_candidate_registry import (
            DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY,
        )
        self.validator = OfficialPredictionCandidateValidator(
            DEFAULT_OFFICIAL_PREDICTION_CANDIDATE_REGISTRY_POLICY
        )

    def test_unicode_whitespace_reason_order_and_display_normalization(self):
        first = command(
            competition_name="  Pre\u0301mier   League ",
            public_reasoning_facts=tuple(reversed(command().public_reasoning_facts)),
        )
        second = command(competition_name="Prémier League")
        a = self.validator.prepare(first)
        b = self.validator.prepare(second)
        self.assertEqual(a.content_fingerprint, b.content_fingerprint)
        self.assertEqual(a.public_reasoning_facts, b.public_reasoning_facts)
        self.assertEqual(a.competition_name, "Prémier   League")
        self.assertEqual(b.competition_name, "Prémier League")

    def test_decimal_and_timestamp_serialization_are_stable(self):
        self.assertEqual(canonical_decimal(Decimal("1.8000")), "1.8")
        self.assertEqual(canonical_decimal(Decimal("0.000")), "0")
        self.assertEqual(canonical_timestamp(NOW), NOW.isoformat())
        first = self.validator.prepare(command(decimal_odds=Decimal("1.8000")))
        second = self.validator.prepare(command(decimal_odds=Decimal("1.8")))
        self.assertEqual(first.content_fingerprint, second.content_fingerprint)

    def test_logical_and_content_fingerprints_are_stable_and_material(self):
        first = self.validator.prepare(command())
        repeated_at = self.validator.prepare(
            command(registration_timestamp=NOW + timedelta(seconds=30))
        )
        changed = self.validator.prepare(command(decimal_odds=Decimal("1.81")))
        self.assertEqual(
            first.logical_identity_fingerprint,
            changed.logical_identity_fingerprint,
        )
        self.assertEqual(first.content_fingerprint, repeated_at.content_fingerprint)
        self.assertNotEqual(first.content_fingerprint, changed.content_fingerprint)

    def test_dictionary_order_does_not_change_content_fingerprint(self):
        fingerprint = OfficialCandidateRegistryFingerprint()
        self.assertEqual(
            fingerprint.content({"a": 1, "b": 2}),
            fingerprint.content({"b": 2, "a": 1}),
        )


class RegistrationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.guard = Guard()
        self.service = build_official_prediction_candidate_registry(
            self.database,
            publication_guard=self.guard,
        )
        self.repository = SQLiteOfficialPredictionCandidateRepository(
            self.database,
            migrate=False,
        )

    def tearDown(self):
        self.database.close()

    def test_first_registration_and_identical_ingestion_are_idempotent(self):
        first = register_official_prediction_candidate(self.service, command())
        repeated = self.service.register_candidate(
            command(registration_timestamp=NOW + timedelta(seconds=30))
        )
        self.assertEqual(first.final_status, CandidateRegistrationStatus.REGISTERED)
        self.assertEqual(first.candidate_version, 1)
        self.assertEqual(
            repeated.final_status,
            CandidateRegistrationStatus.IDEMPOTENT_EXISTING,
        )
        self.assertEqual(first.registry_candidate_id, repeated.registry_candidate_id)
        self.assertEqual(len(self.guard.calls), 1)

    def test_validation_and_scope_failures_return_exact_typed_outcomes(self):
        invalid = self.service.register_candidate(command(decimal_odds=Decimal("1")))
        scoped = self.service.register_candidate(
            command(bankroll_scope=RiskProductScope.LIVE)
        )
        self.assertEqual(
            invalid.final_status,
            CandidateRegistrationStatus.REJECTED_INVALID,
        )
        self.assertEqual(
            scoped.final_status,
            CandidateRegistrationStatus.REJECTED_SCOPE,
        )
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM official_prediction_candidate_versions"
            ).fetchone()[0],
            0,
        )

    def test_material_update_supersedes_previous_and_preserves_history(self):
        first = self.service.register_candidate(command())
        second = self.service.register_candidate(
            command(
                source_event_id="prediction-engine-event-2",
                decimal_odds=Decimal("1.85"),
                registration_timestamp=NOW + timedelta(minutes=1),
            )
        )
        self.assertEqual(
            second.final_status,
            CandidateRegistrationStatus.SUPERSEDED_PREVIOUS,
        )
        self.assertEqual(second.candidate_version, 2)
        self.assertEqual(second.previous_candidate_id, first.registry_candidate_id)
        versions = self.repository.list_candidate_versions(
            second.logical_identity_fingerprint
        )
        self.assertEqual(tuple(item.candidate_version for item in versions), (1, 2))
        self.assertEqual(
            self.repository.current_state(first.registry_candidate_id),
            CandidateLifecycleState.SUPERSEDED,
        )
        self.assertEqual(
            self.repository.current_state(second.registry_candidate_id),
            CandidateLifecycleState.READY,
        )
        ready = self.repository.discover_ready_candidates(NOW)
        self.assertEqual(tuple(item.registry_candidate_id for item in ready), (second.registry_candidate_id,))

    def test_published_and_unknown_states_block_activation(self):
        for state, expected in (
            (CandidatePublicationGuardState.PUBLISHED, CandidateRegistrationStatus.ALREADY_PUBLISHED),
            (CandidatePublicationGuardState.ACTIVE_CLAIM, CandidateRegistrationStatus.CORRECTION_REQUIRED),
            (CandidatePublicationGuardState.INDETERMINATE, CandidateRegistrationStatus.CORRECTION_REQUIRED),
            (CandidatePublicationGuardState.UNKNOWN, CandidateRegistrationStatus.CORRECTION_REQUIRED),
        ):
            with self.subTest(state=state):
                database = Database(":memory:")
                service = build_official_prediction_candidate_registry(
                    database,
                    publication_guard=Guard(state),
                )
                outcome = service.register_candidate(command())
                self.assertEqual(outcome.final_status, expected)
                self.assertEqual(
                    database.connection.execute(
                        "SELECT COUNT(*) FROM official_prediction_candidate_versions"
                    ).fetchone()[0],
                    0,
                )
                database.close()

    def test_identical_retry_remains_idempotent_after_publication(self):
        registered = self.service.register_candidate(command())
        self.guard.value = CandidatePublicationGuardState.PUBLISHED
        repeated = self.service.register_candidate(
            command(registration_timestamp=NOW + timedelta(seconds=30))
        )
        changed = self.service.register_candidate(
            command(
                source_event_id="published-material-change",
                decimal_odds=Decimal("1.81"),
                registration_timestamp=NOW + timedelta(minutes=1),
            )
        )
        self.assertEqual(
            repeated.final_status,
            CandidateRegistrationStatus.IDEMPOTENT_EXISTING,
        )
        self.assertEqual(repeated.registry_candidate_id, registered.registry_candidate_id)
        self.assertEqual(changed.final_status, CandidateRegistrationStatus.ALREADY_PUBLISHED)

    def test_concrete_published_prediction_guard_blocks_registration(self):
        database = Database(":memory:")
        service = build_official_prediction_candidate_registry(database)
        database.connection.execute(
            """
            INSERT INTO published_predictions (
                prediction_id, fixture_id, market, pick, odds, stake,
                published_at, settlement_status
            ) VALUES ('prediction-1', 101, 'MATCH_WINNER', 'HOME', 1.8,
                      NULL, ?, 'PENDING')
            """,
            (NOW.isoformat(),),
        )
        outcome = service.register_candidate(command())
        self.assertEqual(outcome.final_status, CandidateRegistrationStatus.ALREADY_PUBLISHED)
        database.close()

    def test_lifecycle_insert_failure_rolls_back_candidate_version(self):
        self.database.connection.execute(
            """
            CREATE TRIGGER fail_candidate_lifecycle
            BEFORE INSERT ON official_prediction_candidate_lifecycle_events
            BEGIN
                SELECT RAISE(ABORT, 'test lifecycle failure');
            END
            """
        )
        outcome = self.service.register_candidate(command())
        self.assertEqual(
            outcome.final_status,
            CandidateRegistrationStatus.PERSISTENCE_FAILURE,
        )
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM official_prediction_candidate_versions"
            ).fetchone()[0],
            0,
        )

    def test_append_only_triggers_and_deterministic_snapshots(self):
        outcome = self.service.register_candidate(command())
        row = self.database.connection.execute(
            """
            SELECT normalized_snapshot, candidate_snapshot
            FROM official_prediction_candidate_versions
            WHERE registry_candidate_id = ?
            """,
            (outcome.registry_candidate_id,),
        ).fetchone()
        self.assertIn('"decimal_odds","1.8"', row["normalized_snapshot"])
        self.assertEqual(
            row["candidate_snapshot"],
            json.dumps(
                json.loads(row["candidate_snapshot"]),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        statements = (
            "UPDATE official_prediction_candidate_versions SET model_version='changed'",
            "DELETE FROM official_prediction_candidate_versions",
            "UPDATE official_prediction_candidate_lifecycle_events SET reason_code='changed'",
            "DELETE FROM official_prediction_candidate_lifecycle_events",
        )
        for statement in statements:
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(statement)

    def test_fresh_v14_and_v13_upgrade(self):
        versions = tuple(
            row[0]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 16)))
        upgrade = Database(":memory:")
        upgrade.connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for migration in MIGRATIONS[:13]:
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 'existing')",
                (migration.version,),
            )
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(
            upgrade.connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0],
            15,
        )
        upgrade.close()

    def test_concurrent_identical_and_different_registrations_are_safe(self):
        uri = "file:official-registry-concurrency?mode=memory&cache=shared"
        anchor = sqlite3.connect(uri, uri=True)
        anchor.row_factory = sqlite3.Row
        anchor.execute("PRAGMA foreign_keys = ON")
        MigrationManager(anchor).migrate()

        def register(value):
            connection = sqlite3.connect(uri, uri=True, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            service = build_official_prediction_candidate_registry(
                SimpleNamespace(connection=connection),
                publication_guard=Guard(),
            )
            result = service.register_candidate(value)
            connection.close()
            return result

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                identical = tuple(pool.map(register, (command(), command())))
            self.assertEqual(
                {item.final_status for item in identical},
                {
                    CandidateRegistrationStatus.REGISTERED,
                    CandidateRegistrationStatus.IDEMPOTENT_EXISTING,
                },
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                different = tuple(pool.map(
                    register,
                    (
                        command(
                            source_event_id="event-2",
                            decimal_odds=Decimal("1.82"),
                            registration_timestamp=NOW + timedelta(minutes=1),
                        ),
                        command(
                            source_event_id="event-3",
                            decimal_odds=Decimal("1.83"),
                            registration_timestamp=NOW + timedelta(minutes=2),
                        ),
                    ),
                ))
            repository = SQLiteOfficialPredictionCandidateRepository(
                SimpleNamespace(connection=anchor),
                migrate=False,
            )
            versions = repository.list_candidate_versions(
                identical[0].logical_identity_fingerprint
            )
            self.assertIn(
                tuple(item.candidate_version for item in versions),
                ((1, 2), (1, 2, 3)),
            )
            self.assertEqual(len(repository.discover_ready_candidates(NOW)), 1)
            self.assertTrue(any(
                item.final_status is CandidateRegistrationStatus.SUPERSEDED_PREVIOUS
                for item in different
            ))
            self.assertTrue(all(
                item.final_status in {
                    CandidateRegistrationStatus.SUPERSEDED_PREVIOUS,
                    CandidateRegistrationStatus.CONFLICT,
                }
                for item in different
            ))
        finally:
            anchor.close()


class LifecycleAndDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.service = build_official_prediction_candidate_registry(
            self.database,
            publication_guard=Guard(),
        )
        self.repository = SQLiteOfficialPredictionCandidateRepository(
            self.database,
            migrate=False,
        )

    def tearDown(self):
        self.database.close()

    def test_withdrawal_and_invalidation_remove_ready_without_deletion(self):
        for transition, expected in (
            ("withdraw_candidate", CandidateLifecycleState.WITHDRAWN),
            ("invalidate_candidate", CandidateLifecycleState.INVALIDATED),
        ):
            with self.subTest(transition=transition):
                registered = self.service.register_candidate(
                    command(prediction_id=f"prediction-{transition}")
                )
                outcome = getattr(self.service, transition)(
                    registered.registry_candidate_id,
                    reason_code="SOURCE_CORRECTION",
                    event_timestamp=NOW + timedelta(minutes=1),
                )
                self.assertEqual(outcome.status, CandidateLifecycleResultStatus.APPLIED)
                self.assertEqual(outcome.state, expected)
                self.assertEqual(
                    self.repository.find_candidate_by_id(registered.registry_candidate_id).candidate_version,
                    1,
                )
                self.assertNotIn(
                    registered.registry_candidate_id,
                    tuple(
                        item.registry_candidate_id
                        for item in self.repository.discover_ready_candidates(NOW)
                    ),
                )
                self.assertEqual(
                    len(self.repository.lifecycle_history(registered.registry_candidate_id)),
                    2,
                )

    def test_new_version_after_withdrawal_is_allowed_when_unpublished(self):
        first = self.service.register_candidate(command())
        self.service.withdraw_candidate(
            first.registry_candidate_id,
            reason_code="SOURCE_WITHDRAWAL",
            event_timestamp=NOW + timedelta(seconds=30),
        )
        second = self.service.register_candidate(
            command(
                source_event_id="event-after-withdrawal",
                decimal_odds=Decimal("1.84"),
                registration_timestamp=NOW + timedelta(minutes=1),
            )
        )
        self.assertEqual(second.candidate_version, 2)
        self.assertEqual(second.final_status, CandidateRegistrationStatus.REGISTERED)

    def test_historical_version_cannot_be_reactivated_in_place(self):
        first = self.service.register_candidate(command())
        self.service.withdraw_candidate(
            first.registry_candidate_id,
            reason_code="SOURCE_WITHDRAWAL",
            event_timestamp=NOW + timedelta(seconds=30),
        )
        latest = self.repository.lifecycle_history(first.registry_candidate_id)[-1]
        attempted = replace(
            latest,
            event_id="attempted-reactivation",
            event_sequence=latest.event_sequence + 1,
            event_type=CandidateLifecycleState.READY,
            reason_code="REACTIVATE",
            event_timestamp=NOW + timedelta(minutes=1),
        )
        with self.assertRaises(CandidateRegistryConflictError):
            self.repository.append_lifecycle_event(attempted)

    def test_discovery_is_ready_only_ordered_and_excludes_expired(self):
        inputs = (
            command(
                prediction_id="prediction-b",
                match_id="102",
                kickoff_timestamp=NOW + timedelta(hours=3),
            ),
            command(
                prediction_id="prediction-a",
                match_id="103",
                kickoff_timestamp=NOW + timedelta(hours=2),
                prediction_creation_timestamp=NOW - timedelta(minutes=5),
            ),
            command(
                prediction_id="prediction-c",
                match_id="104",
                kickoff_timestamp=NOW + timedelta(hours=2),
                prediction_creation_timestamp=NOW - timedelta(minutes=10),
            ),
        )
        outcomes = tuple(self.service.register_candidate(value) for value in inputs)
        self.service.invalidate_candidate(
            outcomes[0].registry_candidate_id,
            reason_code="BAD_SOURCE",
            event_timestamp=NOW + timedelta(minutes=1),
        )
        ready = self.repository.discover_ready_candidates(NOW)
        self.assertEqual(tuple(item.prediction_id for item in ready), ("prediction-c", "prediction-a"))
        self.assertEqual(self.repository.discover_ready_candidates(NOW + timedelta(hours=4)), ())


class CoordinatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.registry = build_official_prediction_candidate_registry(
            self.database,
            publication_guard=Guard(),
        )
        self.registered = self.registry.register_candidate(command())
        self.contexts = Contexts()
        self.source = build_registry_candidate_source(self.database, self.contexts)

    def tearDown(self):
        self.database.close()

    def test_adapter_supplies_existing_orchestration_request_with_traceability(self):
        references = self.source.load_candidates(NOW, ())
        self.assertEqual(len(references), 1)
        reference = references[0]
        self.assertEqual(reference.registry_candidate_id, self.registered.registry_candidate_id)
        self.assertEqual(reference.immutable_fingerprint, self.registered.candidate_content_fingerprint)
        prediction = reference.request.prediction
        self.assertEqual(prediction.registry_candidate_id, self.registered.registry_candidate_id)
        assembly = OfficialPredictionCandidateAssembler().assemble(
            reference.request,
            publication(),
        )
        normalized = dict(assembly.normalized_input)
        self.assertEqual(normalized["registry_candidate_id"], self.registered.registry_candidate_id)
        self.assertEqual(assembly.calibration_run_id, "calibration-1")
        self.assertEqual(assembly.risk_evaluation_id, "risk-1")
        self.assertEqual(assembly.exposure_evaluation_id, "exposure-1")

    def test_coordinator_dry_run_executes_quality_gate_without_publisher(self):
        publisher = Publisher()
        orchestration = build_official_prediction_orchestration_service(
            self.database,
            publisher,
        )
        coordinator = build_official_prediction_run_coordinator(
            self.database,
            self.source,
            orchestration,
        )
        result = asyncio.run(run_official_prediction_batch(
            coordinator,
            evaluation_timestamp=NOW,
            idempotency_key="registry-dry-run",
        ))
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.DRY_RUN_COMPLETED)
        self.assertEqual(result.approved_not_published_count, 1)
        self.assertEqual(publisher.calls, [])
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM official_quality_gate_evaluations"
            ).fetchone()[0],
            1,
        )

    def test_coordinator_publish_path_uses_injected_test_publisher(self):
        publisher = Publisher()
        orchestration = build_official_prediction_orchestration_service(
            self.database,
            publisher,
        )
        coordinator = build_official_prediction_run_coordinator(
            self.database,
            self.source,
            orchestration,
        )
        result = asyncio.run(run_official_prediction_batch(
            coordinator,
            evaluation_timestamp=NOW,
            idempotency_key="registry-publish-run",
            dry_run=False,
        ))
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.COMPLETED)
        self.assertEqual(result.published_count, 1)
        self.assertEqual(len(publisher.calls), 1)
        approved = publisher.calls[0]
        self.assertEqual(
            dict(approved.assembly.normalized_input)["registry_content_fingerprint"],
            self.registered.candidate_content_fingerprint,
        )

    def test_coordinator_still_blocks_published_active_and_indeterminate_states(self):
        for state in (
            CandidateDiscoveryStatus.ALREADY_PUBLISHED,
            CandidateDiscoveryStatus.ACTIVE_DUPLICATE_CLAIM,
            CandidateDiscoveryStatus.INDETERMINATE,
        ):
            with self.subTest(state=state):
                orchestrator = Orchestrator()
                discovery = DeterministicOfficialPredictionCandidateDiscovery(
                    self.source,
                    States(state),
                )
                result = discovery.discover(
                    OfficialPredictionRunRequest(
                        NOW,
                        f"state-{state.value}",
                        True,
                        False,
                        (),
                    ),
                    OfficialPredictionRunPolicy(),
                )
                self.assertEqual(result.ordered_candidates[0].status, state)

    def test_registry_source_and_coordinator_apply_time_and_batch_policy(self):
        self.registry.invalidate_candidate(
            self.registered.registry_candidate_id,
            reason_code="TEST_SETUP",
            event_timestamp=NOW,
        )
        for value in (
            command(
                prediction_id="prediction-close",
                match_id="201",
                kickoff_timestamp=NOW + timedelta(minutes=10),
            ),
            command(
                prediction_id="prediction-ready",
                match_id="202",
                kickoff_timestamp=NOW + timedelta(hours=1),
            ),
            command(
                prediction_id="prediction-batch",
                match_id="203",
                kickoff_timestamp=NOW + timedelta(minutes=90),
            ),
            command(
                prediction_id="prediction-future",
                match_id="204",
                kickoff_timestamp=NOW + timedelta(hours=3),
            ),
        ):
            self.registry.register_candidate(value)
        discovery = DeterministicOfficialPredictionCandidateDiscovery(
            self.source,
            States(),
        )
        result = discovery.discover(
            OfficialPredictionRunRequest(
                NOW,
                "registry-policy",
                True,
                False,
                (),
            ),
            OfficialPredictionRunPolicy(
                maximum_batch_size=1,
                kickoff_lookahead_window=timedelta(hours=2),
                minimum_time_remaining_before_kickoff=timedelta(minutes=30),
            ),
        )
        statuses = {
            item.reference.prediction_id: item.status
            for item in result.ordered_candidates
        }
        self.assertEqual(statuses["prediction-close"], CandidateDiscoveryStatus.EXPIRED)
        self.assertEqual(statuses["prediction-ready"], CandidateDiscoveryStatus.READY)
        self.assertEqual(
            statuses["prediction-batch"],
            CandidateDiscoveryStatus.NOT_YET_ELIGIBLE,
        )
        self.assertEqual(
            statuses["prediction-future"],
            CandidateDiscoveryStatus.NOT_YET_ELIGIBLE,
        )
