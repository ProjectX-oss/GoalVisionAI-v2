"""LIVE_SELECTION_POLICY_COMPARATOR_V1, pure pre-refresh nominations only.

A and B see exactly the same immutable original-time inputs and exposure set.
No outcome enters selection. An unavailable counterfactual final refresh is
never treated as a successful publication, or as executable-price evidence.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal

from app.adaptive_lab.contracts import digest, utc
from app.adaptive_lab.devig_research import devig
from app.adaptive_lab.performance import finite
from app.lab_v2_shadow.market_consensus import _FAMILIES
from .engine import readiness
from .policy import POLICY
from .context_research import forecast

VERSION = "LIVE_SELECTION_POLICY_COMPARATOR_V1"


def market_evidence(candidate: dict, pool: list[dict]) -> dict:
    """Complete same-state/same-clock feed family; never call 1/odds fair p."""
    quote = candidate["quote"]
    family = next((v for v in _FAMILIES.values() if candidate["market"] in v), ())
    values = {}
    for row in pool:
        q = row["quote"]
        if row["market"] not in family or any(q.get(k) != quote.get(k) for k in (
            "fixture_id", "state_fingerprint", "origin_timestamp", "retrieved_at", "provider", "bookmaker_id"
        )):
            continue
        if utc(q["retrieved_at"]) > utc(candidate["prepared_at_utc"]) or utc(q["origin_timestamp"]) > utc(q["retrieved_at"]):
            continue
        if q.get("quote_fingerprint") != digest({k:v for k,v in q.items() if k != "quote_fingerprint"}):
            return {"status": "MARKET_INTEGRITY_FAILURE"}
        if any(q.get(k) for k in ("blocked", "stopped", "finished", "suspended")):
            return {"status": "MARKET_NOT_ACTIVE"}
        market, odds = row["market"], q["decimal_odds"]
        if market in values and values[market] != odds:
            return {"status": "AMBIGUOUS_MARKET_QUOTE"}
        values[market] = odds
    if set(values) != set(family) or not values:
        return {"status": "COMPLETE_AS_OF_MARKET_UNAVAILABLE"}
    try:
        result = devig(values)
    except ValueError:
        return {"status": "INVALID_COMPLETE_MARKET"}
    return {"status": "AVAILABLE", "quote_set_fingerprint": digest(values), **result,
            "price_kind": "INDICATIVE_PROVIDER_FEED_NOT_EXECUTION_GUARANTEE"}


def compare_pool(candidates: list[dict], *, at: datetime,
                 exposures: list[dict] = ()) -> dict:
    """Initial eligibility at original preparation, then deterministic ranking.

The adapter must provide an observed pool boundary. Ranking as-of the last
retained preparation is a retrospective nomination, not an exact cycle replay.
"""
    if not 0 <= len(candidates) <= 6000:
        raise ValueError("POOL_BOUND")
    ids = [p["prediction_id"] for p in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_CANDIDATE_ID")
    for p in candidates:
        if utc(p["prepared_at_utc"]) > utc(at):
            raise ValueError("FUTURE_CANDIDATE")
        if any(k in p for k in ("outcome", "target", "settlement", "result_label")):
            raise ValueError("LABEL_IN_SELECTION")
    rows = []
    accepted = {"A_CURRENT_60_70": [], "B_VALUE_CONTROL": [], "C_CONTEXT_CONFIDENCE": []}
    counts = {name: Counter() for name in accepted}
    for p in sorted(candidates, key=lambda p: p["prediction_id"]):
        prepared = utc(p["prepared_at_utc"])
        prior = [x for x in exposures if utc(x["known_at"]) < prepared]
        probability, odds = finite(p.get("ensemble_probability")), finite(p.get("captured_odds"))
        if probability is None or odds is None:
            raise ValueError("NONFINITE_CANDIDATE")
        if str(p["quote"]["decimal_odds"]) != str(p["captured_odds"]):
            raise ValueError("ODDS_REPLAY_MISMATCH")
        a = readiness(p["state"], p["quote"], p["ensemble_probability"],
                      uncertainty=p["uncertainty_penalty"], now=prepared, previous=prior,
                      allow_provider_feed=True, quote_age_diagnostic=True, probability_band=True)
        market = market_evidence(p, candidates)
        b = set(a)
        ev = probability*odds-1
        if ev <= 0:
            b.add("RESEARCH_NON_POSITIVE_EV")
        if market["status"] != "AVAILABLE":
            b.add("COMPLETE_AS_OF_MARKET_UNAVAILABLE")
        else:
            fair = Decimal(market["methods"]["MULTIPLICATIVE"]["probabilities"][p["market"]])
            if probability <= fair:
                b.add("RESEARCH_NON_POSITIVE_FAIR_EDGE")
            if abs(probability-fair) > Decimal(str(POLICY.max_market_divergence)):
                b.add("RESEARCH_FAIR_MARKET_DISAGREEMENT")
        context = forecast(p, at=prepared)
        c = set(a) | set(context["blockers"])
        # PREMATCH's calibration cannot be silently applied to the LIVE model.
        # No reviewed LIVE artifact contract exists: self-asserted p is not accepted.
        c.update(("AS_OF_LIVE_CALIBRATOR_UNAVAILABLE", "INDEPENDENT_CONTEXT_EFFECTS_UNVALIDATED"))
        by_policy = {"A_CURRENT_60_70": sorted(a), "B_VALUE_CONTROL": sorted(b),
                     "C_CONTEXT_CONFIDENCE": sorted(c)}
        for name, reasons in by_policy.items():
            counts[name].update(reasons)
            if not reasons:
                accepted[name].append(p)
        rows.append({"candidate_id": p["prediction_id"], "fixture_id": p["fixture_id"],
                     "source_fingerprint": digest(p), "probability": str(probability),
                     "odds": str(odds), "ev": str(ev), "market_evidence": market,
                     "context": context, "blockers": by_policy})
    policies = {}
    for name, eligible in accepted.items():
        ordered = sorted(eligible, key=lambda p: (-Decimal(str(p["ensemble_probability"])), p["prediction_id"]))
        policies[name] = {"eligible_versions": len(eligible),
                          "nomination": ordered[0]["prediction_id"] if ordered else None,
                          "status": "PRE_REFRESH_NOMINATION" if ordered else "NO_PICK",
                          "blocker_counts": dict(sorted(counts[name].items())),
                          "final_refresh_verified": False, "publications": 0}
    value = {"version": VERSION, "at": utc(at).isoformat(), "candidate_count": len(candidates),
             "source_pool_fingerprint": digest(sorted(candidates, key=lambda p:p["prediction_id"])),
             "exposure_fingerprint": digest(sorted(exposures, key=lambda p:(p["known_at"], p["prediction_id"]))),
             "policies": policies, "rows": rows, "mode": "RETROSPECTIVE_PRE_REFRESH_REPLAY",
             "selection_effect": "NONE", "provider_calls": 0, "telegram_sends": 0}
    value["fingerprint"] = digest(value)
    return value
