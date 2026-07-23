import asyncio
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database import (
    Database,
    MigrationManager,
    SQLitePredictionResultRepository,
)
from app.database.migrations import MIGRATIONS
from app.official_prediction_orchestration import (
    ApprovedOfficialPredictionPublication,
    OfficialCandidateFingerprint,
    OfficialPredictionCandidateAssembler,
    PublicationDeliveryState,
    build_official_prediction_orchestration_service,
)
from app.official_prediction_publication import (
    ApprovedPublicReasoning,
    ConfirmedTelegramDeliveryError,
    OfficialPredictionDestination,
    OfficialPredictionMessageBuilder,
    OfficialPredictionMessageInput,
    OfficialPredictionMessagePolicy,
    OfficialPredictionPublicFacts,
    OfficialPredictionPublisherAdapter,
    OfficialStakeRatingMapper,
    PredictionPublicationEventStatus,
    PublisherResultStatus,
    SQLiteAtomicPredictionPublicationRepository,
)
from app.publication_quality_gate import (
    OfficialPublicationQualityGate,
    OfficialQualityGatePolicy,
    SQLiteQualityGateEvaluationRepository,
)
from app.quality_gate import QualityGateStatus
from app.risk_management import (
    RiskAssessmentDecision,
    RiskProductScope,
    StakeBand,
    StakeRecommendation,
    StakeStars,
)
from tests.test_official_prediction_orchestration import (
    exposure,
    prediction,
    publication,
    request,
    risk,
)


NOW = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)


def stake(
    percentage: str = "0.02",
    *,
    final_stake: str = "20.00",
) -> StakeRecommendation:
    value = Decimal(percentage)
    stars = (
        StakeStars.THREE
        if value >= Decimal("0.03")
        else StakeStars.TWO
        if value >= Decimal("0.02")
        else StakeStars.ONE
    )
    band = (
        StakeBand.MAXIMUM
        if stars is StakeStars.THREE
        else StakeBand.STANDARD
        if stars is StakeStars.TWO
        else StakeBand.MINIMUM
    )
    amount = Decimal(final_stake)
    return StakeRecommendation(
        band=band,
        unquantized_stake=amount,
        final_stake=amount,
        internal_stake_percentage=value,
        public_stars=stars,
        currency="EUR",
        currency_quantum=Decimal("0.01"),
    )


def approval(
    *,
    market: str = "MATCH_WINNER",
    selection: str = "HOME",
    line: Decimal | None = None,
    odds: Decimal = Decimal("1.80"),
    expected_value: Decimal = Decimal("0.080"),
) -> ApprovedOfficialPredictionPublication:
    prediction_fact = prediction(
        market=market,
        selection=selection,
        market_line=line,
        decimal_odds=odds,
        expected_value=expected_value,
    )
    assembly_request = request(
        prediction=prediction_fact,
        risk_evaluations=(risk(market=market, selection=selection, market_line=line),),
        exposure_evaluations=(
            exposure(market=market, selection=selection, market_line=line),
        ),
    )
    assembled = OfficialPredictionCandidateAssembler().assemble(
        assembly_request,
        publication(),
    )
    gate = OfficialPublicationQualityGate(OfficialQualityGatePolicy())
    evaluation = gate.evaluate(assembled.gate_candidate)
    candidate_fingerprint = OfficialCandidateFingerprint().generate(assembled)
    return ApprovedOfficialPredictionPublication(
        orchestration_id="official-publication-approval-test",
        assembly=assembled,
        candidate_fingerprint=candidate_fingerprint,
        quality_gate_evaluation=evaluation,
        approval_status=QualityGateStatus.APPROVED,
        evaluated_at=NOW,
        dry_run=False,
    )


def public_facts(
    approved: ApprovedOfficialPredictionPublication,
    **changes,
) -> OfficialPredictionPublicFacts:
    values = {
        "prediction_id": approved.assembly.prediction_id,
        "match_id": approved.assembly.match_id,
        "orchestration_id": approved.orchestration_id,
        "gate_evaluation_id": approved.quality_gate_evaluation.evaluation_id,
        "candidate_fingerprint": approved.candidate_fingerprint,
        "model_version": approved.assembly.gate_candidate.model_version,
        "policy_version": approved.quality_gate_evaluation.policy_version,
        "competition": "Premier League",
        "home_team": "Home FC",
        "away_team": "Away FC",
        "bankroll_scope": RiskProductScope.OFFICIAL,
        "risk_decision": RiskAssessmentDecision.ELIGIBLE,
        "stake_recommendation": stake(),
        "reasoning": ApprovedPublicReasoning((
            "Recent form supports the selected side.",
            "The approved home and away strength comparison supports this market.",
        )),
    }
    values.update(changes)
    return OfficialPredictionPublicFacts(**values)


