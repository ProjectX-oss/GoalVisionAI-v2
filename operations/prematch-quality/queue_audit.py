"""Reproduce frozen pending-review ordering without calling the worker/provider."""
from datetime import datetime
from pathlib import Path
import json
import sqlite3
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.lab_v2_shadow.profiles import resource_priority

def verify(path: Path, cycles: list[dict]) -> dict:
    db = sqlite3.connect(Path(path).absolute().as_uri()+"?mode=ro", uri=True, timeout=.2)
    db.execute("PRAGMA query_only=ON")
    deadline=time.monotonic()+35
    db.set_progress_handler(lambda: int(time.monotonic()>deadline),1000)
    rows=[]
    try:
        for cycle in sorted(cycles, key=lambda c:c["evaluated_at_utc"]):
            at=cycle["evaluated_at_utc"]; q=cycle.get("final_review_queue") or {}
            states={int(s["fixture_id"]):s for s in cycle["global_fixture_states"]}
            due=q.get("due_fixture_ids",[]); attempted=q.get("attempted_fixture_ids",[])
            origins={}
            for r in cycle.get("tracked_final_reviews",[]):
                fid=int(r["fixture_id"])
                if fid not in due:continue
                origin=r.get("origin_candidate_id")
                if origin:
                    found=db.execute("SELECT created_at_utc FROM lab_v2_shadow_evidence WHERE kind='candidate' AND identity=?",(origin,)).fetchone()
                    if found and found[0]<at:origins[fid]=True
            prior={}
            for fid in due:
                prefix="review:"+str(fid)+":"
                found=db.execute("SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='enrichment_service' AND identity>=? AND identity<? ORDER BY identity DESC LIMIT 1",(prefix,prefix+at)).fetchone()
                prior[fid]=json.loads(found[0])["at"] if found else ""
            expected=sorted(due,key=lambda fid:(fid not in origins,states[fid]["kickoff_utc"],prior[fid],resource_priority(states[fid]),fid))
            invalid=[]
            now=datetime.fromisoformat(at)
            from zoneinfo import ZoneInfo
            for fid in attempted:
                state=states[fid];kick=datetime.fromisoformat(state["kickoff_utc"]);local=kick.astimezone(ZoneInfo("Europe/Riga"))
                lead=(kick-now).total_seconds()/60
                profile=state.get("competition_profile")
                if not (10<lead<=75 and local.date()==now.astimezone(ZoneInfo("Europe/Riga")).date() and 9<=local.hour<23) or profile in {"U17_AND_BELOW","DISALLOWED","NON_FOOTBALL"}:
                    invalid.append(fid)
            rows.append({
                "at":at,"due":len(due),"attempted":len(attempted),
                "same_cycle_duplicates":len(attempted)-len(set(attempted)),
                "batch_limit_pass":len(attempted)<=q.get("maximum_batches",2)*q.get("maximum_per_batch",5),
                "invalid_window_attempts":invalid,
                "first_batch_follows_initial_due_order":attempted[:min(5,len(attempted))]==due[:min(5,len(attempted))],
                "deadline_and_least_recent_order_reproduced":expected==due,
                "tracked_membership_basis":"FROZEN_ORIGIN_CANDIDATE_PRECEDES_CYCLE",
                "prior_review_timestamps":{str(k):v or None for k,v in prior.items()},
                "recorded_due":due,"reproduced_due":expected,
                "pending_recorded":q.get("pending_fixture_ids",[]),
                "provider_calls":cycle["api_calls_consumed"],
                "cycle_ceiling":cycle["adaptive_quota_budget"]["effective_cycle_maximum"],
            })
        carry=[]
        ordered=sorted(cycles,key=lambda c:c["evaluated_at_utc"])
        for a,b in zip(ordered,ordered[1:]):
            pending=set((a.get("final_review_queue") or {}).get("pending_fixture_ids",[]))
            next_due=set((b.get("final_review_queue") or {}).get("due_fixture_ids",[]))
            next_attempted=set((b.get("final_review_queue") or {}).get("attempted_fixture_ids",[]))
            if pending:
                carry.append({"from":a["evaluated_at_utc"],"to":b["evaluated_at_utc"],
                              "pending":len(pending),"still_due_next_cycle":len(pending&next_due),
                              "reviewed_next_cycle":len(pending&next_attempted)})
        return {"version":"PREMATCH_QUEUE_FROZEN_REPLAY_V1","cycles":rows,"carry_forward":carry,
                "manual_cycles":0,"provider_calls":0,
                "limitations":["Origins establish preexisting tracked membership; terminal transitions within a cycle remain separately recorded.",
                               "Expired kickoffs need not remain in the next due queue.",
                               "Frozen final-review queue contains two batches; new preliminary candidates can join batch two.",
                               "Window checks use the pre-evening-release calendar active at these recorded starts."]}
    finally:db.close()

if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow",required=True,type=Path)
    parser.add_argument("--as-of",required=True)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    cutoff=datetime.fromisoformat(args.as_of)
    if cutoff.tzinfo is None:
        raise ValueError("OFFSET_REQUIRED")
    db=sqlite3.connect(args.shadow.absolute().as_uri()+"?mode=ro",uri=True,timeout=.2)
    db.execute("PRAGMA query_only=ON")
    deadline=time.monotonic()+35
    db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    try:
        cycles=[json.loads(r[0]) for r in db.execute(
            "SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='rehearsal' AND created_at_utc<=? ORDER BY rowid DESC LIMIT 12",
            (cutoff.isoformat(),))]
    finally:db.close()
    report=verify(args.shadow,cycles)
    report["as_of"]=cutoff.isoformat()
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("QUEUE_REPLAY_COMPLETE")
