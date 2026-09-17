import socket
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app.bankroll import OfficialBankrollSettlementEngine
from app.calibration import (
    CalibrationFitMetadata,
    CalibrationScope,
    CalibrationTrainingWindow,
)
from app.quality_gate import (
    CheckStatus,
    ComboSelection,
    EvidenceAssessment,
    EvidenceCategory,
    EvidenceStatus,
    ExpectedValueService,
    ExposureLimits,
    InMemoryDuplicatePublicationChecker,
    ProbabilitySource,
    PublicationCandidate,
    PublicationIdentity,
    PublicationQualityGate,
    PublicationType,
    QualityGateCheck,
    QualityGateContext,
    QualityGatePolicy,
    QualityGateStatus,
    RejectionReason,
    ReviewReason,
)


PREDICTION_AT = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
EVALUATED_AT = PREDICTION_AT + timedelta(minutes=10)


def candidate(**changes) -> PublicationCandidate:
    values = {
        "prediction_id": "prediction-1",
        "fixture_id": 1001,
        "competition": "Premier League",
        "kickoff_time": PREDICTION_AT + timedelta(hours=2),
        "prediction_timestamp": PREDICTION_AT,
        "market": "Match Winner",
        "selection": "Home",
        "raw_probability": Decimal("0.60"),
        "calibrated_probability": Decimal("0.62"),
        "offered_odds": Decimal("2.00"),
        "odds_timestamp": PREDICTION_AT + timedelta(minutes=5),
        "reference_odds": Decimal("1.95"),
        "expected_value": None,
        "model_version": "model-v1",
        "calibration_scope": CalibrationScope.global_scope(),
        "calibration_method": "platt",
        "calibration_sample_size": 200,
        "calibration_fit_timestamp": PREDICTION_AT - timedelta(minutes=1),
        "calibration_training_cutoff": PREDICTION_AT - timedelta(days=1),
        "confidence_score": Decimal("0.80"),
        "uncertainty_score": Decimal("0.10"),
    }
    values.update(changes)
    return PublicationCandidate(**values)


def available_evidence() -> tuple[EvidenceAssessment, ...]:
    return tuple(
        EvidenceAssessment(category, EvidenceStatus.AVAILABLE)
        for category in EvidenceCategory
        if category not in {EvidenceCategory.LINEUP, EvidenceCategory.INJURIES}
    )


def context(**changes) -> QualityGateContext:
    values = {
        "evaluation_timestamp": EVALUATED_AT,
        "data_completeness_status": EvidenceStatus.AVAILABLE,
        "data_freshness_status": EvidenceStatus.AVAILABLE,
        "lineup_status": EvidenceStatus.AVAILABLE,
        "injury_data_status": EvidenceStatus.AVAILABLE,
        "market_consensus_probability": Decimal("0.58"),
        "market_disagreement": None,
        "current_exposure": Decimal("0.10"),
        "daily_exposure": Decimal("1.00"),
        "competition_exposure": Decimal("0.50"),
        "correlated_exposure": Decimal("0.25"),
        "sample_size": 500,
        "calibration_sample_size": 200,
        "evidence": available_evidence(),
    }
    values.update(changes)
    return QualityGateContext(**values)


def policy(**changes) -> QualityGatePolicy:
    values = {}
    values.update(changes)
    return QualityGatePolicy(**values)


def gate(
    configured_policy: QualityGatePolicy | None = None,
    active: tuple[PublicationIdentity, ...] = (),
) -> PublicationQualityGate:
    return PublicationQualityGate(
        configured_policy or policy(),
        InMemoryDuplicatePublicationChecker(active),
    )


def evidence_with(
    category: EvidenceCategory,
    status: EvidenceStatus,
) -> tuple[EvidenceAssessment, ...]:
    return tuple(
        replace(item, status=status) if item.category is category else item
        for item in available_evidence()
    )


