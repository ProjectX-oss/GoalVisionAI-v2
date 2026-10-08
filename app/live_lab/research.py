"""Pure LIVE diagnostics over already captured data; no worker/provider/transport hook."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean, median
from app.adaptive_lab.contracts import digest, utc
from .engine import quote_timing

VERSION = "LIVE_DIAGNOSTICS_V1"
LIMITS = (20, 30, 45)


def age_bucket(age: float | None) -> str:
    """Right-closed intervals: exactly 20 seconds belongs to 10–20."""
    if age is None:
        return "MISSING"
    if age < 0:
        return "INVALID_FUTURE"
    lower = 0
    for upper in (10, 20, 30, 45, 60):
        if age <= upper:
            return f"{lower}-{upper}"
        lower = upper
    return ">60"


def distribution(values: list[float]) -> dict:
    return {"n": len(values), "minimum": min(values) if values else None,
            "median": median(values) if values else None,
            "mean": mean(values) if values else None,
            "maximum": max(values) if values else None}


def candidate_diagnostic(row: dict) -> dict:
    """Counterfactual initial readiness, retaining every recorded non-age blocker."""
    timing = quote_timing(row.get("quote") or {}, now=utc(row["prepared_at_utc"]))
    reasons = set(row.get("blockers") or [])
    other = reasons - {"STALE_LIVE_ODDS"}
    # A hypothetical longer cap never rescues broken temporal provenance.
    if timing["status"] != "VALID":
        other.add("LIVE_QUOTE_TIMESTAMP_INVALID")
    ages = (timing["origin_age_seconds"], timing["retrieval_age_seconds"])
    maximum = max(ages) if all(v is not None for v in ages) else None
    counterfactual = {str(limit): not other and maximum is not None and 0 <= maximum <= limit
                      for limit in LIMITS}
    return {
        "candidate_id": row["candidate_id"], "fixture_id": row["fixture_id"],
        "market": row["market"], "league_id": row.get("league_id"), "policy": row.get("policy"),
        "prepared_at": row["prepared_at_utc"], "provider_timestamp": row.get("provider_origin_timestamp_utc"),
        "retrieved_at": row.get("goalvision_retrieved_at_utc"),
        "provider_market_id": (row.get("quote") or {}).get("live_market_id"),
        "bookmaker_attributed": bool(row.get("bookmaker_id") and row.get("bookmaker")),
        "quote_fingerprint": row.get("quote_provenance_fingerprint"),
        "state_fingerprint": row.get("live_match_state_fingerprint"),
        "minute": row.get("live_minute"), "odds": row.get("captured_odds"),
        "probability": row.get("ensemble_probability"), "ev": row.get("expected_value"),
        "uncertainty": row.get("uncertainty_penalty"),
        "timing": timing, "age_bucket": age_bucket(timing["origin_age_seconds"]),
        "blockers": sorted(reasons), "non_age_blockers": sorted(other),
        "age_only_rejected": reasons == {"STALE_LIVE_ODDS"} and timing["status"] == "VALID",
        "counterfactual_initial_ready": counterfactual,
        "source_fingerprint": digest(row),
    }


def report(candidates: list[dict], diagnostics: list[dict], cycles: list[dict],
           publications: list[dict], claims: list[dict], settlements: list[dict],
           *, as_of: datetime, since: datetime) -> dict:
    """Bounded as-of report. Candidate versions are not independent bets."""
    now, start = utc(as_of), utc(since)
    selected = [r for r in candidates if start <= utc(r["prepared_at_utc"]) <= now]
    rows = [candidate_diagnostic(r) for r in selected]
    diag = [r for r in diagnostics if start <= utc(r["created_at"]) <= now]
    runs = [r for r in cycles if start <= utc(r["at"]) <= now]
    sent = [r for r in publications if r.get("status") == "SENT"
            and start <= utc(r["sent_at_utc"]) <= now]
    claimed = [r for r in claims if start <= utc(r["created_at"]) <= now]
    results = {r["prediction_id"]: r for r in settlements if utc(r["settled_at_utc"]) <= now}
    unique_quotes = {r["quote_fingerprint"]: r for r in rows if r["quote_fingerprint"]}
    by_policy = {}
    for policy in sorted({str(r["policy"]) for r in rows}):
        subset = [r for r in rows if str(r["policy"]) == policy]
        by_policy[policy] = {
            "candidate_versions": len(subset), "unique_fixtures": len({r["fixture_id"] for r in subset}),
            "recorded_ready_versions": sum(not r["blockers"] for r in subset),
            "blocker_counts": dict(Counter(x for r in subset for x in r["blockers"])),
            "quote_age_buckets": dict(Counter(r["age_bucket"] for r in subset)),
            "age_only_rejected_versions": sum(r["age_only_rejected"] for r in subset),
            "counterfactual_initial_ready": {str(t): sum(r["counterfactual_initial_ready"][str(t)] for r in subset)
                                           for t in LIMITS},
        }
    # Only same-state successive observations: match evolution is not quote-only movement.
    groups = defaultdict(list)
    for r in rows:
        groups[(r["fixture_id"], r["market"], r["state_fingerprint"])].append(r)
    movements = []
    for group in groups.values():
        ordered = sorted(group, key=lambda r: r["prepared_at"])
        for a, b in zip(ordered, ordered[1:]):
            if a["quote_fingerprint"] != b["quote_fingerprint"]:
                movements.append(float(b["odds"])/float(a["odds"])-1)
    calls = sum(r.get("api_calls", 0) for r in runs)
    funnel = {k: sum((r.get("discovery_evidence") or {}).get(k, 0) for r in runs)
              for k in ("fixtures_discovered", "live_odds_rows", "fresh_feed_fixtures",
                        "eligible_feed_fixtures", "fixtures_reviewed", "quote_age_diagnostic_fixtures")}
    result = {
        "version": VERSION, "as_of": now.isoformat(), "since": start.isoformat(),
        "selection_effect": "NONE", "provider_calls_initiated": 0, "telegram_sends_initiated": 0,
        "cycles": len(runs), "natural_provider_calls": calls, "candidate_funnel": funnel,
        "cycle_status_counts": dict(Counter(r.get("status", "UNKNOWN") for r in runs)),
        "delivery_status_counts": dict(Counter(d.get("status", "UNKNOWN") for r in runs for d in r.get("deliveries", []))),
        "fixture_diagnostic_counts": dict(Counter(x for d in diag for x in d.get("reasons", []))),
        "by_policy": by_policy, "candidate_versions": len(rows),
        "unique_fixtures": len({r["fixture_id"] for r in rows}),
        "unique_quote_age_buckets": dict(Counter(r["age_bucket"] for r in unique_quotes.values())),
        "quote_to_preparation_seconds": distribution([r["timing"]["retrieval_age_seconds"] for r in rows
                                                      if r["timing"]["status"] == "VALID"]),
        "http_latency_seconds": None, "http_latency_status": "NOT_CAPTURED",
        "provider_feed_age_distribution": "UNAVAILABLE_FOR_DISCARDED_BROAD_FEED_ROWS",
        "same_state_odds_movement": distribution(movements),
        "claims": len(claimed), "confirmed_publications": len(sent),
        "claims_without_receipt": sum(c["selection_id"] not in {r["selection_id"] for r in sent} for c in claimed),
        "settled_publications": sum(r["selection_id"] in results for r in sent),
        "result_counts": dict(Counter(results[r["selection_id"]]["status"] if r["selection_id"] in results
                                     else "PENDING" for r in sent)),
        "provider_calls_per_confirmed_publication": calls/len(sent) if sent else None,
        "rows": rows,
        "source_fingerprint": digest({"candidates": [r["source_fingerprint"] for r in rows],
                                     "diagnostics": diag, "cycles": runs,
                                     "publications": [[r["selection_id"], r["sent_at_utc"]] for r in sent],
                                     "claims": [[r["selection_id"], r["created_at"]] for r in claimed],
                                     "settlements": sorted((k, digest(v)) for k,v in results.items())}),
        "limitations": [
            "Counterfactuals cover stored initial candidate versions, not discarded broad-feed rows or guaranteed final publication.",
            "Fixture/quote exposures and blockers overlap; these are not independent match counts.",
            "HTTP start/end times and raw mismatch payloads were not retained; latency and exact mismatch cause cannot be reconstructed.",
            "Broad-feed status filters include blocked/stopped/finished and timestamps; zero fresh feed is not proof all rows were stale.",
            "Successive same-state quote samples are sparse; no executable-bookmaker price or slippage guarantee.",
            "Changing request order may change score/minute alignment; no measured gain or budget change is asserted.",
        ],
    }
    result["fingerprint"] = digest(result)
    return result


def provider_evidence(payload: object, *, state: dict | None = None) -> dict:
    """Sanitized evidence from an ALREADY received response; never an API request."""
    if not isinstance(payload, dict):
        return {"response_shape":"NON_ENVELOPE", "http_latency_seconds":None}
    response=payload.get("response")
    if not isinstance(response,list):
        return {"response_shape":"MISSING_RESPONSE_LIST","provider_errors_present":bool(payload.get("errors")),
                "http_latency_seconds":None}
    rows=[]
    for value in response[:100]:
        if not isinstance(value,dict):continue
        fixture=value.get("fixture") or {}
        if not isinstance(fixture,dict):continue
        teams=value.get("teams") or {}
        status=fixture.get("status") or {}
        score=[(teams.get(k) or {}).get("goals") for k in ("home","away")]
        try:
            update=utc(value.get("update")).isoformat()
        except (ValueError,TypeError,AttributeError):
            update=None
        item={"fixture_id":fixture.get("id"),"provider_update":update,
              "provider_minute":status.get("elapsed"),"provider_score":score}
        if state is not None and fixture.get("id")==state["fixture_id"]:
            item.update(expected_minute=state["minute"],expected_score=[state["home_score"],state["away_score"]],
                        minute_matches=status.get("elapsed")==state["minute"],
                        score_matches=score==[state["home_score"],state["away_score"]])
        rows.append(item)
    return {"response_shape":"LIST","response_rows":len(response),"rows":rows,
            "truncated":len(response)>100, "provider_errors_present":bool(payload.get("errors")),
            "source_payload_fingerprint":digest(payload),
            "http_latency_seconds":None,
            "latency_note":"Client/quota elapsed time is not isolated HTTP transport latency."}
