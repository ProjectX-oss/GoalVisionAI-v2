"""Read-only coupon calibration diagnostics, never PREMATCH learning inputs.

Frozen leg probabilities are descriptive and may contain market information.
Their product assumes independence; a correlation screen is not a calibrated
joint-probability model. No runtime publisher, training or activation hook.
"""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from statistics import mean

from .contracts import digest, utc
from .performance import band, finite, probability_metrics

VERSION = "LAB_COMBO_COUPON_EVIDENCE_V1"
DOUBLE_COHORT = "COMBO_DOUBLE_20261006_V1"


def _before(value: object, cutoff: datetime) -> bool:
    try:
        return utc(value) <= utc(cutoff)
    except (ValueError, TypeError, AttributeError):
        return False


def _product(values: list[Decimal | None]) -> Decimal | None:
    if not values or any(v is None for v in values):
        return None
    result = Decimal(1)
    for value in values:
        result *= value
    return result


def _text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def coupon_rows(ledger: object, *, now: datetime) -> tuple[list[dict], dict]:
    """Export confirmed coupons at a fixed cutoff without recipient/message data."""
    rows, diagnostics = [], Counter()
    for prediction in ledger.all("prediction"):
        identity = prediction["prediction_id"]
        receipt = next((r for prefix in ("combo_prediction:", "prediction:")
                        if (r := ledger.get("receipt", prefix + identity))
                        and r.get("status") == "SENT"), None)
        if receipt is None or not _before(receipt.get("sent_at_utc"), now):
            continue
        publication = receipt["sent_at_utc"]
        settlement = ledger.get("settlement", identity)
        if settlement and not _before(settlement.get("settled_at_utc"), now):
            settlement = None
        legs = []
        for leg in prediction.get("legs", []):
            probability = finite(leg.get("ensemble_probability"))
            if probability is None:
                probability = finite(leg.get("probability"))
            valid_probability = probability is not None and 0 < probability < 1
            if not valid_probability:
                diagnostics["MISSING_OR_INVALID_FROZEN_LEG_PROBABILITY"] += 1
            odds = finite(leg.get("captured_odds", leg.get("odds")))
            if odds is not None and odds <= 1:
                odds = None
            legs.append({
                "fixture_id": leg.get("fixture_id"), "market": leg.get("market"),
                "league_id": leg.get("league_id"), "competition": leg.get("competition_profile"),
                "model_probability": _text(probability) if valid_probability else None,
                "probability_kind": leg.get("probability_kind", "UNSPECIFIED"),
                "bookmaker_odds": _text(odds), "bookmaker_id": leg.get("bookmaker_id"),
                "kickoff_utc": leg.get("kickoff_utc"),
                "model_generation": leg.get("model_generation"),
                "quote_provenance_fingerprint": leg.get("quote_provenance_fingerprint"),
            })
        naive = _product([finite(l["model_probability"]) for l in legs])
        declared = finite(prediction.get("estimated_probability_if_independent"))
        if naive is not None and declared is not None and abs(naive - declared) > Decimal("1e-24"):
            diagnostics["DECLARED_VS_DERIVED_JOINT_MISMATCH"] += 1
        combined = finite(prediction.get("combined_odds"))
        leg_product = _product([finite(l["bookmaker_odds"]) for l in legs])
        if combined is not None and leg_product is not None and abs(combined - leg_product) > Decimal("1e-20"):
            diagnostics["COMBINED_ODDS_VS_LEG_PRODUCT_MISMATCH"] += 1
        try:
            kickoffs = [utc(l["kickoff_utc"]) for l in legs]
            lead = (min(kickoffs) - utc(publication)).total_seconds()/60 if kickoffs else None
        except (ValueError, TypeError, AttributeError):
            lead = None
        status = settlement.get("status") if settlement else "PENDING"
        if status not in {"WON", "LOST", "VOID", "PARTIAL_VOID", "PENDING"}:
            diagnostics["INVALID_SETTLEMENT_STATUS"] += 1
            status, settlement = "PENDING", None
        partial_void = bool((settlement or {}).get("partial_void")) or status == "PARTIAL_VOID"
        adjusted = finite(prediction.get("correlation_adjusted_joint_probability"))
        if adjusted is not None and not 0 < adjusted < 1:
            adjusted = None
            diagnostics["INVALID_STORED_CORRELATION_ADJUSTED_PROBABILITY"] += 1
        rows.append({
            "prediction_id": identity, "source_product": "COMBO",
            "source_prediction_fingerprint": digest(prediction),
            "source_settlement_fingerprint": digest(settlement) if settlement else None,
            "cohort": prediction.get("statistics_cohort") or prediction.get("combo_selection_policy") or "LEGACY_COMBO",
            "policy_version": prediction.get("combo_selection_policy") or prediction.get("policy"),
            "leg_count": len(legs), "legs": legs,
            "combined_odds": _text(combined), "naive_joint_probability": _text(naive),
            "declared_joint_probability": _text(declared),
            "joint_probability_provenance": "PRODUCT_OF_FROZEN_LEG_ESTIMATES_IN_STORED_ORDER",
            "correlation_adjusted_joint_probability": _text(adjusted),
            "correlation_adjustment_status": "STORED" if adjusted is not None else "NOT_AVAILABLE",
            "correlation_review": prediction.get("correlation_review"),
            "ranking_score_if_independent": prediction.get("ranking_score_if_independent"),
            "published_at": publication, "kickoff_lead_minutes": lead,
            "settled_at": (settlement or {}).get("settled_at_utc"),
            "status": status, "partial_void": partial_void,
            "remaining_leg_tracking_count": len((settlement or {}).get("pending_legs", [])),
            "flat_unit_pnl": (settlement or {}).get("unit_result"),
            "lead_time_bucket": band(lead, (10, 25, 45, 90, 360)),
            "combined_odds_bucket": band(combined, (2, 3, 5, 10, 20)),
        })
    return sorted(rows, key=lambda r: r["prediction_id"]), dict(diagnostics)


