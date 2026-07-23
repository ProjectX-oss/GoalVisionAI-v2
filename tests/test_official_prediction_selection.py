import sqlite3
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from app.database import Database
from app.database.migrations import MIGRATIONS, MigrationManager
from app.market_value_assessment import (
    ActionabilityStatus,
    FreshnessState,
    MarketSelection,
    MarketType,
    ValueClassification,
)
from app.market_value_assessment.fingerprint import assessment_fingerprint
from app.official_prediction_selection import (
    DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY,
    DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
    AssessmentEligibilityStatus,
    OfficialNoSelectionDecision,
    OfficialPredictionSelectionCommand,
    OfficialPredictionSelectionPolicy,
    OfficialSelectionOutcomeStatus,
    PublicationProtectionState,
    SQLiteOfficialPredictionSelectionRepository,
    SelectedOfficialPrediction,
    SelectionMappingError,
    SelectionReason,
    build_official_prediction_selection_service,
    select_official_prediction,
    to_official_risk_handoff,
)
from app.official_prediction_selection.fingerprint import (
    policy_fingerprint,
    request_fingerprint,
)
from app.risk_management import RiskProductScope
from tests import test_market_value_assessment as market_value_fixture


class PublicationStates:
    def __init__(
        self,
        state: PublicationProtectionState = PublicationProtectionState.NOT_PUBLISHED,
    ) -> None:
        self.state = state
        self.calls: list[tuple[object, ...]] = []

    def classify(self, *args):
        self.calls.append(args)
        return self.state


class OfficialPredictionSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = market_value_fixture.MarketValueAssessmentTests()
        self.upstream.setUp()
        assessed = self.upstream.assess()
        self.base = self.upstream.repository.load_assessment_by_id(
            assessed.value_assessment_id
        )
        self.repository = SQLiteOfficialPredictionSelectionRepository(
            self.upstream.database
        )
        self.publication = PublicationStates()
        self.counter = 0

    def tearDown(self) -> None:
        self.upstream.tearDown()

    def service(self, *, policy=None, publication=None):
        return build_official_prediction_selection_service(
            self.repository,
            policy or DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
            DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY,
            publication or self.publication,
        )

    def command(self, assessments=None, **changes):
        self.counter += 1
        base = OfficialPredictionSelectionCommand(
            selection_request_identity=f"official-selection-request-{self.counter}",
            match_id=self.base.match_id,
            selection_timestamp=self.base.assessment_timestamp
            + timedelta(seconds=10),
            kickoff_timestamp=self.base.kickoff_timestamp,
            bankroll_scope=RiskProductScope.OFFICIAL,
            destination_scope=RiskProductScope.OFFICIAL,
            assessments=(self.base,) if assessments is None else assessments,
            selection_policy_version=(
                DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY.version
            ),
        )
        return replace(base, **changes)

    def variant(self, label: str, **changes):
        candidate = replace(
            self.base,
            value_assessment_id=f"official-selection-assessment-{label}",
            assessment_fingerprint="",
            derivation_version=f"{self.base.derivation_version}-{label}",
            **changes,
        )
        candidate = replace(
            candidate,
            assessment_fingerprint=assessment_fingerprint(candidate),
        )
        self.upstream.repository.append_value_assessment(candidate)
        return candidate

    def select(self, assessments=None, *, policy=None, publication=None, **changes):
        command = self.command(assessments, **changes)
        if policy is not None and "selection_policy_version" not in changes:
            command = replace(command, selection_policy_version=policy.version)
        return select_official_prediction(
            self.service(policy=policy, publication=publication), command
        )

    def test_default_policy_is_exact_and_cannot_expand_to_combos(self) -> None:
        policy = DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY
        self.assertEqual(policy.minimum_decimal_odds, Decimal("1.60"))
        self.assertEqual(policy.minimum_expected_value, Decimal("0.02"))
        self.assertEqual(policy.strong_expected_value, Decimal("0.05"))
        self.assertEqual(policy.maximum_selected_predictions_per_match, 1)
        self.assertEqual(
            policy.supported_markets,
            (
                MarketType.MATCH_WINNER,
                MarketType.DOUBLE_CHANCE,
                MarketType.TOTALS,
                MarketType.BTTS,
            ),
        )
        with self.assertRaises(ValueError):
            OfficialPredictionSelectionPolicy(
                maximum_selected_predictions_per_match=2
            )

    def test_policy_fingerprint_is_stable_and_version_sensitive(self) -> None:
        first = policy_fingerprint(
            DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
            DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY,
        )
        self.assertEqual(
            first,
            policy_fingerprint(
                DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
                DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY,
            ),
        )
        changed = replace(
            DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
            version="official-prediction-selection-policy-v1-revision",
        )
        self.assertNotEqual(
            first,
            policy_fingerprint(
                changed, DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY
            ),
        )

    def test_factory_construction_has_no_evaluation_or_persistence_side_effect(self) -> None:
        before = self.upstream.database.connection.execute(
            "SELECT COUNT(*) FROM official_prediction_selection_decisions"
        ).fetchone()[0]
        service = self.service()
        after = self.upstream.database.connection.execute(
            "SELECT COUNT(*) FROM official_prediction_selection_decisions"
        ).fetchone()[0]
        self.assertIsNotNone(service)
        self.assertEqual((before, after), (0, 0))
        self.assertEqual(self.publication.calls, [])

    def test_request_fingerprint_changes_for_every_material_input(self) -> None:
        changed_odds = self.variant(
            "fingerprint-odds", bookmaker_decimal_odds=Decimal("3.01")
        )
        changed_ev = self.variant(
            "fingerprint-ev", expected_value=Decimal("0.36")
        )
        base = self.command()
        values = (
            base,
            replace(base, assessments=(changed_odds,)),
            replace(base, assessments=(changed_ev,)),
            replace(
                base,
                selection_policy_version="official-selection-different-policy",
            ),
            replace(
                base,
                selection_timestamp=base.selection_timestamp
                + timedelta(seconds=1),
            ),
            replace(
                base,
                kickoff_timestamp=base.kickoff_timestamp
                + timedelta(seconds=1),
            ),
        )
        fingerprints = tuple(
            request_fingerprint(
                value, DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY.version
            )
            for value in values
        )
        self.assertEqual(len(fingerprints), len(set(fingerprints)))

    def test_valid_and_empty_requests_produce_durable_decisions(self) -> None:
        selected = self.select()
        empty = self.select(())
        self.assertEqual(selected.final_status, OfficialSelectionOutcomeStatus.SELECTED)
        self.assertIsInstance(selected.decision, SelectedOfficialPrediction)
        self.assertEqual(empty.final_status, OfficialSelectionOutcomeStatus.NO_SELECTION)
        self.assertIsInstance(empty.decision, OfficialNoSelectionDecision)
        self.assertEqual(empty.decision.assessment_count, 0)

    def test_request_required_fields_and_timing_fail_closed(self) -> None:
        cases = (
            (dict(match_id=""), SelectionReason.INVALID_REQUEST),
            (dict(kickoff_timestamp=None), SelectionReason.INVALID_REQUEST),
            (dict(selection_timestamp=None), SelectionReason.INVALID_REQUEST),
            (
                dict(selection_timestamp=self.base.kickoff_timestamp),
                SelectionReason.INVALID_REQUEST,
            ),
        )
        for changes, reason in cases:
            with self.subTest(changes=changes):
                outcome = self.select(**changes)
                self.assertEqual(
                    outcome.final_status,
                    OfficialSelectionOutcomeStatus.REJECTED_INVALID_REQUEST,
                )
                self.assertIn(reason, outcome.ordered_reason_codes)

    def test_non_official_scopes_are_rejected(self) -> None:
        bankroll = self.select(bankroll_scope=RiskProductScope.COMBO)
        destination = self.select(destination_scope=RiskProductScope.LIVE)
        self.assertEqual(bankroll.final_status, OfficialSelectionOutcomeStatus.REJECTED_SCOPE)
        self.assertEqual(destination.final_status, OfficialSelectionOutcomeStatus.REJECTED_SCOPE)

    def test_duplicates_and_collection_limit_are_rejected(self) -> None:
        same_fingerprint = replace(
            self.base, value_assessment_id="different-assessment-id"
        )
        for values in (
            (self.base, self.base),
            (self.base, same_fingerprint),
        ):
            with self.subTest(values=values):
                outcome = self.select(values)
                self.assertEqual(
                    outcome.final_status,
                    OfficialSelectionOutcomeStatus.REJECTED_INVALID_REQUEST,
                )
                self.assertIn(
                    SelectionReason.DUPLICATE_ASSESSMENT,
                    outcome.ordered_reason_codes,
                )
        too_many = self.select(
            (self.base,)
            * (DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY.maximum_assessment_count + 1)
        )
        self.assertIn(
            SelectionReason.COLLECTION_LIMIT_EXCEEDED,
            too_many.ordered_reason_codes,
        )

    def test_match_kickoff_fingerprint_and_persistence_provenance(self) -> None:
        cases = (
            replace(self.base, match_id="different-match"),
            replace(
                self.base,
                kickoff_timestamp=self.base.kickoff_timestamp + timedelta(seconds=1),
            ),
            replace(self.base, expected_value=Decimal("0.99")),
            replace(
                self.base,
                value_assessment_id="missing-persisted-assessment",
                assessment_fingerprint=assessment_fingerprint(
                    replace(
                        self.base,
                        value_assessment_id="missing-persisted-assessment",
                        assessment_fingerprint="",
                    )
                ),
            ),
        )
        for value in cases:
            with self.subTest(value=value.value_assessment_id):
                outcome = self.select((value,))
                self.assertEqual(
                    outcome.final_status,
                    OfficialSelectionOutcomeStatus.REJECTED_PROVENANCE,
                )

    def test_malformed_nan_and_infinite_decimals_are_rejected(self) -> None:
        for value in (1.2, Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=value):
                outcome = self.select((replace(self.base, expected_value=value),))
                self.assertEqual(
                    outcome.final_status,
                    OfficialSelectionOutcomeStatus.REJECTED_INVALID_REQUEST,
                )

    def test_metadata_is_normalized_and_sensitive_content_rejected(self) -> None:
        valid = self.select(metadata=((" batch ", " one  two "),))
        invalid = self.select(metadata=(("api_key", "secret"),))
        self.assertEqual(valid.final_status, OfficialSelectionOutcomeStatus.SELECTED)
        self.assertEqual(
            invalid.final_status,
            OfficialSelectionOutcomeStatus.REJECTED_INVALID_REQUEST,
        )
        self.assertIn(SelectionReason.INVALID_METADATA, invalid.ordered_reason_codes)

    def test_exact_odds_and_ev_boundaries_are_inclusive(self) -> None:
        exact = self.variant(
            "exact-boundaries",
            bookmaker_decimal_odds=Decimal("1.60"),
            expected_value=Decimal("0.02"),
            value_classification=ValueClassification.POSITIVE_VALUE,
        )
        outcome = self.select((exact,))
        self.assertEqual(outcome.final_status, OfficialSelectionOutcomeStatus.SELECTED)
        self.assertEqual(outcome.selected_odds, Decimal("1.60"))
        self.assertEqual(outcome.selected_expected_value, Decimal("0.02"))

    def test_below_odds_or_ev_produces_no_selection(self) -> None:
        cases = (
            (
                self.variant("below-odds", bookmaker_decimal_odds=Decimal("1.599")),
                SelectionReason.ODDS_BELOW_OFFICIAL_MINIMUM,
            ),
            (
                self.variant("below-ev", expected_value=Decimal("0.019999")),
                SelectionReason.EV_BELOW_OFFICIAL_MINIMUM,
            ),
        )
        for value, reason in cases:
            with self.subTest(reason=reason):
                outcome = self.select((value,))
                self.assertEqual(
                    outcome.final_status, OfficialSelectionOutcomeStatus.NO_SELECTION
                )
                self.assertIn(reason, outcome.ordered_reason_codes)

    def test_strong_positive_neutral_and_negative_classifications(self) -> None:
        strong = self.variant(
            "strong-exact",
            expected_value=Decimal("0.05"),
            value_classification=ValueClassification.STRONG_VALUE,
        )
        self.assertEqual(
            self.select((strong,)).final_status,
            OfficialSelectionOutcomeStatus.SELECTED,
        )
        for classification in (
            ValueClassification.NEUTRAL_VALUE,
            ValueClassification.NEGATIVE_VALUE,
        ):
            value = self.variant(
                f"classification-{classification.value}",
                value_classification=classification,
            )
            self.assertEqual(
                self.select((value,)).final_status,
                OfficialSelectionOutcomeStatus.NO_SELECTION,
            )

    def test_freshness_and_actionability_fail_closed(self) -> None:
        cases = (
            (
                dict(overall_freshness=FreshnessState.STALE),
                SelectionReason.STALE_ASSESSMENT,
            ),
            (
                dict(overall_freshness=FreshnessState.EXPIRED),
                SelectionReason.EXPIRED_ASSESSMENT,
            ),
            (
                dict(overall_freshness=FreshnessState.AGING),
                SelectionReason.AGING_ASSESSMENT,
            ),
            (
                dict(actionability_status=ActionabilityStatus.NON_ACTIONABLE_INVALID),
                SelectionReason.NON_ACTIONABLE_ASSESSMENT,
            ),
        )
        for index, (changes, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                value = self.variant(f"freshness-{index}", **changes)
                outcome = self.select((value,))
                self.assertEqual(outcome.final_status, OfficialSelectionOutcomeStatus.NO_SELECTION)
                self.assertIn(reason, outcome.ordered_reason_codes)

    def test_aging_requires_explicit_policy(self) -> None:
        aging = self.variant(
            "aging-explicit",
            odds_freshness=FreshnessState.AGING,
            overall_freshness=FreshnessState.AGING,
        )
        policy = replace(
            DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
            version="official-prediction-selection-policy-v1-aging",
            allow_aging_assessments=True,
        )
        outcome = self.select((aging,), policy=policy)
        self.assertEqual(outcome.final_status, OfficialSelectionOutcomeStatus.SELECTED)

    def test_kickoff_boundary_rejects_only_below_five_minutes(self) -> None:
        exact = self.select(
            selection_timestamp=self.base.kickoff_timestamp - timedelta(seconds=300)
        )
        below = self.select(
            selection_timestamp=self.base.kickoff_timestamp - timedelta(seconds=299)
        )
        self.assertEqual(exact.final_status, OfficialSelectionOutcomeStatus.SELECTED)
        self.assertEqual(below.final_status, OfficialSelectionOutcomeStatus.NO_SELECTION)
        self.assertIn(SelectionReason.TOO_CLOSE_TO_KICKOFF, below.ordered_reason_codes)

    def test_unsupported_market_identity_produces_no_selection(self) -> None:
        unsupported = self.variant(
            "unsupported-combination",
            market_type=MarketType.TOTALS,
            selection=MarketSelection.HOME,
            market_line=Decimal("2.5"),
        )
        outcome = self.select((unsupported,))
        self.assertEqual(outcome.final_status, OfficialSelectionOutcomeStatus.NO_SELECTION)
        self.assertIn(SelectionReason.UNSUPPORTED_MARKET, outcome.ordered_reason_codes)

    def test_publication_protection_states_fail_closed(self) -> None:
        expected = {
            PublicationProtectionState.PUBLISHED: SelectionReason.ALREADY_PUBLISHED,
            PublicationProtectionState.ACTIVE_CLAIM: SelectionReason.ACTIVE_PUBLICATION_CLAIM,
            PublicationProtectionState.INDETERMINATE: SelectionReason.INDETERMINATE_PUBLICATION_STATE,
            PublicationProtectionState.UNKNOWN: SelectionReason.INDETERMINATE_PUBLICATION_STATE,
        }
        for state, reason in expected.items():
            with self.subTest(state=state):
                outcome = self.select(publication=PublicationStates(state))
                self.assertEqual(outcome.final_status, OfficialSelectionOutcomeStatus.NO_SELECTION)
                self.assertIn(reason, outcome.ordered_reason_codes)

    def test_publication_port_failure_is_indeterminate(self) -> None:
        class BrokenPublication:
            def classify(self, *args):
                raise RuntimeError("unavailable")

        outcome = self.select(publication=BrokenPublication())
        self.assertIn(
            SelectionReason.INDETERMINATE_PUBLICATION_STATE,
            outcome.ordered_reason_codes,
        )

    def test_logical_market_dedup_retains_better_odds_without_averaging(self) -> None:
        low = self.variant(
            "dedup-low",
            bookmaker_id="Book Low",
            bookmaker_decimal_odds=Decimal("2.00"),
        )
        high = self.variant(
            "dedup-high",
            bookmaker_id="Book High",
            bookmaker_decimal_odds=Decimal("3.20"),
        )
        outcome = self.select((low, high))
        stored = self.repository.load_selection_with_evaluations(
            outcome.selection_decision_id
        )
        self.assertEqual(outcome.selected_value_assessment_id, high.value_assessment_id)
        self.assertEqual(outcome.selected_odds, Decimal("3.20"))
        self.assertEqual(outcome.eligible_assessment_count, 1)
        self.assertEqual(
            tuple(item.eligibility_status for item in stored.evaluations).count(
                AssessmentEligibilityStatus.DEDUPLICATED
            ),
            1,
        )

    def test_different_markets_remain_eligible_but_only_one_is_selected(self) -> None:
        btts = self.variant(
            "different-market",
            market_type=MarketType.BTTS,
            selection=MarketSelection.YES,
            market_line=None,
        )
        outcome = self.select((self.base, btts))
        self.assertEqual(outcome.eligible_assessment_count, 2)
        self.assertIsNotNone(outcome.selected_value_assessment_id)
        self.assertEqual(
            self.upstream.database.connection.execute(
                "SELECT COUNT(*) FROM official_prediction_selection_decisions "
                "WHERE selected_value_assessment_id IS NOT NULL"
            ).fetchone()[0],
            1,
        )

    def test_primary_numeric_ranking_chain_is_decimal_safe(self) -> None:
        tests = (
            ("ev", dict(expected_value=Decimal("0.36")), dict(expected_value=Decimal("0.35"))),
            ("fair", dict(fair_probability=Decimal("0.46")), dict(fair_probability=Decimal("0.45"))),
            ("edge", dict(absolute_probability_edge=Decimal("0.117")), dict(absolute_probability_edge=Decimal("0.116"))),
            ("odds", dict(bookmaker_decimal_odds=Decimal("3.01")), dict(bookmaker_decimal_odds=Decimal("3.00"))),
        )
        for index, (label, winner_changes, loser_changes) in enumerate(tests):
            with self.subTest(label=label):
                winner = self.variant(f"rank-{index}-winner", **winner_changes)
                loser = self.variant(f"rank-{index}-loser", **loser_changes)
                outcome = self.select((loser, winner))
                self.assertEqual(
                    outcome.selected_value_assessment_id,
                    winner.value_assessment_id,
                )

    def test_freshness_and_newer_odds_rank_before_identical_peers(self) -> None:
        policy = replace(
            DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
            version="official-prediction-selection-policy-v1-aging-rank",
            allow_aging_assessments=True,
        )
        fresh = self.variant("fresh-rank", bookmaker_id="Book Fresh")
        aging = self.variant(
            "aging-rank",
            bookmaker_id="Book Aging",
            odds_freshness=FreshnessState.AGING,
            overall_freshness=FreshnessState.AGING,
        )
        outcome = self.select((aging, fresh), policy=policy)
        self.assertEqual(outcome.selected_value_assessment_id, fresh.value_assessment_id)

        newer = self.variant("newer-odds", bookmaker_id="Book New", odds_age_seconds=0)
        older = self.variant("older-odds", bookmaker_id="Book Old", odds_age_seconds=1)
        newer_outcome = self.select((older, newer))
        self.assertEqual(
            newer_outcome.selected_value_assessment_id,
            newer.value_assessment_id,
        )

    def test_policy_priority_tie_breakers_are_ordered(self) -> None:
        cases = (
            (
                "market",
                dict(market_type=MarketType.MATCH_WINNER, selection=MarketSelection.HOME, market_line=None),
                dict(market_type=MarketType.BTTS, selection=MarketSelection.YES, market_line=None),
            ),
            (
                "selection",
                dict(market_type=MarketType.MATCH_WINNER, selection=MarketSelection.HOME, market_line=None),
                dict(market_type=MarketType.MATCH_WINNER, selection=MarketSelection.AWAY, market_line=None),
            ),
            (
                "line",
                dict(market_type=MarketType.TOTALS, selection=MarketSelection.OVER, market_line=Decimal("1.5")),
                dict(market_type=MarketType.TOTALS, selection=MarketSelection.OVER, market_line=Decimal("2.5")),
            ),
        )
        for index, (label, first_changes, second_changes) in enumerate(cases):
            with self.subTest(label=label):
                first = self.variant(f"priority-{index}-first", **first_changes)
                second = self.variant(f"priority-{index}-second", **second_changes)
                outcome = self.select((second, first))
                self.assertEqual(outcome.selected_value_assessment_id, first.value_assessment_id)

    def test_bookmaker_and_assessment_identity_are_stable_final_ties(self) -> None:
        book_a = self.variant("book-a", bookmaker_id="A Book")
        book_b = self.variant("book-b", bookmaker_id="B Book")
        outcome = self.select((book_b, book_a))
        self.assertEqual(outcome.selected_value_assessment_id, book_a.value_assessment_id)

        id_a = self.variant("a-final-id", bookmaker_id="Same Book")
        id_b = self.variant("b-final-id", bookmaker_id="Same Book")
        outcome = self.select((id_b, id_a))
        self.assertEqual(outcome.selected_value_assessment_id, id_a.value_assessment_id)

    def test_input_order_does_not_change_request_fingerprint_or_selection(self) -> None:
        other = self.variant(
            "order-independent",
            market_type=MarketType.BTTS,
            selection=MarketSelection.YES,
            expected_value=Decimal("0.40"),
        )
        command = self.command((self.base, other))
        reversed_command = replace(command, assessments=(other, self.base))
        self.assertEqual(
            request_fingerprint(
                command, DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY.version
            ),
            request_fingerprint(
                reversed_command,
                DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY.version,
            ),
        )
        first = select_official_prediction(self.service(), command)
        replay = select_official_prediction(self.service(), reversed_command)
        self.assertEqual(first.selected_value_assessment_id, other.value_assessment_id)
        self.assertEqual(replay.final_status, OfficialSelectionOutcomeStatus.IDEMPOTENT_EXISTING)

    def test_replay_is_idempotent_and_changed_content_conflicts(self) -> None:
        command = self.command()
        first = select_official_prediction(self.service(), command)
        second = select_official_prediction(self.service(), command)
        conflict = select_official_prediction(
            self.service(),
            replace(
                command,
                selection_timestamp=command.selection_timestamp + timedelta(seconds=1),
            ),
        )
        self.assertEqual(first.final_status, OfficialSelectionOutcomeStatus.SELECTED)
        self.assertEqual(second.final_status, OfficialSelectionOutcomeStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(first.decision_fingerprint, second.decision_fingerprint)
        self.assertEqual(conflict.final_status, OfficialSelectionOutcomeStatus.CONFLICT)

    def test_selected_and_no_selection_fingerprints_are_repeatable(self) -> None:
        selected_command = self.command()
        selected = select_official_prediction(self.service(), selected_command)
        empty_command = self.command(())
        empty = select_official_prediction(self.service(), empty_command)
        self.assertEqual(len(selected.decision_fingerprint), 64)
        self.assertEqual(len(empty.decision_fingerprint), 64)
        self.assertEqual(
            self.repository.find_by_decision_fingerprint(
                selected.decision_fingerprint
            ),
            selected.decision,
        )

    def test_selected_decision_has_full_provenance_and_no_approval_or_stake(self) -> None:
        outcome = self.select()
        decision = outcome.decision
        self.assertEqual(decision.inference_id, self.base.inference_id)
        self.assertEqual(decision.model_input_id, self.base.model_input_id)
        self.assertEqual(decision.feature_set_id, self.base.feature_set_id)
        self.assertEqual(
            decision.calibration_set_fingerprint,
            self.base.calibration_set_fingerprint,
        )
        self.assertFalse(hasattr(decision, "stake"))
        self.assertFalse(hasattr(decision, "quality_gate_approved"))

    def test_persistence_queries_round_trip_decimal_snapshots(self) -> None:
        selected = self.select()
        no_selection = self.select(
            (),
            selection_timestamp=self.base.assessment_timestamp
            + timedelta(seconds=11),
        )
        loaded = self.repository.load_selection_with_evaluations(
            selected.selection_decision_id
        )
        self.assertEqual(loaded.decision, selected.decision)
        self.assertEqual(len(loaded.evaluations), 1)
        self.assertIsInstance(loaded.evaluations[0].verified_odds, Decimal)
        self.assertEqual(
            self.repository.find_by_request_identity(
                selected.decision.selection_request_identity
            ),
            selected.decision,
        )
        self.assertEqual(len(self.repository.list_selection_decisions_for_match(self.base.match_id)), 2)
        self.assertEqual(self.repository.list_selected_decisions(), (selected.decision,))
        self.assertEqual(self.repository.list_no_selection_decisions(), (no_selection.decision,))
        self.assertEqual(self.repository.find_latest_selection_for_match(self.base.match_id), no_selection.decision)

    def test_persistence_is_immutable_and_foreign_keys_are_declared(self) -> None:
        outcome = self.select()
        connection = self.upstream.database.connection
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE official_prediction_selection_decisions SET match_id = 'x'"
            )
        connection.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM official_prediction_selection_evaluations")
        connection.rollback()
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(official_prediction_selection_evaluations)"
        ).fetchall()
        self.assertEqual(
            {row[2] for row in foreign_keys},
            {
                "official_prediction_selection_decisions",
                "market_value_assessments",
            },
        )
        self.assertIsNotNone(outcome.selection_decision_id)

    def test_atomic_append_rolls_back_when_evaluation_insert_fails(self) -> None:
        connection = self.upstream.database.connection
        connection.execute(
            """
            CREATE TRIGGER official_selection_test_abort
            BEFORE INSERT ON official_prediction_selection_evaluations
            BEGIN SELECT RAISE(ABORT, 'test rollback'); END
            """
        )
        outcome = self.select()
        self.assertEqual(
            outcome.final_status,
            OfficialSelectionOutcomeStatus.PERSISTENCE_FAILURE,
        )
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM official_prediction_selection_decisions"
            ).fetchone()[0],
            0,
        )

    def test_fresh_v20_migration_and_v19_upgrade(self) -> None:
        fresh = Database(":memory:")
        try:
            MigrationManager(fresh.connection).migrate()
            self.assertEqual(
                fresh.connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0],
                29,
            )
            tables = {
                row[0]
                for row in fresh.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertIn("official_prediction_selection_decisions", tables)
            self.assertIn("official_prediction_selection_evaluations", tables)
            indexes = {
                row[0]
                for row in fresh.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            self.assertTrue(
                {
                    "idx_official_selection_match",
                    "idx_official_selection_timestamp",
                    "idx_official_selection_selected_assessment",
                    "idx_official_selection_status",
                    "idx_official_selection_market",
                    "idx_official_selection_policy",
                }.issubset(indexes)
            )
        finally:
            fresh.close()

        upgrade = Database(":memory:")
        try:
            upgrade.connection.execute(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            for migration in MIGRATIONS:
                if migration.version > 19:
                    break
                for statement in migration.statements:
                    upgrade.connection.execute(statement)
                upgrade.connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, datetime('now'))",
                    (migration.version,),
                )
            upgrade.connection.commit()
            self.assertEqual(
                upgrade.connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0],
                19,
            )
            MigrationManager(upgrade.connection).migrate()
            self.assertEqual(
                upgrade.connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0],
                29,
            )
        finally:
            upgrade.close()

    def test_risk_handoff_preserves_facts_and_rejects_no_selection(self) -> None:
        selected = self.select().decision
        handoff = to_official_risk_handoff(selected)
        self.assertEqual(handoff.expected_value, selected.expected_value)
        self.assertEqual(
            handoff.bookmaker_decimal_odds,
            selected.bookmaker_decimal_odds,
        )
        self.assertEqual(
            handoff.logical_market_identity,
            selected.logical_market_identity,
        )
        self.assertEqual(handoff.inference_id, selected.inference_id)
        self.assertEqual(
            handoff.calibration_set_fingerprint,
            selected.calibration_set_fingerprint,
        )
        self.assertFalse(hasattr(handoff, "stake"))
        with self.assertRaises(SelectionMappingError):
            to_official_risk_handoff(self.select(()).decision)


if __name__ == "__main__":
    unittest.main()