class ApprovalAndOddsTests(unittest.TestCase):
    def test_valid_single_bet_is_approved(self):
        decision = gate().evaluate(candidate(), context())

        self.assertEqual(decision.status, QualityGateStatus.APPROVED)
        self.assertTrue(decision.automatic_publication_eligible)
        self.assertFalse(decision.is_no_bet)
        self.assertEqual(decision.evaluated_probability, Decimal("0.62"))
        self.assertEqual(decision.probability_source, ProbabilitySource.CALIBRATED)
        self.assertEqual(decision.expected_value, Decimal("0.2400"))

    def test_odds_exactly_minimum_are_allowed(self):
        value = candidate(
            offered_odds=Decimal("1.60"),
            calibrated_probability=Decimal("0.70"),
        )
        decision = gate().evaluate(value, context(
            market_consensus_probability=Decimal("0.68")
        ))

        self.assertEqual(decision.status, QualityGateStatus.APPROVED)

    def test_odds_below_minimum_are_rejected(self):
        decision = gate().evaluate(
            candidate(offered_odds=Decimal("1.59")),
            context(),
        )

        self.assertIn(RejectionReason.ODDS_BELOW_MINIMUM, decision.rejection_reasons)
        self.assertTrue(decision.is_no_bet)

    def test_invalid_and_non_finite_odds_are_rejected(self):
        for odds in (
            Decimal("1"),
            Decimal("0"),
            Decimal("NaN"),
            Decimal("Infinity"),
            2.0,
        ):
            with self.subTest(odds=odds):
                decision = gate().evaluate(candidate(offered_odds=odds), context())
                self.assertIn(RejectionReason.INVALID_ODDS, decision.rejection_reasons)

    def test_reference_odds_are_validated(self):
        decision = gate().evaluate(
            candidate(reference_odds=Decimal("NaN")),
            context(),
        )

        self.assertIn(RejectionReason.INVALID_ODDS, decision.rejection_reasons)

    def test_expected_value_service_is_unrounded(self):
        result = ExpectedValueService.calculate(
            Decimal("1.73"),
            Decimal("0.6123456789"),
        )

        self.assertEqual(result, Decimal("0.059358024497"))


class TimingAndEvidenceTests(unittest.TestCase):
    def test_prediction_before_kickoff_is_valid(self):
        decision = gate().evaluate(candidate(), context())

        self.assertNotIn(
            RejectionReason.PREDICTION_AFTER_KICKOFF,
            decision.rejection_reasons,
        )

    def test_prediction_exactly_at_kickoff_is_rejected(self):
        value = candidate(kickoff_time=PREDICTION_AT)

        decision = gate().evaluate(value, context())

        self.assertIn(
            RejectionReason.PREDICTION_AFTER_KICKOFF,
            decision.rejection_reasons,
        )

    def test_stale_odds_are_rejected(self):
        value = candidate(
            odds_timestamp=EVALUATED_AT - timedelta(minutes=16)
        )

        decision = gate().evaluate(value, context())

        self.assertIn(RejectionReason.ODDS_STALE, decision.rejection_reasons)

    def test_odds_at_maximum_age_are_not_stale(self):
        value = candidate(
            odds_timestamp=EVALUATED_AT - timedelta(minutes=15)
        )

        decision = gate().evaluate(value, context())

        self.assertNotIn(RejectionReason.ODDS_STALE, decision.rejection_reasons)

    def test_missing_required_evidence_is_rejected(self):
        decision = gate().evaluate(
            candidate(),
            context(evidence=evidence_with(
                EvidenceCategory.TEAM_FORM,
                EvidenceStatus.MISSING,
            )),
        )

        self.assertIn(
            RejectionReason.REQUIRED_DATA_MISSING,
            decision.rejection_reasons,
        )

    def test_partial_optional_lineup_requires_review(self):
        decision = gate().evaluate(
            candidate(),
            context(lineup_status=EvidenceStatus.PARTIAL),
        )

        self.assertEqual(decision.status, QualityGateStatus.REVIEW_REQUIRED)
        self.assertIn(ReviewReason.LINEUP_UNCONFIRMED, decision.review_reasons)

    def test_missing_optional_injury_data_requires_review(self):
        decision = gate().evaluate(
            candidate(),
            context(injury_data_status=EvidenceStatus.MISSING),
        )

        self.assertIn(
            ReviewReason.CRITICAL_INJURY_DATA_MISSING,
            decision.review_reasons,
        )

    def test_stale_blocking_evidence_is_rejected(self):
        decision = gate().evaluate(
            candidate(),
            context(evidence=evidence_with(
                EvidenceCategory.MODEL_FEATURES,
                EvidenceStatus.STALE,
            )),
        )

        self.assertIn(RejectionReason.DATA_STALE, decision.rejection_reasons)

    def test_missing_freshness_evidence_is_not_treated_as_neutral(self):
        decision = gate().evaluate(
            candidate(),
            context(data_freshness_status=EvidenceStatus.MISSING),
        )

        self.assertIn(
            RejectionReason.REQUIRED_DATA_MISSING,
            decision.rejection_reasons,
        )

    def test_naive_timestamp_is_collected_as_rejection(self):
        decision = gate().evaluate(
            candidate(prediction_timestamp=PREDICTION_AT.replace(tzinfo=None)),
            context(),
        )

        self.assertIn(RejectionReason.INVALID_TIMESTAMP, decision.rejection_reasons)


