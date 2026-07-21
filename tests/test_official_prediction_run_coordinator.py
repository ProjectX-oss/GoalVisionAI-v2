import asyncio
import sqlite3
import unittest
from dataclasses import replace
from datetime import timedelta

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.official_prediction_orchestration import (
    OfficialPredictionOrchestrationOutcome,
    OrchestrationStatus,
    build_official_prediction_orchestration_service,
)
from app.official_prediction_publication import OfficialPredictionDestination
from app.official_prediction_run_coordinator import (
    CandidateDiscoveryStatus,
    CandidateHistoricalState,
    DeterministicOfficialPredictionCandidateDiscovery,
    OfficialPredictionCandidateReference,
    OfficialPredictionRunCoordinator,
    OfficialPredictionRunFingerprint,
    OfficialPredictionRunItemResult,
    OfficialPredictionRunItemStatus,
    OfficialPredictionRunPolicy,
    OfficialPredictionRunPersistenceError,
    OfficialPredictionRunRequest,
    OfficialPredictionRunResult,
    OfficialPredictionRunStart,
    OfficialPredictionRunStatus,
    SQLiteOfficialPredictionRunRepository,
    SQLiteOfficialCandidateHistoricalStateReader,
    build_official_prediction_run_coordinator,
    run_official_prediction_batch,
)
from app.risk_management import RiskProductScope
from tests.test_official_prediction_orchestration import NOW, request
from tests.test_official_prediction_publication import (
    Clock,
    FactsProvider,
    Telegram,
    public_facts,
)


def candidate(
    prediction_id: str = "prediction-1",
    *,
    match_id: str = "101",
    kickoff_delta: timedelta = timedelta(hours=2),
    created_delta: timedelta = timedelta(minutes=-10),
    bankroll_scope: RiskProductScope = RiskProductScope.OFFICIAL,
    destination_scope: RiskProductScope = RiskProductScope.OFFICIAL,
    fingerprint: str | None = None,
) -> OfficialPredictionCandidateReference:
    source = request()
    prediction = replace(
        source.prediction,
        prediction_id=prediction_id,
        match_id=match_id,
        prediction_timestamp=NOW + created_delta,
        kickoff_timestamp=NOW + kickoff_delta,
    )
    bankroll = replace(source.bankroll, product_scope=bankroll_scope)
    assembly_request = replace(
        source,
        prediction=prediction,
        bankroll=bankroll,
    )
    return OfficialPredictionCandidateReference(
        prediction_id=prediction_id,
        match_id=match_id,
        immutable_fingerprint=fingerprint or f"immutable-{prediction_id}",
        kickoff_timestamp=prediction.kickoff_timestamp,
        prediction_created_timestamp=prediction.prediction_timestamp,
        bankroll_scope=bankroll_scope,
        destination_scope=destination_scope,
        request=assembly_request,
    )


def run_request(
    key: str = "manual-run-1",
    *,
    dry_run: bool = False,
    force_review: bool = False,
    filters: tuple[tuple[str, str], ...] = (),
) -> OfficialPredictionRunRequest:
    return OfficialPredictionRunRequest(
        evaluation_timestamp=NOW,
        idempotency_key=key,
        dry_run=dry_run,
        force_review=force_review,
        normalized_discovery_filters=tuple(sorted(filters)),
    )


class Source:
    def __init__(self, values=(), error=None):
        self.values = tuple(values)
        self.error = error
        self.calls = []

    def load_candidates(self, evaluated_at, normalized_filters):
        self.calls.append((evaluated_at, normalized_filters))
        if self.error is not None:
            raise self.error
        return self.values


class States:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, value, evaluated_at):
        return self.values.get(
            value.prediction_id,
            CandidateHistoricalState(CandidateDiscoveryStatus.READY),
        )


