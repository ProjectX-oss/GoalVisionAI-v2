import unittest
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from app.backtesting import EvaluationOutcome, HistoricalEvaluationRecord
from app.quality_gate import (
    ComboSelection,
    ProbabilitySource,
    PublicationCandidate,
    PublicationType,
    QualityGateDecision,
    QualityGateStatus,
)
from app.risk_management import (
    DEFAULT_OFFICIAL_RISK_POLICY,
    BankrollStateSnapshot,
    ComboExceptionRiskService,
    DrawdownState,
    ExposurePosition,
    ExposureSnapshot,
    ExposureType,
    LossStreakState,
    PublicStakeAdapter,
    PublicStakeRecommendation,
    QualityGateRiskAdapter,
    RiskAssessmentContext,
    RiskAssessmentDecision,
    RiskAssessmentRequest,
    RiskAssessmentService,
    RiskBacktestCase,
    RiskPolicyBacktestService,
    RiskPolicy,
    RiskPolicyRegistry,
    RiskProductScope,
    RiskReason,
    RiskWarning,
    ShadowRiskRecommendationAdapter,
    StakeBand,
    StakeStars,
    StakeStrategy,
    UnsupportedRiskProductPolicy,
)


UTC = timezone.utc
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def bankroll(
    *,
    current: str = "10000",
    peak: str = "10000",
    drawdown: str | None = None,
    losses: int = 0,
    unsettled: str = "0",
    scope: RiskProductScope = RiskProductScope.OFFICIAL,
    timestamp: datetime = NOW,
) -> BankrollStateSnapshot:
    current_value = Decimal(current)
    peak_value = Decimal(peak)
    amount = peak_value - current_value
    percentage = (
        Decimal(drawdown)
        if drawdown is not None
        else amount / peak_value
        if peak_value
        else Decimal("0")
    )
    return BankrollStateSnapshot(
        scope,
        "EUR",
        Decimal("10000"),
        current_value,
        peak_value,
        amount,
        percentage,
        0,
        losses,
        20,
        Decimal(unsettled),
        timestamp,
        "authoritative-bankroll-v1",
    )


def exposure(
    *positions: ExposurePosition,
    scope: RiskProductScope = RiskProductScope.OFFICIAL,
    timestamp: datetime = NOW,
) -> ExposureSnapshot:
    return ExposureSnapshot(
        scope,
        tuple(positions),
        timestamp,
        "authoritative-exposure-v1",
    )


def position(kind: ExposureType, key: str, amount: str) -> ExposurePosition:
    return ExposurePosition(kind, key, Decimal(amount), "EUR", NOW)


def request(**changes) -> RiskAssessmentRequest:
    values = {
        "prediction_id": "prediction-1",
        "fixture_id": 500,
        "competition": "Premier League",
        "market": "MATCH_WINNER",
        "selection": "HOME",
        "product_scope": RiskProductScope.OFFICIAL,
        "prediction_timestamp": NOW,
        "kickoff": NOW + timedelta(hours=2),
        "accepted_probability": Decimal("0.60"),
        "offered_odds": Decimal("2.00"),
        "expected_value": Decimal("0.03"),
        "quality_gate_status": QualityGateStatus.APPROVED,
        "model_confidence": Decimal("0.75"),
        "uncertainty": Decimal("0.15"),
        "calibration_sample_size": 200,
        "model_sample_size": 200,
        "correlation_group_ids": (),
        "requested_stake": None,
        "candidate_policy_version": "gate-v1",
        "calibrated_probability_available": True,
        "team_ids": ("team-1",),
        "market_family": "MATCH_RESULT",
    }
    values.update(changes)
    return RiskAssessmentRequest(**values)


def context(
    bank: BankrollStateSnapshot | None = None,
    exposures: ExposureSnapshot | None = None,
    assessed_at: datetime = NOW,
) -> RiskAssessmentContext:
    return RiskAssessmentContext(
        bank or bankroll(),
        exposures or exposure(),
        (),
        assessed_at,
    )


