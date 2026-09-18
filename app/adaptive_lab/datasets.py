"""Chronological datasets with fixture grouping, label availability purge and embargo."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta
from .contracts import digest, stream_name, utc
from .policy import POLICY


def chronological_dataset(rows: list[dict], stream: str, *, now: datetime,
                          consumed_holdout: set[str] | None = None) -> dict:
    stream_name(stream)
    consumed = consumed_holdout or set()
    rows=sorted((r for r in rows if r['stream']==stream and r['target'] is not None and utc(r['settled_at'])<=utc(now)),
                key=lambda r:(utc(r['prediction_created_at']),r['observation_id']))
    if len(rows)>POLICY.training_rows_limit or len({r['observation_id'] for r in rows})!=len(rows):
        raise ValueError('DATASET_BOUND_OR_DUPLICATE')
    groups=defaultdict(list)
    for row in rows:
        groups[str(row['fixture_id'])].append(row)
    # An entire fixture belongs to one partition, including multiple live snapshots.
    ordered=sorted(groups.values(),key=lambda g:(min(utc(r['prediction_created_at']) for r in g),str(g[0]['fixture_id'])))
    if len(ordered)<10:
        raise ValueError('INSUFFICIENT_CHRONOLOGICAL_GROUPS')
    a,b=int(len(ordered)*.6),int(len(ordered)*.8)
    validation_start=min(utc(r['prediction_created_at']) for r in ordered[a])
    holdout_start=min(utc(r['prediction_created_at']) for r in ordered[b])
    embargo=timedelta(hours=POLICY.embargo_hours)
    parts={'TRAIN':[],'VALIDATION':[],'SEALED_HOLDOUT':[],'PURGED':[]}
    for i,group in enumerate(ordered):
        partition='TRAIN' if i<a else 'VALIDATION' if i<b else 'SEALED_HOLDOUT'
        boundary=validation_start if i<a else holdout_start if i<b else None
        if boundary and any(max(utc(r['settled_at']),utc(r['prediction_created_at'])) >= boundary-embargo for r in group):
            partition='PURGED'
        if partition=='SEALED_HOLDOUT' and any(r['observation_id'] in consumed for r in group):
            partition='PURGED'
        parts[partition].extend(group)
    material={'stream':stream,'created_at':utc(now).isoformat(),'validation_start':validation_start.isoformat(),
              'holdout_start':holdout_start.isoformat(),'embargo_hours':POLICY.embargo_hours,
              'assignments':{k:[(r['observation_id'],r['observation_fingerprint']) for r in v] for k,v in parts.items()}}
    return {**material,'dataset_fingerprint':digest(material),'partitions':parts}
