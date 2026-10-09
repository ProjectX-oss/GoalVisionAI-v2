"""Read-only hardening research. Never runs a production cycle or transport."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
import runpy
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.adaptive_lab.contracts import digest, utc
from app.adaptive_lab.performance import probability_metrics
from app.live_lab.policy_research import compare_pool
from app.adaptive_lab.joint_scenarios import scenario_probability


def deny_network() -> None:
    def denied(*args, **kwargs):
        raise RuntimeError("OUTBOUND_NETWORK_DENIED")
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied


def read_live(path: Path, *, until) -> tuple[dict, str]:
    """Verify and materialize inputs, closing the read transaction before replay."""
    helper = runpy.run_path(str(ROOT/"operations/live-combo-research/audit.py"))
    tables, sources = {}, []
    db = helper["readonly"](path)
    try:
        for table in ("live_candidates", "live_claims", "live_publications", "live_settlements", "live_result_receipts"):
            rows = db.execute("SELECT id,document,fingerprint FROM "+table+
                              " WHERE created_at<=? ORDER BY created_at,id LIMIT 20001", (until.isoformat(),)).fetchall()
            if len(rows) > 20000:
                raise ValueError("SOURCE_BOUND")
            tables[table] = [helper["verified"](r[1],r[2],live=True) for r in rows]
            sources.extend([table,r[0],r[2]] for r in rows)
    finally:
        db.close()
    return tables, digest(sources)


def score_rows(rows: list[dict], facts: dict, *, until) -> dict:
    """Descriptive frozen nominations, NOT counterfactual executed bets."""
    from app.current_odds_forward_test.service import _won
    output, pairs = [], []
    pnl = Decimal(0)
    for row in rows:
        fact = facts.get(row["fixture_id"])
        outcome = "PENDING"
        if fact and utc(row["prepared_at_utc"]) < utc(fact["settled_at"]) <= until:
            if fact["status"] == "VOID":
                outcome = "VOID"
            elif fact["status"] == "RESOLVED":
                outcome = "WON" if _won(row["market"], fact["home_goals"], fact["away_goals"]) else "LOST"
        unit = (Decimal(row["captured_odds"])-1 if outcome=="WON" else
                Decimal(-1) if outcome=="LOST" else Decimal(0) if outcome=="VOID" else None)
        if unit is not None:
            pnl += unit
        if outcome in {"WON", "LOST"}:
            pairs.append((float(row["ensemble_probability"]),int(outcome=="WON")))
        output.append({"candidate_id":row["prediction_id"], "fixture_id":row["fixture_id"],
                       "market":row["market"], "prepared_at":row["prepared_at_utc"],
                       "probability":row["ensemble_probability"], "odds":row["captured_odds"],
                       "outcome":outcome, "indicative_flat_pnl":str(unit) if unit is not None else None,
                       "result_fingerprint":fact.get("source_fingerprint") if fact else None})
    counts = Counter(r["outcome"] for r in output)
    settled = len(rows)-counts["PENDING"]
    streak = maximum = 0
    for row in output:
        streak = streak+1 if row["outcome"]=="LOST" else 0
        maximum = max(maximum,streak)
    return {"nominations":len(rows), "unique_fixtures":len({r["fixture_id"] for r in rows}),
            "settled":settled, "outcomes":dict(counts),
            "indicative_flat_pnl":str(pnl), "indicative_flat_roi":str(pnl/settled) if settled else None,
            "observed_hit_rate":sum(y for _,y in pairs)/len(pairs) if pairs else None,
            "max_known_losing_streak":maximum, **probability_metrics(pairs), "rows":output,
            "executed_or_prospective":False, "ranking_eligible":False,
            "confidence_interval":None, "paired_strategy_delta":None,
            "limitation":"Snapshot nominations with actual historical exposure; not cycle selection or verified final refresh."}


def run(database: Path, ledger: Path, *, since, until) -> dict:
    tables, source = read_live(database,until=until)
    all_candidates = {p["prediction_id"]:p for p in tables["live_candidates"]}
    candidates = [p for p in all_candidates.values() if since<=utc(p["prepared_at_utc"])<=until]
    exposures = [{**all_candidates[c["selection_id"]], "known_at": c["created_at"]}
                 for c in tables["live_claims"] if c["selection_id"] in all_candidates]
    pools = defaultdict(list)
    for p in candidates:
        # These exact retained snapshot boundaries are verifiable; an exact
        # initial-vs-final cycle candidate set was not recorded and is not guessed.
        pools[(p["state"]["state_fingerprint"],p["quote"]["retrieved_at"],p["rates"]["source_fingerprint"])].append(p)
    comparisons, chosen = [], defaultdict(list)
    context_rows, market_status = [], Counter()
    for key,pool in sorted(pools.items(),key=lambda item:(max(p["prepared_at_utc"] for p in item[1]),item[0])):
        at = max(utc(p["prepared_at_utc"]) for p in pool)
        comparison = compare_pool(pool,at=at,exposures=exposures)
        comparisons.append(comparison)
        for row in comparison["rows"]:
            context_rows.append(row["context"])
            market_status[row["market_evidence"]["status"]] += 1
        for name,policy in comparison["policies"].items():
            if policy["nomination"]:
                chosen[name].append(all_candidates[policy["nomination"]])
    # Labels are fetched only AFTER all inference and selection have completed.
    from app.dixon_coles_research.sources import results
    raw_facts = results(ledger,database,fixture_ids={p["fixture_id"] for p in candidates},now=until)
    facts, conflicts = {}, set()
    for fact in raw_facts:
        fid = fact["fixture_id"]
        if fid in facts and any(facts[fid][k]!=fact[k] for k in ("status","home_goals","away_goals")):
            conflicts.add(fid)
        else:
            facts[fid] = fact
    for fid in conflicts:
        facts.pop(fid,None)
    policy_summaries = {}
    for name in ("A_CURRENT_60_70", "B_VALUE_CONTROL", "C_CONTEXT_CONFIDENCE"):
        policy_summaries[name] = {"snapshot_pools":len(comparisons),
            "no_pick_pools":sum(c["policies"][name]["nomination"] is None for c in comparisons),
            **score_rows(chosen[name],facts,until=until)}
    contexts = {r["candidate_id"]:r for r in context_rows}
    paired_base, paired_v2, paired_ids = [], [], []
    # Fixed first retained version per fixture/market, not whichever forecast won.
    seen = set()
    for p in sorted(candidates,key=lambda p:(p["prepared_at_utc"],p["prediction_id"])):
        key = p["fixture_id"],p["market"]
        if key in seen:
            continue
        seen.add(key)
        context = contexts[p["prediction_id"]]
        fact = facts.get(p["fixture_id"])
        if context["probabilities"] is None or not fact or fact["status"]!="RESOLVED":
            continue
        if not utc(p["prepared_at_utc"])<utc(fact["settled_at"])<=until:
            continue
        from app.current_odds_forward_test.service import _won
        y = int(_won(p["market"],fact["home_goals"],fact["away_goals"]))
        paired_base.append((float(p["ensemble_probability"]),y))
        paired_v2.append((context["probabilities"][p["market"]],y))
        paired_ids.append({"candidate_id":p["prediction_id"],"fixture_id":p["fixture_id"],"market":p["market"]})
    base_metrics, v2_metrics = probability_metrics(paired_base), probability_metrics(paired_v2)
    post = runpy.run_path(str(ROOT/"operations/live-postmortem/audit.py"))
    actual = post["published_rows"](tables,since=since,until=until)
    cohorts = defaultdict(list)
    for row in actual:
        candidate = all_candidates[row["prediction_id"]]
        cohorts[candidate.get("statistics_cohort") or "LEGACY_EV_FIRST"].append(row)
    cohort_summaries = {k:post["summary"](cohorts[k]) for k in ("LEGACY_EV_FIRST","LIVE_P60_70_20261009_V1")}
    from app.adaptive_lab.observations import ReadOnlyLedger
    from app.adaptive_lab.combo_research import performance_comparison
    connection = ReadOnlyLedger(ledger)
    try:
        coupons = performance_comparison(connection,now=until)
    finally:
        connection.close()
    coupon_rows = []
    for coupon in coupons["rows"]:
        legs = coupon["legs"]
        joint = scenario_probability(legs,None,at=utc(coupon["published_at"]))
        coupon_rows.append({"prediction_id":coupon["prediction_id"],"cohort":coupon["cohort"],
            "status":coupon["status"],"leg_count":coupon["leg_count"],"flat_unit_pnl":coupon["flat_unit_pnl"],
            "source_prediction_fingerprint":coupon["source_prediction_fingerprint"],
            "losing_legs_known":sum(l["outcome"]=="LOST" for l in legs),
            "unknown_legs":sum(l["outcome"]=="UNKNOWN" for l in legs),
            "joint":joint,"calibrated_leg_probability_status":"NO_VERIFIED_FROZEN_ARTIFACT",
            "leg_findings":[{"candidate_id":l["candidate_id"],"fixture_id":l["fixture_id"],
                "market":l["market"],"league_id":l["league_id"],"outcome":l["outcome"],
                "raw_probability":l["model_probability"],"calibrated_probability":None,
                "model_generation":l["model_generation"],"odds":l["bookmaker_odds"],
                "market_fair_probability":l["market_fair_probability"],
                "findings":l["findings"],"shared_signal_groups":l["signal_independence_groups"]} for l in legs]})
    combo = {"source_evidence_fingerprint":coupons["source_evidence_fingerprint"],
             "overall":coupons["overall"],"cohorts":coupons["cohorts"],"confidence":coupons["confidence"],
             "coupons":coupon_rows,"risk_counts":dict(Counter(r for c in coupon_rows for r in c["joint"]["risk_flags"])),
             "loss_count_distribution":dict(Counter(str(c["losing_legs_known"]) for c in coupon_rows if c["status"]=="LOST")),
             "leg_diagnostics":coupons["leg_diagnostics"],"ranking_status":coupons["ranking_status"],
             "joint_fit_invoked":False,"model_learning_observations":0}
    result = {"version":"GOALVISION_LIVE_COMBO_ACCURACY_HARDENING_V1", "since":since.isoformat(),
        "as_of":until.isoformat(), "source_fingerprint":source, "candidate_versions":len(candidates),
        "unique_fixtures":len({p["fixture_id"] for p in candidates}),
        "actual_cohorts":cohort_summaries, "snapshot_comparisons":comparisons,"combo":combo,
        "policy_screen_summaries":policy_summaries, "market_evidence_status":dict(market_status),
        "context_v2":{"versions":len(context_rows),"forecast_versions":sum(r["probabilities"] is not None for r in context_rows),
            "blockers":dict(Counter(b for r in context_rows for b in r["blockers"])),
            "paired_sample":paired_ids,"paired_baseline":base_metrics,"paired_v2":v2_metrics,
            "paired_brier_delta": v2_metrics["brier"]-base_metrics["brier"] if paired_ids else None,
            "paired_log_loss_delta":v2_metrics["log_loss"]-base_metrics["log_loss"] if paired_ids else None,
            "confidence_interval":None,"verdict":"BLOCKED_NEEDS_MORE_EVIDENCE"},
        "result_source_fingerprint":digest(raw_facts), "result_conflict_fixtures":sorted(conflicts),
        "provider_calls":0,"telegram_sends":0,"production_writes":0,"fit_invoked":False,
        "limitations":["Research-only snapshot nominations, NOT an exact natural-cycle counterfactual.",
            "Retained rows do not identify initial vs final-refresh candidate pool. No synthetic final refresh is accepted.",
            "Actual historical exposure is shared; hypothetical nominations are not appended as published claims.",
            "Nominations can be dependent and overlap; indicative quote arithmetic is not executed profit.",
            "C is deliberately blocked: no verified LIVE calibrator or independent context-effects evidence.",
            "V2 is a zero-card venue/competition ablation. Red-card effect fitting and xG effects remain unavailable.",
            "Different selected populations cannot establish paired strategy improvement."]}
    result["fingerprint"] = digest(result)
    return result


def main() -> None:
    deny_network()
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("database","ledger","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--since",required=True); p.add_argument("--until",required=True)
    a = p.parse_args()
    since,until = utc(a.since),utc(a.until)
    if until<since:
        raise ValueError("INVALID_WINDOW")
    value = run(a.database,a.ledger,since=since,until=until)
    helper = runpy.run_path(str(ROOT/"operations/live-combo-research/audit.py"))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    helper["write"](a.output,value)
    print(json.dumps({"status":"READ_ONLY_COMPLETE","fingerprint":value["fingerprint"],
                      "candidate_versions":value["candidate_versions"],"context_v2":value["context_v2"]},sort_keys=True))


if __name__=="__main__":
    main()