class Orchestrator:
    def __init__(self, outcomes=None, errors=None, protect_duplicates=False):
        self.outcomes = outcomes or {}
        self.errors = errors or {}
        self.protect_duplicates = protect_duplicates
        self.calls = []
        self.active = 0
        self.maximum_active = 0
        self.published = set()

    async def prepare_and_publish_official_prediction(self, value):
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.calls.append(value)
        await asyncio.sleep(0)
        self.active -= 1
        prediction_id = value.prediction.prediction_id
        if prediction_id in self.errors:
            raise self.errors[prediction_id]
        if value.dry_run:
            status = self.outcomes.get(
                prediction_id,
                OrchestrationStatus.APPROVED_NOT_PUBLISHED,
            )
        elif self.protect_duplicates and prediction_id in self.published:
            status = OrchestrationStatus.DUPLICATE_BLOCKED
        else:
            status = self.outcomes.get(
                prediction_id,
                OrchestrationStatus.PUBLISHED,
            )
        if status is OrchestrationStatus.PUBLISHED:
            self.published.add(prediction_id)
        return outcome(prediction_id, status, value.dry_run)


def outcome(prediction_id, status, dry_run=False):
    return OfficialPredictionOrchestrationOutcome(
        orchestration_id=f"orchestration-{prediction_id}-{status.value}",
        prediction_id=prediction_id,
        candidate_fingerprint=f"orchestration-fingerprint-{prediction_id}",
        quality_gate_evaluation_id=f"gate-{prediction_id}",
        final_status=status,
        ordered_reason_codes=(f"REASON_{status.value}",),
        internal_explanations=(),
        publication_attempt_reference=(
            f"attempt-{prediction_id}" if not dry_run else None
        ),
        evaluated_timestamp=NOW,
        dry_run=dry_run,
        policy_version="gate-v1",
        model_version="model-v1",
    )


