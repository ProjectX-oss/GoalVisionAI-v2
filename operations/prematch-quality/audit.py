"""Bounded read-only odds-yield and coupon audit; no provider, fit or transport."""
from collections import Counter, defaultdict
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.adaptive_lab.contracts import digest, utc
from app.adaptive_lab.performance import band
from app.adaptive_lab.observations import ReadOnlyLedger
from app.adaptive_lab.combo_evidence import coupon_report
from app.real_match_lab_analysis.fingerprint import fingerprint

MISSING = {"ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD", "NO_CURRENT_ODDS",
           "ODDS_EMPTY_RESPONSE", "ODDS_EMPTY_BOOKMAKERS",
           "ODDS_FIXTURE_RECORD_NO_BOOKMAKERS", "CURRENT_ODDS_UNAVAILABLE"}


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path).absolute().as_uri()+"?mode=ro", uri=True, timeout=.2)
    connection.execute("PRAGMA query_only=ON")
    deadline = time.monotonic()+45
    connection.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
    connection.execute("BEGIN")
    return connection


def verified(document: str, expected: str) -> dict:
    value=json.loads(document)
    if fingerprint(value) != expected:
        raise ValueError("QUALITY_AUDIT_SOURCE_INTEGRITY_FAILURE")
    return value


def metadata(state: dict, at: str) -> dict:
    try:
        lead = (utc(state["kickoff_utc"])-utc(at)).total_seconds()/60
    except (ValueError, KeyError, TypeError):
        lead = None
    provider = state.get("provider_metadata") or {}
    status = ((provider.get("fixture") or {}).get("status") or {}).get("short", "UNKNOWN")
    return {
        "competition": str(state.get("competition_profile", "UNKNOWN")),
        "league": str(state.get("league_id", "UNKNOWN")),
        "league_name": str(state.get("league_name", state.get("league", "UNKNOWN"))),
        "country": str(state.get("country", "UNKNOWN")),
        "fixture_status": status,
        "lead_time_bucket": band(lead, (0, 10, 25, 45, 75, 180, 360, 1440)),
        "provider": "API_FOOTBALL",
        "provider_status": "NOT_RECORDED_PER_ATTEMPT",
    }


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    statuses = Counter(r["status"] for r in rows)
    fresh = sum(r["fresh"] for r in rows)
    stale = sum(r["status"] == "ODDS_STALE" for r in rows)
    missing = sum(r["status"] in MISSING for r in rows)
    unknown_detail = sum(r["status"] in {"WAITING_CURRENT_ODDS", "NO_YIELD_REASON_UNRECORDED"} for r in rows)
    repeat_eligible = [r for r in rows if r.get("previous_fixture_refresh_success") is False]
    repeated = sum(not r["fresh"] for r in repeat_eligible)
    return {
        "fixture_observations": n, "unique_fixtures": len({r["fixture_id"] for r in rows}),
        "fresh_successes": fresh, "fresh_success_rate": fresh/n if n else None,
        "stale": stale, "stale_rate": stale/n if n and not unknown_detail else None,
        "observed_stale_rate_lower_bound": stale/n if n else None,
        "no_record_or_missing": missing, "no_record_rate": missing/n if n and not unknown_detail else None,
        "observed_no_record_rate_lower_bound": missing/n if n else None,
        "failure_reason_unavailable": unknown_detail,
        "statuses": dict(statuses),
        "previous_no_yield_attempts": len(repeat_eligible),
        "repeated_no_yield": repeated,
        "repeated_no_yield_rate_after_prior_failure": repeated/len(repeat_eligible) if repeat_eligible else None,
        "repeated_no_yield_share_all_attempts": repeated/n if n else None,
    }