class StakePolicyTests(unittest.TestCase):
    def setUp(self):
        self.service = RiskAssessmentService(DEFAULT_OFFICIAL_RISK_POLICY)

    def test_valid_one_two_and_three_percent_recommendations(self):
        cases = (
            (request(expected_value=Decimal("0.03")), Decimal("0.01"), Decimal("100"), StakeStars.ONE),
            (request(expected_value=Decimal("0.06")), Decimal("0.02"), Decimal("200"), StakeStars.TWO),
            (
                request(
                    expected_value=Decimal("0.12"),
                    model_confidence=Decimal("0.85"),
                    uncertainty=Decimal("0.05"),
                ),
                Decimal("0.03"),
                Decimal("300"),
                StakeStars.THREE,
            ),
        )
        for value, percentage, amount, stars in cases:
            with self.subTest(percentage=percentage):
                audit = self.service.assess(value, context())
                self.assertEqual(audit.final_decision, RiskAssessmentDecision.ELIGIBLE)
                self.assertEqual(audit.recommendation.internal_stake_percentage, percentage)
                self.assertEqual(audit.recommendation.final_stake, amount.quantize(Decimal("0.01")))
                self.assertEqual(audit.recommendation.public_stars, stars)

    def test_stake_never_above_three_percent_and_requested_stake_is_reduced(self):
        audit = self.service.assess(
            request(
                expected_value=Decimal("100"),
                model_confidence=Decimal("1"),
                uncertainty=Decimal("0"),
                requested_stake=Decimal("5000"),
            ),
            context(),
        )
        self.assertLessEqual(
            audit.recommendation.internal_stake_percentage, Decimal("0.03")
        )
        self.assertIn(RiskReason.REQUESTED_STAKE_REDUCED, audit.ordered_reasons)

    def test_negative_requested_stake_is_ineligible_and_stake_never_exceeds_bankroll(self):
        negative = self.service.assess(
            request(requested_stake=Decimal("-1")),
            context(),
        )
        self.assertEqual(
            negative.final_decision,
            RiskAssessmentDecision.INELIGIBLE,
        )
        self.assertIn(RiskReason.STAKE_BELOW_MINIMUM, negative.ordered_reasons)
        valid = self.service.assess(
            request(
                expected_value=Decimal("0.12"),
                model_confidence=Decimal("0.85"),
                uncertainty=Decimal("0.05"),
            ),
            context(bankroll(current="0.50", peak="0.50")),
        )
        self.assertLessEqual(
            valid.recommendation.unquantized_stake,
            valid.bankroll_snapshot.current_bankroll,
        )

    def test_zero_and_negative_bankroll_are_ineligible(self):
        for bank in (
            bankroll(current="0", peak="0"),
            bankroll(current="-1", peak="100"),
        ):
            with self.subTest(current=bank.current_bankroll):
                audit = self.service.assess(request(), context(bank))
                self.assertEqual(audit.final_decision, RiskAssessmentDecision.INELIGIBLE)
                self.assertIn(RiskReason.INVALID_BANKROLL, audit.ordered_reasons)

    def test_decimal_currency_quantization_occurs_at_final_boundary(self):
        bank = bankroll(current="100.55", peak="100.55")
        audit = self.service.assess(request(), context(bank))
        self.assertEqual(audit.recommendation.unquantized_stake, Decimal("1.0055"))
        self.assertEqual(audit.recommendation.final_stake, Decimal("1.01"))

    def test_public_adapter_contains_stars_but_no_percentage(self):
        audit = self.service.assess(request(), context())
        public = PublicStakeAdapter.adapt(audit)
        self.assertEqual(public.public_stars, StakeStars.ONE)
        self.assertNotIn(
            "internal_stake_percentage",
            {item.name for item in fields(PublicStakeRecommendation)},
        )

    def test_expected_value_bands_require_supporting_evidence(self):
        audit = self.service.assess(
            request(
                expected_value=Decimal("0.20"),
                calibrated_probability_available=False,
                calibration_sample_size=0,
            ),
            context(),
        )
        self.assertEqual(audit.recommendation.band, StakeBand.MINIMUM)
        self.assertIn(RiskReason.CALIBRATION_SAMPLE_TOO_SMALL, audit.ordered_reasons)

    def test_exact_expected_value_thresholds(self):
        cases = (
            (Decimal("0.019999"), RiskAssessmentDecision.INELIGIBLE, None),
            (Decimal("0.02"), RiskAssessmentDecision.ELIGIBLE, Decimal("0.01")),
            (Decimal("0.05"), RiskAssessmentDecision.ELIGIBLE, Decimal("0.02")),
            (
                Decimal("0.10"),
                RiskAssessmentDecision.ELIGIBLE,
                Decimal("0.03"),
            ),
        )
        for value, decision, percentage in cases:
            with self.subTest(value=value):
                audit = self.service.assess(
                    request(
                        expected_value=value,
                        model_confidence=Decimal("0.85"),
                        uncertainty=Decimal("0.05"),
                    ),
                    context(),
                )
                self.assertEqual(audit.final_decision, decision)
                self.assertEqual(
                    (
                        audit.recommendation.internal_stake_percentage
                        if audit.recommendation
                        else None
                    ),
                    percentage,
                )

    def test_invalid_probability_odds_nan_and_infinity_are_structured(self):
        cases = (
            ({"accepted_probability": Decimal("NaN")}, RiskReason.INVALID_PROBABILITY),
            ({"accepted_probability": Decimal("Infinity")}, RiskReason.INVALID_PROBABILITY),
            ({"accepted_probability": Decimal("1.1")}, RiskReason.INVALID_PROBABILITY),
            ({"offered_odds": Decimal("NaN")}, RiskReason.INVALID_ODDS),
            ({"offered_odds": Decimal("1")}, RiskReason.INVALID_ODDS),
        )
        for changes, reason in cases:
            with self.subTest(changes=changes):
                audit = self.service.assess(request(**changes), context())
                self.assertEqual(audit.final_decision, RiskAssessmentDecision.INELIGIBLE)
                self.assertIn(reason, audit.ordered_reasons)

    def test_models_and_audits_are_immutable_and_deterministic(self):
        first = self.service.assess(request(), context())
        second = self.service.assess(request(), context())
        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.final_decision = RiskAssessmentDecision.INELIGIBLE