def summarize_coupons(rows: list[dict]) -> dict:
    """One statistical observation per coupon; voids excluded from binary scores."""
    counts = Counter(r["status"] for r in rows)
    settled = [r for r in rows if r["status"] != "PENDING"]
    values = [finite(r["flat_unit_pnl"]) for r in settled]
    pnl = sum(values, Decimal(0)) if all(v is not None for v in values) else None
    binary = [r for r in settled if r["status"] in {"WON", "LOST"} and not r["partial_void"]]
    pairs = [(float(p), int(r["status"] == "WON")) for r in binary
             if (p := finite(r["naive_joint_probability"])) is not None and 0 < p < 1
             and 0 < float(p) < 1]
    probabilities = [float(p) for r in rows if (p := finite(r["naive_joint_probability"])) is not None]
    scores = probability_metrics(pairs)
    scores["coupon_probability_observations"] = scores.pop("probability_observations")
    return {
        "published": len(rows), "settled": len(settled), "pending": counts["PENDING"],
        **{k: counts[k] for k in ("WON", "LOST", "VOID", "PARTIAL_VOID")},
        "partial_void_count": sum(r["partial_void"] for r in settled),
        "flat_unit_pnl": _text(pnl),
        "flat_roi": float(pnl/len(settled)) if pnl is not None and settled else None,
        "observed_hit_rate": sum(r["status"] == "WON" for r in binary)/len(binary) if binary else None,
        "mean_predicted_joint_published": mean(probabilities) if probabilities else None,
        "mean_predicted_joint_scored": mean(p for p, _ in pairs) if pairs else None,
        "binary_missing_probability": sum(finite(r["naive_joint_probability"]) is None for r in binary),
        "unscorable_float_extreme_probability": sum((p := finite(r["naive_joint_probability"])) is not None
                                                    and not 0 < float(p) < 1 for r in binary),
        "model_learning_observations": 0, **scores,
    }


def coupon_report(ledger: object, *, now: datetime) -> dict:
    rows, diagnostics = coupon_rows(ledger, now=now)
    cohorts = sorted({r["cohort"] for r in rows} | {DOUBLE_COHORT})
    groups = defaultdict(list)
    for row in rows:
        for dimension in ("lead_time_bucket", "combined_odds_bucket"):
            groups[(row["cohort"], dimension, row[dimension])].append(row)
    report = {
        "version": VERSION, "as_of": utc(now).isoformat(), "metrics_unit": "COUPON",
        "model_learning_observations": 0, "fit_invoked": False,
        "selection_effect": "NONE", "rows": rows, "diagnostics": diagnostics,
        "overall": summarize_coupons(rows),
        "cohorts": {c: summarize_coupons([r for r in rows if r["cohort"] == c]) for c in cohorts},
        "segments": [{"cohort": c, "dimension": d, "value": v, **summarize_coupons(sample)}
                     for (c, d, v), sample in sorted(groups.items())],
        "source_evidence_fingerprint": digest([[r["prediction_id"], r["source_prediction_fingerprint"],
                                               r["source_settlement_fingerprint"], r["published_at"]] for r in rows]),
        "limitations": [
            "Naive joint estimates assume independence; correlation screening is not a probability adjustment.",
            "Frozen ensemble estimates may be market-inclusive and are not proven calibrated model probabilities.",
            "Coupon diagnostics are never model-learning observations or calibration-fit rows.",
            "Coupons can share fixtures across time; no independence or significance claim is made.",
            "Early losses mature sooner than winners; incomplete cohorts can distort descriptive calibration.",
            "No fresh bookmaker odds were acquired; only original publication-time evidence was read.",
        ],
    }
    report["report_fingerprint"] = digest(report)
    return report