def breakdown(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        for dimension in ("phase", "competition", "league", "country", "fixture_status",
                          "lead_time_bucket", "provider", "provider_status",
                          "previous_fixture_refresh_status"):
            groups[(dimension, str(row.get(dimension, "NO_RECORDED_PRIOR_ATTEMPT")))].append(row)
    return [{"dimension": d, "value": v, **stats(sample)}
            for (d, v), sample in sorted(groups.items())]


def odds_report(cycles: list[dict], tracked: dict[str, list[dict]]) -> dict:
    """Separate broad coverage from observed exact outcomes; deduplicate leg rows."""
    broad, exact, per_cycle = [], [], []
    previous = {}
    league_names = {}
    for cycle in sorted(cycles, key=lambda c: c["evaluated_at_utc"]):
        at = cycle["evaluated_at_utc"]
        states = {str(s["fixture_id"]): s for s in cycle["global_fixture_states"]}
        for state in states.values():
            league_names[str(state.get("league_id"))] = {
                "name": state.get("league_name"), "country": state.get("country"),
                "competition": state.get("competition_profile")}
        page = cycle["odds_pagination"]
        local_broad = []
        for fid, reason in page["fixture_coverage_reasons"].items():
            local_broad.append({"at": at, "fixture_id": str(fid), "status": reason,
                                "fresh": reason == "CURRENT_ODDS_AVAILABLE",
                                "phase": "DATE_SWEEP", **metadata(states.get(str(fid), {}), at)})
        broad.extend(local_broad)
        local_exact = []
        for row in tracked.get(at, []):
            local_exact.append({"fixture_id": str(row["fixture_id"]), "status": row["status"],
                                "fresh": row["status"] == "AVAILABLE", "phase": "TRACKED_EXACT"})
        for row in page.get("priority_exact_retries", []):
            local_exact.append({"fixture_id": str(row["fixture_id"]),
                                "status": "AVAILABLE" if row["recovered"] else "NO_YIELD_REASON_UNRECORDED",
                                "fresh": row["recovered"], "phase": "PRIORITY_EXACT"})
        # Each reviewed fixture can have many tracked market rows.
        reviews = {}
        attempted = {str(fid) for fid in (cycle.get("final_review_queue") or {}).get("attempted_fixture_ids", [])}
        for row in cycle.get("tracked_final_reviews", []):
            fid = str(row["fixture_id"])
            review = row.get("final_review") or {}
            if fid not in attempted or review.get("odds_status") is None:
                continue
            key = (fid, review.get("odds_retrieved_at_utc"))
            current = {"fixture_id": fid, "status": review["odds_status"],
                       "fresh": review["odds_status"] == "AVAILABLE", "phase": "FINAL_REVIEW"}
            if key in reviews and reviews[key] != current:
                raise ValueError("CONFLICTING_FROZEN_REVIEW_OUTCOMES")
            reviews[key] = current
        local_exact.extend(reviews.values())
        for row in local_exact:
            fid = row["fixture_id"]
            prior = previous.get(fid)
            row.update({"at": at, **metadata(states.get(fid, {}), at),
                        "previous_fixture_refresh_success": prior["fresh"] if prior else None,
                        "previous_fixture_refresh_status": prior["status"] if prior else "NO_RECORDED_PRIOR_ATTEMPT"})
        # Prior means a preceding cycle, not another phase in this same cycle.
        for row in local_exact:
            previous[row["fixture_id"]] = row
        exact.extend(local_exact)
        calls = cycle["exact_fixture_odds_refresh_calls"]
        successful_fixtures = len({r["fixture_id"] for r in local_exact if r["fresh"]})
        per_cycle.append({
            "at": at, "broad_coverage": stats(local_broad),
            "post_refresh_current_odds_fixtures": cycle["current_odds_fixtures"],
            "recorded_exact_outcomes": stats(local_exact),
            "exact_http_calls": calls, "date_sweep_http_calls": cycle["api_call_allocation"].get("/odds(date)", 0),
            "provider_calls": cycle["api_calls_consumed"],
            "cycle_ceiling": cycle["adaptive_quota_budget"]["effective_cycle_maximum"],
            "quota_remaining": cycle.get("current_remaining_daily_quota"),
            "all_date_sweeps_complete": all(v["stable_complete_sweep"] for v in page["coverage_by_date"].values()),
            "known_successful_exact_fixture_refreshes": successful_fixtures,
        })
    exact_calls = sum(r["exact_http_calls"] for r in per_cycle)
    successes = sum(r["known_successful_exact_fixture_refreshes"] for r in per_cycle)
    segments = breakdown(exact)
    leagues = [s for s in segments if s["dimension"] == "league" and s["fixture_observations"] >= 5]
    return {
        "version": "PREMATCH_ODDS_REFRESH_YIELD_AUDIT_V1",
        "broad_scope": stats(broad), "exact_recorded_outcomes": stats(exact),
        "tracked_exact": stats([r for r in exact if r["phase"] == "TRACKED_EXACT"]),
        "exact_http_calls": exact_calls,
        "known_successful_exact_fixture_refreshes": successes,
        "http_calls_per_known_successful_fresh_fixture": exact_calls/successes if successes else None,
        "date_sweep_http_calls": sum(r["date_sweep_http_calls"] for r in per_cycle),
        "cycles": per_cycle, "broad_breakdown": breakdown(broad), "exact_breakdown": segments,
        "best_observed_leagues_minimum_5_attempts": sorted(leagues, key=lambda s: (-s["fresh_success_rate"], -s["fixture_observations"], s["value"]))[:10],
        "worst_observed_leagues_minimum_5_attempts": sorted(leagues, key=lambda s: (s["fresh_success_rate"], -s["fixture_observations"], s["value"]))[:10],
        "league_names": league_names, "exact_rows": exact,
        "limitations": [
            "Counts are repeated fixture-cycle observations, not independent fixtures.",
            "Broad date-sweep statuses precede exact overrides and have a different denominator.",
            "Exact status evidence covers tracked, priority and tracked final reviews; untracked final outcomes may be absent.",
            "Exact HTTP cost includes retries; individual outcome rows do not record their own HTTP cost.",
            "Calls per known success is an upper bound when successful untracked outcomes are absent, not cost per market quote.",
            "WAITING_CURRENT_ODDS does not distinguish empty, stale, provider error or bookmaker filtering.",
            "Provider HTTP status is not retained per tracked attempt; it cannot be inferred from a missing quote.",
            "Repeated no-yield uses only preceding recorded cycles in this bounded audit.",
            "Observational league yield is confounded by lead time and priority; no causal reordering gain is established.",
        ],
    }


def disagreement_report(candidates: list[dict]) -> dict:
    """Descriptive candidate-level association, never causal threshold tuning."""
    groups = defaultdict(list)
    tracked_reasons = ("SEVERE_MODEL_MARKET_CONTRADICTION", "MATERIAL_SIGNAL_DISAGREEMENT",
                       "ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE")
    from app.adaptive_lab.performance import finite, timing
    for row in candidates:
        reasons = set().union(*(set(row.get(k) or []) for k in
                             ("rejection_reasons", "readiness_reasons", "hard_failures", "soft_findings")))
        p, q = finite(row.get("ensemble_probability")), finite(row.get("market_fair_probability"))
        temporal = timing(row, selected_at=row.get("evaluated_at_utc"))
        fresh_state = ("STALE_MARKER_PRESENT" if any("STALE" in r for r in reasons) else
                       "MISSING_CURRENT_ODDS" if q is None or row.get("captured_odds") is None else
                       "NO_STALE_MARKER_WITH_CURRENT_PRICE")
        completeness = ("MISSING_QUOTE" if q is None else
                        "QUOTE_WITHOUT_API_PREDICTION" if row.get("api_prediction_available") is not True else
                        "QUOTE_AND_API_PREDICTION")
        sample = {"fixture_id": row["fixture_id"], "reasons": reasons,
                  "divergence": float(abs(p-q)) if p is not None and q is not None else None}
        dims = {
            "market": row.get("market", "UNKNOWN"),
            "competition": row.get("competition_profile", "UNKNOWN"),
            "league": str(row.get("league_id", "UNKNOWN")),
            "odds": band(row.get("captured_odds"), (1.3, 1.5, 1.7, 2, 3, 5)),
            "model_probability": band(p, (.4, .5, .6, .7, .8, .9)),
            "lead_time": temporal["prematch_lead_minutes_bucket"],
            "odds_age": temporal["odds_age_seconds_bucket"],
            "data_freshness_state": fresh_state, "provider_completeness": completeness,
            "model_generation": row.get("model_generation") or "UNKNOWN",
            "context_quality": (str(row["context_quality"]) if row.get("context_quality") else
                                "CONTEXT_BLOCKER_RECORDED" if any("CONTEXT" in r for r in reasons) else
                                "NOT_EXPLICITLY_RATED"),
        }
        groups[("ALL", "ALL")].append(sample)
        for dimension, value in dims.items():
            groups[(dimension, str(value))].append(sample)
    segments = []
    for (dimension, value), sample in sorted(groups.items()):
        counts = Counter(reason for row in sample for reason in row["reasons"])
        divergence = [r["divergence"] for r in sample if r["divergence"] is not None]
        segments.append({
            "dimension": dimension, "value": value, "candidate_rows": len(sample),
            "unique_fixtures": len({r["fixture_id"] for r in sample}),
            "reason_counts": dict(counts),
            "disagreement_rates": {r: counts[r]/len(sample) for r in tracked_reasons},
            "divergence_observations": len(divergence),
            "mean_absolute_ensemble_market_divergence": sum(divergence)/len(divergence) if divergence else None,
        })
    return {"version": "PREMATCH_DISAGREEMENT_ASSOCIATION_V2", "segments": segments,
            "selection_effect": "NONE",
            "limitations": [
                "Repeated candidate-market-cycle rows are not independent bets.",
                "Missing evaluated rows do not establish no disagreement.",
                "Completeness records quote/API-prediction availability, not every upstream field.",
                "No stale marker is not independent proof of provider timestamp correctness.",
                "Association cannot separate model misspecification from provider errors causally.",
                "Context quality is an explicit source rating or a recorded context blocker; absence is not a positive quality grade.",
                "Missing generation is UNKNOWN, never inferred from the current champion.",
            ]}


def run(shadow: Path, ledger_path: Path, *, as_of: str, output: Path, limit: int = 24) -> None:
    if not 1 <= limit <= 48:
        raise ValueError("AUDIT_CYCLE_LIMIT")
    output.mkdir(parents=True, exist_ok=True)
    connection = readonly(shadow)
    try:
        records = connection.execute(
            "SELECT identity,content_fingerprint,document_json FROM lab_v2_shadow_evidence "
            "WHERE kind='rehearsal' AND created_at_utc<=? ORDER BY rowid DESC LIMIT ?",
            (as_of, limit)).fetchall()
        cycles = [verified(r[2],r[1]) for r in records]
        tracked = {}
        for cycle in cycles:
            at = cycle["evaluated_at_utc"]; prefix = at+":"
            tracked[at] = [verified(r[0],r[1]) for r in connection.execute(
                "SELECT document_json,content_fingerprint FROM lab_v2_shadow_evidence "
                "WHERE kind='tracked_odds_refresh' AND identity>=? AND identity<?", (prefix, prefix+"~"))]
        candidate_ids = list(dict.fromkeys(i for c in cycles[:12] for i in c["candidate_ids"]))
        if len(candidate_ids) > 50000:
            raise ValueError("CANDIDATE_AUDIT_CAP")
        candidates = []
        for identity in candidate_ids:
            raw, created, expected = connection.execute(
                "SELECT document_json,created_at_utc,content_fingerprint FROM lab_v2_shadow_evidence WHERE kind='candidate' AND identity=?",
                (identity,)).fetchone()
            row = verified(raw,expected)
            row["evaluated_at_utc"] = max(created, row.get("goalvision_retrieved_at_utc") or created)
            candidates.append(row)
        disagreement = disagreement_report(candidates)
        disagreement.update(as_of=as_of, candidate_cycles=[c["evaluated_at_utc"] for c in cycles[:12]])
        report = odds_report(cycles, tracked)
        report.update(as_of=as_of, source_cycle_fingerprint=digest([[r[0], r[1]] for r in records]),
                      cycle_limit=limit, provider_calls_initiated=0, selection_effect="NONE")
    finally:
        connection.close()
    (output/"disagreement.json").write_text(json.dumps(disagreement, indent=2, sort_keys=True, allow_nan=False)+"\n")
    (output/"odds_yield.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
    ledger = ReadOnlyLedger(ledger_path)
    try:
        coupons = coupon_report(ledger, now=utc(as_of))
    finally:
        ledger.close()
    (output/"combo_calibration.json").write_text(json.dumps(coupons, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps({"odds": report["exact_recorded_outcomes"], "tracked": report["tracked_exact"],
                      "combo": coupons["overall"], "cohorts": coupons["cohorts"]}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=24)
    args = parser.parse_args()
    run(args.shadow, args.ledger, as_of=utc(args.as_of).isoformat(), output=args.output, limit=args.cycles)
