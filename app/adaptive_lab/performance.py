"""Lab-only descriptive snapshots from confirmed publications and immutable results."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from math import log
from statistics import mean, median
from .contracts import utc

VERSION = "LAB_PERFORMANCE_SNAPSHOT_V1"
LEAD_BOUNDS = (10, 25, 45, 90)
AGE_BOUNDS = (60, 300, 900, 1800, 3600, 14400)


def finite(value):
    try:
        v = Decimal(str(value))
        return v if v.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def band(value, bounds):
    value = finite(value)
    if value is None:
        return "MISSING"
    if value < 0:
        return "INVALID_NEGATIVE"
    for i, bound in enumerate(bounds):
        if value < Decimal(str(bound)):
            return f"[{bounds[i-1] if i else 0},{bound})"
    return f"[{bounds[-1]},inf)"


def timing(prediction: dict, *, selected_at=None) -> dict:
    """Only timestamps captured at selection; never current age of old odds."""
    selected = selected_at or prediction.get("prepared_at_utc") or prediction.get("prediction_created_at")
    kickoff = prediction.get("kickoff_utc")
    origin = prediction.get("provider_origin_timestamp_utc") or prediction.get("quote_origin_timestamp")
    def difference(a, b, divisor):
        try:
            return (utc(a) - utc(b)).total_seconds() / divisor
        except (ValueError, TypeError, AttributeError):
            return None
    lead = difference(kickoff, selected, 60)
    age = difference(selected, origin, 1)
    return {"prematch_lead_minutes": lead, "prematch_lead_minutes_bucket": band(lead, LEAD_BOUNDS),
            "odds_age_seconds": age, "odds_age_seconds_bucket": band(age, AGE_BOUNDS)}


def probability_metrics(pairs: list[tuple[float, int]]) -> dict:
    """Observed calibration diagnostics; does not fit or modify a probability."""
    bins = []
    for i in range(10):
        sample = [(p, y) for p, y in pairs if min(9, int(p * 10)) == i]
        if sample:
            p, y = mean(v[0] for v in sample), mean(v[1] for v in sample)
            bins.append({"lower": i / 10, "upper": (i + 1) / 10,
                         "n": len(sample), "predicted": p, "observed": y, "error": p - y})
    n = len(pairs)
    return {"probability_observations": n,
            "brier": mean((p-y)**2 for p, y in pairs) if n else None,
            "log_loss": mean(-y*log(p)-(1-y)*log(1-p) for p, y in pairs) if n else None,
            "ece": sum(b["n"]*abs(b["error"]) for b in bins)/n if n else None,
            "mce": max(abs(b["error"]) for b in bins) if bins else None,
            "reliability_bins": bins}


def summarize(rows: list[dict], *, product: str) -> dict:
    counts = Counter(r["status"] for r in rows)
    settled = [r for r in rows if r["status"] != "PENDING"]
    pnl_values = [r["pnl"] for r in settled if r["pnl"] is not None]
    complete = len(pnl_values) == len(settled)
    pnl = sum(pnl_values, Decimal(0)) if complete else None
    odds = [r["odds"] for r in rows if r["odds"] is not None and r["odds"] > 1]
    binary = [r for r in rows if r["status"] in {"WON", "LOST"}]
    wins = counts["WON"]
    pairs = [(float(r["probability"]), int(r["status"] == "WON")) for r in binary
             if r["probability"] is not None and 0 < r["probability"] < 1] if product == "SINGLE" else []
    result = {"total_published": len(rows), "total_settled": len(settled),
              **{k: counts[k] for k in ("WON", "LOST", "VOID", "PARTIAL_VOID")},
              "partial_void_count": sum(r["partial_void"] for r in settled),
              "pending": counts["PENDING"], "pending_settlements": counts["PENDING"],
              "hit_rate": wins/len(binary) if binary else None,
              "flat_unit_pnl": str(pnl) if pnl is not None else None,
              "flat_roi": float(pnl / len(settled)) if pnl is not None and settled else None,
              "average_odds": str(mean(odds)) if odds else None,
              "median_odds": str(median(odds)) if odds else None,
              "odds_sample": len(odds), "missing_pnl_count": len(settled)-len(pnl_values),
              "missing_probability_count": sum(r["probability"] is None for r in rows),
              **probability_metrics(pairs)}
    result["roi"] = str(pnl / len(settled)) if pnl is not None and settled else None
    if product == "COMBO":
        result["average_combined_odds"] = result["average_odds"]
        result["predictive_calibration_observations"] = 0
    return result


def dimensions(prediction: dict) -> dict:
    p = finite(prediction.get("ensemble_probability"))
    odds = finite(prediction.get("captured_odds"))
    market_p = finite(prediction.get("market_fair_probability"))
    t = timing(prediction)
    return {"odds_band": band(odds, (1.5, 2, 3, 5, 10)),
            "probability_band": band(p, (.4, .5, .6, .7, .8, .9)),
            "market": str(prediction.get("market") or "MISSING"),
            "league": str(prediction.get("league_id") or prediction.get("league") or "MISSING"),
            "competition": str(prediction.get("competition_profile") or "MISSING"),
            "lead_time_bucket": t["prematch_lead_minutes_bucket"],
            "odds_age_bucket": t["odds_age_seconds_bucket"],
            "model_confidence_bucket": str(prediction.get("confidence") or "MISSING"),
            "model_market_disagreement_bucket": band(
                abs(p-market_p) if p is not None and market_p is not None else None, (.05, .10, .20, .30)),
            "value_cohort": ("MISSING" if p is None or odds is None else
                              "NEGATIVE_EV" if p*odds < 1 else "ZERO_EV" if p*odds == 1 else "POSITIVE_EV")}


def _before(value, now):
    try:
        return utc(value) <= utc(now)
    except (ValueError, TypeError, AttributeError):
        return False


def performance_snapshot(ledger, *, now: datetime) -> dict:
    """One stake per confirmed ticket; void stakes count in settled ROI denominator."""
    products = {}
    diagnostic = Counter()
    for product, prediction_kind, result_kind, prefixes in (
        ("SINGLE", "single_prediction", "single_settlement", ("single_prediction:",)),
        ("COMBO", "prediction", "settlement", ("combo_prediction:", "prediction:"))):
        rows = []
        for prediction in ledger.all(prediction_kind):
            pid = prediction["prediction_id"]
            receipt = next((r for prefix in prefixes if (r := ledger.get("receipt", prefix+pid))
                            and r.get("status") == "SENT"), None)
            if receipt is None:
                continue
            if not _before(receipt.get("sent_at_utc"), now):
                diagnostic["MISSING_OR_FUTURE_PUBLICATION_TIME"] += 1
                continue
            result = ledger.get(result_kind, pid)
            if result and not _before(result.get("settled_at_utc"), now):
                diagnostic["MISSING_OR_FUTURE_SETTLEMENT_TIME"] += 1
                result = None
            status = result.get("status") if result else "PENDING"
            if status not in {"WON", "LOST", "VOID", "PARTIAL_VOID", "PENDING"}:
                diagnostic["INVALID_SETTLEMENT_STATUS"] += 1
                status, result = "PENDING", None
            if product == "SINGLE":
                d = dimensions(prediction)
                p = finite(prediction.get("ensemble_probability"))
                odds = finite(prediction.get("captured_odds"))
            else:
                legs = prediction.get("legs") or []
                leg_dimensions = [dimensions(leg) for leg in legs]
                d = {k: "|".join(sorted({v[k] for v in leg_dimensions}))
                     for k in leg_dimensions[0]} if leg_dimensions else {}
                p = finite(prediction.get("estimated_probability_if_independent"))
                odds = finite(prediction.get("combined_odds"))
                d["odds_band"] = band(odds, (2, 3, 5, 10, 20))
                d["probability_band"] = band(p, (.2, .3, .4, .5, .6, .7))
                d["value_cohort"] = ("MISSING" if p is None or odds is None else
                                    "NEGATIVE_EV" if p*odds < 1 else "ZERO_EV" if p*odds == 1 else "POSITIVE_EV")
            rows.append({"status": status, "probability": p, "odds": odds,
                         "pnl": finite(result.get("unit_result")) if result else None,
                         "partial_void": bool((result or {}).get("partial_void")), "dimensions": d})
        products[product] = rows
    segments = {}
    for product, rows in products.items():
        groups = defaultdict(list)
        for row in rows:
            for key, value in row["dimensions"].items():
                groups[(key, value)].append(row)
        segments[product] = [{"dimension": key, "value": value, **summarize(group, product=product)}
                             for (key, value), group in sorted(groups.items())]
    return {"version": VERSION, "accounting": "LAB_ONLY_HYPOTHETICAL_ONE_UNIT",
            "as_of": utc(now).isoformat(), "roi_denominator": "ALL_SETTLED_TICKETS_INCLUDING_VOID",
            "odds_population": "ALL_CONFIRMED_PUBLISHED_TICKETS",
            "hit_rate_population": "WON_PLUS_LOST_EXCLUDING_VOID_AND_PARTIAL_VOID",
            "status": "PARTIAL" if diagnostic else "COMPLETE", "diagnostics": dict(diagnostic),
            **{product: summarize(rows, product=product) for product, rows in products.items()},
            "negative_ev": {p: summarize([r for r in rows if r["dimensions"].get("value_cohort") == "NEGATIVE_EV"],
                                         product=p) for p, rows in products.items()},
            "non_positive_ev": {p: summarize([r for r in rows if r["dimensions"].get("value_cohort") in {"NEGATIVE_EV", "ZERO_EV"}],
                                             product=p) for p, rows in products.items()},
            "segments": segments}


def candidate_timing_diagnostics(candidates: list[dict], *, selected_at: datetime) -> dict:
    """Candidate denominators include rejected rows; no-pick is not a loss."""
    groups = defaultdict(list)
    for c in candidates:
        t = timing(c, selected_at=selected_at)
        for key in ("prematch_lead_minutes_bucket", "odds_age_seconds_bucket"):
            groups[(key, t[key])].append(c)
    result = []
    for (dimension, value), rows in sorted(groups.items()):
        reasons = Counter(reason for r in rows for reason in
                          set(r.get("rejection_reasons") or []) | set(r.get("readiness_reasons") or []))
        invalid = sum(any("INVALID" in reason or "STALE" in reason for reason in
                          set(r.get("rejection_reasons") or []) | set(r.get("hard_failures") or [])) for r in rows)
        disagreement = []
        for r in rows:
            p, q = finite(r.get("ensemble_probability")), finite(r.get("market_fair_probability"))
            if p is not None and q is not None:
                disagreement.append(float(abs(p-q)))
        result.append({"dimension": dimension, "value": value, "candidate_count": len(rows),
                       "no_pick_reasons": dict(sorted(reasons.items())),
                       "invalid_or_stale_count": invalid, "invalid_or_stale_rate": invalid/len(rows),
                       "mean_model_market_disagreement": mean(disagreement) if disagreement else None})
    return {"population": "EVALUATED_CANDIDATE_MARKETS", "groups": result,
            "unscored_fixture_timing": "UNAVAILABLE_WITHOUT_FROZEN_CANDIDATE",
            "publication_policy_changed": False}


def snapshot_from_path(path, *, now: datetime) -> dict:
    """Bounded read-only snapshot; missing source is explicit, never zero performance."""
    from pathlib import Path
    import sqlite3
    from .observations import ReadOnlyLedger
    reader = None
    try:
        reader = ReadOnlyLedger(Path(path))
        return performance_snapshot(reader, now=now)
    except (OSError, ValueError, sqlite3.Error):
        return {"version": VERSION, "accounting": "LAB_ONLY_HYPOTHETICAL_ONE_UNIT",
                "as_of": utc(now).isoformat(), "status": "UNAVAILABLE",
                "reason": "LAB_LEDGER_SNAPSHOT_UNAVAILABLE"}
    finally:
        if reader is not None:
            reader.close()
