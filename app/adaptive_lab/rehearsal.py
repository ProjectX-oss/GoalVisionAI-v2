"""One read-only inventory over already persisted real Lab evidence. No network."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from .observations import ReadOnlyLedger, import_prematch
from .repository import AuditRepository
from .policy import eligibility
from .metrics import metrics


def real_rehearsal(ledger_path: Path, *, now: datetime) -> dict:
    """All linkage projections are disposable in-memory records, never real DB writes."""
    source=ReadOnlyLedger(ledger_path)
    scratch=AuditRepository(':memory:')
    try:
        linkage=import_prematch(source,scratch,now=now.isoformat())
        rows=scratch.all('learning_observations','PREMATCH')
        singles=[r for r in rows if r['source_product']=='SINGLE']
        actual=source.all('single_settlement')
        published=[r for r in actual if source.get('receipt','single_prediction:'+r['prediction_id'])]
        combos=scratch.all('combo_analytics','COMBO')
        return {'linkage':linkage,'PREMATCH':{'published_settlements':len(published),
            'raw_outcomes':{s:sum(r['status']==s for r in published) for s in ('WON','LOST','VOID')},
            'linked_single_metrics':metrics(singles,'PREMATCH'),'learning_metrics':metrics(rows,'PREMATCH'),
            'eligibility':eligibility(rows,'PREMATCH',now),
            'missing_provenance':sorted({k for r in rows for k in r['missing_provenance']})},
            'COMBO':{'resolved':len(combos),'outcomes':{s:sum(r['outcome']==s for r in combos) for s in ('WON','LOST','VOID','PARTIAL_VOID')},
                     'flat_unit_pnl':sum(float(r['flat_unit_pnl']) for r in combos),'predictive_combo_targets':0},
            'LIVE':{'real_observations':0,'status':'LIVE_FORWARD_SAMPLE_EMPTY'},
            'challenger_created':False,'activation_performed':False,'external_api_calls':0,'telegram_sends':0,
            'database':{'foreign_key_check':[list(r) for r in scratch.connection.execute('PRAGMA foreign_key_check')],
                        'integrity_check':scratch.connection.execute('PRAGMA integrity_check').fetchone()[0]}}
    finally:
        source.close(); scratch.close()
