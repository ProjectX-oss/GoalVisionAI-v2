"""Bounded read-only review of cached natural pools; never prospective or a send."""
from collections import Counter
from datetime import datetime
from decimal import Decimal,InvalidOperation
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.lab_private_single.policy import review


def replay(database: Path, count=3):
    db=sqlite3.connect(database.absolute().as_uri()+'?mode=ro',uri=True,timeout=.1)
    db.execute('PRAGMA query_only=ON')
    deadline=time.monotonic()+30
    db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    results=[]
    try:
        cycles=db.execute("SELECT created_at_utc,document_json FROM lab_v2_shadow_evidence WHERE kind='rehearsal' ORDER BY rowid DESC LIMIT ?",(count,)).fetchall()
        upper=None
        for started,encoded in cycles:
            cycle=json.loads(encoded)
            publication=db.execute("SELECT created_at_utc FROM lab_v2_shadow_evidence WHERE kind='publication_cycle' AND created_at_utc>=? AND (? IS NULL OR created_at_utc<?) ORDER BY rowid ASC LIMIT 1",(started,upper,upper)).fetchone()
            upper=started
            if publication is None:
                results.append({'cycle':started,'status':'NO_COMPLETED_PUBLICATION_BOUNDARY'});continue
            cutoff=datetime.fromisoformat(publication[0])
            ids=list(dict.fromkeys(cycle.get('candidate_ids',[])))
            if len(ids)>5000:raise ValueError('REPLAY_CANDIDATE_CAP')
            numeric=[];qualified=[];reasons=Counter();fixtures=set()
            for identity in ids:
                if time.monotonic()>deadline:raise TimeoutError('REPLAY_BUDGET')
                raw=db.execute("SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='candidate' AND identity=?",(identity,)).fetchone()
                if raw is None:raise ValueError('MISSING_CANDIDATE')
                row=json.loads(raw[0]);fixtures.add(row['fixture_id'])
                try:
                    p,o=Decimal(str(row['ensemble_probability'])),Decimal(str(row['captured_odds']))
                    match=p.is_finite() and o.is_finite() and o>=Decimal('1.70') and Decimal('.70')<=p<=Decimal('.80')
                except (KeyError,InvalidOperation,ValueError,TypeError):match=False
                if not match:continue
                numeric.append(identity)
                gate=review(row,now=cutoff)
                reasons.update(gate['rejection_reasons'])
                if gate['eligible']:
                    qualified.append({k:row.get(k) for k in ('fixture_id','market','captured_odds','ensemble_probability','candidate_id')})
            results.append({'cycle':started,'reviewed_as_of':cutoff.isoformat(),'candidates':len(ids),
                'fixtures':len(fixtures),'numeric_matches':len(numeric),'quality_eligible':len(qualified),
                'eligible':qualified,'numeric_match_blockers':dict(sorted(reasons.items()))})
    finally:db.close()
    return {'scope':'DEVELOPMENT_ONLY_CACHED_REPLAY_NOT_PROSPECTIVE','cycles':results,
            'provider_calls':0,'telegram_sends':0,'database_writes':0}

if __name__=='__main__':
    print(json.dumps(replay(Path('/home/arvis/GoalVisionAI/var/lab_v2/shadow.db')),sort_keys=True,indent=2))
