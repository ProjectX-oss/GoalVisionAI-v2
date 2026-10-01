import json
import sqlite3
from dataclasses import replace
from unittest.mock import patch

import pytest

from app.admin_alerts.autorepair import bundle, enqueue
from app.admin_alerts.model import DISCOVERY, Event
from app.admin_autorepair.protocol import atomic_json, job_id, read_json, validate_bundle


def event(key='one', **kwargs):
    return Event(DISCOVERY, 'DATABASE_LOCK', key, key, 1000, 'test', **kwargs)


def add(store, value):
    store.ingest([value], {}, value.observed)
    return store.db.execute('SELECT * FROM incidents WHERE id=?', (value.signature,)).fetchone()


def test_activation_and_reopened_episode(store, spool):
    value = event()
    add(store, value)
    assert enqueue(store, spool, 1000) is None
    assert enqueue(store, spool, 1001) is None
    add(store, replace(value, healthy=True, observed=1002))
    add(store, replace(value, occurrence='again', observed=1003))
    key = enqueue(store, spool, 1003)
    assert key == job_id(value.signature, 2)
    for _ in range(5):
        assert enqueue(store, spool, 1004) is None
    assert len(list((spool/'queue').iterdir())) == 1
    assert store.db.execute('SELECT count(*) FROM repair_jobs').fetchone()[0] == 1


@pytest.mark.parametrize('state', ['PENDING', 'RECOVERED', 'INVALIDATED'])
def test_ineligible_states(store, spool, state):
    enqueue(store, spool, 1000)
    value = event()
    add(store, value)
    with store.db:
        store.db.execute('UPDATE incidents SET state=?', (state,))
    assert enqueue(store, spool, 1001) is None


def test_activation_snapshots_all_active_and_pending(store, spool):
    for i, state in enumerate(('OPEN', 'REPEATED', 'ESCALATED', 'PENDING')):
        value = event(str(i))
        add(store, value)
        with store.db:
            store.db.execute('UPDATE incidents SET state=? WHERE id=?', (state, value.signature))
    enqueue(store, spool, 1001)
    assert store.db.execute('SELECT count(*) FROM repair_exclusions').fetchone()[0] == 4
    with store.db:
        store.db.execute("UPDATE incidents SET state='OPEN'")
    assert enqueue(store, spool, 1002) is None


def test_caps_and_terminal_frees_slot(store, spool):
    enqueue(store, spool, 999)
    for i in range(7):
        add(store, event(str(i)))
    for i in range(5):
        enqueue(store, spool, 1000+i)
        assert len(list((spool/'queue').iterdir())) == i+1
    assert enqueue(store, spool, 1006) is None
    first = store.db.execute('SELECT id FROM repair_jobs LIMIT 1').fetchone()[0]
    with store.db:
        store.db.execute("INSERT INTO operator_jobs VALUES (?,'COMPLETED',1,'{}',0,0)", (first,))
    (spool/'queue'/(first+'.json')).rename(spool/'done'/(first+'.json'))
    assert enqueue(store, spool, 1007)


def test_crash_between_db_and_spool_reconciles_once(store, spool):
    enqueue(store, spool, 999)
    add(store, event())
    with patch('app.admin_alerts.autorepair.atomic_json', side_effect=OSError()):
        with pytest.raises(OSError):
            enqueue(store, spool, 1000)
    assert store.db.execute('SELECT count(*) FROM repair_jobs').fetchone()[0] == 1
    assert enqueue(store, spool, 1001)
    assert enqueue(store, spool, 1002) is None


def test_maintenance_excludes_episode_after_expiry(store, spool):
    enqueue(store, spool, 999)
    add(store, event())
    with store.db:
        store.put('maintenance', {'x': {'scope': DISCOVERY, 'until': 1005}})
    assert enqueue(store, spool, 1000) is None
    assert enqueue(store, spool, 1010) is None


@pytest.mark.parametrize('table', ['repair_activation', 'repair_exclusions', 'repair_jobs'])
def test_history_immutable(store, spool, table):
    add(store, event('old'))
    enqueue(store, spool, 999)
    add(store, event())
    enqueue(store, spool, 1000)
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute(f'DELETE FROM {table}')
    store.db.rollback()


@pytest.mark.parametrize('rule,mode', [
    ('DATABASE_LOCK','FIX_ALLOWED'), ('SERVICE_FAILURE','FIX_ALLOWED'),
    ('INTEGRITY_FAILURE','FIX_ALLOWED'), ('MISSING_OUTPUT','FIX_ALLOWED'),
    ('QUOTA_DB_CONTENTION','FIX_ALLOWED'), ('PROVIDER_FAILURE','DIAGNOSE_ONLY'),
    ('AUTH_FAILURE','DIAGNOSE_ONLY'), ('QUOTA_FAILURE','DIAGNOSE_ONLY'),
    ('DELIVERY_UNCERTAIN','DIAGNOSE_ONLY'), ('DELIVERY_FAILURE','DIAGNOSE_ONLY'),
    ('TIMER_INACTIVE','DIAGNOSE_ONLY'), ('MISSING_START','DIAGNOSE_ONLY')])
def test_mapping(store, rule, mode):
    row = add(store, replace(event(), rule=rule))
    value = bundle(dict(row), 1001)
    assert value['target'] == 'PREMATCH'
    assert value['mode'] == mode
    assert validate_bundle(value) == value


def test_admin_target_and_config_diagnose(store):
    row = add(store, replace(event(), service='monitor', rule='MONITORING_COVERAGE_DEGRADED',
        facts={'reason': 'OUTPUT_CONTRACT_ROUTE_UNKNOWN'}))
    value = bundle(dict(row), 1001)
    assert value['target'] == 'ADMIN'
    assert value['mode'] == 'DIAGNOSE_ONLY'
    validate_bundle(value)


def test_no_free_text_even_in_identifier_or_fact(store):
    secret = 'SECRET_TOKEN_WITHOUT_PUNCTUATION'
    row = add(store, replace(event(secret), invocation=secret, cycle=secret, facts={
        'message': secret, 'exception': secret, 'code': secret, 'exit_status': secret,
        'result': secret, 'reason': secret, 'claim_exists': True, 'receipt_persisted': False}))
    value = bundle(dict(row), 1001)
    assert secret not in json.dumps(value)
    assert value['facts'] == {'claim_exists': True, 'receipt_persisted': False}
    validate_bundle(value)
    with pytest.raises(ValueError):
        validate_bundle({**value, 'message': secret})


def test_bounded_and_symlink_rejection(spool, tmp_path):
    path = spool/'queue'/'x.json'
    with pytest.raises(ValueError):
        atomic_json(path, {'x': 'a'*65536})
    assert not path.exists()
    target = tmp_path/'target'
    target.write_text('{}')
    path.symlink_to(target)
    with pytest.raises(OSError):
        read_json(path)
    assert target.read_text() == '{}'


def test_group_access_despite_admin_umask(spool):
    import os
    from app.admin_autorepair.protocol import spool_lock
    before = os.umask(0o077)
    try:
        with spool_lock(spool):
            atomic_json(spool/'queue'/'x.json', {})
    finally:
        os.umask(before)
    assert (spool/'handoff.lock').stat().st_mode & 0o777 == 0o660
    assert (spool/'queue'/'x.json').stat().st_mode & 0o777 == 0o660