def message_input(
    approved: ApprovedOfficialPredictionPublication,
    facts: OfficialPredictionPublicFacts | None = None,
) -> OfficialPredictionMessageInput:
    return OfficialPredictionMessageInput(
        approved,
        facts or public_facts(approved),
        OfficialPredictionDestination(RiskProductScope.OFFICIAL, "@official"),
    )


class OfficialMessageBuilderTests(unittest.TestCase):
    def setUp(self):
        self.builder = OfficialPredictionMessageBuilder(
            OfficialPredictionMessagePolicy()
        )

    def render(self, **approval_changes):
        approved = approval(**approval_changes)
        return self.builder.build(message_input(approved))

    def test_supported_market_formatting(self):
        cases = (
            ({}, "Home FC to win"),
            ({"selection": "DRAW"}, "Draw"),
            ({"selection": "AWAY"}, "Away FC to win"),
            ({"market": "DOUBLE_CHANCE", "selection": "HOME OR DRAW"}, "Home FC or draw"),
            ({"market": "DOUBLE_CHANCE", "selection": "AWAY OR DRAW"}, "Away FC or draw"),
            ({"market": "DOUBLE_CHANCE", "selection": "HOME OR AWAY"}, "Home FC or Away FC"),
            ({"market": "TOTALS", "selection": "OVER", "line": Decimal("2.5")}, "Over 2.5 goals"),
            ({"market": "TOTALS", "selection": "UNDER", "line": Decimal("2.5")}, "Under 2.5 goals"),
            ({"market": "BTTS", "selection": "YES"}, "Both teams to score — Yes"),
            ({"market": "BTTS", "selection": "NO"}, "Both teams to score — No"),
        )
        for changes, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, self.render(**changes).rendered_text)

    def test_correct_score_unsupported_and_inconsistent_selection_rejected(self):
        approved = approval()
        for changes in (
            {"market": "CORRECT_SCORE", "selection": "2-1"},
            {"market": "CORNERS", "selection": "OVER"},
            {"market": "MATCH_WINNER", "selection": "YES"},
        ):
            candidate = replace(approved.assembly.gate_candidate, **changes)
            broken = replace(
                approved,
                assembly=replace(approved.assembly, gate_candidate=candidate),
            )
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.builder.build(message_input(broken, public_facts(broken)))

    def test_calibrated_probability_odds_and_deterministic_formatting(self):
        value = self.render(odds=Decimal("1.800"))

        self.assertIn("Model probability: <b>60%</b>", value.rendered_text)
        self.assertNotIn("62%", value.rendered_text)
        self.assertIn("Odds: <b>1.80</b>", value.rendered_text)
        self.assertEqual(value.approved_odds, Decimal("1.800"))
        self.assertEqual(value.calibrated_probability, Decimal("0.60"))

    def test_odds_below_official_minimum_rejected(self):
        approved = approval()
        candidate = replace(
            approved.assembly.gate_candidate,
            decimal_odds=Decimal("1.59"),
        )
        broken = replace(
            approved,
            assembly=replace(approved.assembly, gate_candidate=candidate),
        )
        with self.assertRaises(ValueError):
            self.builder.build(message_input(broken, public_facts(broken)))

    def test_stake_star_mapping_and_reduced_stake_never_rounds_up(self):
        mapper = OfficialStakeRatingMapper(
            OfficialPredictionMessagePolicy().stake_rating
        )
        cases = (
            ("0.01", RiskAssessmentDecision.ELIGIBLE, "★☆☆"),
            ("0.02", RiskAssessmentDecision.ELIGIBLE, "★★☆"),
            ("0.03", RiskAssessmentDecision.ELIGIBLE, "★★★"),
            ("0.019", RiskAssessmentDecision.REDUCED_STAKE, "★☆☆"),
            ("0.029", RiskAssessmentDecision.REDUCED_STAKE, "★★☆"),
        )
        for percentage, decision, expected in cases:
            with self.subTest(percentage=percentage):
                self.assertEqual(
                    mapper.map(stake(percentage), decision).rendered,
                    expected,
                )
        with self.assertRaises(ValueError):
            mapper.map(stake("0", final_stake="0"), RiskAssessmentDecision.INELIGIBLE)

    def test_html_escaping_reasoning_order_and_no_internal_values(self):
        approved = approval()
        facts = public_facts(
            approved,
            competition="League <Admin>",
            home_team="Home & Co",
            reasoning=ApprovedPublicReasoning((
                "First <fact>.",
                "Second & final fact.",
            )),
        )
        payload = self.builder.build(message_input(approved, facts))

        self.assertIn("League &lt;Admin&gt;", payload.rendered_text)
        self.assertIn("Home &amp; Co", payload.rendered_text)
        self.assertLess(
            payload.rendered_text.index("First &lt;fact&gt;"),
            payload.rendered_text.index("Second &amp; final fact"),
        )
        for internal in ("expected value", "brier", "calibration", "stake percentage"):
            self.assertNotIn(internal, payload.rendered_text.casefold())

    def test_missing_unsafe_and_invented_reasoning_are_rejected(self):
        approved = approval()
        for reasoning in (
            ApprovedPublicReasoning(()),
            ApprovedPublicReasoning(("This is a guaranteed winner.",)),
            ApprovedPublicReasoning(("The exact score will be 2-1.",)),
            ApprovedPublicReasoning(("Raw probability is 62%.",)),
            ApprovedPublicReasoning(("Read more at https://bookmaker.test.",)),
            ApprovedPublicReasoning(("Fact.",) * 5),
            ApprovedPublicReasoning(
                ("Approved fact.",),
                "Expected score 2-1.",
            ),
        ):
            with self.subTest(reasoning=reasoning), self.assertRaises(ValueError):
                self.builder.build(
                    message_input(
                        approved,
                        public_facts(approved, reasoning=reasoning),
                    )
                )

        with self.assertRaises(ValueError):
            self.builder.build(message_input(
                approved,
                public_facts(approved, competition="https://sponsor.test"),
            ))

    def test_message_length_determinism_and_fingerprint_materiality(self):
        approved = approval()
        first = self.builder.build(message_input(approved))
        second = self.builder.build(message_input(approved))
        self.assertEqual(first, second)

        changed = self.builder.build(message_input(
            approved,
            public_facts(
                approved,
                reasoning=ApprovedPublicReasoning(("A different approved fact.",)),
            ),
        ))
        self.assertNotEqual(first.message_fingerprint, changed.message_fingerprint)
        later = self.builder.build(message_input(replace(
            approved,
            evaluated_at=approved.evaluated_at + timedelta(seconds=1),
        )))
        self.assertNotEqual(first.message_fingerprint, later.message_fingerprint)

        short = OfficialPredictionMessageBuilder(
            OfficialPredictionMessagePolicy(maximum_message_length=100)
        )
        with self.assertRaises(ValueError):
            short.build(message_input(approved))