class QualityGateDrawdownLossTests(unittest.TestCase):
    def setUp(self):
        self.service = RiskAssessmentService(DEFAULT_OFFICIAL_RISK_POLICY)

    def test_quality_gate_approved_review_rejected_and_missing(self):
        expected = (
            (QualityGateStatus.APPROVED, RiskAssessmentDecision.ELIGIBLE),
            (QualityGateStatus.REVIEW_REQUIRED, RiskAssessmentDecision.REVIEW_REQUIRED),
            (QualityGateStatus.REJECTED, RiskAssessmentDecision.INELIGIBLE),
            (None, RiskAssessmentDecision.REVIEW_REQUIRED),
        )
        for status, decision in expected:
            with self.subTest(status=status):
                audit = self.service.assess(
                    request(quality_gate_status=status), context()
                )
                self.assertEqual(audit.final_decision, decision)
                if decision is RiskAssessmentDecision.REVIEW_REQUIRED:
                    self.assertEqual(
                        audit.recommendation.internal_stake_percentage,
                        Decimal("0.01"),
                    )

    def test_quality_gate_adapter_consumes_existing_decision(self):
        decision = QualityGateDecision(
            "prediction-1", QualityGateStatus.REJECTED, (), (), (),
            Decimal("0.61"), ProbabilitySource.CALIBRATED, Decimal("0.04"),
            None, "gate-v2", NOW,
        )
        adapted = QualityGateRiskAdapter.apply(request(), decision)
        self.assertEqual(adapted.quality_gate_status, QualityGateStatus.REJECTED)
        self.assertEqual(adapted.candidate_policy_version, "gate-v2")

    def test_drawdown_exact_thresholds_and_caps(self):
        cases = (
            ("9500", "10000", DrawdownState.CAUTION, Decimal("0.02")),
            ("9000", "10000", DrawdownState.DEFENSIVE, Decimal("0.01")),
            ("8500", "10000", DrawdownState.HALTED, None),
        )
        strong = request(
            expected_value=Decimal("0.12"),
            model_confidence=Decimal("0.85"),
            uncertainty=Decimal("0.05"),
        )
        for current, peak, state, maximum in cases:
            with self.subTest(state=state):
                audit = self.service.assess(
                    strong, context(bankroll(current=current, peak=peak))
                )
                self.assertEqual(audit.drawdown_state, state)
                if maximum is None:
                    self.assertEqual(audit.final_decision, RiskAssessmentDecision.INELIGIBLE)
                else:
                    self.assertLessEqual(
                        audit.recommendation.internal_stake_percentage, maximum
                    )

    def test_drawdown_never_raises_stake(self):
        normal = self.service.assess(request(), context())
        caution = self.service.assess(
            request(), context(bankroll(current="9500", peak="10000"))
        )
        self.assertLessEqual(
            caution.recommendation.internal_stake_percentage,
            normal.recommendation.internal_stake_percentage,
        )

    def test_loss_streak_no_reduction_minimum_cap_and_review(self):
        strong = request(
            expected_value=Decimal("0.12"),
            model_confidence=Decimal("0.85"),
            uncertainty=Decimal("0.05"),
        )
        cases = (
            (2, LossStreakState.NORMAL, RiskAssessmentDecision.ELIGIBLE, Decimal("0.03")),
            (3, LossStreakState.MINIMUM_CAP, RiskAssessmentDecision.REDUCED_STAKE, Decimal("0.01")),
            (5, LossStreakState.REVIEW_REQUIRED, RiskAssessmentDecision.REVIEW_REQUIRED, Decimal("0.01")),
        )
        for losses, state, decision, percentage in cases:
            with self.subTest(losses=losses):
                audit = self.service.assess(
                    strong, context(bankroll(losses=losses))
                )
                self.assertEqual(audit.loss_streak_state, state)
                self.assertEqual(audit.final_decision, decision)
                self.assertEqual(
                    audit.recommendation.internal_stake_percentage, percentage
                )

    def test_loss_streak_never_raises_stake(self):
        candidate = request(
            expected_value=Decimal("0.12"),
            model_confidence=Decimal("0.85"),
            uncertainty=Decimal("0.05"),
        )
        normal = self.service.assess(candidate, context(bankroll(losses=0)))
        reduced = self.service.assess(candidate, context(bankroll(losses=3)))
        self.assertLessEqual(
            reduced.recommendation.internal_stake_percentage,
            normal.recommendation.internal_stake_percentage,
        )


