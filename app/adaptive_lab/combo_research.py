"""Offline coupon research; no production registration, learning, fitting or transport.

Use immutable original candidates and a separate result map. Selection never
receives labels. Descriptive cohorts are not randomized/paired strategy trials.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from itertools import combinations
from random import Random
from statistics import mean
from zoneinfo import ZoneInfo
from .contracts import digest, utc
from .performance import finite, probability_metrics
from .combo_evidence import coupon_report, summarize_coupons

VERSION = "COMBO_QUALITY_RESEARCH_V1"
MIN_CI_COUPONS = 30
MIN_CI_CLUSTERS = 7
EXPECTED_COHORTS = (
    "LEGACY_COMBO", "LAB_COMBO_ACCURACY_FROM_SINGLES_V1",
    "LAB_COMBO_ACCURACY_FROM_SINGLES_V2_LEG_MIN_ODDS_130",
    "COMBO_MARKET_20261004_V1", "COMBO_AGREEMENT_20261004_V1",
    "COMBO_DOUBLE_20261006_V1",
)


def joint_diagnostics(legs: list[dict]) -> dict:
    """Frechet bounds are mathematical bounds, NOT fitted joint probabilities."""
    probs = [finite(l.get("model_probability", l.get("ensemble_probability"))) for l in legs]
    valid = bool(probs) and all(p is not None and 0 < p < 1 for p in probs)
    product = Decimal(1)
    if valid:
        for p in probs:
            product *= p
    fixtures = [l.get("fixture_id") for l in legs]
    teams = [l.get(k) for l in legs for k in ("home_team_id", "away_team_id")]
    leagues = [l.get("league_id") for l in legs]
    families = [set(l.get("signal_independence_groups", [])) for l in legs]
    risks = []
    if len(set(fixtures)) != len(fixtures):
        risks.append("SHARED_FIXTURE")
    if any(v is None for v in teams+fixtures):
        risks.append("MISSING_TEAM_OR_FIXTURE_IDENTITY")
    elif len(set(teams)) != len(teams):
        risks.append("SHARED_TEAM")
    if any(v is not None and leagues.count(v) > 1 for v in leagues):
        risks.append("SHARED_LEAGUE")
    if any(a & b for a,b in combinations(families, 2)):
        risks.append("SHARED_SIGNAL_FAMILY")
    market_families = [market_family(l.get("market", "")) for l in legs]
    if len(set(market_families)) < len(market_families):
        risks.append("SHARED_MARKET_FAMILY")
    if not all(families):
        risks.append("SIGNAL_DEPENDENCY_EVIDENCE_MISSING")
    return {
        "version": "COMBO_JOINT_PROBABILITY_RESEARCH_V1",
        "naive_joint_probability": str(product) if valid else None,
        "frechet_lower_bound": str(max(Decimal(0), sum(probs)-len(probs)+1)) if valid else None,
        "frechet_upper_bound": str(min(probs)) if valid else None,
        "correlation_adjusted_probability": None,
        "empirical_joint_calibrator": None, "fit_status": "INSUFFICIENT_EVIDENCE",
        "risk_flags": sorted(risks),
        "risk_screen_is_joint_model": False,
    }


def market_family(market: str) -> str:
    market = market or ""
    return ("1X2" if market in {"HOME_WIN", "DRAW", "AWAY_WIN"} else
            "TOTALS" if market.startswith(("OVER_", "UNDER_")) else
            "BTTS" if market.startswith("BTTS_") else "UNKNOWN")


def clustered_interval(rows: list[dict]) -> dict:
    """Descriptive day/fixture-connected cluster bootstrap, never strategy ranking."""
    settled = [r for r in rows if r["status"] != "PENDING"]
    parent = list(range(len(settled)))
    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen = {}
    for i, row in enumerate(settled):
        day = utc(row["published_at"]).astimezone(ZoneInfo("Europe/Riga")).date().isoformat()
        keys = [("day", day)] + [("fixture", str(l["fixture_id"])) for l in row["legs"]]
        for key in keys:
            if key in seen:
                parent[root(i)] = root(seen[key])
            else:
                seen[key] = i
    groups = defaultdict(list)
    for i,row in enumerate(settled):
        groups[root(i)].append(row)
    base = {"minimum_coupons": MIN_CI_COUPONS, "minimum_clusters": MIN_CI_CLUSTERS,
            "coupons": len(settled), "clusters": len(groups), "roi_95_interval": None,
            "ranking_eligible": False, "bootstrap_seed": 1708}
    if len(settled) < MIN_CI_COUPONS or len(groups) < MIN_CI_CLUSTERS or any(r["status"] == "PENDING" for r in rows):
        return {**base, "status": "INSUFFICIENT_EVIDENCE_OR_IMMATURE_COHORT"}
    if any(finite(r["flat_unit_pnl"]) is None for r in settled):
        return {**base, "status": "MISSING_PNL"}
    random = Random(1708)
    clusters = list(groups.values())
    boot = []
    for _ in range(2000):
        sample = [r for __ in clusters for r in random.choice(clusters)]
        boot.append(mean(float(r["flat_unit_pnl"]) for r in sample))
    boot.sort()
    return {**base, "status": "DESCRIPTIVE_CLUSTER_BOOTSTRAP",
            "roi_95_interval": [boot[49], boot[1949]],
            "limitation": "Nonrandom cohorts, selection bias and unobserved dependence remain."}


def performance_comparison(ledger: object, *, now: datetime) -> dict:
    """Extend the authoritative coupon exporter instead of creating another ledger."""
    result = coupon_report(ledger, now=now)
    result["comparison_version"] = "COMBO_PERFORMANCE_COMPARISON_V1"
    rows = result["rows"]
    for cohort in EXPECTED_COHORTS:
        result["cohorts"].setdefault(cohort, summarize_coupons([]))
    failure_segments = defaultdict(list)
    losing = []
    for row in rows:
        row["joint_diagnostics"] = joint_diagnostics(row["legs"])
        families = {market_family(l["market"]) for l in row["legs"]}
        row["market_family"] = next(iter(families)) if len(families) == 1 else "MIXED"
        row["losing_leg_count_known"] = sum(l["outcome"] == "LOST" for l in row["legs"])
        row["unknown_leg_count"] = sum(l["outcome"] == "UNKNOWN" for l in row["legs"])
        if row["status"] == "LOST":
            losing.append({"prediction_id": row["prediction_id"], "cohort": row["cohort"],
                           "losing_legs": [l for l in row["legs"] if l["outcome"] == "LOST"],
                           "unknown_leg_count": row["unknown_leg_count"],
                           "joint_diagnostics": row["joint_diagnostics"]})
        for dimension in ("leg_count", "market_family", "lead_time_bucket", "combined_odds_bucket"):
            failure_segments[(row["cohort"], dimension, str(row[dimension]))].append(row)
    result["losing_coupon_analysis"] = losing
    result["additional_segments"] = [
        {"cohort": c, "dimension": d, "value": v, **summarize_coupons(sample)}
        for (c,d,v),sample in sorted(failure_segments.items())]
    # Leg calibration is diagnostic and never fed into model learning.
    leg_groups = defaultdict(dict)
    for row in rows:
        for leg in row["legs"]:
            for dim,value in (("market",leg["market"]),("league",str(leg["league_id"])),
                              ("probability_kind",leg["probability_kind"])):
                leg_groups[(row["cohort"],dim,value)][(leg["fixture_id"],leg["market"],leg["candidate_id"])] = leg
    result["leg_diagnostics"] = []
    for (cohort,dim,value), mapping in sorted(leg_groups.items()):
        legs = list(mapping.values())
        pairs = [(float(p),int(l["outcome"]=="WON")) for l in legs
                 if l["outcome"] in {"WON","LOST"}
                 and (p:=finite(l["model_probability"])) is not None and 0 < float(p) < 1]
        result["leg_diagnostics"].append({
            "cohort":cohort,"dimension":dim,"value":value,
            "candidate_leg_versions":len(legs),"unique_fixtures":len({l["fixture_id"] for l in legs}),
            "outcomes":dict(Counter(l["outcome"] for l in legs)), **probability_metrics(pairs)})
    result["confidence"] = {c: clustered_interval([r for r in rows if r["cohort"]==c]) for c in result["cohorts"]}
    result["paired_strategy_score_delta"] = None
    result["ranking_status"] = "BLOCKED_NONPAIRED_COHORTS_AND_INSUFFICIENT_FORWARD_EVIDENCE"
    result["report_fingerprint"] = digest({k:v for k,v in result.items() if k != "report_fingerprint"})
    return result


class MemoryLedger:
    """Selection writes only here; no sqlite connection or external side effect."""
    def __init__(self, predictions: list[dict] = ()) -> None:
        self.rows = {}
        for prediction in predictions:
            self.rows[("prediction", prediction["prediction_id"])] = deepcopy(prediction)
            self.rows[("claim", "combo_prediction:"+prediction["prediction_id"])] = {"research_exposure":True}

    def all(self, kind: str) -> list[dict]:
        return [deepcopy(v) for (k,_),v in self.rows.items() if k == kind]

    def get(self, kind: str, identity: str) -> dict | None:
        return deepcopy(self.rows.get((kind,identity)))

    def append(self, kind: str, identity: str, value: dict) -> bool:
        key = kind,identity
        if key in self.rows:
            if self.rows[key] != value:
                raise ValueError("RESEARCH_IMMUTABLE_CONFLICT")
            return False
        self.rows[key] = deepcopy(value)
        return True


def quality_value_screen(candidates: list[dict], *, at: datetime) -> dict:
    """Explain C's no-selection without pretending raw p is calibrated p."""
    from app.lab_v2_shadow.publication_policy import review_accuracy_publication
    counts = Counter()
    rows = []
    for c in candidates:
        review = review_accuracy_publication(c, now=at)
        reasons = set(review["rejection_reasons"])
        # No reviewed as-of calibration/joint forecast contract exists in V1.
        # Fail closed even if an untrusted row says calibration_status=CALIBRATED.
        reasons.update(("AS_OF_VERIFIED_LEG_CALIBRATION_UNAVAILABLE",
                        "VALIDATED_JOINT_PROBABILITY_UNAVAILABLE"))
        p, q, odds = (finite(c.get(k)) for k in
                       ("ensemble_probability", "market_fair_probability", "captured_odds"))
        if q is None or not 0 < q < 1:
            reasons.add("COMPLETE_CURRENT_DEVIG_MARKET_UNAVAILABLE")
        if not c.get("independent_probability_available"):
            reasons.add("INDEPENDENT_MODEL_EVIDENCE_UNAVAILABLE")
        counts.update(reasons)
        rows.append({"candidate_id":c["candidate_id"], "fixture_id":c["fixture_id"],
                     "market":c["market"], "league_id":c.get("league_id"),
                     "raw_model_probability":str(p) if p is not None else None,
                     "market_fair_probability":str(q) if q is not None else None,
                     "raw_probability_difference":str(p-q) if p is not None and q is not None else None,
                     "raw_ev":str(p*odds-1) if p is not None and odds is not None else None,
                     "calibrated_probability":None, "reasons":sorted(reasons)})
    return {"selected":[], "status":"NO_COMBO_SELECTION",
            "blocked_by":["AS_OF_VERIFIED_LEG_CALIBRATION_UNAVAILABLE",
                          "VALIDATED_JOINT_PROBABILITY_UNAVAILABLE"],
            "rejection_counts":dict(counts),"candidate_diagnostics":rows,
            "ranking_implemented":False,
            "next_gate":"Define and validate the joint/calibration evidence contract before enabling a ranker."}


