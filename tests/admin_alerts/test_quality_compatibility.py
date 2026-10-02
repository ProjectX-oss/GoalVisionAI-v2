"""Quality-release compatibility: bounded, offline, immutable producer evidence."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

import pytest

from app.admin_alerts.model import UNITS, identity
from app.admin_alerts.output_contracts import expected_document
from app.admin_alerts.rules import completed_health
from app.admin_alerts.sources import MAX_HEALTH_SOURCE, MAX_LINE, health_rows, invocation_output, journal
from app.admin_alerts.store import Store
from app.admin_alerts.model import Event

NOW = 1790915400.0
STAMP = datetime.fromtimestamp(NOW, timezone.utc).isoformat()
INV = 'a' * 32


def observer():
    return dict(stream='PREMATCH', created_at=STAMP, linkage={}, state={}, metrics={},
                LIVE='DISABLED', heavy_training=False, api_calls=0, telegram_sends=0,
                PERFORMANCE={'diagnostic': 'x' * 6500})


def line(doc, inv=INV):
    return json.dumps({'_SYSTEMD_UNIT': UNITS[2], '_SYSTEMD_INVOCATION_ID': inv,
        '__REALTIME_TIMESTAMP': int(NOW * 1e6), '__CURSOR': 'cursor-' + inv,
        'MESSAGE': json.dumps(doc)})


@pytest.mark.parametrize('exact', [False, True])
def test_large_journal_message_uses_all_and_recovers_exact_invocation(tmp_path, exact):
    doc = observer()
    assert 4096 < len(json.dumps(doc)) < MAX_LINE
    calls = []
    def read(args):
        calls.append(args)
        entry = json.loads(line(doc))
        if '--all' not in args:  # Actual journalctl JSON behavior over 4096 bytes.
            entry['MESSAGE'] = None
        return json.dumps(entry)
    events = (invocation_output(UNITS[2], INV, NOW + 1, read) if exact else
              journal({}, NOW + 1, read)[0])
    assert calls and all('--all' in args for args in calls)
    healthy = [e for e in events if e.rule == 'MISSING_OUTPUT' and e.healthy]
    assert len(healthy) == 1 and healthy[0].invocation == INV
    store = Store(tmp_path)
    try:
        fault = Event(UNITS[2], 'MISSING_OUTPUT', INV, INV, NOW, 'journal', invocation=INV)
        other = Event(UNITS[2], 'MISSING_OUTPUT', 'b' * 32, 'b' * 32, NOW, 'journal',
                      invocation='b' * 32)
        store.ingest([fault, other], {}, NOW)
        store.enqueue(NOW)
        store.ingest(events, {}, NOW + 1)
        store.enqueue(NOW + 1)
        rows = dict(store.db.execute('SELECT id,state FROM incidents'))
        assert rows[fault.signature] == 'RECOVERED'
        assert rows[other.signature] == 'OPEN'
        assert store.db.execute("SELECT count(*) FROM outbox WHERE state='SUPERSEDED'").fetchone()[0] == 1
    finally:
        store.close()


@pytest.mark.parametrize('message', [None, 'x' * (MAX_LINE + 1), 'ž' * (MAX_LINE // 2)])
def test_no_proof_from_null_or_oversized_message(message):
    doc = observer()
    if message is not None:
        doc['PERFORMANCE']['diagnostic'] = message
        encoded = json.dumps(doc, ensure_ascii=False)
        assert len(encoded.encode()) > MAX_LINE
    else:
        encoded = None
    row = json.loads(line(doc))
    row['MESSAGE'] = encoded
    events, state = journal({}, NOW, lambda _: json.dumps(row, ensure_ascii=False))
    assert not any(e.rule == 'MISSING_OUTPUT' and e.healthy for e in events)
    assert not state['output_proofs_v1']


def database(path, rows):
    conn = sqlite3.connect(path)
    for table in ('cycle_health', 'observer_runs'):
        conn.execute(f'CREATE TABLE {table}(id TEXT,created_at TEXT,stream TEXT,document TEXT)')
        conn.execute(f'CREATE INDEX {table}_stream_time ON {table}(stream,created_at,id)')
        conn.executemany(f'INSERT INTO {table} VALUES (?,?,?,?)',
            [(f'{i:05}', STAMP, 'PREMATCH', doc) for i, doc in enumerate(rows)])
    conn.commit()
    conn.close()


@pytest.mark.parametrize('payload', [
    {'result': 'HEALTHY', 'quota': {'status': 'OK'}},
    {'result': 'FAILED', 'failure': {'code': 'DATABASE_LOCKED'}},
    {'result': 'FAILED', 'failure': {'code': 'AUTHENTICATION_FAILED'}},
    {'result': 'FAILED', 'publication': {'status': 'UNKNOWN', 'deliveries': [
        {'prediction_id': 'pick-a', 'transport_attempted': True,
         'acknowledgement_received': True, 'receipt_persisted': False}]}},
])
def test_large_performance_preserves_every_health_and_delivery_event(tmp_path, payload):
    base = {**payload, 'created_at': STAMP, 'completed_at': STAMP, 'evidence_at': STAMP}
    doc = {**base, 'PERFORMANCE': {'segments': 'x' * (MAX_LINE * 2)}}
    path = tmp_path / 'producer.db'
    database(path, [json.dumps(doc)])
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    events, state = health_rows(path, {}, NOW + 1)
    expected = [e for unit in (UNITS[0], UNITS[2]) for e in
                completed_health(doc, unit, identity('00000'), NOW + 1, 'health-' + identity('00000'))]
    assert list(map(asdict, events)) == list(map(asdict, expected))
    assert all(cursor == [STAMP, '00000'] for cursor in state.values())
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()
    assert health_rows(path, state, NOW + 2)[0] == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ['producer.db']


@pytest.mark.parametrize('doc', [
    {'PERFORMANCE': 'x' * MAX_HEALTH_SOURCE},
    {'PERFORMANCE': 'x' * MAX_LINE, 'publication': {'data': 'x' * MAX_LINE}},
    {'unrecognized_diagnostic': 'x' * (MAX_LINE + 1)},
])
def test_real_oversize_outside_projection_still_fails_closed(tmp_path, doc):
    path = tmp_path / 'producer.db'
    database(path, [json.dumps(doc)])
    events, _ = health_rows(path, {}, NOW)
    assert len(events) == 2
    assert all(e.facts['reason'] == 'OVERSIZED_RECORD' and not e.healthy for e in events)


@pytest.mark.parametrize('doc', ['{broken', '[]', 'null', '[' * (MAX_LINE + 1)])
def test_bad_json_is_not_recovery_evidence(tmp_path, doc):
    path = tmp_path / 'producer.db'
    database(path, [doc])
    events, _ = health_rows(path, {}, NOW)
    assert events and all(e.rule == 'MONITORING_COVERAGE_DEGRADED' and not e.healthy for e in events)


def test_projection_cursor_bounded_across_more_than_one_page(tmp_path):
    path = tmp_path / 'producer.db'
    database(path, [json.dumps({'result': 'HEALTHY', 'PERFORMANCE': 'x' * 140000})] * 129)
    events, state = health_rows(path, {}, NOW)
    assert all(cursor[1] == '00127' for cursor in state.values())
    assert sum(e.facts.get('reason') == 'SCAN_BACKLOG' for e in events) == 2
    later, state = health_rows(path, state, NOW + 1)
    assert all(cursor[1] == '00128' for cursor in state.values())
    assert not any(e.rule == 'MONITORING_COVERAGE_DEGRADED' for e in later)


def readiness():
    return {'status': 'RESEARCH_DATASET_NOT_READY',
        'dataset_fingerprint': 'a' * 64,
        'counts': {'TRAIN': 626, 'VALIDATION': 3, 'SEALED_HOLDOUT': 313, 'PURGED': 984},
        'required_minimums': {'TRAIN': 1, 'VALIDATION': 30, 'SEALED_HOLDOUT': 100, 'PURGED': 0},
        'training_contract': {'required_classes': [0, 1], 'single_stream': True, 'maximum_rows': 50000},
        'blocked_by': ['VALIDATION_SAMPLE_INSUFFICIENT']}


def test_readiness_block_is_final_artifact_without_training():
    assert expected_document(UNITS[3], readiness())
    assert expected_document(UNITS[3], {'status': 'RESEARCH_DATASET_NOT_READY',
        'counts': None, 'blocked_by': ['DATASET_EMPTY'], 'split_unavailable': True})
    assert not expected_document(UNITS[3], {'status': 'RESEARCH_DATASET_NOT_READY'})
    bad = readiness()
    bad['counts']['VALIDATION'] = True
    assert not expected_document(UNITS[3], bad)
    assert not expected_document(UNITS[3], {**readiness(), 'blocked_by': []})


def test_calibration_block_requires_explicit_unconsumed_evidence():
    doc = {'status': 'CALIBRATION_DATASET_NOT_READY', 'counts': readiness()['counts'],
        'calibration_readiness': {'blocked_by': ['CALIBRATION_FIT_INSUFFICIENT']},
        'research_cycle_consumed': False, 'holdout_consumed': False}
    assert expected_document(UNITS[3], doc)
    for key in ('research_cycle_consumed', 'holdout_consumed'):
        assert not expected_document(UNITS[3], {**doc, key: True})
        assert not expected_document(UNITS[3], {k:v for k,v in doc.items() if k != key})