class FactsProvider:
    def __init__(self, value=None, transform=None):
        self.value = value
        self.transform = transform

    def get(self, approved):
        if self.transform is not None:
            return self.transform(approved)
        return self.value


class Clock:
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1
        return NOW + timedelta(seconds=self.count)


class Telegram:
    def __init__(self, *, error=None, publications=None):
        self.error = error
        self.publications = publications
        self.calls = []

    async def send_message(self, chat_id, text, parse_mode=None):
        if self.publications is not None:
            latest = self.publications.latest("prediction-1", "OFFICIAL")
            if latest is None or latest.status is not PredictionPublicationEventStatus.CLAIMED:
                raise AssertionError("Atomic claim must exist before Telegram send.")
        self.calls.append((chat_id, text, parse_mode))
        if self.error is not None:
            raise self.error
        return 777


class FailingClaimRepository:
    def begin_attempt(self, payload, attempted_at):
        raise ValueError("claim unavailable")

    def latest(self, prediction_id, destination_scope):
        return None

    def append_terminal(self, *args, **kwargs):
        raise AssertionError("No terminal event expected")


class FailingPublishedWriter:
    def save_published(self, prediction):
        raise ValueError("published reference unavailable")


class OfficialPublisherAdapterTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.approved = approval()
        SQLiteQualityGateEvaluationRepository(self.database).append(
            self.approved.quality_gate_evaluation
        )
        self.publications = SQLiteAtomicPredictionPublicationRepository(
            self.database,
            migrate=False,
        )
        self.telegram = Telegram(publications=self.publications)
        self.provider = FactsProvider(public_facts(self.approved))

    def tearDown(self):
        self.database.close()

    def adapter(
        self,
        *,
        provider=None,
        telegram=None,
        publications=None,
        writer=None,
        destination=None,
    ):
        return OfficialPredictionPublisherAdapter(
            messages=OfficialPredictionMessageBuilder(
                OfficialPredictionMessagePolicy()
            ),
            facts=provider or self.provider,
            publications=publications or self.publications,
            telegram=telegram or self.telegram,
            published_predictions=writer or SQLitePredictionResultRepository(
                self.database,
                migrate=False,
            ),
            destination=destination or OfficialPredictionDestination(
                RiskProductScope.OFFICIAL,
                "@official",
            ),
            clock=Clock(),
        )

    def publish(self, approved=None, **changes):
        return asyncio.run(self.adapter(**changes).publish(approved or self.approved))

    def test_approval_identity_mismatches_fail_closed_without_send(self):
        cases = (
            replace(self.approved, approval_status=QualityGateStatus.REJECTED),
            replace(self.approved, approval_status=QualityGateStatus.REVIEW_REQUIRED),
            replace(self.approved, dry_run=True),
            replace(self.approved, candidate_fingerprint="wrong"),
        )
        for value in cases:
            with self.subTest(value=value):
                result = self.publish(value)
                self.assertEqual(result.status, PublisherResultStatus.RETRYABLE_FAILURE)
        self.assertEqual(self.telegram.calls, [])

    def test_public_fact_identity_model_policy_and_scope_mismatches_block(self):
        changes = (
            {"prediction_id": "other"},
            {"match_id": "999"},
            {"gate_evaluation_id": "other-gate"},
            {"orchestration_id": "other-orchestration"},
            {"candidate_fingerprint": "other-fingerprint"},
            {"model_version": "other-model"},
            {"policy_version": "other-policy"},
            {"bankroll_scope": RiskProductScope.COMBO},
        )
        for change in changes:
            with self.subTest(change=change):
                provider = FactsProvider(public_facts(self.approved, **change))
                result = self.publish(provider=provider)
                self.assertEqual(result.status, PublisherResultStatus.RETRYABLE_FAILURE)
        self.assertEqual(self.telegram.calls, [])

    def test_non_official_or_missing_destination_is_rejected(self):
        with self.assertRaises(ValueError):
            OfficialPredictionDestination(RiskProductScope.COMBO, "@combo")
        with self.assertRaises(ValueError):
            OfficialPredictionDestination(RiskProductScope.OFFICIAL, "")

    def test_claim_precedes_send_and_confirmed_send_publishes(self):
        result = self.publish()

        self.assertEqual(result.status, PublisherResultStatus.PUBLISHED)
        self.assertEqual(len(self.telegram.calls), 1)
        history = self.publications.history("prediction-1")
        self.assertEqual(
            tuple(item.status for item in history),
            (
                PredictionPublicationEventStatus.CLAIMED,
                PredictionPublicationEventStatus.PUBLISHED,
            ),
        )
        self.assertIsNotNone(
            SQLitePredictionResultRepository(
                self.database,
                migrate=False,
            ).get_published("prediction-1")
        )

    def test_identical_repeat_is_duplicate_and_message_fingerprint_stable(self):
        first = self.publish()
        second = self.publish()

        self.assertEqual(first.status, PublisherResultStatus.PUBLISHED)
        self.assertEqual(second.status, PublisherResultStatus.DUPLICATE_BLOCKED)
        self.assertEqual(len(self.telegram.calls), 1)
        history = self.publications.history("prediction-1")
        fingerprints = {item.payload.message_fingerprint for item in history}
        self.assertEqual(len(fingerprints), 1)
        self.assertEqual(len(history), 2)

    def test_active_claim_is_duplicate_blocked_without_send(self):
        payload = OfficialPredictionMessageBuilder(
            OfficialPredictionMessagePolicy()
        ).build(message_input(self.approved))
        self.publications.begin_attempt(payload, NOW)

        result = self.publish()

        self.assertEqual(result.status, PublisherResultStatus.DUPLICATE_BLOCKED)
        self.assertEqual(self.telegram.calls, [])
        self.assertEqual(len(self.publications.history("prediction-1")), 1)

    def test_material_message_change_cannot_edit_published_prediction(self):
        first = self.publish()
        changed_facts = public_facts(
            self.approved,
            reasoning=ApprovedPublicReasoning(("Changed approved public evidence.",)),
        )
        second = self.publish(provider=FactsProvider(changed_facts))

        self.assertEqual(first.status, PublisherResultStatus.PUBLISHED)
        self.assertEqual(second.status, PublisherResultStatus.DUPLICATE_BLOCKED)
        self.assertEqual(len(self.telegram.calls), 1)

    def test_confirmed_failure_is_retryable_and_next_attempt_can_send(self):
        failed_telegram = Telegram(
            error=ConfirmedTelegramDeliveryError("not delivered"),
            publications=self.publications,
        )
        first = self.publish(telegram=failed_telegram)
        second = self.publish()

        self.assertEqual(first.status, PublisherResultStatus.RETRYABLE_FAILURE)
        self.assertEqual(second.status, PublisherResultStatus.PUBLISHED)
        history = self.publications.history("prediction-1")
        self.assertEqual([item.attempt_number for item in history], [1, 1, 2, 2])

    def test_unknown_delivery_is_indeterminate_and_never_resent(self):
        unknown = Telegram(
            error=RuntimeError("unknown after send"),
            publications=self.publications,
        )
        first = self.publish(telegram=unknown)
        second = self.publish()

        self.assertEqual(
            first.status,
            PublisherResultStatus.INDETERMINATE_FAILURE,
        )
        self.assertEqual(
            second.status,
            PublisherResultStatus.INDETERMINATE_FAILURE,
        )
        self.assertEqual(len(unknown.calls), 1)
        self.assertEqual(self.telegram.calls, [])

    def test_repository_failure_before_claim_prevents_send(self):
        result = self.publish(publications=FailingClaimRepository())
        self.assertEqual(result.status, PublisherResultStatus.RETRYABLE_FAILURE)
        self.assertEqual(self.telegram.calls, [])

    def test_persistence_failure_after_send_is_indeterminate(self):
        result = self.publish(writer=FailingPublishedWriter())
        self.assertEqual(
            result.status,
            PublisherResultStatus.INDETERMINATE_FAILURE,
        )
        self.assertEqual(len(self.telegram.calls), 1)
        self.assertEqual(
            self.publications.latest("prediction-1", "OFFICIAL").status,
            PredictionPublicationEventStatus.INDETERMINATE,
        )

    def test_payload_and_fingerprint_exclude_destination_and_credentials(self):
        self.publish()
        event = self.publications.latest("prediction-1", "OFFICIAL")
        self.assertNotIn("@official", event.payload.rendered_text)
        self.assertNotIn("@official", event.payload.message_fingerprint)
        row = self.database.connection.execute(
            "SELECT payload_snapshot FROM official_prediction_publication_events LIMIT 1"
        ).fetchone()[0]
        self.assertNotIn("@official", row)
        self.assertNotIn("token", row.casefold())