class MarketAndComboPolicyTests(unittest.TestCase):
    @staticmethod
    def combo_candidate(**changes) -> PublicationCandidate:
        selections = (
            ComboSelection(
                "Match Winner",
                "Home",
                Decimal("1.50"),
                Decimal("0.80"),
            ),
            ComboSelection(
                "Over 1.5",
                "Over",
                Decimal("1.55"),
                Decimal("0.82"),
            ),
        )
        values = {
            "market": "Combo",
            "selection": "Home + Over 1.5",
            "publication_type": PublicationType.COMBO,
            "combo_selections": selections,
            "offered_odds": Decimal("2.10"),
        }
        values.update(changes)
        return candidate(**values)

    def test_correct_score_is_rejected(self):
        decision = gate().evaluate(
            candidate(market="Correct Score", selection="2-1"),
            context(),
        )

        self.assertIn(
            RejectionReason.CORRECT_SCORE_FORBIDDEN,
            decision.rejection_reasons,
        )

    def test_combo_is_forbidden_when_exception_disabled(self):
        decision = gate(policy(combo_exception_enabled=False)).evaluate(
            self.combo_candidate(),
            context(),
        )

        self.assertIn(RejectionReason.COMBO_NOT_ALLOWED, decision.rejection_reasons)

    def test_valid_combo_exception_representation_is_approved(self):
        decision = gate().evaluate(self.combo_candidate(), context())

        self.assertEqual(decision.status, QualityGateStatus.APPROVED)

    def test_combo_exception_requires_two_low_odds_high_confidence_selections(self):
        bad_selection = ComboSelection(
            "Match Winner",
            "Home",
            Decimal("1.60"),
            Decimal("0.70"),
        )
        decision = gate().evaluate(
            self.combo_candidate(combo_selections=(bad_selection,)),
            context(),
        )

        self.assertIn(
            RejectionReason.COMBO_EXCEPTION_REQUIREMENTS_NOT_MET,
            decision.rejection_reasons,
        )

    def test_single_candidate_cannot_smuggle_combo_components(self):
        component = ComboSelection(
            "Match Winner",
            "Home",
            Decimal("1.50"),
            Decimal("0.80"),
        )
        decision = gate().evaluate(
            candidate(combo_selections=(component,)),
            context(),
        )

        self.assertIn(RejectionReason.COMBO_NOT_ALLOWED, decision.rejection_reasons)

    def test_non_official_product_scope_is_rejected(self):
        decision = gate().evaluate(
            candidate(product_scope="LIVE"),
            context(),
        )

        self.assertIn(
            RejectionReason.FORBIDDEN_PRODUCT_SCOPE,
            decision.rejection_reasons,
        )


