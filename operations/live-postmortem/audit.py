"""Offline LIVE publication postmortem. Read-only inputs; no provider/transport."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import runpy
import socket
import sys
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.adaptive_lab.contracts import digest, utc
from app.live_lab.engine import readiness, remaining_goal_probabilities, quote_timing
from app.live_lab.provider import history_rates
from app.current_odds_forward_test.service import _won

TABLES = ("live_candidates", "live_claims", "live_publications", "live_settlements",
          "live_result_receipts", "live_diagnostics")
VERSION = "LIVE_PUBLICATION_POSTMORTEM_V1"


def probability_metrics(rows, field):
    values = [(float(r[field]), int(r["result"] == "WON"))
              for r in rows if r["result"] in {"WON", "LOST"}]
    if not values:
        return {"n": 0}
    if any(not 0 < p < 1 for p, _ in values):
        raise ValueError("PROBABILITY_BOUNDARY")
    bins = []
    for i in range(10):
        subset = [(p, y) for p, y in values if i / 10 <= p < (i + 1) / 10]
        if subset:
            bins.append({"lower": i / 10, "upper": (i + 1) / 10, "n": len(subset),
                         "predicted": mean(p for p, _ in subset),
                         "observed": mean(y for _, y in subset)})
    return {"n": len(values), "mean_probability": mean(p for p, _ in values),
            "hit_rate": mean(y for _, y in values),
            "brier": mean((p-y)**2 for p, y in values),
            "log_loss": mean(-(y*math.log(p)+(1-y)*math.log1p(-p)) for p, y in values),
            "bias_predicted_minus_observed": mean(p-y for p, y in values),
            "ece_10_equal_width": sum(b["n"]*abs(b["predicted"]-b["observed"]) for b in bins)/len(values),
            "reliability_bins": bins,
            "inference": "DESCRIPTIVE_ONLY_SMALL_DEPENDENT_SAMPLE"}


def summary(rows):
    settled = [r for r in rows if r["result"] in {"WON", "LOST", "VOID"}]
    pnl = sum((Decimal(r["flat_pnl"]) for r in settled), Decimal(0))
    odds = [Decimal(r["odds"]) for r in rows]
    return {"published": len(rows), "independent_fixtures": len({r["fixture_id"] for r in rows}),
            "settled": len(settled), "outcomes": dict(Counter(r["result"] for r in rows)),
            "flat_pnl": str(pnl), "flat_roi": str(pnl/len(settled)) if settled else None,
            "average_odds": str(sum(odds)/len(odds)) if odds else None,
            "median_odds": str(median(odds)) if odds else None,
            "model_metrics": probability_metrics(rows, "probability"),
            "raw_price_implied_metrics": probability_metrics(rows, "raw_implied_probability"),
            "price_baseline_note": "1/odds, NOT de-vig, NOT executable-price evidence",
            "probability_below_half": sum(float(r["probability"]) < .5 for r in rows),
            "red_card_publications": sum(any(r["red_cards"]) for r in rows)}


def history_profile(candidate):
    state, rates = candidate["state"], candidate["rates"]
    out = []
    for team, payload in zip((state["home_team_id"], state["away_team_id"]), rates["frozen_history_payloads"]):
        accepted = []
        for row in payload.get("response", []):
            f, t = row.get("fixture") or {}, row.get("teams") or {}
            goals = (row.get("score") or {}).get("fulltime") or {}
            if (f.get("id") == state["fixture_id"] or (f.get("status") or {}).get("short") != "FT"
                    or utc(f["date"]) >= utc(state["kickoff_utc"])
                    or team not in {(t.get("home") or {}).get("id"), (t.get("away") or {}).get("id")}
                    or not all(type(goals.get(k)) is int and 0 <= goals[k] <= 30 for k in ("home", "away"))):
                continue
            accepted.append(row)
        ids = [r["fixture"]["id"] for r in accepted]
        dates = [utc(r["fixture"]["date"]) for r in accepted]
        out.append({"team_id": team, "sample": len(accepted), "unique_fixtures": len(set(ids)),
                    "duplicate_fixture_count": len(ids)-len(set(ids)),
                    "oldest_kickoff": min(dates).isoformat() if dates else None,
                    "newest_kickoff": max(dates).isoformat() if dates else None,
                    "oldest_age_days": (utc(state["kickoff_utc"])-min(dates)).total_seconds()/86400 if dates else None,
                    "competitions": dict(Counter(str((r.get("league") or {}).get("id")) for r in accepted)),
                    "countries": dict(Counter(str((r.get("league") or {}).get("country")) for r in accepted)),
                    "current_fixture_excluded": state["fixture_id"] not in ids,
                    "all_kickoffs_before_current": all(d < utc(state["kickoff_utc"]) for d in dates)})
    return out


def published_rows(tables, *, since, until):
    candidates = {r["prediction_id"]: r for r in tables["live_candidates"]}
    results = {r["prediction_id"]: r for r in tables["live_settlements"] if utc(r["settled_at_utc"]) <= until}
    result_receipts = {r["selection_id"]: r for r in tables["live_result_receipts"]
                       if r.get("status") == "SENT" and utc(r["sent_at_utc"]) <= until}
    publications = [r for r in tables["live_publications"] if r.get("status") == "SENT"
                    and since <= utc(r["sent_at_utc"]) <= until]
    if len({r["selection_id"] for r in publications}) != len(publications):
        raise ValueError("DUPLICATE_PUBLICATION")
    output = []
    for pub in sorted(publications, key=lambda r: r["sent_at_utc"]):
        p = candidates[pub["selection_id"]]
        if utc(p["prepared_at_utc"]) > utc(pub["sent_at_utc"]):
            raise ValueError("PUBLICATION_BEFORE_PREPARATION")
        s, q, rates = p["state"], p["quote"], p["rates"]
        result = results.get(p["prediction_id"])
        if result and (result["fixture_id"] != p["fixture_id"] or result["market"] != p["market"]
                       or result["captured_odds"] != p["captured_odds"]
                       or utc(result["settled_at_utc"]) < utc(pub["sent_at_utc"])):
            raise ValueError("SETTLEMENT_PROVENANCE_MISMATCH")
        prediction = float(p["ensemble_probability"])
        recomputed = remaining_goal_probabilities(s, rates, as_of=utc(p["prepared_at_utc"]))[p["market"]]
        rebuilt = history_rates(s, *rates["frozen_history_payloads"], retrieved_at=utc(rates["available_at"]))
        prior = [candidates[c["selection_id"]] for c in tables["live_claims"]
                 if utc(c["created_at"]) < utc(p["prepared_at_utc"]) and c["selection_id"] != p["prediction_id"]]
        blockers = readiness(s, q, prediction, uncertainty=p["uncertainty_penalty"],
                             now=utc(pub["sent_at_utc"]), previous=prior, allow_provider_feed=True,
                             quote_age_diagnostic=p["policy"] == "LAB_LIVE_API_FEED_AGE_DIAGNOSTIC_V2")
        status = result["status"] if result else "PENDING"
        score = [result.get("fulltime_home"), result.get("fulltime_away")] if result else [None, None]
        reproduced = ("WON" if _won(p["market"], *score) else "LOST") if status in {"WON", "LOST"} else status
        if reproduced != status:
            raise ValueError("SETTLEMENT_REPLAY_MISMATCH")
        hypothetical = dict(s, red_cards_home=0, red_cards_away=0)
        p_no_cards = remaining_goal_probabilities(hypothetical, rates, as_of=utc(p["prepared_at_utc"]))[p["market"]]
        odds = Decimal(p["captured_odds"])
        pnl = odds-1 if status == "WON" else Decimal(-1) if status == "LOST" else Decimal(0) if status == "VOID" else None
        origin_age = (utc(pub["sent_at_utc"])-utc(q["origin_timestamp"])).total_seconds()
        output.append({
            "prediction_id": p["prediction_id"], "candidate_fingerprint": digest(p),
            "publication_fingerprint": digest(pub), "settlement_fingerprint": digest(result) if result else None,
            "fixture_id": p["fixture_id"], "league_id": p["league_id"],
            "match": p["home_team"]+" – "+p["away_team"], "market": p["market"],
            "minute": s["minute"], "added_time": s.get("added_time"),
            "score_at_publication": [s["home_score"], s["away_score"]], "final_regulation_score": score,
            "red_cards": p["red_card_state"], "odds": str(odds), "probability": p["ensemble_probability"],
            "raw_implied_probability": str(Decimal(1)/odds), "estimated_ev": p["expected_value"],
            "model_market_difference": prediction-1/float(odds), "uncertainty": p["uncertainty_penalty"],
            "model_generation": p["model_generation"], "policy": p["policy"],
            "sent_at": pub["sent_at_utc"], "prepared_at": p["prepared_at_utc"],
            "settled_at": result.get("settled_at_utc") if result else None,
            "result": status, "provider_final_status": result.get("provider_status") if result else None,
            "flat_pnl": str(pnl) if pnl is not None else None,
            "result_receipt_present": p["prediction_id"] in result_receipts,
            "result_receipt_delay_seconds": (utc(result_receipts[p["prediction_id"]]["sent_at_utc"])-utc(result["settled_at_utc"])).total_seconds()
                if result and p["prediction_id"] in result_receipts else None,
            "goal_rates": {k: rates[k] for k in ("home_goal_rate", "away_goal_rate", "home_sample", "away_sample")},
            "history": history_profile(p), "optional_features_present": sorted(s.get("optional_features", {})),
            "poisson_probability_absolute_replay_error": abs(prediction-recomputed),
            "rates_replay_equal": rebuilt == rates,
            "zero_red_cards_probability": p_no_cards, "red_card_probability_effect": recomputed-p_no_cards,
            "readiness_at_receipt_replay_blockers": blockers, "settlement_replay": "PASS",
            "quote_age_at_send_seconds": origin_age,
            "quote_retrieval_to_send_seconds": (utc(pub["sent_at_utc"])-utc(q["retrieved_at"])).total_seconds(),
            "state_age_at_send_seconds": (utc(pub["sent_at_utc"])-utc(s["retrieved_at"])).total_seconds(),
            "events_age_at_send_seconds": (utc(pub["sent_at_utc"])-utc(s["event_retrieved_at"])).total_seconds(),
            "legacy_age_counterfactual": {str(limit): origin_age <= limit for limit in (20, 30, 45)},
            "quote_timing_at_preparation": quote_timing(q, now=utc(p["prepared_at_utc"])),
            "bookmaker_verified": bool(q.get("bookmaker_verified", q.get("bookmaker_id"))),
        })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    def denied(*a, **k):
        raise RuntimeError("OUTBOUND_NETWORK_DENIED")
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    since, until = utc(args.since), utc(args.until)
    if until < since:
        raise ValueError("INVALID_WINDOW")
    audit = runpy.run_path(str(ROOT/"operations/live-combo-research/audit.py"))
    db = audit["readonly"](args.database)
    tables, source = {}, []
    try:
        for table in TABLES:
            records = db.execute("SELECT id,document,fingerprint FROM "+table+
                                 " WHERE created_at<=? ORDER BY created_at,id LIMIT 20001", (until.isoformat(),)).fetchall()
            if len(records) > 20000:
                raise ValueError("EVIDENCE_BOUND")
            tables[table] = [audit["verified"](r[1], r[2], live=True) for r in records]
            source.extend([table, r[0], r[2]] for r in records)
    finally:
        db.close()
    rows = published_rows(tables, since=since, until=until)
    from app.live_lab.research import report
    live = report(tables["live_candidates"], tables["live_diagnostics"], audit["journal"](since, until),
                  tables["live_publications"], tables["live_claims"], tables["live_settlements"],
                  as_of=until, since=since)
    live.pop("rows", None)
    grouped = {}
    for name, key in (("market", lambda r:r["market"]), ("fixture", lambda r:str(r["fixture_id"])),
                      ("league", lambda r:str(r["league_id"])), ("red_cards", lambda r:str(any(r["red_cards"])))):
        groups = defaultdict(list)
        for row in rows:
            groups[key(row)].append(row)
        grouped[name] = {k:summary(v) for k,v in sorted(groups.items())}
    value = {"version": VERSION, "since": since.isoformat(), "as_of": until.isoformat(),
             "source_fingerprint": digest(source), "source_row_counts": {k:len(v) for k,v in tables.items()},
             "published": rows, "summary": summary(rows), "segments": grouped, "pipeline": live,
             "counterfactual_scope": "Fixed published selections only; no replacement/re-ranking, NOT performance of an alternative policy",
             "legacy_age_published_subset": {str(limit):summary([r for r in rows if r["legacy_age_counterfactual"][str(limit)]]) for limit in (20,30,45)},
             "limitations": ["This small, clustered sample cannot support reliable model ranking or calibration inference.",
                            "1/odds includes unknown margin and cannot establish fair market probability.",
                            "Receipt-time gate replay is later than claim-time; it is a stricter diagnostic, not the original gate event.",
                            "History inclusion proves kickoff chronology, not provider revision availability before original historical kickoff.",
                            "No raw final-result API response retained here; outcomes reproduced from immutable stored regulation scores.",
                            "HTTP latency and rejected raw quote/state pairs were not retained.",
                            "Equal-stake P/L uses indicative feed quotes; no executed betting return."],
             "safety": {"provider_calls":0, "telegram_calls":0, "telegram_sends":0, "production_writes":0,
                        "policy_changes":0, "training":False, "activation":False}}
    value["fingerprint"] = digest(value)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+"\n"
    if args.output.exists() and args.output.read_text() != encoded:
        raise ValueError("IMMUTABLE_OUTPUT_CONFLICT")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded)
    print(json.dumps({"fingerprint":value["fingerprint"], "source_fingerprint":value["source_fingerprint"],
                      "summary":value["summary"], "output":str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
