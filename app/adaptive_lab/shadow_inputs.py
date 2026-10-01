"""Read-only adapters for existing current provider evidence; no network clients."""
from __future__ import annotations
from .contracts import digest, utc
from .shadow_research import fixture_identity, MAX_CONTEXT_AGE
from app.real_match_lab_analysis.fingerprint import fingerprint


def current_results_context(fixture, cached_rows, *, now):
    """Use fresh cached FT results. Never fetch or fabricate availability times."""
    identity = fixture_identity(fixture,now)
    source = []
    results = {}
    for cached in sorted(cached_rows,key=lambda r:utc(r["retrieved_at"]),reverse=True):
        query = cached["query"]
        if (cached.get("endpoint") != "/fixtures(results)" or query.get("status") != "FT"
                or query.get("league") != identity["league_id"]):
            continue
        retrieved = utc(cached["retrieved_at"])
        if not 0 <= (utc(now)-retrieved).total_seconds() <= MAX_CONTEXT_AGE:
            continue
        payload = cached["payload"]
        if fingerprint(payload) != cached["payload_fingerprint"] or not isinstance(payload,list):
            raise ValueError("CURRENT_RESULT_CACHE_INTEGRITY_FAILURE")
        source.append(cached["payload_fingerprint"])
        for row in payload:
            f,l,t = row["fixture"],row["league"],row["teams"]
            if f["status"]["short"] != "FT" or l["id"] != identity["league_id"]:
                continue
            if f["id"] == identity["fixture_id"] or not utc(f["date"]) < retrieved:
                raise ValueError("CURRENT_RESULT_CACHE_CHRONOLOGY_INVALID")
            fulltime = row["score"]["fulltime"]
            projected = {"fixture_id":f["id"],"league_id":l["id"],"home_team_id":t["home"]["id"],
                         "away_team_id":t["away"]["id"],"kickoff_utc":f["date"],
                         "available_at":retrieved.isoformat(),"status":"RESOLVED",
                         "source_fingerprint":digest([cached["payload_fingerprint"],row]),
                         "home_goals":fulltime["home"],"away_goals":fulltime["away"]}
            old = results.get(f["id"])
            if old and any(old[k]!=projected[k] for k in ("home_goals","away_goals","home_team_id","away_team_id")):
                raise ValueError("CURRENT_RESULT_CACHE_CONFLICT")
            results.setdefault(f["id"],projected)
    if not results:
        raise ValueError("CURRENT_RESULTS_CACHE_UNAVAILABLE")
    return {**identity,"captured_at":utc(now).isoformat(),"version":"CURRENT_RESULTS_CONTEXT_V1",
            "fixture_source":fixture,"current_cache_fingerprints":sorted(set(source)),
            "results":sorted(results.values(),key=lambda r:(utc(r["kickoff_utc"]),r["fixture_id"]))}
