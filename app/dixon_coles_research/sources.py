"""Bounded, query-only adapters for existing natural-cycle evidence.

No provider clients. Database constructors that migrate/create production tables
are deliberately excluded. Cached result observation times remain authoritative.
"""
from __future__ import annotations
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import time
from .contracts import utc, digest, verify_plan, integer
from app.real_match_lab_analysis.fingerprint import fingerprint
from app.adaptive_lab.devig_research import verify_capture
from app.current_odds_forward_test.freshness import API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS, RETRIEVAL_MAX_AGE_SECONDS

@contextmanager
def readonly(path: Path):
    connection=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=.1)
    connection.row_factory=sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    deadline=time.monotonic()+5
    connection.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    try: yield connection
    finally: connection.close()

def _evidence(connection, kind: str, identity: str) -> dict:
    row=connection.execute("SELECT content_fingerprint,document_json FROM lab_v2_shadow_evidence WHERE kind=? AND identity=?",
                           (kind,identity)).fetchone()
    if row is None: raise ValueError("SOURCE_REFERENCE_MISSING")
    value=json.loads(row["document_json"])
    if fingerprint(value)!=row["content_fingerprint"]: raise ValueError("SOURCE_INTEGRITY")
    return value

def consumed_holdout_fixtures(path: Path) -> frozenset[int]:
    """Only indexed references are read, never holdout scores or model evaluation."""
    result=set()
    with readonly(path) as connection:
        rows=connection.execute("SELECT fingerprint,document FROM holdout_results WHERE stream='PREMATCH' LIMIT 1001").fetchall()
        if len(rows)>1000: raise ValueError("HOLDOUT_REFERENCE_CAPACITY")
        for row in rows:
            item=json.loads(row["document"])
            if digest(item)!=row["fingerprint"]: raise ValueError("HOLDOUT_REFERENCE_INTEGRITY")
            ids=item["observation_ids"]
            if len(ids)>50000: raise ValueError("HOLDOUT_REFERENCE_CAPACITY")
            for oid in ids:
                observation=connection.execute("SELECT document,fingerprint FROM learning_observations WHERE id=? AND stream='PREMATCH'",(oid,)).fetchone()
                if observation is None: raise ValueError("HOLDOUT_REFERENCE_MISSING")
                document=json.loads(observation["document"])
                if digest(document)!=observation["fingerprint"]: raise ValueError("HOLDOUT_REFERENCE_INTEGRITY")
                result.add(integer(document["fixture_id"]))
    return frozenset(result)

def _history(connection, league: int, season: int, cutoff: datetime) -> list[dict]:
    values=[]
    for year in (season-1,season):
        query={"league":league,"season":year,"status":"FT","last":99}
        row=connection.execute(
            "SELECT * FROM lab_v2_provider_cache WHERE endpoint=? AND query_fingerprint=? AND retrieved_at_utc<=? ORDER BY retrieved_at_utc DESC LIMIT 1",
            ("/fixtures(results)",fingerprint(query),utc(cutoff).isoformat())).fetchone()
        if row is None: continue
        if len(row["payload_json"].encode())>4*1024*1024: raise ValueError("SOURCE_CAPACITY")
        payload=json.loads(row["payload_json"])
        if (fingerprint(payload)!=row["payload_fingerprint"] or json.loads(row["query_json"])!=query
                or fingerprint(query)!=row["query_fingerprint"]): raise ValueError("CACHE_INTEGRITY")
        response=payload if isinstance(payload,list) else payload.get("response",[]) if isinstance(payload,dict) else None
        if not isinstance(response,list) or len(response)>99: raise ValueError("HISTORY_RESPONSE_CONTRACT")
        for record in response:
            f=record.get("fixture",{}); teams=record.get("teams",{}); league_row=record.get("league",{})
            fulltime=(record.get("score") or {}).get("fulltime") or {}
            if f.get("status",{}).get("short")!="FT": continue
            values.append({"fixture_id":f.get("id"),"league_id":league_row.get("id"),
                "kickoff_utc":f.get("date"),"observed_at_utc":row["retrieved_at_utc"],
                "home_team_id":teams.get("home",{}).get("id"),"away_team_id":teams.get("away",{}).get("id"),
                "home_goals":fulltime.get("home"),"away_goals":fulltime.get("away"),
                "neutral":False,"status":"FT","source_fingerprint":row["payload_fingerprint"]})
    return values