class DiscoveryTests(unittest.TestCase):
    def discover(self, values, *, states=None, policy=None, execution=None):
        return DeterministicOfficialPredictionCandidateDiscovery(
            Source(values),
            States(states),
        ).discover(
            execution or run_request(),
            policy or OfficialPredictionRunPolicy(),
        )

    def test_deterministic_ordering_and_batch_limit(self):
        values = (
            candidate("c", kickoff_delta=timedelta(hours=3)),
            candidate("b", kickoff_delta=timedelta(hours=2), created_delta=timedelta(minutes=-5)),
            candidate("a", kickoff_delta=timedelta(hours=2), created_delta=timedelta(minutes=-10)),
        )
        result = self.discover(
            tuple(reversed(values)),
            policy=OfficialPredictionRunPolicy(maximum_batch_size=2),
        )
        self.assertEqual(
            [item.reference.prediction_id for item in result.ordered_candidates],
            ["a", "b", "c"],
        )
        self.assertEqual(
            result.ordered_candidates[-1].status,
            CandidateDiscoveryStatus.NOT_YET_ELIGIBLE,
        )
        self.assertEqual(
            result.ordered_candidates[-1].ordered_reason_codes,
            ("BATCH_LIMIT_REACHED",),
        )

    def test_time_scope_malformed_and_duplicate_classification(self):
        base = candidate("valid")
        malformed = replace(candidate("malformed"), immutable_fingerprint="")
        duplicate = replace(base)
        values = (
            candidate("expired", kickoff_delta=timedelta(minutes=10)),
            candidate("future", kickoff_delta=timedelta(hours=25)),
            candidate("bank", bankroll_scope=RiskProductScope.COMBO),
            candidate("channel", destination_scope=RiskProductScope.COMBO),
            malformed,
            base,
            duplicate,
        )
        result = self.discover(values)
        statuses = {
            item.reference.prediction_id: item.status
            for item in result.ordered_candidates
            if item.reference.prediction_id != "valid"
        }
        self.assertEqual(statuses["expired"], CandidateDiscoveryStatus.EXPIRED)
        self.assertEqual(statuses["future"], CandidateDiscoveryStatus.NOT_YET_ELIGIBLE)
        self.assertEqual(statuses["bank"], CandidateDiscoveryStatus.NON_OFFICIAL)
        self.assertEqual(statuses["channel"], CandidateDiscoveryStatus.NON_OFFICIAL)
        self.assertEqual(statuses["malformed"], CandidateDiscoveryStatus.MALFORMED)
        valid = [
            item for item in result.ordered_candidates
            if item.reference.prediction_id == "valid"
        ]
        self.assertEqual(len(valid), 2)
        self.assertEqual(valid[0].status, CandidateDiscoveryStatus.READY)
        self.assertEqual(valid[1].status, CandidateDiscoveryStatus.MALFORMED)

    def test_all_historical_delivery_states_remain_distinct(self):
        state_values = {
            "published": CandidateHistoricalState(CandidateDiscoveryStatus.ALREADY_PUBLISHED),
            "claim": CandidateHistoricalState(CandidateDiscoveryStatus.ACTIVE_DUPLICATE_CLAIM),
            "retry": CandidateHistoricalState(
                CandidateDiscoveryStatus.RETRYABLE_CONFIRMED_FAILURE,
                attempt_count=1,
                last_attempt_timestamp=NOW - timedelta(minutes=10),
            ),
            "unknown": CandidateHistoricalState(CandidateDiscoveryStatus.INDETERMINATE),
            "rejected": CandidateHistoricalState(CandidateDiscoveryStatus.REJECTED_IMMUTABLE),
            "review": CandidateHistoricalState(CandidateDiscoveryStatus.REVIEW_REQUIRED_IMMUTABLE),
        }
        result = self.discover(
            tuple(candidate(value) for value in state_values),
            states=state_values,
        )
        self.assertEqual(
            {item.reference.prediction_id: item.status for item in result.ordered_candidates},
            {key: value.status for key, value in state_values.items()},
        )


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")

    def tearDown(self):
        self.database.close()

    def coordinator(self, values, *, states=None, orchestrator=None, policy=None, runs=None):
        return OfficialPredictionRunCoordinator(
            DeterministicOfficialPredictionCandidateDiscovery(
                Source(values),
                States(states),
            ),
            orchestrator or Orchestrator(),
            runs or SQLiteOfficialPredictionRunRepository(self.database),
            policy or OfficialPredictionRunPolicy(),
        )

    def execute(self, coordinator, execution=None):
        return asyncio.run(
            coordinator.run_official_prediction_batch(execution or run_request())
        )

    def test_no_eligible_candidates_persists_complete_skipped_summary(self):
        value = candidate("published")
        coordinator = self.coordinator(
            (value,),
            states={
                "published": CandidateHistoricalState(
                    CandidateDiscoveryStatus.ALREADY_PUBLISHED
                )
            },
        )
        result = self.execute(coordinator)
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.NO_ELIGIBLE_CANDIDATES)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(
            result.ordered_items[0].status,
            OfficialPredictionRunItemStatus.SKIPPED_ALREADY_PUBLISHED,
        )

    def test_multiple_candidates_are_sequential_ordered_and_timestamped(self):
        orchestrator = Orchestrator()
        coordinator = self.coordinator(
            (
                candidate("later", kickoff_delta=timedelta(hours=3)),
                candidate("first", kickoff_delta=timedelta(hours=1)),
            ),
            orchestrator=orchestrator,
        )
        result = self.execute(coordinator)
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.COMPLETED)
        self.assertEqual(result.published_count, 2)
        self.assertEqual(
            [value.prediction.prediction_id for value in orchestrator.calls],
            ["first", "later"],
        )
        self.assertEqual(orchestrator.maximum_active, 1)
        self.assertTrue(all(value.evaluation_timestamp == NOW for value in orchestrator.calls))
        self.assertEqual(
            [item.item_index for item in result.ordered_items],
            [0, 1],
        )

    def test_all_orchestration_outcomes_map_without_collapsing(self):
        statuses = tuple(OrchestrationStatus)
        values = tuple(candidate(f"p-{index}") for index in range(len(statuses)))
        configured = {
            value.prediction_id: status
            for value, status in zip(values, statuses)
        }
        result = self.execute(
            self.coordinator(values, orchestrator=Orchestrator(configured))
        )
        self.assertEqual(
            [item.status.value for item in result.ordered_items],
            [configured[item.prediction_id].value for item in result.ordered_items],
        )
        self.assertEqual(result.published_count, 1)
        self.assertEqual(result.approved_not_published_count, 1)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.review_required_count, 1)
        self.assertEqual(result.duplicate_blocked_count, 1)
        self.assertEqual(result.retryable_failure_count, 1)
        self.assertEqual(result.indeterminate_failure_count, 1)
        self.assertEqual(result.assembly_failure_count, 1)
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.INDETERMINATE)

    def test_internal_failure_isolated_and_default_continues(self):
        orchestrator = Orchestrator(errors={"bad": RuntimeError("private")})
        result = self.execute(
            self.coordinator(
                (candidate("bad", kickoff_delta=timedelta(hours=1)), candidate("good")),
                orchestrator=orchestrator,
            )
        )
        self.assertEqual(result.internal_failure_count, 1)
        self.assertEqual(result.published_count, 1)
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.COMPLETED_WITH_FAILURES)
        self.assertEqual(len(orchestrator.calls), 2)
        self.assertNotIn("private", str(result))

    def test_stop_after_failure_aborts_and_skips_remaining(self):
        orchestrator = Orchestrator(errors={"bad": RuntimeError("bad")})
        policy = OfficialPredictionRunPolicy(stop_batch_after_failure=True)
        result = self.execute(
            self.coordinator(
                (candidate("bad", kickoff_delta=timedelta(hours=1)), candidate("later")),
                orchestrator=orchestrator,
                policy=policy,
            )
        )
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.ABORTED)
        self.assertEqual(result.internal_failure_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(len(orchestrator.calls), 1)
        self.assertEqual(result.stop_reason, "STOPPED_AFTER_INTERNAL_FAILURE")

    def test_retry_limit_cooldown_and_allowed_retry(self):
        values = (
            candidate("limit"),
            candidate("cooldown"),
            candidate("retry"),
        )
        states = {
            "limit": CandidateHistoricalState(
                CandidateDiscoveryStatus.RETRYABLE_CONFIRMED_FAILURE,
                attempt_count=3,
                last_attempt_timestamp=NOW - timedelta(hours=1),
            ),
            "cooldown": CandidateHistoricalState(
                CandidateDiscoveryStatus.RETRYABLE_CONFIRMED_FAILURE,
                attempt_count=1,
                last_attempt_timestamp=NOW - timedelta(minutes=1),
            ),
            "retry": CandidateHistoricalState(
                CandidateDiscoveryStatus.RETRYABLE_CONFIRMED_FAILURE,
                attempt_count=1,
                last_attempt_timestamp=NOW - timedelta(minutes=10),
            ),
        }
        orchestrator = Orchestrator()
        result = self.execute(
            self.coordinator(values, states=states, orchestrator=orchestrator)
        )
        by_id = {item.prediction_id: item.status for item in result.ordered_items}
        self.assertEqual(by_id["limit"], OfficialPredictionRunItemStatus.SKIPPED_RETRY_LIMIT)
        self.assertEqual(by_id["cooldown"], OfficialPredictionRunItemStatus.SKIPPED_RETRY_COOLDOWN)
        self.assertEqual(by_id["retry"], OfficialPredictionRunItemStatus.PUBLISHED)
        self.assertEqual(len(orchestrator.calls), 1)

    def test_active_indeterminate_and_published_are_never_retried(self):
        values = tuple(candidate(value) for value in ("claim", "unknown", "published"))
        states = {
            "claim": CandidateHistoricalState(CandidateDiscoveryStatus.ACTIVE_DUPLICATE_CLAIM),
            "unknown": CandidateHistoricalState(CandidateDiscoveryStatus.INDETERMINATE),
            "published": CandidateHistoricalState(CandidateDiscoveryStatus.ALREADY_PUBLISHED),
        }
        orchestrator = Orchestrator()
        result = self.execute(
            self.coordinator(values, states=states, orchestrator=orchestrator)
        )
        self.assertEqual(result.skipped_count, 3)
        self.assertEqual(orchestrator.calls, [])

    def test_idempotency_and_prediction_duplicate_protection(self):
        orchestrator = Orchestrator(protect_duplicates=True)
        coordinator = self.coordinator(
            (candidate("p"),),
            orchestrator=orchestrator,
        )
        first = self.execute(coordinator)
        repeated = self.execute(coordinator)
        changed = self.execute(coordinator, run_request("manual-run-2"))
        self.assertEqual(first, repeated)
        self.assertEqual(len(orchestrator.calls), 2)
        self.assertEqual(changed.duplicate_blocked_count, 1)
        self.assertNotEqual(first.run_id, changed.run_id)

    def test_force_review_only_dry_run_and_never_bypasses_orchestration(self):
        value = candidate("review")
        states = {
            "review": CandidateHistoricalState(
                CandidateDiscoveryStatus.REVIEW_REQUIRED_IMMUTABLE
            )
        }
        orchestrator = Orchestrator({"review": OrchestrationStatus.REVIEW_REQUIRED})
        coordinator = self.coordinator(
            (value,), states=states, orchestrator=orchestrator
        )
        normal = self.execute(coordinator, run_request("normal", dry_run=True))
        forced = self.execute(
            coordinator,
            run_request("forced", dry_run=True, force_review=True),
        )
        self.assertEqual(normal.skipped_count, 1)
        self.assertEqual(forced.review_required_count, 1)
        self.assertEqual(forced.run_status, OfficialPredictionRunStatus.DRY_RUN_COMPLETED)
        self.assertEqual(len(orchestrator.calls), 1)
        with self.assertRaises(ValueError):
            run_request("unsafe", force_review=True)

    def test_duplicate_source_reference_never_invokes_twice_in_one_run(self):
        value = candidate("duplicate")
        orchestrator = Orchestrator()
        result = self.execute(
            self.coordinator((value, replace(value)), orchestrator=orchestrator)
        )
        self.assertEqual(len(orchestrator.calls), 1)
        self.assertEqual(result.published_count, 1)
        self.assertEqual(result.skipped_count, 1)

    def test_immutable_rejection_requires_changed_fingerprint(self):
        source = Source((candidate("rejected"),))
        orchestrator = Orchestrator({
            "rejected": OrchestrationStatus.REJECTED,
        })
        coordinator = build_official_prediction_run_coordinator(
            self.database,
            source,
            orchestrator,
        )
        first = self.execute(coordinator, run_request("reject-1"))
        unchanged = self.execute(coordinator, run_request("reject-2"))
        source.values = (
            replace(source.values[0], immutable_fingerprint="changed-material"),
        )
        changed = self.execute(coordinator, run_request("reject-3"))
        self.assertEqual(first.rejected_count, 1)
        self.assertEqual(unchanged.skipped_count, 1)
        self.assertEqual(
            unchanged.ordered_items[0].discovery_status,
            CandidateDiscoveryStatus.REJECTED_IMMUTABLE,
        )
        self.assertEqual(changed.rejected_count, 1)
        self.assertEqual(len(orchestrator.calls), 2)


class FingerprintAndPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.repository = SQLiteOfficialPredictionRunRepository(self.database)
        self.policy = OfficialPredictionRunPolicy()

    def tearDown(self):
        self.database.close()

    def start(self, execution=None):
        execution = execution or run_request()
        fingerprint = OfficialPredictionRunFingerprint().generate(execution, self.policy)
        return OfficialPredictionRunStart(
            run_id=f"official-prediction-run-{fingerprint}",
            run_fingerprint=fingerprint,
            request=execution,
            policy_version=self.policy.version,
            bankroll_scope=RiskProductScope.OFFICIAL,
            destination_scope=RiskProductScope.OFFICIAL,
            request_snapshot=(("policy", self.policy.version),),
        )

    def item(self, start, status=OfficialPredictionRunItemStatus.PUBLISHED):
        value = candidate("persisted")
        return OfficialPredictionRunItemResult(
            run_id=start.run_id,
            item_index=0,
            prediction_id=value.prediction_id,
            match_id=value.match_id,
            candidate_fingerprint=value.immutable_fingerprint,
            kickoff_timestamp=value.kickoff_timestamp,
            discovery_status=CandidateDiscoveryStatus.READY,
            status=status,
            was_eligible=True,
            started_timestamp=NOW,
            completed_timestamp=NOW,
            orchestration_id="orchestration-persisted",
        )

    def result(self, start, item):
        return OfficialPredictionRunResult(
            run_id=start.run_id,
            run_fingerprint=start.run_fingerprint,
            started_timestamp=NOW,
            completed_timestamp=NOW,
            run_status=OfficialPredictionRunStatus.COMPLETED,
            policy_version=self.policy.version,
            dry_run=False,
            discovered_count=1,
            eligible_count=1,
            processed_count=1,
            published_count=1,
            approved_not_published_count=0,
            rejected_count=0,
            review_required_count=0,
            duplicate_blocked_count=0,
            retryable_failure_count=0,
            indeterminate_failure_count=0,
            assembly_failure_count=0,
            skipped_count=0,
            internal_failure_count=0,
            ordered_items=(item,),
        )

    def test_run_fingerprint_is_canonical_and_material(self):
        fingerprint = OfficialPredictionRunFingerprint()
        first = run_request(filters=(("league", "1"), ("model", "v1")))
        reordered = run_request(filters=(("model", "v1"), ("league", "1")))
        self.assertEqual(
            fingerprint.generate(first, self.policy),
            fingerprint.generate(reordered, self.policy),
        )
        changed = run_request("other", filters=first.normalized_discovery_filters)
        self.assertNotEqual(
            fingerprint.generate(first, self.policy),
            fingerprint.generate(changed, self.policy),
        )
        stop_after_failure = replace(self.policy, stop_batch_after_failure=True)
        self.assertNotEqual(
            fingerprint.generate(first, self.policy),
            fingerprint.generate(first, stop_after_failure),
        )

    def test_begin_append_finalize_load_and_idempotent_lookup(self):
        start = self.start()
        claim = self.repository.begin_run(start)
        self.assertTrue(claim.acquired)
        item = self.repository.append_item(self.item(start))
        result = self.result(start, item)
        self.assertEqual(self.repository.finalize_run(result), result)
        self.assertEqual(self.repository.load_complete_run(start.run_id), result)
        repeated = self.repository.begin_run(start)
        self.assertFalse(repeated.acquired)
        self.assertEqual(repeated.existing_result, result)
        with self.assertRaises(OfficialPredictionRunPersistenceError):
            self.repository.finalize_run(result)

    def test_incomplete_run_is_detected_and_not_reacquired(self):
        start = self.start()
        self.repository.begin_run(start)
        repeated = self.repository.load_by_fingerprint(start.run_fingerprint)
        self.assertTrue(repeated.incomplete)
        self.assertIsNone(repeated.existing_result)
        self.assertFalse(self.repository.begin_run(start).acquired)

    def test_append_only_triggers_and_unique_fingerprint(self):
        start = self.start()
        self.repository.begin_run(start)
        self.repository.append_item(self.item(start))
        for statement in (
            "UPDATE official_prediction_runs SET policy_version='changed'",
            "DELETE FROM official_prediction_runs",
            "UPDATE official_prediction_run_items SET item_status='REJECTED'",
            "DELETE FROM official_prediction_run_items",
        ):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(statement)

    def test_fresh_latest_and_v12_upgrade(self):
        versions = tuple(
            row[0]
            for row in self.database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 17)))
        upgrade = Database(":memory:")
        upgrade.connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for migration in MIGRATIONS[:12]:
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
            16,
        )
        upgrade.close()

    def test_concrete_state_reader_blocks_published_prediction(self):
        value = candidate("published", match_id="501")
        self.database.connection.execute(
            """
            INSERT INTO published_predictions (
                prediction_id, fixture_id, market, pick, odds, stake,
                published_at, settlement_status
            ) VALUES (?, ?, 'MATCH_WINNER', 'HOME', 1.8, NULL, ?, 'PENDING')
            """,
            (value.prediction_id, 501, NOW.isoformat()),
        )
        state = SQLiteOfficialCandidateHistoricalStateReader(
            self.database,
            migrate=False,
        ).get(value, NOW)
        self.assertEqual(state.status, CandidateDiscoveryStatus.ALREADY_PUBLISHED)

    def test_immutable_state_reader_matches_any_historical_fingerprint(self):
        original = candidate("history", fingerprint="fingerprint-original")
        changed = candidate("history", fingerprint="fingerprint-changed")
        for item_index, value, status in (
            (0, original, OfficialPredictionRunItemStatus.REJECTED),
            (1, changed, OfficialPredictionRunItemStatus.REVIEW_REQUIRED),
        ):
            start = replace(
                self.start(run_request(f"history-{item_index}")),
                run_id=f"run-history-{item_index}",
                run_fingerprint=f"run-fingerprint-history-{item_index}",
            )
            self.repository.begin_run(start)
            self.repository.append_item(
                replace(
                    self.item(start),
                    item_index=0,
                    prediction_id=value.prediction_id,
                    match_id=value.match_id,
                    candidate_fingerprint=value.immutable_fingerprint,
                    status=status,
                )
            )

        reader = SQLiteOfficialCandidateHistoricalStateReader(
            self.database,
            migrate=False,
        )
        self.assertEqual(
            reader.get(original, NOW).status,
            CandidateDiscoveryStatus.REJECTED_IMMUTABLE,
        )
        self.assertEqual(
            reader.get(changed, NOW).status,
            CandidateDiscoveryStatus.REVIEW_REQUIRED_IMMUTABLE,
        )

    def test_inconsistent_run_counters_are_rejected(self):
        start = self.start()
        item = self.item(start)
        with self.assertRaises(ValueError):
            replace(self.result(start, item), published_count=0)


