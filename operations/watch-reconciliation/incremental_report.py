"""Read existing frozen forecasts and relevant labels. No capture, fit, DB writes or send."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research import sources
from app.dixon_coles_forward import incremental
from app.dixon_coles_forward.contracts import load_plan


def run(research,audit,ledger,*,now):
    plan=incremental.load_plan();forward=load_plan()
    store=ResearchStore(research,readonly=True,protected_paths=(audit,ledger))
    try:
        if store.get('plan',forward['fingerprint'])!=forward:raise ValueError('FORWARD_PLAN_NOT_ENROLLED')
        forecasts=store.all('forecast');models={m['fingerprint']:m for m in store.all('model')}
    finally:store.close()
    reserved=sources.consumed_holdout_fixtures(audit)
    selected,counts=incremental.eligible_forecasts(forecasts,plan=plan,forward=forward,now=now,additional_reserved=reserved)
    # Empty selection performs no result/label read at all.
    facts=sources.results(ledger,audit,fixture_ids={r['fixture_id'] for r in selected},now=now) if selected else []
    rows,diagnostics=incremental.prepare(forecasts,models,facts,plan=plan,forward=forward,now=now,additional_reserved=reserved)
    return incremental.report(rows,plan=plan,forward=forward,now=now,diagnostics=diagnostics)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('research','audit','ledger'):p.add_argument('--'+key,required=True,type=Path)
    p.add_argument('--as-of',required=True);a=p.parse_args()
    result=run(a.research,a.audit,a.ledger,now=datetime.fromisoformat(a.as_of))
    print(json.dumps(result,sort_keys=True,allow_nan=False))
if __name__=='__main__':main()