def snapshot(shadow: Path, audit: Path, *, plan: dict, now: datetime,
             limit: int = 20) -> dict:
    """Read prospective first-capture inputs; never replay forecasts after kickoff."""
    verify_plan(plan); cutoff=utc(now); integer(limit,high=50)
    reserved=consumed_holdout_fixtures(audit)
    fixed={int(v) for v in plan["protected_calendar"]["reserved_holdout_fixtures"]}|set(reserved)
    diagnostics=Counter(); items=[]; seen=set()
    with readonly(shadow) as connection:
        cursor=connection.execute(
            "SELECT identity,created_at_utc,content_fingerprint,document_json FROM lab_v2_shadow_evidence "
            "WHERE kind='devig_research' AND identity>=? ORDER BY rowid DESC LIMIT 501",("devig-v2:",))
        rows=[]; byte_count=0
        for raw in cursor:
            byte_count+=len(raw["document_json"].encode())
            if byte_count>64*1024*1024: raise ValueError("SOURCE_CAPACITY")
            rows.append(raw)
        diagnostics["capture_rows_examined"]=min(500,len(rows))
        diagnostics["older_captures_not_scanned"]=int(len(rows)>500)
        for row in rows[:500]:
            if len(row["document_json"].encode())>2*1024*1024: raise ValueError("SOURCE_CAPACITY")
            capture=json.loads(row["document_json"])
            if digest(capture)!=row["content_fingerprint"] or capture.get("capture_id")!=row["identity"]:
                raise ValueError("SOURCE_INTEGRITY")
            stamp=utc(capture["captured_at"]); kickoff=utc(capture["kickoff_utc"])
            if stamp!=utc(row["created_at_utc"]): raise ValueError("SOURCE_TIMESTAMP_INTEGRITY")
            if stamp<utc(plan["declared_at"]): diagnostics["before_declaration"]+=1; continue
            if stamp>cutoff: diagnostics["future_capture"]+=1; continue
            if not cutoff<kickoff<utc(plan["evaluation_end"]): diagnostics["not_upcoming_evaluation"]+=1; continue
            if (cutoff-stamp).total_seconds()>RETRIEVAL_MAX_AGE_SECONDS:
                diagnostics["stale_capture"]+=1; continue
            if capture["fixture_id"] in fixed: diagnostics["reserved_holdout"]+=1; continue
            verify_capture(capture)
            if capture["status"]!="AVAILABLE": diagnostics["unavailable_current_odds"]+=1; continue
            key=(capture["fixture_id"],capture["market_family"])
            if key in seen: continue
            refs=capture["model_probabilities"]
            candidates={}
            for market,ref in sorted(refs.items()):
                candidate=_evidence(connection,"candidate",ref["candidate_id"])
                if (fingerprint(candidate)!=ref["candidate_fingerprint"]
                        or candidate["fixture_id"]!=capture["fixture_id"]
                        or candidate["market"]!=market or candidate["kickoff_utc"]!=capture["kickoff_utc"]):
                    raise ValueError("MODEL_REFERENCE_INTEGRITY")
                candidates[market]=candidate
            family_markets={m for book in capture["bookmakers"] if book["status"]=="AVAILABLE"
                            for m in book["methods"]["MULTIPLICATIVE"]["probabilities"]}
            candidates={m:c for m,c in candidates.items() if m in family_markets}
            if not candidates: diagnostics["missing_model_reference"]+=1; continue
            first=next(iter(candidates.values()))
            identity_keys=("league_id","season","home_team_id","away_team_id","competition_profile")
            if any(any(c[k]!=first[k] for k in identity_keys) for c in candidates.values()):
                raise ValueError("FIXTURE_REFERENCE_CONFLICT")
            rows_for_fit=_history(connection,first["league_id"],first["season"],stamp)
            items.append({"capture":capture,"candidates":candidates,"training_results":rows_for_fit})
            seen.add(key)
            if len(items)>=limit: diagnostics["intake_limit_reached"]+=1; break
    return {"items":items,"diagnostics":dict(diagnostics),"additional_reserved":sorted(reserved),
            "as_of":cutoff.isoformat(),"read_only":True,"provider_calls":0}

def results(ledger: Path, audit: Path, *, fixture_ids: set[int], now: datetime) -> list[dict]:
    """Read existing SINGLE/canonical terminal facts. COMBO legs are never labels."""
    from app.adaptive_lab.devig_integration import _result
    output=[]
    with readonly(ledger) as connection:
        rows=connection.execute("SELECT fingerprint,document FROM evidence WHERE kind='single_settlement' LIMIT 50001").fetchall()
        if len(rows)>50000: raise ValueError("RESULT_CAPACITY")
        for row in rows:
            value=json.loads(row["document"])
            if value.get("fixture_id") not in fixture_ids: continue
            if fingerprint(value)!=row["fingerprint"]: raise ValueError("RESULT_INTEGRITY")
            result=_result(value,product="SINGLE")
            if utc(result["settled_at"])<=utc(now): output.append(result)
    with readonly(audit) as connection:
        rows=connection.execute("SELECT fingerprint,document FROM canonical_results WHERE stream='PREMATCH' AND created_at<=? LIMIT 50001",
                                (utc(now).isoformat(),)).fetchall()
        if len(rows)>50000: raise ValueError("RESULT_CAPACITY")
        for row in rows:
            value=json.loads(row["document"])
            if int(value.get("fixture_id",0)) not in fixture_ids: continue
            if digest(value)!=row["fingerprint"]: raise ValueError("RESULT_INTEGRITY")
            output.append(_result(value,product="SHADOW"))
    return output