class FailureAndCompositionTests(unittest.TestCase):
    def test_repository_failure_before_start_prevents_discovery(self):
        source = Source((candidate(),))

        class BrokenRuns:
            def begin_run(self, start):
                raise ValueError("unavailable")

        coordinator = OfficialPredictionRunCoordinator(
            DeterministicOfficialPredictionCandidateDiscovery(source, States()),
            Orchestrator(),
            BrokenRuns(),
            OfficialPredictionRunPolicy(),
        )
        result = asyncio.run(coordinator.run_official_prediction_batch(run_request()))
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.FAILED_TO_START)
        self.assertEqual(source.calls, [])

    def test_discovery_failure_is_aborted_and_terminally_persisted(self):
        database = Database(":memory:")
        repository = SQLiteOfficialPredictionRunRepository(database)
        coordinator = OfficialPredictionRunCoordinator(
            DeterministicOfficialPredictionCandidateDiscovery(
                Source(error=ValueError("discovery")), States()
            ),
            Orchestrator(),
            repository,
            OfficialPredictionRunPolicy(),
        )
        result = asyncio.run(coordinator.run_official_prediction_batch(run_request()))
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.ABORTED)
        self.assertEqual(repository.load_complete_run(result.run_id), result)
        database.close()

    def test_item_and_finalization_persistence_failures_are_indeterminate(self):
        class FailingRuns:
            def __init__(self, fail_item):
                self.fail_item = fail_item

            def begin_run(self, start):
                from app.official_prediction_run_coordinator import OfficialPredictionRunClaim
                return OfficialPredictionRunClaim(True, start)

            def append_item(self, item):
                if self.fail_item:
                    raise ValueError("item")
                return item

            def finalize_run(self, result):
                raise ValueError("terminal")

        for fail_item in (True, False):
            with self.subTest(fail_item=fail_item):
                coordinator = OfficialPredictionRunCoordinator(
                    DeterministicOfficialPredictionCandidateDiscovery(
                        Source((candidate(),)), States()
                    ),
                    Orchestrator(),
                    FailingRuns(fail_item),
                    OfficialPredictionRunPolicy(),
                )
                result = asyncio.run(
                    coordinator.run_official_prediction_batch(run_request())
                )
                self.assertEqual(result.run_status, OfficialPredictionRunStatus.INDETERMINATE)

    def test_manual_default_dry_run_uses_real_boundary_without_send(self):
        database = Database(":memory:")
        telegram = Telegram()
        service = build_official_prediction_orchestration_service(
            database,
            telegram=telegram,
            public_facts=FactsProvider(transform=lambda approved: public_facts(approved)),
            destination=OfficialPredictionDestination(
                RiskProductScope.OFFICIAL,
                "@official",
            ),
            clock=Clock(),
        )
        coordinator = build_official_prediction_run_coordinator(
            database,
            Source((candidate(),)),
            service,
        )
        self.assertEqual(telegram.calls, [])
        result = asyncio.run(
            run_official_prediction_batch(
                coordinator,
                evaluation_timestamp=NOW,
                idempotency_key="manual-dry-run",
            )
        )
        self.assertEqual(result.run_status, OfficialPredictionRunStatus.DRY_RUN_COMPLETED)
        self.assertEqual(result.approved_not_published_count, 1)
        self.assertEqual(telegram.calls, [])
        self.assertEqual(
            database.connection.execute(
                "SELECT COUNT(*) FROM official_prediction_publication_events"
            ).fetchone()[0],
            0,
        )
        database.close()


if __name__ == "__main__":
    unittest.main()
