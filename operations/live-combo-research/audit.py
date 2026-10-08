"""Bounded read-only LIVE/COMBO audit and original-candidate replay. No network calls."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import socket
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.adaptive_lab.contracts import digest, utc
from app.adaptive_lab.observations import ReadOnlyLedger
from app.adaptive_lab.combo_research import performance_comparison, replay, score_replay
from app.adaptive_lab.combo_evidence import summarize_coupons
from app.live_lab.research import report as live_report
from app.real_match_lab_analysis.fingerprint import fingerprint

MAX_CYCLES = 24


def readonly(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.absolute().as_uri()+"?mode=ro", uri=True, timeout=.2)
    db.execute("PRAGMA query_only=ON")
    deadline = time.monotonic()+60
    db.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
    db.execute("BEGIN")
    return db


def verified(document: str, expected: str, *, live: bool = False) -> dict:
    value=json.loads(document)
    if (digest(value) if live else fingerprint(value)) != expected:
        raise ValueError("RESEARCH_SOURCE_INTEGRITY_FAILURE")
    return value


def write(path: Path, value: dict) -> None:
    """Immutable output: repeat is permitted only if bytes agree."""
    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n"
    if path.exists():
        if path.read_text() != encoded:
            raise ValueError("RESEARCH_OUTPUT_ALREADY_EXISTS_WITH_DIFFERENT_CONTENT:"+path.name)
        return
    path.write_text(encoded)


def journal(since: datetime, cutoff: datetime) -> list[dict]:
    call = subprocess.run(["journalctl","--no-pager","-u","goalvision-lab-live-evening.service",
                           "--since",since.isoformat(),"--until",cutoff.isoformat(),"-o","json"],
                          text=True,capture_output=True,timeout=20)
    if call.returncode:
        raise ValueError("LIVE_JOURNAL_UNAVAILABLE")
    output=[]
    for line in call.stdout.splitlines():
        envelope=json.loads(line)
        try: value=json.loads(envelope["MESSAGE"])
        except (ValueError,TypeError): continue
        if not isinstance(value,dict) or "api_calls" not in value: continue
        # Whitelist: never retain recipient/message/token fields from receipts.
        clean={k:value[k] for k in ("status","api_calls","candidates","settled","discovery_evidence") if k in value}
        clean["deliveries"]=[{k:v for k,v in d.items() if k in ("status","sent","blockers")}
                             for d in value.get("deliveries",[])]
        clean["at"]=datetime.fromtimestamp(int(envelope["__REALTIME_TIMESTAMP"])/1e6,timezone.utc).isoformat()
        output.append(clean)
    return output


def live(database: Path, *, since: datetime, now: datetime) -> dict:
    db=readonly(database)
    try:
        tables={}
        for table in ("live_candidates","live_diagnostics","live_publications","live_claims","live_settlements"):
            rows=db.execute("SELECT document,fingerprint FROM "+table+" WHERE created_at>=? AND created_at<=? ORDER BY created_at,id LIMIT 20001",
                            (since.isoformat(),now.isoformat())).fetchall()
            if len(rows)>20000:raise ValueError("LIVE_EVIDENCE_CAP")
            tables[table]=[verified(r[0],r[1],live=True) for r in rows]
        value=live_report(tables["live_candidates"],tables["live_diagnostics"],journal(since,now),
                          tables["live_publications"],tables["live_claims"],tables["live_settlements"],
                          as_of=now,since=since)
    finally:db.close()
    return value


def before(value: object, now: datetime) -> bool:
    try:return utc(value)<=now
    except (ValueError,TypeError,AttributeError):return False


def frozen_replay(shadow: Path, ledger_path: Path, *, audit_path: Path, now: datetime, limit: int) -> dict:
    if not 1<=limit<=MAX_CYCLES: raise ValueError("CYCLE_CAP")
    ledger=ReadOnlyLedger(ledger_path)
    try:
        predictions=ledger.all("prediction")
        known=[]
        for p in predictions:
            receipt=next((r for prefix in ("combo_prediction:","prediction:")
                          if (r:=ledger.get("receipt",prefix+p["prediction_id"])) and r.get("status")=="SENT"),None)
            if receipt and before(receipt.get("sent_at_utc"),now):
                known.append((p,utc(receipt["sent_at_utc"])))
        facts={}
        conflicts=set()
        for fact in ledger.all("leg_result"):
            if not before(fact.get("retrieved_at_utc"),now):continue
            fid=str(fact["fixture_id"])
            if fid in facts:
                keys=("provider_status","fulltime_home","fulltime_away")
                if any(facts[fid].get(k)!=fact.get(k) for k in keys): conflicts.add(fid)
                elif utc(fact["retrieved_at_utc"]) < utc(facts[fid]["retrieved_at_utc"]): facts[fid]=fact
            else:facts[fid]=fact
        for fid in conflicts:facts.pop(fid,None)
    finally:ledger.close()
    db=readonly(shadow)
    events=[]
    selected_rows={name:[] for name in ("A_CURRENT_DOUBLE","B_SINGLES_BASED_V2","C_QUALITY_VALUE_FIRST")}
    simulated={name:[] for name in selected_rows}
    try:
        cycles=[verified(r[0],r[1]) for r in db.execute(
            "SELECT document_json,content_fingerprint FROM lab_v2_shadow_evidence WHERE kind='rehearsal' AND created_at_utc<=? ORDER BY rowid DESC LIMIT ?",
            (now.isoformat(),limit))]
        for cycle in sorted(cycles,key=lambda c:c["evaluated_at_utc"]):
            started=utc(cycle["evaluated_at_utc"])
            phase_id=fingerprint((started,"PUBLICATION_PREPARATION"))+":end"
            phase_row=db.execute("SELECT document_json,content_fingerprint FROM lab_v2_shadow_evidence WHERE kind='cycle_phase' AND identity=?",
                                 (phase_id,)).fetchone()
            if not phase_row:
                events.append({"cycle":started.isoformat(),"status":"BLOCKED_MISSING_PREPARATION_TIME"});continue
            phase=verified(phase_row[0],phase_row[1])
            at=utc(phase["completed_at"])
            if at>now or phase["status"]!="COMPLETED":continue
            candidates=[]
            source=[]
            for identity in cycle["candidate_ids"]:
                record=db.execute("SELECT document_json,content_fingerprint,created_at_utc FROM lab_v2_shadow_evidence WHERE kind='candidate' AND identity=?",
                                  (identity,)).fetchone()
                if record is None:raise ValueError("MISSING_FROZEN_CANDIDATE")
                if utc(record[2])>at:raise ValueError("FUTURE_STORED_CANDIDATE")
                candidates.append(verified(record[0],record[1]));source.append([identity,record[1]])
            if not candidates:continue
            # Same known actual exposure set for all strategies; prior hypothetical
            # choices are separately carried per strategy to prevent replay duplicates.
            exposures=[p for p,sent_at in known if sent_at<=utc(phase["started_at"])]
            same_cycle_dc=[p for p in predictions if p.get("statistics_cohort")=="COMBO_AGREEMENT_20261004_V1"
                           and utc(phase["started_at"])<=utc(p["created_at_utc"])<=at]
            exposures.extend(same_cycle_dc)
            outputs={}
            # Run independently with each strategy's own prior simulated exposures.
            for name in selected_rows:
                value=replay(candidates,exposures+simulated[name],at=at,strategy=name)
                chosen=value[name]["selected"]
                simulated[name].extend(chosen)
                scored=score_replay(chosen,facts,cutoff=now)
                selected_rows[name].extend(scored)
                outputs[name]={k:v for k,v in value[name].items() if k!="selected"}
                outputs[name]["selected"]=[{
                    "prediction_id":p["prediction_id"],"candidate_ids":[l["candidate_id"] for l in p["legs"]],
                    "combined_odds":p["combined_odds"],"naive_joint_probability":p["estimated_probability_if_independent"],
                    "fingerprint":digest(p)} for p in chosen]
            events.append({"cycle":started.isoformat(),"at":at.isoformat(),"preparation_started_at":phase["started_at"],
                           "clock_basis":"RECORDED_PREPARATION_END_NOT_EXACT_SELECTOR_CALL",
                           "candidate_count":len(candidates),"source_candidates":source,
                           "source_pool_fingerprint":digest(candidates),
                           "actual_exposure_fingerprint":digest(exposures),"strategies":outputs})
    finally:db.close()
    # Existing SINGLE/canonical result facts are read only after every selection.
    from app.dixon_coles_research.sources import results
    ids={int(l["fixture_id"]) for values in simulated.values() for p in values for l in p["legs"]}
    for result in results(ledger_path,audit_path,fixture_ids=ids,now=now):
        if result["status"] not in {"VOID","RESOLVED"}:
            continue
        fid=str(result["fixture_id"])
        item={"fixture_id":result["fixture_id"],"outcome":"VOID" if result["status"]=="VOID" else "RESOLVED",
              "provider_status":"RESOLVED_REGULATION_FACT",
              "fulltime_home":result["home_goals"],"fulltime_away":result["away_goals"],
              "retrieved_at_utc":result["settled_at"],"source_fingerprint":result["source_fingerprint"],
              "source_document_fingerprint":result["source_document_fingerprint"]}
        if fid in facts:
            old=facts[fid]
            if ((old["outcome"]=="VOID") != (item["outcome"]=="VOID")
                    or any(old.get(k)!=item[k] for k in ("fulltime_home","fulltime_away"))):
                conflicts.add(fid)
            elif utc(item["retrieved_at_utc"])<utc(old["retrieved_at_utc"]):
                facts[fid]=item
        else:
            facts[fid]=item
    for fid in conflicts:facts.pop(fid,None)
    selected_rows={name:score_replay(values,facts,cutoff=now) for name,values in simulated.items()}
    summaries={}
    for name,rows in selected_rows.items():
        ev=[e for e in events if "strategies" in e]
        summaries[name]={"candidate_count":sum(e["candidate_count"] for e in ev),
                         "selected":len(rows),"no_pick_cycles":sum(not e["strategies"][name]["selected"] for e in ev),
                         **summarize_coupons(rows)}
    return {"version":"COMBO_SELECTION_RESEARCH_V1","as_of":now.isoformat(),"cycles":events,
            "summaries":summaries,"scored_hypothetical_coupons":selected_rows,
            "mode":"RETROSPECTIVE_REPLAY_NOT_PROSPECTIVE","provider_calls":0,"telegram_sends":0,
            "result_facts_fingerprint":digest(facts),"conflicting_result_fixtures_excluded":sorted(conflicts),
            "paired_score_delta":None,"ranking":"NOT_ELIGIBLE",
            "limitations":[
                "Preparation-end clock is observed and all inputs must precede it; exact original selector-call microsecond was not recorded.",
                "Same-cycle DC exposure is retained; strategies use independent in-memory exposure carry-forward.",
                "A/B use existing production selectors; C deliberately refuses selection without verified as-of calibration/joint evidence.",
                "Only already retained final result facts are used. Unobserved results remain pending, not invented losses or wins.",
                "Different selected coupons have different binary targets; their Brier differences are NOT paired score deltas.",
                "A fixed frozen candidate pool is shared, but no claim of prospective superiority or exact original publication reproduction is made."]}


def main() -> None:
    # This entry point is deliberately offline, including imported adapters.
    def denied(*args, **kwargs):
        raise RuntimeError("RESEARCH_NETWORK_DISABLED")
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("audit","shadow","ledger","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--as-of",required=True)
    parser.add_argument("--live-since",required=True)
    parser.add_argument("--cycles",type=int,default=12)
    a=parser.parse_args()
    now,since=utc(a.as_of),utc(a.live_since)
    a.output.mkdir(parents=True,exist_ok=True)
    live_value=live(a.audit,since=since,now=now)
    write(a.output/"live.json",live_value)
    ledger=ReadOnlyLedger(a.ledger)
    try:combo=performance_comparison(ledger,now=now)
    finally:ledger.close()
    write(a.output/"combo.json",combo)
    replay_value=frozen_replay(a.shadow,a.ledger,audit_path=a.audit,now=now,limit=a.cycles)
    write(a.output/"replay.json",replay_value)
    print(json.dumps({"status":"READ_ONLY_RESEARCH_COMPLETE","LIVE":{
        k:live_value[k] for k in ("cycles","natural_provider_calls","candidate_versions","confirmed_publications",
                                  "result_counts","fixture_diagnostic_counts","delivery_status_counts")},
        "COMBO":combo["overall"],"replay":replay_value["summaries"]},sort_keys=True))


if __name__=="__main__":
    main()
