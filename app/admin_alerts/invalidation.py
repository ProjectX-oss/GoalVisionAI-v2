"""Conservative eligibility shared by scanning and read-only operator preflight."""
from __future__ import annotations

import json
import sqlite3

from .output_contracts import CONTRACTS

ACTIONABLE = ('OPEN', 'REPEATED', 'ESCALATED')
REASON = 'OUTPUT_CONTRACT_NOT_APPLICABLE'


def eligible(db: sqlite3.Connection, row: sqlite3.Row) -> bool:
    """Recognize v1 absence evidence; unknown or contradictory evidence refuses."""
    contract = CONTRACTS.get(row['service'])
    if (row['rule'] != 'MISSING_OUTPUT' or row['state'] not in ACTIONABLE
            or contract is None or contract.source != 'NONE'
            or contract.association != 'UNAVAILABLE'):
        return False
    try:
        evidence = json.loads(row['evidence'])
    except (ValueError, TypeError):
        return False
    if not isinstance(evidence, dict) or set(evidence) != {
            'service', 'rule', 'object_id', 'occurrence', 'observed', 'source', 'severity',
            'invocation', 'cycle', 'facts', 'healthy', 'debounce'}:
        return False
    # Exact old Event shape, including absence of new contract/diagnostic facts.
    if (evidence.get('source') != 'journal-output' or evidence.get('facts') != {}
            or evidence.get('healthy') is not False or evidence.get('debounce') != 1
            or row['invocation'] == 'UNKNOWN'
            or any(evidence.get(k) != row[k] for k in ('service', 'rule', 'object_id', 'invocation'))
            or row['object_id'] != row['invocation']
            or evidence.get('occurrence') != row['invocation']):
        return False
    sources = db.execute('SELECT DISTINCT source FROM occurrences WHERE incident=?', (row['id'],)).fetchall()
    if not sources or any(r[0] != 'journal-output' for r in sources):
        return False
    # Any independent fault for this invocation is a conservative veto, even if
    # recovered later. Never infer producer success from a NONE contract.
    if db.execute("""SELECT 1 FROM incidents WHERE service=? AND invocation=?
            AND rule!='MISSING_OUTPUT' LIMIT 1""", (row['service'], row['invocation'])).fetchone():
        return False
    return True


IDLE_REASON = 'IDLE_NO_DELIVERY_WORK_NOT_TRANSPORT_FAILURE'


def idle_eligible(db: sqlite3.Connection, row: sqlite3.Row) -> bool:
    """Require the complete retained v1.3 default-UNKNOWN footprint, with no attempts."""
    from .model import Event
    if (row['rule'] != 'ADMIN_DELIVERY_DEGRADED' or row['state'] not in ACTIONABLE
            or row['service'] != 'monitor' or row['object_id'] != 'admin'
            or row['last_sent'] != 0 or row['notified_state'] != ''
            or row['episode'] != 1 or row['count'] != 1):
        return False
    # The defective path defaulted an ABSENT delivery state. Any retained transport
    # state (including validation failures without attempt rows) vetoes cleanup.
    if db.execute("SELECT 1 FROM metadata WHERE key='delivery'").fetchone():
        return False
    try:
        evidence = json.loads(row['evidence'])
        expected = Event('monitor', 'ADMIN_DELIVERY_DEGRADED', 'admin', 'UNKNOWN',
                         row['first_seen'], 'admin-transport', facts={'code': 'UNKNOWN'})
        if evidence != expected.document() or row['id'] != expected.signature:
            return False
        retained = db.execute('SELECT document FROM source_evidence WHERE incident=?', (row['id'],)).fetchall()
        if not retained or any(json.loads(r[0]) != evidence for r in retained):
            return False
    except (ValueError, TypeError):
        return False
    occurrences = db.execute('SELECT * FROM occurrences WHERE incident=?', (row['id'],)).fetchall()
    if len(occurrences) != 1 or occurrences[0]['source'] != 'admin-transport':
        return False
    for outbox in db.execute('SELECT * FROM outbox WHERE incident=?', (row['id'],)):
        if (outbox['state'] not in ('PENDING', 'SUPERSEDED') or outbox['attempts'] != 0
                or outbox['acknowledged'] != 0 or outbox['receipt'] is not None
                or outbox['error'] is not None or db.execute(
                    'SELECT 1 FROM attempts WHERE outbox=?', (outbox['id'],)).fetchone()):
            return False
    return True