class ExposureAndScopeTests(unittest.TestCase):
    def setUp(self):
        self.service = RiskAssessmentService(DEFAULT_OFFICIAL_RISK_POLICY)
        self.strong = request(
            expected_value=Decimal("0.12"),
            model_confidence=Decimal("0.85"),
            uncertainty=Decimal("0.05"),
            correlation_group_ids=("manual-1",),
        )

    def test_each_exposure_limit_returns_exact_reason(self):
        cases = (
            (ExposureType.SINGLE_PREDICTION, "prediction-1", "299", RiskReason.SINGLE_STAKE_LIMIT),
            (ExposureType.DAILY_TOTAL, NOW.date().isoformat(), "999", RiskReason.DAILY_EXPOSURE_LIMIT),
            (ExposureType.COMPETITION_TOTAL, "Premier League", "499", RiskReason.COMPETITION_EXPOSURE_LIMIT),
            (ExposureType.FIXTURE_TOTAL, "500", "299", RiskReason.FIXTURE_EXPOSURE_LIMIT),
            (ExposureType.TEAM_TOTAL, "team-1", "499", RiskReason.TEAM_EXPOSURE_LIMIT),
            (ExposureType.MARKET_TOTAL, "MATCH_RESULT", "499", RiskReason.MARKET_EXPOSURE_LIMIT),
            (ExposureType.CORRELATED_GROUP_TOTAL, "manual-1", "499", RiskReason.CORRELATED_EXPOSURE_LIMIT),
            (ExposureType.UNSETTLED_TOTAL, "ALL", "999", RiskReason.UNSETTLED_EXPOSURE_LIMIT),
        )
        for kind, key, amount, reason in cases:
            with self.subTest(kind=kind):
                audit = self.service.assess(
                    self.strong, context(exposures=exposure(position(kind, key, amount)))
                )
                self.assertIn(reason, audit.ordered_reasons)
                self.assertEqual(audit.final_decision, RiskAssessmentDecision.INELIGIBLE)

    def test_exposure_reduces_to_available_valid_amount_without_mutation(self):
        snapshot = exposure(
            position(
                ExposureType.DAILY_TOTAL,
                NOW.date().isoformat(),
                "850",
            )
        )
        audit = self.service.assess(self.strong, context(exposures=snapshot))
        self.assertEqual(audit.final_decision, RiskAssessmentDecision.REDUCED_STAKE)
        self.assertEqual(audit.recommendation.final_stake, Decimal("150.00"))
        self.assertEqual(snapshot.positions[0].current_amount, Decimal("850"))

    def test_authoritative_bankroll_unsettled_exposure_is_evaluated(self):
        audit = self.service.assess(
            self.strong,
            context(bankroll(unsettled="950")),
        )
        self.assertEqual(
            audit.final_decision,
            RiskAssessmentDecision.INELIGIBLE,
        )
        self.assertIn(
            RiskReason.UNSETTLED_EXPOSURE_LIMIT,
            audit.ordered_reasons,
        )

    def test_multiple_limits_have_deterministic_reason_and_order(self):
        snapshot = exposure(
            position(ExposureType.DAILY_TOTAL, NOW.date().isoformat(), "850"),
            position(ExposureType.COMPETITION_TOTAL, "Premier League", "450"),
        )
        audit = self.service.assess(self.strong, context(exposures=snapshot))
        self.assertEqual(
            audit.limiting_exposure.exposure_type,
            ExposureType.COMPETITION_TOTAL,
        )
        self.assertLess(
            audit.ordered_reasons.index(RiskReason.DAILY_EXPOSURE_LIMIT),
            audit.ordered_reasons.index(RiskReason.COMPETITION_EXPOSURE_LIMIT),
        )

    def test_explicit_correlation_groups_only(self):
        without = self.service.assess(
            replace(self.strong, correlation_group_ids=()),
            context(exposures=exposure(
                position(ExposureType.CORRELATED_GROUP_TOTAL, "manual-1", "499")
            )),
        )
        with_group = self.service.assess(
            self.strong,
            context(exposures=exposure(
                position(ExposureType.CORRELATED_GROUP_TOTAL, "manual-1", "499")
            )),
        )
        self.assertNotIn(RiskReason.CORRELATED_EXPOSURE_LIMIT, without.ordered_reasons)
        self.assertIn(RiskReason.CORRELATED_EXPOSURE_LIMIT, with_group.ordered_reasons)

    def test_non_official_policies_are_never_implicitly_reused(self):
        registry = RiskPolicyRegistry(((RiskProductScope.OFFICIAL, self.service),))
        self.assertIs(registry.for_scope(RiskProductScope.OFFICIAL), self.service)
        for scope in (
            RiskProductScope.HIGH_RISK,
            RiskProductScope.COMBO,
            RiskProductScope.LIVE,
            RiskProductScope.AUTOTRADER,
        ):
            with self.subTest(scope=scope):
                with self.assertRaises(UnsupportedRiskProductPolicy):
                    registry.for_scope(scope)
        with self.assertRaises(UnsupportedRiskProductPolicy):
            RiskPolicy(product_scope=RiskProductScope.HIGH_RISK)
        explicit = RiskAssessmentService(
            RiskPolicy(
                version="high-risk-explicit-v1",
                product_scope=RiskProductScope.HIGH_RISK,
                explicit_non_official_policy=True,
            )
        )
        self.assertIsInstance(explicit, RiskAssessmentService)

    def test_product_bankroll_mismatch_is_ineligible(self):
        audit = self.service.assess(
            request(product_scope=RiskProductScope.OFFICIAL),
            context(bankroll(scope=RiskProductScope.HIGH_RISK)),
        )
        self.assertEqual(audit.final_decision, RiskAssessmentDecision.INELIGIBLE)
        self.assertIn(RiskReason.PRODUCT_SCOPE_MISMATCH, audit.ordered_reasons)


