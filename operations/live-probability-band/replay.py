"""Read-only initial-gate replay; never claims, selects, sends or evaluates outcomes."""
import argparse
from collections import Counter
import json
from pathlib import Path
import runpy
import socket
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.adaptive_lab.contracts import digest,utc
from app.live_lab.engine import readiness
from app.live_lab.selection import in_probability_band


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",type=Path,required=True)
    parser.add_argument("--since",required=True)
    parser.add_argument("--until",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    def denied(*a,**k):raise RuntimeError("OUTBOUND_NETWORK_DENIED")
    socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
    since,until=utc(args.since),utc(args.until)
    if until<since:raise ValueError("INVALID_WINDOW")
    helper=runpy.run_path(str(ROOT/"operations/live-combo-research/audit.py"))
    db=helper["readonly"](args.database)
    source=[];tables={}
    try:
        for table in ("live_candidates","live_claims","live_publications"):
            records=db.execute("SELECT id,document,fingerprint FROM "+table+
                               " WHERE created_at<=? ORDER BY created_at,id LIMIT 20001",(until.isoformat(),)).fetchall()
            if len(records)>20000:raise ValueError("SOURCE_BOUND")
            tables[table]=[helper["verified"](r[1],r[2],live=True) for r in records]
            source.extend([table,r[0],r[2]] for r in records)
    finally:db.close()
    candidates={p["prediction_id"]:p for p in tables["live_candidates"]}
    rows=[]
    for p in candidates.values():
        now=utc(p["prepared_at_utc"])
        if not since<=now<=until:continue
        prior=[candidates[c["selection_id"]] for c in tables["live_claims"]
               if utc(c["created_at"])<now and c["selection_id"]!=p["prediction_id"]]
        reasons=readiness(p["state"],p["quote"],float(p["ensemble_probability"]),
                          uncertainty=p["uncertainty_penalty"],now=now,previous=prior,
                          allow_provider_feed=True,quote_age_diagnostic=True,probability_band=True)
        rows.append({"candidate_id":p["prediction_id"],"source_fingerprint":digest(p),
                     "fixture_id":p["fixture_id"],"probability":p["ensemble_probability"],
                     "odds":p["captured_odds"],"original_blockers":p["blockers"],"new_initial_blockers":reasons,
                     "ev_diagnostic":p["expected_value"]})
    published=[candidates[p["selection_id"]] for p in tables["live_publications"]
               if p["status"]=="SENT" and since<=utc(p["sent_at_utc"])<=until]
    eligible=[r for r in rows if not r["new_initial_blockers"]]
    value={"version":"LIVE_PROBABILITY_BAND_INITIAL_GATE_REPLAY_V1","since":since.isoformat(),"until":until.isoformat(),
           "source_fingerprint":digest(source),"candidate_versions":len(rows),"unique_fixtures":len({r["fixture_id"] for r in rows}),
           "initial_eligible_versions":len(eligible),"initial_eligible_fixtures":len({r["fixture_id"] for r in eligible}),
           "eligible_negative_ev_versions":sum(r["ev_diagnostic"]<0 for r in eligible),
           "eligible_zero_ev_versions":sum(r["ev_diagnostic"]==0 for r in eligible),
           "blocker_counts":dict(Counter(x for r in rows for x in r["new_initial_blockers"])),
           "actual_publications":len(published),"actual_publications_inside_new_band":sum(in_probability_band(p["ensemble_probability"]) for p in published),
           "rows":rows,"provider_calls":0,"telegram_sends":0,"production_writes":0,
           "limitations":["Retrospective initial-gate replay using only original frozen input.",
                          "Uses actual historical exposure; not an alternative strategy backtest.",
                          "No candidate replacement, final refresh, hypothetical publication or outcome scoring.",
                          "Eligible versions are repeated observations, not independent bets or guaranteed future picks."]}
    value["fingerprint"]=digest(value)
    encoded=json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n"
    if args.output.exists() and args.output.read_text()!=encoded:raise ValueError("IMMUTABLE_OUTPUT_CONFLICT")
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(encoded)
    print(json.dumps({k:v for k,v in value.items() if k!="rows"},sort_keys=True))


if __name__=="__main__":main()
