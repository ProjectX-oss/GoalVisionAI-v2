"""Retire only the reviewed false DELIVERY_FAILURE; retain every sent receipt."""
import hashlib
import json
import sqlite3
from datetime import datetime

INCIDENT = 'bd52a22acbc330714271ae9a'
REASON = 'PRETRANSPORT_REJECTION_NOT_DELIVERY_FAILURE_V1'
SERVICE = 'goalvision-lab-v2-discover.service'


def stamp(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()


def prove_health(health, key, observed):
    row = health.execute("SELECT stream,document FROM cycle_health WHERE id=?", (key,)).fetchone()
    if not row or row[0] != 'PREMATCH':
        raise ValueError('HEALTH_EVIDENCE_MISSING')
    value = json.loads(row[1])
    pub = value.get('publication') or {}
    deliveries = pub.get('deliveries') or []
    if (stamp(value.get('evidence_at') or value.get('completed_at')) != observed
            or value.get('failure') or value.get('published') != 0
            or pub.get('status') != 'DEGRADED' or pub.get('failure')
            or pub.get('publication_attempt_count') != 0
            or pub.get('send_attempted') is not False
            or pub.get('singles_sent') != 0 or pub.get('combos_sent') != 0
            or not 0 < len(deliveries) <= 200):
        raise ValueError('HEALTH_NOT_PROVEN_PRETRANSPORT')
    for item in deliveries:
        if (item.get('stage') != 'REJECTED_BEFORE_TRANSPORT'
                or item.get('status') != 'SELECTION_ORIGIN_OR_APPROVAL_INVALID'
                or item.get('transport_attempted') is not False
                or any(item.get(k) for k in ('acknowledgement_received','receipt_persisted',
                    'reconciliation_required','claim_persisted','persistence_failure',
                    'transport_failure_kind','unknown_marker_persisted','sent','acknowledgement'))):
            raise ValueError('DELIVERY_NOT_PROVEN_PRETRANSPORT')
    return {'health_id':key, 'sha256':hashlib.sha256(row[1].encode()).hexdigest(),
            'deliveries':len(deliveries), 'observed':observed}


def inspect(db, health):
    row = db.execute('SELECT * FROM incidents WHERE id=?', (INCIDENT,)).fetchone()
    if not row:
        raise ValueError('INCIDENT_MISSING')
    audit = db.execute('SELECT evidence FROM invalidations WHERE incident=?', (INCIDENT,)).fetchone()
    if audit:
        if row['state'] == 'INVALIDATED' and json.loads(audit[0]).get('reason') == REASON:
            return None
        raise ValueError('EXISTING_AUDIT_CONFLICT')
    if (row['rule'] != 'DELIVERY_FAILURE' or row['service'] != SERVICE
            or row['object_id'] != 'UNKNOWN' or row['invocation'] != 'UNKNOWN'
            or row['state'] not in ('OPEN','REPEATED','ESCALATED')
            or row['count'] != 9 or row['episode'] != 1 or row['generation'] != 1):
        raise ValueError('INCIDENT_CHANGED_REVIEW_REQUIRED')
    docs = db.execute('SELECT document FROM source_evidence WHERE incident=?', (INCIDENT,)).fetchall()
    if len(docs) != 9:
        raise ValueError('EVIDENCE_COUNT_MISMATCH')
    proofs, keys = [], set()
    for doc in docs:
        evidence = json.loads(doc[0])
        source = evidence['source']
        if (not source.startswith('health-') or source != evidence['cycle']
                or source != evidence['occurrence'] or evidence['healthy'] is not False
                or evidence['facts'] != {} or evidence['rule'] != row['rule']
                or evidence['service'] != row['service'] or evidence['object_id'] != 'UNKNOWN'
                or evidence['invocation'] != 'UNKNOWN'):
            raise ValueError('EVIDENCE_CONTRADICTION')
        key = source[len('health-'):]
        keys.add(key)
        proofs.append(prove_health(health, key, evidence['observed']))
    if (len(keys) != 9 or min(p['observed'] for p in proofs) != row['first_seen']
            or max(p['observed'] for p in proofs) != row['last_seen']):
        raise ValueError('EVIDENCE_RANGE_MISMATCH')
    outbox = [dict(r) for r in db.execute('SELECT * FROM outbox WHERE incident=?', (INCIDENT,))]
    return dict(row), outbox, proofs


def retire(db, health, now):
    """Caller holds ADMIN scan lock; audit and retirement commit atomically."""
    with db:
        db.execute('BEGIN IMMEDIATE')
        result = inspect(db, health)
        if result is None:
            return 'ALREADY_INVALIDATED'
        row, outbox, proofs = result
        db.execute('INSERT INTO invalidations VALUES (?,?,?,?,?)', (INCIDENT,now,
            json.dumps({'reason':REASON,'health_proofs':proofs},sort_keys=True),
            json.dumps(row,sort_keys=True),json.dumps(outbox,sort_keys=True)))
        db.execute("UPDATE incidents SET state='INVALIDATED' WHERE id=?", (INCIDENT,))
        db.execute("""UPDATE outbox SET state='SUPERSEDED' WHERE incident=?
            AND state='PENDING' AND attempts=0 AND acknowledged=0 AND receipt IS NULL
            AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.outbox=outbox.id)""", (INCIDENT,))
    return 'INVALIDATED'