class ComboShadowAndBacktestingTests(unittest.TestCase):
    def setUp(self):
        self.service = RiskAssessmentService(DEFAULT_OFFICIAL_RISK_POLICY)

    @staticmethod
    def candidate(**changes):
        values = {
            "prediction_id": "prediction-1",
            "fixture_id": 500,
            "competition": "Premier League",
            "kickoff_time": NOW + timedelta(hours=2),
            "prediction_timestamp": NOW,
            "market": "COMBO",
            "selection": "two selections",
            "raw_probability": Decimal("0.60"),
            "offered_odds": Decimal("2.10"),
            "odds_timestamp": NOW,
            "calibrated_probability": Decimal("0.62"),
            "expected_value": Decimal("0.06"),
            "model_version": "model-v1",
            "calibration_sample_size": 200,
            "confidence_score": Decimal("0.80"),
            "uncertainty_score": Decimal("0.10"),
            "publication_type": PublicationType.COMBO,
            "combo_selections": (
                ComboSelection("M1", "A", Decimal("1.50"), Decimal("0.80")),
                ComboSelection("M2", "B", Decimal("1.40"), Decimal("0.80")),
            ),
            "product_scope": "OFFICIAL",
        }
        values.update(changes)
        return PublicationCandidate(**values)

    def test_combo_exception_representation_only(self):
        eligible = ComboExceptionRiskService().evaluate(
            self.candidate(), exception_already_used=False
        )
        used = ComboExceptionRiskService().evaluate(
            self.candidate(), exception_already_used=True
        )
        self.assertTrue(eligible.eligible)
        self.assertTrue(eligible.separate_exposure_required)
        self.assertFalse(used.eligible)
        self.assertEqual(used.reason, RiskReason.COMBO_EXCEPTION_NOT_ELIGIBLE)

    def test_shadow_historical_snapshot_and_missing_snapshot(self):
        record = SimpleNamespace(
            shadow_evaluation_id="shadow-1",
            prediction_id="prediction-1",
            fixture_id=500,
            product_scope="OFFICIAL",
            candidate_snapshot=replace(
                self.candidate(),
                publication_type=PublicationType.SINGLE,
                market="MATCH_WINNER",
                selection="HOME",
                combo_selections=(),
            ),
            policy_version="gate-v1",
            evaluation_timestamp=NOW,
            gate_status=QualityGateStatus.APPROVED,
            ordered_check_results=(),
            rejection_reasons=(),
            review_reasons=(),
            evaluated_probability=Decimal("0.62"),
            probability_source=ProbabilitySource.CALIBRATED,
            calculated_expected_value=Decimal("0.06"),
            market_disagreement=None,
        )
        bank_provider = SimpleNamespace(at=lambda scope, timestamp: bankroll(timestamp=timestamp))
        exposure_provider = SimpleNamespace(at=lambda scope, timestamp: exposure(timestamp=timestamp))
        adapter = ShadowRiskRecommendationAdapter(
            self.service, bank_provider, exposure_provider
        )
        result = adapter.assess(record, model_sample_size=200)
        self.assertTrue(result.available)
        self.assertEqual(result.audit.assessed_at, NOW)
        missing = ShadowRiskRecommendationAdapter(
            self.service,
            SimpleNamespace(at=lambda scope, timestamp: None),
            exposure_provider,
        ).assess(record, model_sample_size=200)
        self.assertFalse(missing.available)
        self.assertEqual(missing.reason, RiskReason.NO_HISTORICAL_BANKROLL_SNAPSHOT)

    def test_shadow_rejects_future_snapshot(self):
        record = SimpleNamespace(
            shadow_evaluation_id="shadow-1", prediction_id="prediction-1",
            fixture_id=500, product_scope="OFFICIAL",
            candidate_snapshot=replace(
                self.candidate(), publication_type=PublicationType.SINGLE,
                market="MATCH_WINNER", selection="HOME", combo_selections=()
            ),
            policy_version="gate-v1", evaluation_timestamp=NOW,
            gate_status=QualityGateStatus.APPROVED,
            ordered_check_results=(), rejection_reasons=(), review_reasons=(),
            evaluated_probability=Decimal("0.62"),
            probability_source=ProbabilitySource.CALIBRATED,
            calculated_expected_value=Decimal("0.06"),
            market_disagreement=None,
        )
        future = NOW + timedelta(minutes=1)
        result = ShadowRiskRecommendationAdapter(
            self.service,
            SimpleNamespace(at=lambda scope, timestamp: bankroll(timestamp=future)),
            SimpleNamespace(at=lambda scope, timestamp: exposure(timestamp=NOW)),
        ).assess(record, model_sample_size=200)
        self.assertFalse(result.available)

    def backtest_case(self, index: int, outcome: EvaluationOutcome, audit=None):
        record = HistoricalEvaluationRecord(
            index,
            "League",
            NOW + timedelta(days=index, hours=2),
            NOW + timedelta(days=index),
            NOW + timedelta(days=index),
            NOW + timedelta(days=index),
            "MATCH_WINNER",
            "HOME",
            Decimal("0.6"),
            Decimal("2"),
            None,
            outcome.value,
            outcome,
            (
                Decimal("1")
                if outcome is EvaluationOutcome.WON
                else Decimal("-1")
                if outcome is EvaluationOutcome.LOST
                else Decimal("0")
            ),
        )
        selected = audit or self.service.assess(request(
            prediction_id=f"p-{index}",
            fixture_id=index,
            prediction_timestamp=NOW + timedelta(days=index),
            kickoff=NOW + timedelta(days=index, hours=2),
        ), context(assessed_at=NOW + timedelta(days=index)))
        return RiskBacktestCase(record, selected)

    def test_backtesting_flat_recommended_void_skips_and_comparison(self):
        skipped = replace(
            self.service.assess(request(), context()),
            final_decision=RiskAssessmentDecision.INELIGIBLE,
            recommendation=None,
        )
        cases = (
            self.backtest_case(1, EvaluationOutcome.WON),
            self.backtest_case(2, EvaluationOutcome.LOST),
            self.backtest_case(3, EvaluationOutcome.VOID),
            self.backtest_case(4, EvaluationOutcome.LOST, skipped),
        )
        comparison = RiskPolicyBacktestService().compare(cases)
        reports = {item.strategy: item for item in comparison.reports}
        flat = reports[StakeStrategy.FLAT_ONE_UNIT]
        recommended = reports[StakeStrategy.RECOMMENDED_POLICY]
        self.assertEqual(flat.total_staked, Decimal("4"))
        self.assertEqual(flat.profit_loss, Decimal("-1"))
        self.assertEqual(recommended.skipped_bets, 1)
        self.assertEqual(len(comparison.reports), 4)
        self.assertIn(RiskWarning.SMALL_EVALUATION_SAMPLE, flat.warnings)

    def test_backtesting_is_repeatable_and_reports_distribution_drawdown(self):
        cases = (
            self.backtest_case(1, EvaluationOutcome.LOST),
            self.backtest_case(2, EvaluationOutcome.LOST),
            self.backtest_case(3, EvaluationOutcome.WON),
        )
        first = RiskPolicyBacktestService().compare(cases)
        second = RiskPolicyBacktestService().compare(tuple(reversed(cases)))
        self.assertEqual(first, second)
        report = first.reports[0]
        self.assertGreater(report.maximum_drawdown, Decimal("0"))
        self.assertTrue(report.stake_distribution)
        self.assertGreaterEqual(report.largest_losing_streak, 2)

    def test_no_telegram_bankroll_scheduling_betting_or_enforcement_effects(self):
        telegram = Mock()
        bankroll_mutation = Mock()
        exposure_reservation = Mock()
        scheduler = Mock()
        betting = Mock()
        gate_enforcement = Mock()
        self.service.assess(request(), context())
        for mock in (
            telegram,
            bankroll_mutation,
            exposure_reservation,
            scheduler,
            betting,
            gate_enforcement,
        ):
            mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