class CalibrationAndValueTests(unittest.TestCase):
    def test_missing_calibrated_probability_is_rejected(self):
        decision = gate().evaluate(
            candidate(calibrated_probability=None),
            context(),
        )

        self.assertIn(
            RejectionReason.PROBABILITY_NOT_CALIBRATED,
            decision.rejection_reasons,
        )

    def test_identity_calibration_can_be_allowed(self):
        decision = gate(policy(identity_calibration_allowed=True)).evaluate(
            candidate(calibration_method="identity"),
            context(),
        )

        self.assertEqual(decision.status, QualityGateStatus.APPROVED)

    def test_identity_calibration_can_be_forbidden(self):
        decision = gate().evaluate(
            candidate(calibration_method="identity"),
            context(),
        )

        self.assertIn(
            RejectionReason.PROBABILITY_NOT_CALIBRATED,
            decision.rejection_reasons,
        )

    def test_insufficient_calibration_sample_is_rejected(self):
        decision = gate().evaluate(
            candidate(calibration_sample_size=99),
            context(calibration_sample_size=99),
        )

        self.assertIn(
            RejectionReason.CALIBRATION_SAMPLE_TOO_SMALL,
            decision.rejection_reasons,
        )

    def test_insufficient_model_sample_is_rejected(self):
        decision = gate().evaluate(candidate(), context(sample_size=99))

        self.assertIn(
            RejectionReason.MODEL_SAMPLE_TOO_SMALL,
            decision.rejection_reasons,
        )

    def test_future_calibration_fit_is_rejected(self):
        decision = gate().evaluate(
            candidate(
                calibration_fit_timestamp=PREDICTION_AT + timedelta(seconds=1)
            ),
            context(),
        )

        self.assertIn(
            RejectionReason.PROBABILITY_NOT_CALIBRATED,
            decision.rejection_reasons,
        )

    def test_non_earlier_training_cutoff_is_rejected(self):
        decision = gate().evaluate(
            candidate(calibration_training_cutoff=PREDICTION_AT),
            context(),
        )

        self.assertIn(
            RejectionReason.PROBABILITY_NOT_CALIBRATED,
            decision.rejection_reasons,
        )

    def test_calibration_fit_before_training_cutoff_is_rejected(self):
        decision = gate().evaluate(
            candidate(
                calibration_fit_timestamp=PREDICTION_AT - timedelta(days=2),
                calibration_training_cutoff=PREDICTION_AT - timedelta(days=1),
            ),
            context(),
        )

        self.assertIn(
            RejectionReason.PROBABILITY_NOT_CALIBRATED,
            decision.rejection_reasons,
        )

    def test_invalid_calibrated_probability_is_rejected(self):
        for probability in (Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(probability=probability):
                decision = gate().evaluate(
                    candidate(calibrated_probability=probability),
                    context(),
                )
                self.assertIn(
                    RejectionReason.INVALID_PROBABILITY,
                    decision.rejection_reasons,
                )

    def test_candidate_consumes_existing_fit_metadata(self):
        metadata = CalibrationFitMetadata(
            fitted_at=PREDICTION_AT - timedelta(minutes=1),
            training_window=CalibrationTrainingWindow(
                PREDICTION_AT - timedelta(days=30),
                PREDICTION_AT - timedelta(days=1),
            ),
            observation_count=200,
            scope=CalibrationScope.global_scope(),
            method_name="platt",
            version="cal-v1",
            model_version="model-v1",
        )
        base = candidate()
        candidate_fields = {
            item.name: getattr(base, item.name)
            for item in fields(PublicationCandidate)
            if not item.name.startswith("calibration_")
            and item.name != "calibrated_probability"
        }
        value = PublicationCandidate.with_calibration_metadata(
            metadata=metadata,
            calibrated_probability=Decimal("0.62"),
            **candidate_fields,
        )

        self.assertEqual(value.calibration_scope, metadata.scope)
        self.assertEqual(value.calibration_sample_size, 200)

    def test_expected_value_is_calculated_from_calibrated_probability(self):
        decision = gate().evaluate(candidate(), context())

        self.assertEqual(decision.expected_value, Decimal("0.2400"))
        self.assertEqual(decision.probability_source, ProbabilitySource.CALIBRATED)

    def test_expected_value_exactly_at_threshold_is_allowed(self):
        decision = gate(policy(
            minimum_expected_value=Decimal("0.2400")
        )).evaluate(candidate(), context())

        self.assertEqual(decision.status, QualityGateStatus.APPROVED)

    def test_expected_value_below_threshold_is_rejected(self):
        decision = gate(policy(
            minimum_expected_value=Decimal("0.2401")
        )).evaluate(candidate(), context())

        self.assertIn(
            RejectionReason.EXPECTED_VALUE_TOO_LOW,
            decision.rejection_reasons,
        )

    def test_raw_probability_requires_explicit_policy_permission(self):
        configured = policy(
            calibration_required=False,
            raw_probability_allowed=True,
        )
        decision = gate(configured).evaluate(
            candidate(
                calibrated_probability=None,
                calibration_scope=None,
                calibration_method=None,
                calibration_sample_size=None,
                calibration_fit_timestamp=None,
                calibration_training_cutoff=None,
            ),
            context(),
        )

        self.assertEqual(decision.probability_source, ProbabilitySource.RAW)
        self.assertEqual(decision.evaluated_probability, Decimal("0.60"))


class ConflictUncertaintyAndExposureTests(unittest.TestCase):
    def test_low_market_disagreement_passes(self):
        decision = gate().evaluate(
            candidate(),
            context(market_consensus_probability=Decimal("0.57")),
        )

        self.assertEqual(decision.status, QualityGateStatus.APPROVED)
        self.assertEqual(decision.market_disagreement, Decimal("0.05"))

    def test_review_level_market_disagreement_requires_review(self):
        decision = gate().evaluate(
            candidate(),
            context(market_consensus_probability=Decimal("0.50")),
        )

        self.assertEqual(decision.status, QualityGateStatus.REVIEW_REQUIRED)
        self.assertIn(ReviewReason.MARKET_CONFLICT, decision.review_reasons)

    def test_rejection_level_market_disagreement_is_rejected(self):
        decision = gate().evaluate(
            candidate(),
            context(market_consensus_probability=Decimal("0.40")),
        )

        self.assertEqual(decision.status, QualityGateStatus.REJECTED)
        self.assertIn(RejectionReason.MARKET_CONFLICT, decision.rejection_reasons)

    def test_severe_conflict_and_incomplete_data_adds_specific_reason(self):
        decision = gate().evaluate(
            candidate(),
            context(
                market_consensus_probability=Decimal("0.40"),
                data_completeness_status=EvidenceStatus.PARTIAL,
            ),
        )

        self.assertIn(
            RejectionReason.MARKET_CONFLICT_WITH_INCOMPLETE_DATA,
            decision.rejection_reasons,
        )

    def test_uncertainty_at_review_threshold_requires_review(self):
        decision = gate().evaluate(
            candidate(uncertainty_score=Decimal("0.20")),
            context(),
        )

        self.assertIn(
            ReviewReason.EXCESSIVE_UNCERTAINTY,
            decision.review_reasons,
        )

    def test_uncertainty_at_rejection_threshold_is_rejected(self):
        decision = gate().evaluate(
            candidate(uncertainty_score=Decimal("0.35")),
            context(),
        )

        self.assertIn(
            RejectionReason.EXCESSIVE_UNCERTAINTY,
            decision.rejection_reasons,
        )

    def test_each_exposure_limit_is_enforced(self):
        cases = (
            ("current_exposure", Decimal("1"), RejectionReason.EXPOSURE_LIMIT_REACHED),
            ("daily_exposure", Decimal("10"), RejectionReason.DAILY_EXPOSURE_LIMIT_REACHED),
            (
                "competition_exposure",
                Decimal("5"),
                RejectionReason.COMPETITION_EXPOSURE_LIMIT_REACHED,
            ),
            (
                "correlated_exposure",
                Decimal("2"),
                RejectionReason.CORRELATED_EXPOSURE_LIMIT_REACHED,
            ),
        )
        for field, value, reason in cases:
            with self.subTest(field=field):
                decision = gate().evaluate(candidate(), context(**{field: value}))
                self.assertIn(reason, decision.rejection_reasons)

    def test_exposure_context_is_evaluated_without_mutation(self):
        state = context()
        before = (
            state.current_exposure,
            state.daily_exposure,
            state.competition_exposure,
            state.correlated_exposure,
        )

        gate().evaluate(candidate(), state)

        self.assertEqual(before, (
            state.current_exposure,
            state.daily_exposure,
            state.competition_exposure,
            state.correlated_exposure,
        ))


class DuplicatePrecedenceAndSafetyTests(unittest.TestCase):
    def test_duplicate_identity_uses_fixture_market_selection_and_product(self):
        active = PublicationIdentity.create(
            1001,
            " match   winner ",
            " home ",
            " official ",
        )

        decision = gate(active=(active,)).evaluate(candidate(), context())

        self.assertIn(
            RejectionReason.DUPLICATE_PUBLICATION,
            decision.rejection_reasons,
        )

    def test_multiple_independent_rejections_are_collected(self):
        value = candidate(
            market="Correct Score",
            selection="2-1",
            offered_odds=Decimal("1.20"),
            odds_timestamp=EVALUATED_AT - timedelta(hours=1),
        )

        decision = gate().evaluate(value, context(sample_size=10))

        self.assertIn(RejectionReason.ODDS_BELOW_MINIMUM, decision.rejection_reasons)
        self.assertIn(RejectionReason.ODDS_STALE, decision.rejection_reasons)
        self.assertIn(
            RejectionReason.CORRECT_SCORE_FORBIDDEN,
            decision.rejection_reasons,
        )
        self.assertIn(RejectionReason.MODEL_SAMPLE_TOO_SMALL, decision.rejection_reasons)

    def test_reason_ordering_is_enum_deterministic(self):
        value = candidate(
            market="Correct Score",
            selection="2-1",
            offered_odds=Decimal("1.20"),
            odds_timestamp=EVALUATED_AT - timedelta(hours=1),
        )
        decision = gate().evaluate(value, context(sample_size=10))
        order = {reason: index for index, reason in enumerate(RejectionReason)}

        self.assertEqual(
            decision.rejection_reasons,
            tuple(sorted(decision.rejection_reasons, key=order.get)),
        )

    def test_review_required_precedence(self):
        decision = gate().evaluate(
            candidate(),
            context(lineup_status=EvidenceStatus.PARTIAL),
        )

        self.assertEqual(decision.status, QualityGateStatus.REVIEW_REQUIRED)
        self.assertFalse(decision.automatic_publication_eligible)

    def test_rejected_precedence_over_review(self):
        decision = gate().evaluate(
            candidate(offered_odds=Decimal("1.50")),
            context(lineup_status=EvidenceStatus.PARTIAL),
        )

        self.assertEqual(decision.status, QualityGateStatus.REJECTED)
        self.assertTrue(decision.rejection_reasons)
        self.assertTrue(decision.review_reasons)

    def test_check_order_matches_documented_pipeline(self):
        decision = gate().evaluate(candidate(), context())

        self.assertEqual(
            tuple(item.check for item in decision.checks),
            tuple(QualityGateCheck),
        )
        self.assertTrue(all(
            item.status in {
                CheckStatus.PASSED,
                CheckStatus.NOT_APPLICABLE,
            }
            for item in decision.checks
        ))

    def test_candidate_is_immutable_and_not_mutated(self):
        value = candidate()
        before = value

        gate().evaluate(value, context())

        self.assertEqual(value, before)
        with self.assertRaises(FrozenInstanceError):
            value.offered_odds = Decimal("3")

    def test_repeated_evaluation_is_deterministic(self):
        value = candidate()
        state = context()
        quality_gate = gate()

        self.assertEqual(
            quality_gate.evaluate(value, state),
            quality_gate.evaluate(value, state),
        )

    def test_probabilities_exactly_zero_and_one_are_valid(self):
        configured = policy(minimum_expected_value=Decimal("-1"))
        for probability in (Decimal("0"), Decimal("1")):
            with self.subTest(probability=probability):
                value = candidate(
                    raw_probability=probability,
                    calibrated_probability=probability,
                )
                decision = gate(configured).evaluate(
                    value,
                    context(
                        market_consensus_probability=None,
                        market_disagreement=None,
                    ),
                )
                self.assertNotIn(
                    RejectionReason.INVALID_PROBABILITY,
                    decision.rejection_reasons,
                )

    def test_nan_and_infinite_probabilities_are_rejected(self):
        for probability in (Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(probability=probability):
                decision = gate().evaluate(
                    candidate(
                        raw_probability=probability,
                        calibrated_probability=probability,
                    ),
                    context(),
                )
                self.assertIn(
                    RejectionReason.INVALID_PROBABILITY,
                    decision.rejection_reasons,
                )

    def test_evaluation_timestamp_is_caller_supplied(self):
        decision = gate().evaluate(candidate(), context())

        self.assertEqual(decision.evaluation_timestamp, EVALUATED_AT)

    def test_no_network_or_telegram_side_effects(self):
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network access attempted"),
        ) as network:
            decision = gate().evaluate(candidate(), context())

        self.assertEqual(decision.status, QualityGateStatus.APPROVED)
        network.assert_not_called()

    def test_no_bankroll_mutation(self):
        with patch.object(
            OfficialBankrollSettlementEngine,
            "settle",
            side_effect=AssertionError("bankroll settlement attempted"),
        ) as settle:
            decision = gate().evaluate(candidate(), context())

        self.assertEqual(decision.status, QualityGateStatus.APPROVED)
        settle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