def replay(candidates: list[dict], exposures: list[dict], *, at: datetime, strategy: str | None = None) -> dict:
    """Original-time A/B replay in an isolated process with explicit policy flags.

    No outcomes accepted. C is fail-closed until a separately reviewed, as-of
    calibration + joint-probability evidence contract exists. It must not rank
    uncalibrated p as calibrated quality or invent a correlation coefficient.
    """
    import os
    from app.lab_v2_shadow.combo_double import prepare as double_prepare
    from app.lab_v2_shadow.publication import prepare_v2_publications
    if not 1 <= len(candidates) <= 6000:
        raise ValueError("RESEARCH_POOL_CAP_OR_EMPTY")
    now = utc(at)
    for c in candidates:
        for key in ("goalvision_retrieved_at_utc", "provider_origin_timestamp_utc",
                    "final_review_completed_at_utc"):
            if c.get(key) and utc(c[key]) > now:
                raise ValueError("RESEARCH_FUTURE_INPUT")
        if any(k in c for k in ("target", "outcome", "settlement", "result_label")):
            raise ValueError("RESEARCH_LABEL_IN_SELECTION")
    pool_fingerprint = digest(candidates)
    flags = {"GOALVISION_COMBO_DOUBLE_170":"1", "GOALVISION_COMBO_CONSERVATIVE_AGREEMENT":"0",
             "GOALVISION_COMBO_MARKET_PARALLEL":"0", "GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130":"1",
             "GOALVISION_LAB_EVENING_MODE":"1",
             "GOALVISION_LAB_SINGLE_MIN_ODDS_130":"0", "GOALVISION_LAB_SINGLE_MIN_ODDS_150":"1"}
    if strategy not in {None, "A_CURRENT_DOUBLE", "B_SINGLES_BASED_V2", "C_QUALITY_VALUE_FIRST"}:
        raise ValueError("RESEARCH_STRATEGY_UNKNOWN")
    a, ad, b = [], {}, {"combos": [], "combo_diagnostics": {}}
    previous = {k:os.environ.get(k) for k in flags}
    try:
        os.environ.update(flags)
        if strategy in {None, "A_CURRENT_DOUBLE"}:
            a, ad = double_prepare(deepcopy(candidates), MemoryLedger(exposures), now=now, label_origin=True)
        os.environ["GOALVISION_COMBO_DOUBLE_170"] = "0"
        if strategy in {None, "B_SINGLES_BASED_V2"}:
            b = prepare_v2_publications({"candidate_markets":deepcopy(candidates)}, MemoryLedger(exposures),
                                        now=now,label_origin=True,accuracy_combos=True)
    finally:
        for k,v in previous.items():
            if v is None: os.environ.pop(k,None)
            else: os.environ[k]=v
    assert digest(candidates) == pool_fingerprint
    c = quality_value_screen(candidates, at=now) if strategy in {None, "C_QUALITY_VALUE_FIRST"} else {}
    return {"version":"COMBO_SELECTION_RESEARCH_V1", "at":now.isoformat(),
            "candidate_count":len(candidates), "source_pool_fingerprint":pool_fingerprint,
            "exposure_fingerprint":digest(exposures),
            "A_CURRENT_DOUBLE": {"selected":a,"diagnostics":ad},
            "B_SINGLES_BASED_V2": {"selected":b["combos"],"diagnostics":b["combo_diagnostics"]},
            "C_QUALITY_VALUE_FIRST":c, "mode":"RETROSPECTIVE_REPLAY_NOT_PROSPECTIVE",
            "selection_effect":"NONE", "model_learning_observations":0}


