"""Audit retirement, replay and future real fault/recovery on isolated SQLite."""
import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
import pytest
from app.admin_alerts.model import Event, DISCOVERY
from app.admin_alerts.store import Store


@pytest.fixture
def evidence(tmp_path):
    spec=importlib.util.spec_from_file_location('cleanup','operations/admin-autorepair/retire_false_delivery.py')
    cleanup=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleanup)
    store=Store(tmp_path)
    health=sqlite3.connect(':memory:')
    health.execute('CREATE TABLE cycle_health(id TEXT,stream TEXT,document TEXT)')
    for i in range(9):
        when=1000+i
        stamp=datetime.fromtimestamp(when,timezone.utc).isoformat()
        key=str(i)
        doc={'evidence_at':stamp,'published':0,'publication':{'status':'DEGRADED',
            'publication_attempt_count':0,'send_attempted':False,'singles_sent':0,
            'combos_sent':0,'deliveries':[{'stage':'REJECTED_BEFORE_TRANSPORT',
            'status':'SELECTION_ORIGIN_OR_APPROVAL_INVALID','transport_attempted':False}]}}
        health.execute('INSERT INTO cycle_health VALUES (?,?,?)',(key,'PREMATCH',json.dumps(doc)))
        event=Event(DISCOVERY,'DELIVERY_FAILURE','UNKNOWN','health-'+key,when,
                    'health-'+key,cycle='health-'+key)
        store.ingest([event],{},when)
    store.enqueue(1010)
    store.db.execute("UPDATE outbox SET state='SENT',attempts=1,acknowledged=1,receipt='{}'")
    store.db.commit()
    yield cleanup,store,health,event
    store.close();health.close()


def test_retirement_audit_preserves_receipts_and_future_faults(evidence):
    cleanup,store,health,old=evidence
    sent=[tuple(r) for r in store.db.execute('SELECT * FROM outbox')]
    assert cleanup.retire(store.db,health,1100)=='INVALIDATED'
    assert cleanup.retire(store.db,health,1101)=='ALREADY_INVALIDATED'
    assert [tuple(r) for r in store.db.execute('SELECT * FROM outbox')]==sent
    store.ingest([old],{},1102)
    store.enqueue(4000)
    assert [tuple(r) for r in store.db.execute('SELECT * FROM outbox')]==sent
    fault=Event(DISCOVERY,'DELIVERY_FAILURE','UNKNOWN','new-fault',4001,'synthetic')
    store.ingest([fault],{},4001)
    store.enqueue(4001)
    new=store.db.execute("SELECT * FROM incidents WHERE state='OPEN'").fetchone()
    assert new and new['id']!=cleanup.INCIDENT
    assert store.db.execute("SELECT count(*) FROM outbox WHERE state='PENDING'").fetchone()[0]==1
    store.ingest([Event(DISCOVERY,'DELIVERY_FAILURE','UNKNOWN','real-recovery',4002,
                        'synthetic',healthy=True)],{},4002)
    assert store.db.execute('SELECT state FROM incidents WHERE id=?',(new['id'],)).fetchone()[0]=='RECOVERED'
    assert store.db.execute('SELECT state FROM incidents WHERE id=?',(cleanup.INCIDENT,)).fetchone()[0]=='INVALIDATED'
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute('DELETE FROM invalidations')


@pytest.mark.parametrize('change',['attempt','missing','count','evidence','health_failure'])
def test_ambiguous_or_real_delivery_is_not_retired(evidence,change):
    cleanup,store,health,_=evidence
    if change=='missing':
        health.execute("DELETE FROM cycle_health WHERE id='0'")
    elif change in ('attempt','health_failure'):
        doc=json.loads(health.execute("SELECT document FROM cycle_health WHERE id='0'").fetchone()[0])
        if change=='attempt':
            doc['publication']['deliveries'][0]['transport_attempted']=True
        else:
            doc['publication']['failure']={'code':'TRANSPORT_ERROR'}
        health.execute("UPDATE cycle_health SET document=? WHERE id='0'",(json.dumps(doc),))
    elif change=='count':
        store.db.execute('UPDATE incidents SET count=10')
    else:
        store.db.execute("INSERT INTO source_evidence VALUES ('contradiction',?,1100,'{}')",(cleanup.INCIDENT,))
    store.db.commit()
    with pytest.raises((ValueError,KeyError)):
        cleanup.retire(store.db,health,1100)
    assert store.db.execute('SELECT count(*) FROM invalidations').fetchone()[0]==0
    assert store.db.execute('SELECT state FROM incidents').fetchone()[0]=='REPEATED'


def test_delayed_genuine_fault_is_not_hidden_by_old_timestamp(evidence):
    cleanup,store,health,_=evidence
    cleanup.retire(store.db,health,1100)
    store.ingest([Event(DISCOVERY,'DELIVERY_FAILURE','UNKNOWN','late-real-fault',
                        900,'synthetic')],{},1200)
    assert store.db.execute("SELECT count(*) FROM incidents WHERE state='OPEN'").fetchone()[0]==1


def test_retirement_failure_rolls_back_audit_and_incident(evidence):
    cleanup,store,health,_=evidence
    store.db.execute("""CREATE TRIGGER reject_retirement BEFORE UPDATE ON incidents
        WHEN NEW.state='INVALIDATED' BEGIN SELECT RAISE(ABORT,'INJECTED_FAILURE'); END""")
    store.db.commit()
    with pytest.raises(sqlite3.IntegrityError,match='INJECTED_FAILURE'):
        cleanup.retire(store.db,health,1100)
    assert store.db.execute('SELECT count(*) FROM invalidations').fetchone()[0]==0
    assert store.db.execute('SELECT state FROM incidents').fetchone()[0]=='REPEATED'
