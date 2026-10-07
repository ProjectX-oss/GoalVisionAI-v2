from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
from pathlib import Path
import unittest

from app.adaptive_lab.combo_evidence import coupon_report, DOUBLE_COHORT
from app.adaptive_lab.contracts import learning_source

spec = importlib.util.spec_from_file_location("quality_audit", Path(__file__).parents[1]/"operations/prematch-quality/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
NOW = datetime(2026, 10, 7, 17, tzinfo=timezone.utc)


class Ledger:
    def __init__(self, predictions, results=None, receipts=None):
        self.predictions = deepcopy(predictions)
        self.results = deepcopy(results or {})
        self.receipts = deepcopy(receipts if receipts is not None else {
            "combo_prediction:"+p["prediction_id"]: {"status": "SENT", "sent_at_utc": "2026-10-07T10:00:00+00:00"}
            for p in predictions})
    def all(self, kind):
        assert kind == "prediction"
        return self.predictions
    def get(self, kind, identity):
        return (self.receipts if kind == "receipt" else self.results).get(identity)


def prediction(identity="one", cohort=DOUBLE_COHORT):
    return {"prediction_id": identity, "statistics_cohort": cohort, "combined_odds": "3.06",
            "estimated_probability_if_independent": "0.56", "legs": [
                {"fixture_id": 1, "ensemble_probability": ".7", "captured_odds": "1.7",
                 "kickoff_utc": "2026-10-07T11:00:00+00:00"},
                {"fixture_id": 2, "ensemble_probability": ".8", "captured_odds": "1.8",
                 "kickoff_utc": "2026-10-07T12:00:00+00:00"}]}


def result(status="WON", pnl="2.06", **kw):
    return {"status": status, "unit_result": pnl, "settled_at_utc": "2026-10-07T14:00:00+00:00", **kw}


class CouponEvidenceTests(unittest.TestCase):
    def test_exact_coupon_metrics_and_immutable_input(self):
        ledger = Ledger([prediction()], {"one": result()})
        before = deepcopy(ledger.__dict__)
        report = coupon_report(ledger, now=NOW)
        self.assertEqual(ledger.__dict__, before)
        row = report["rows"][0]
        self.assertEqual(Decimal(row["naive_joint_probability"]), Decimal(".56"))
        self.assertEqual(row["kickoff_lead_minutes"], 60)
        self.assertEqual(row["correlation_adjusted_joint_probability"], None)
        self.assertEqual(report["overall"]["coupon_probability_observations"], 1)
        self.assertAlmostEqual(report["overall"]["brier"], .44**2)
        self.assertEqual(report["overall"]["flat_unit_pnl"], "2.06")
        self.assertEqual(report["model_learning_observations"], 0)
        self.assertFalse(learning_source(row))

    def test_coupon_never_valid_learning_source(self):
        self.assertFalse(learning_source({"source_product": "COMBO"}))
        self.assertFalse(learning_source({"source_product": "COMBO_LEG"}))
        self.assertTrue(learning_source({"source_product": "SINGLE"}))

    def test_unknown_delivery_and_future_publication_excluded(self):
        p = prediction()
        self.assertEqual(coupon_report(Ledger([p], receipts={}), now=NOW)["overall"]["published"], 0)
        receipt = {"combo_prediction:one": {"status": "SENT", "sent_at_utc": "2026-10-08T00:00:00+00:00"}}
        self.assertEqual(coupon_report(Ledger([p], receipts=receipt), now=NOW)["overall"]["published"], 0)

    def test_future_settlement_remains_pending(self):
        r = result(settled_at_utc="2026-10-08T00:00:00+00:00")
        report = coupon_report(Ledger([prediction()], {"one": r}), now=NOW)
        self.assertEqual(report["overall"]["pending"], 1)
        self.assertEqual(report["overall"]["coupon_probability_observations"], 0)

    def test_void_and_partial_void_excluded_from_binary_metrics(self):
        ps = [prediction("a"), prediction("b"), prediction("c")]
        ledger = Ledger(ps, {"a": result("VOID", "0"), "b": result("WON", ".7", partial_void=True),
                             "c": result("LOST", "-1")})
        summary = coupon_report(ledger, now=NOW)["overall"]
        self.assertEqual(summary["coupon_probability_observations"], 1)
        self.assertEqual(summary["partial_void_count"], 1)
        self.assertEqual(summary["VOID"], 1)
        self.assertEqual(summary["flat_unit_pnl"], "-0.3")
        self.assertAlmostEqual(summary["flat_roi"], -.1)

    def test_early_loss_scored_once_pending_legs_are_not_pending_coupon(self):
        ledger = Ledger([prediction()], {"one": result("LOST", "-1", pending_legs=[{}, {}])})
        report = coupon_report(ledger, now=NOW)
        self.assertEqual(report["overall"]["pending"], 0)
        self.assertEqual(report["overall"]["coupon_probability_observations"], 1)
        self.assertEqual(report["rows"][0]["remaining_leg_tracking_count"], 2)

    def test_legacy_joint_is_explicitly_derived_no_correlation_fabrication(self):
        p = prediction(); p.pop("estimated_probability_if_independent")
        p["correlation_review"] = "PASSED"
        row = coupon_report(Ledger([p]), now=NOW)["rows"][0]
        self.assertEqual(row["declared_joint_probability"], None)
        self.assertEqual(Decimal(row["naive_joint_probability"]), Decimal(".56"))
        self.assertEqual(row["correlation_adjustment_status"], "NOT_AVAILABLE")

    def test_invalid_or_missing_probability_is_not_clamped(self):
        for value in ("0", "1", "NaN", None):
            p = prediction(); p["legs"][0]["ensemble_probability"] = value
            report = coupon_report(Ledger([p], {"one": result()}), now=NOW)
            self.assertIsNone(report["rows"][0]["naive_joint_probability"])
            self.assertEqual(report["overall"]["binary_missing_probability"], 1)
            self.assertEqual(report["overall"]["coupon_probability_observations"], 0)

    def test_cohorts_determinism_and_empty_double(self):
        ps = [prediction("a", "V2"), prediction("b", "LEGACY")]
        a = coupon_report(Ledger(ps), now=NOW)
        b = coupon_report(Ledger(list(reversed(ps))), now=NOW)
        self.assertEqual(a, b)
        self.assertEqual(a["cohorts"][DOUBLE_COHORT]["published"], 0)
        self.assertEqual(a["cohorts"]["V2"]["published"], 1)

    def test_float_extremes_are_not_clamped_or_mislabeled_missing(self):
        p = prediction()
        for leg in p["legs"]:
            leg["ensemble_probability"] = ".999999999999999999999999"
        report = coupon_report(Ledger([p], {"one": result()}), now=NOW)
        self.assertEqual(report["overall"]["unscorable_float_extreme_probability"], 1)
        self.assertEqual(report["overall"]["binary_missing_probability"], 0)
        self.assertEqual(report["overall"]["coupon_probability_observations"], 0)
        self.assertLess(Decimal(report["rows"][0]["naive_joint_probability"]), Decimal(1))

    def test_recorded_joint_mismatch_is_observable_not_silently_repaired(self):
        p = prediction();p["estimated_probability_if_independent"] = ".9"
        report = coupon_report(Ledger([p]), now=NOW)
        self.assertEqual(report["diagnostics"]["DECLARED_VS_DERIVED_JOINT_MISMATCH"], 1)
        self.assertEqual(report["rows"][0]["declared_joint_probability"], "0.9")


def cycle(at="2026-10-07T10:00:00+00:00", status="ODDS_STALE"):
    return {
        "evaluated_at_utc": at, "global_fixture_states": [
            {"fixture_id": 1, "league_id": 5, "country": "Test", "league_name": "Cup",
             "competition_profile": "DOMESTIC_CUP", "kickoff_utc": "2026-10-07T11:00:00+00:00",
             "provider_metadata": {"fixture": {"status": {"short": "NS"}}}}],
        "odds_pagination": {"fixture_coverage_reasons": {"1": status},
                            "coverage_by_date": {"2026-10-07": {"stable_complete_sweep": True}},
                            "priority_exact_retries": []},
        "tracked_final_reviews": [], "final_review_queue": {"attempted_fixture_ids": [1]},
        "exact_fixture_odds_refresh_calls": 2, "api_call_allocation": {"/odds(date)": 1},
        "current_odds_fixtures": 1, "api_calls_consumed": 5,
        "adaptive_quota_budget": {"effective_cycle_maximum": 10},
        "current_remaining_daily_quota": 4000,
    }


class RefreshYieldTests(unittest.TestCase):
    def test_broad_missing_and_exact_success_are_separate(self):
        c = cycle(status="ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD")
        r = audit.odds_report([c], {c["evaluated_at_utc"]: [{"fixture_id": 1, "status": "AVAILABLE"}]})
        self.assertEqual(r["broad_scope"]["no_record_rate"], 1)
        self.assertEqual(r["tracked_exact"]["fresh_success_rate"], 1)
        self.assertEqual(r["http_calls_per_known_successful_fresh_fixture"], 2)

    def test_repeated_failures_use_only_prior_cycle_and_unknown_reason_stays_unknown(self):
        a, b = cycle(), cycle("2026-10-07T10:30:00+00:00")
        tracked = {c["evaluated_at_utc"]: [{"fixture_id": 1, "status": "WAITING_CURRENT_ODDS"}] for c in (a, b)}
        r = audit.odds_report([b, a], tracked)
        self.assertEqual(r["tracked_exact"]["repeated_no_yield"], 1)
        self.assertEqual(r["tracked_exact"]["no_record_or_missing"], 0)
        self.assertEqual(r["tracked_exact"]["stale"], 0)
        self.assertIsNone(r["tracked_exact"]["stale_rate"])
        self.assertIsNone(r["tracked_exact"]["no_record_rate"])
        self.assertEqual(r["tracked_exact"]["failure_reason_unavailable"], 2)

    def test_duplicate_market_reviews_count_once(self):
        c = cycle()
        review = {"fixture_id": 1, "final_review": {"odds_status": "AVAILABLE",
                  "odds_retrieved_at_utc": "2026-10-07T10:01:00+00:00"}}
        c["tracked_final_reviews"] = [review, deepcopy(review)]
        r = audit.odds_report([c], {})
        self.assertEqual(r["exact_recorded_outcomes"]["fixture_observations"], 1)
        self.assertEqual(r["known_successful_exact_fixture_refreshes"], 1)

    def test_conflicting_frozen_final_outcomes_reject(self):
        c = cycle()
        c["tracked_final_reviews"] = [
            {"fixture_id": 1, "final_review": {"odds_status": "AVAILABLE", "odds_retrieved_at_utc": "x"}},
            {"fixture_id": 1, "final_review": {"odds_status": "ODDS_STALE", "odds_retrieved_at_utc": "x"}}]
        with self.assertRaisesRegex(ValueError, "CONFLICTING"):
            audit.odds_report([c], {})


class DisagreementTests(unittest.TestCase):
    def test_reason_union_deduplicates_and_missingness_is_explicit(self):
        rows = [{"fixture_id": 1, "ensemble_probability": ".8", "market_fair_probability": ".4",
                 "captured_odds": "2.0", "api_prediction_available": False,
                 "rejection_reasons": ["SEVERE_MODEL_MARKET_CONTRADICTION"],
                 "hard_failures": ["SEVERE_MODEL_MARKET_CONTRADICTION"]}]
        report = audit.disagreement_report(rows)
        overall = next(r for r in report["segments"] if r["dimension"] == "ALL")
        self.assertEqual(overall["reason_counts"]["SEVERE_MODEL_MARKET_CONTRADICTION"], 1)
        self.assertAlmostEqual(overall["mean_absolute_ensemble_market_divergence"], .4)
        self.assertTrue(any(r["value"] == "QUOTE_WITHOUT_API_PREDICTION" for r in report["segments"]))

    def test_stale_marker_remains_diagnostic(self):
        rows = [{"fixture_id": 1, "hard_failures": ["ODDS_STALE"]}]
        report = audit.disagreement_report(rows)
        self.assertTrue(any(r["value"] == "STALE_MARKER_PRESENT" for r in report["segments"]))
        self.assertEqual(report["selection_effect"], "NONE")


if __name__ == "__main__":
    unittest.main()