class PublicationMigrationAndCompositionTests(unittest.TestCase):
    def test_fresh_latest_schema_append_only_and_v11_upgrade(self):
        database = Database(":memory:")
        MigrationManager(database.connection).migrate()
        versions = tuple(
            row[0]
            for row in database.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        self.assertEqual(versions, tuple(range(1, 32)))
        approved = approval()
        SQLiteQualityGateEvaluationRepository(database).append(
            approved.quality_gate_evaluation
        )
        payload = OfficialPredictionMessageBuilder(
            OfficialPredictionMessagePolicy()
        ).build(message_input(approved))
        SQLiteAtomicPredictionPublicationRepository(database).begin_attempt(
            payload,
            NOW,
        )
        for statement in (
            "UPDATE official_prediction_publication_events SET status='FAILED'",
            "DELETE FROM official_prediction_publication_events",
        ):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                database.connection.execute(statement)
        database.close()

        upgrade = Database(":memory:")
        upgrade.connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for migration in MIGRATIONS[:11]:
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
                31,
        )
        upgrade.close()

    def test_production_composition_executes_final_callable_boundary(self):
        database = Database(":memory:")
        telegram = Telegram()
        provider = FactsProvider(
            transform=lambda approved: public_facts(approved)
        )
        service = build_official_prediction_orchestration_service(
            database,
            telegram=telegram,
            public_facts=provider,
            destination=OfficialPredictionDestination(
                RiskProductScope.OFFICIAL,
                "@official",
            ),
            clock=Clock(),
        )
        self.assertEqual(telegram.calls, [])
        self.assertEqual(
            database.connection.execute(
                "SELECT COUNT(*) FROM official_prediction_publication_events"
            ).fetchone()[0],
            0,
        )

        outcome = asyncio.run(
            service.prepare_and_publish_official_prediction(request())
        )

        self.assertEqual(outcome.final_status.value, "PUBLISHED")
        self.assertEqual(len(telegram.calls), 1)
        database.close()


if __name__ == "__main__":
    unittest.main()
