"""Offline synthetic chronological replay; never a genuine forward result."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import time
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.dixon_coles_forward import model, service, combo
from app.dixon_coles_research.contracts import seal
from tests.test_dixon_coles_forward import PLAN, START, item, fact, history

def run() -> dict:
    begun=time.process_time(); forecasts=[]; models={}; results=[]; batches=[]; used=set()
    for date in range(10):
        now=START+timedelta(days=date)
        artifact=model.fit(history(),league_id=71,as_of=now,plan=PLAN)
        models[artifact["fingerprint"]]=artifact
        current=[]
        for index in range(3):
            fid=200000+date*3+index
            source=item(index,now=now,fixture_id=fid)
            record=service.forecast(source,artifact=artifact,plan=PLAN,now=now)
            current.append(record);forecasts.append(record)
            score=((date+index)%4,(date*2+index)%3)
            results.append(fact(index,fixture_id=fid,score=score,settled_at=(now+timedelta(hours=3)).isoformat()))
        batch=combo.build_batch(current,plan=PLAN,now=now,used_fixtures=frozenset(used))
        assert batch==combo.build_batch(list(reversed(current)),plan=PLAN,now=now,used_fixtures=frozenset(used))
        batches.append(batch)
        for triples in batch["selections"].values():
            used.update(leg["fixture_id"] for triple in triples for leg in triple["legs"])
    end=START+timedelta(days=11)
    metrics=service.evaluate(forecasts,models,results,plan=PLAN,now=end)
    combos=combo.evaluate(batches,forecasts,results,plan=PLAN,now=end)
    assert metrics["overall"]["fixtures"]==30
    assert metrics["overall"]["market_rows"]==60
    assert metrics["overall"]["kickoff_dates"]==10
    assert all(v["bets"]==10 and v["settled"]==10 for v in combos["policies"].values())
    return seal({"kind":"SYNTHETIC_CONTROLLED_REPLAY_NOT_PROSPECTIVE_EVIDENCE",
        "plan_fingerprint":PLAN["fingerprint"],"fixtures":30,"kickoff_dates":10,
        "forecast_families":len(forecasts),"market_rows":60,"synthetic_training_results":120,
        "deterministic_reversed_input":True,"cpu_seconds":time.process_time()-begun,
        "probability_metrics":metrics,"combo_metrics":combos,
        "predictive_improvement_demonstrated":False,"historical_bookmaker_odds_used":False,
        "provider_calls":0,"telegram_sends":0,"production_writes":0})

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.write_text(json.dumps(run(),indent=2,sort_keys=True)+"\n")
    print("SYNTHETIC_REPLAY_PASS; 30 fixtures; 10 dates; 60 market rows; 10 COMBOs per policy")
