"""Read-only deterministic operator views; never loads credentials or constructs clients."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from .contracts import canonical
from .repository import AuditRepository
from .metrics import metrics, segments, diagnostics
from .policy import eligibility
from .governance import Governance

COMMANDS=('status','eligibility','report','loss-review','win-review','calibration','champion','challengers',
          'shadow','champion-history','promotion-evidence','rollback-history','why-not-learning',
          'why-not-promoted','why-rollback','unlinked-settlements','fixtures','tracking','candidates',
          'statistics','settlement-diagnostics')


def report(repository: AuditRepository, stream: str, command: str, *, now: datetime) -> dict:
    rows=repository.all('learning_observations',stream)
    if command in {'status','eligibility','why-not-learning'}:
        cycles=repository.all('learning_cycles',stream)
        value=eligibility(rows,stream,now,previous=cycles[-1] if cycles else None)
        if stream=='LIVE' and not rows:
            value['forward_sample_status']='LIVE_FORWARD_SAMPLE_EMPTY'
        return value
    if command in {'report','statistics','calibration'}:
        return {'metrics':metrics(rows,stream),'segments':segments(rows,stream)}
    if command in {'win-review','loss-review'}:
        target=1 if command=='win-review' else 0
        return {'association_only':True,'observations':[{'id':r['observation_id'],'flags':diagnostics(r)} for r in rows if r['target']==target]}
    if command=='champion':
        return {'champion':repository.champion(stream)}
    if command in {'shadow','why-not-promoted'}:
        return {'shadow':[Governance(repository).evidence(r['shadow_id']) for r in repository.all('shadow_runs',stream)]}
    tables={'challengers':'candidate_events','champion-history':'champion_generations','promotion-evidence':'promotion_gates',
            'rollback-history':'rollback_events','why-rollback':'rollback_events','unlinked-settlements':'linkage_diagnostics',
            'fixtures':'live_snapshots','tracking':'live_diagnostics','candidates':'live_candidates',
            'settlement-diagnostics':'live_diagnostics'}
    return {'records':repository.all(tables[command],stream)}


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('product',choices=('learning','live'))
    parser.add_argument('command',choices=COMMANDS)
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--at',help='UTC clock for deterministic eligibility replay')
    args=parser.parse_args(argv)
    from .contracts import utc
    now=utc(args.at) if args.at else datetime.now(timezone.utc)
    repo=AuditRepository(args.database,readonly=True)
    try:
        result=report(repo,'LIVE' if args.product=='live' else 'PREMATCH',args.command,now=now)
        print(canonical(result) if args.json else json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False))
    finally:
        repo.close()
    return 0