def score_replay(coupons: list[dict], facts: dict[str,dict], *, cutoff: datetime) -> list[dict]:
    """Outcome attachment occurs AFTER selection; use frozen odds and regulation results."""
    from app.current_odds_forward_test.service import _won
    rows = []
    for c in coupons:
        legs, outcomes = [], []
        for l in c["legs"]:
            fact = facts.get(str(l["fixture_id"]))
            outcome = "UNKNOWN"
            if (fact and str(fact.get("fixture_id")) == str(l["fixture_id"])
                    and utc(c["created_at_utc"]) < utc(fact["retrieved_at_utc"]) <= utc(cutoff)):
                if fact["outcome"] == "VOID":
                    outcome = "VOID"
                elif fact.get("provider_status") in {"FT","AET","PEN","RESOLVED_REGULATION_FACT"} and all(
                        type(fact.get(k)) is int and 0 <= fact[k] <= 30 for k in ("fulltime_home","fulltime_away")):
                    outcome = "WON" if _won(l["market"],fact["fulltime_home"],fact["fulltime_away"]) else "LOST"
            outcomes.append(outcome)
            legs.append({"fixture_id":l["fixture_id"],"market":l["market"],"outcome":outcome,
                         "bookmaker_odds":l["captured_odds"],"model_probability":l["ensemble_probability"]})
        status = ("LOST" if "LOST" in outcomes else "PENDING" if "UNKNOWN" in outcomes else
                  "VOID" if all(o=="VOID" for o in outcomes) else "PARTIAL_VOID" if "VOID" in outcomes else "WON")
        effective = Decimal(1)
        for leg in legs:
            effective *= Decimal(1) if leg["outcome"]=="VOID" else Decimal(leg["bookmaker_odds"])
        pnl = None if status=="PENDING" else "-1" if status=="LOST" else "0" if status=="VOID" else str(effective-1)
        rows.append({"prediction_id":c["prediction_id"],"published_at":c["created_at_utc"],
                     "status":status,"partial_void":"VOID" in outcomes and not all(o=="VOID" for o in outcomes),
                     "combined_odds":c["combined_odds"],"naive_joint_probability":c["estimated_probability_if_independent"],
                     "flat_unit_pnl":pnl,"legs":legs, "hypothetical":True})
    return rows
