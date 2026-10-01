import json
import pytest

from app.admin_alerts import operator_jobs
from app.admin_alerts.autorepair import enqueue
from app.admin_alerts.delivery import DeliveryError, SenderConfig
from app.admin_alerts.model import DISCOVERY, Event
from app.admin_autorepair.protocol import atomic_json


@pytest.fixture
def job(store, spool):
    enqueue(store, spool, 999)
    store.ingest([Event(DISCOVERY, 'DATABASE_LOCK', 'pipeline', 'one', 1000, 'test')], {}, 1000)
    key = enqueue(store, spool, 1000)
    return json.loads(store.db.execute('SELECT bundle FROM repair_jobs WHERE id=?', (key,)).fetchone()[0])


def status(job, state='RUNNING', heartbeat=1001, sequence=1, **kwargs):
    return {'version':1, 'job_id':job['job_id'], 'state':state, 'started_at':1001,
        'heartbeat_at':heartbeat, 'finished_at':0, 'sequence':sequence, 'outcome':'',
        'changed_files':0, 'elapsed_seconds':heartbeat-1001, 'source_commit':'a'*40,
        'diff_check':'NOT_RUN', 'failure':'', **kwargs}


def write(spool, job, **kwargs):
    atomic_json(spool/'status'/(job['job_id']+'.json'), status(job, **kwargs))


def kinds(store):
    return [r[0] for r in store.db.execute('SELECT kind FROM operator_outbox ORDER BY rowid')]


def test_lifecycle_throttle_completion_no_incident_effects(store, spool, job):
    before = store.report('UNKNOWN')
    for stamp, sequence in ((1001,1),(1300,2),(1600,3),(1601,4),(1700,5),(2201,6)):
        write(spool, job, heartbeat=stamp, sequence=sequence)
        operator_jobs.sync(store, spool, stamp)
    assert kinds(store) == ['STARTED','RUNNING','RUNNING']
    write(spool, job, state='COMPLETED', heartbeat=2300, sequence=7, finished_at=2300,
          outcome='PATCH_READY', changed_files=2, diff_check='PASS')
    operator_jobs.sync(store, spool, 2300)
    operator_jobs.sync(store, spool, 2301)
    assert kinds(store) == ['STARTED','RUNNING','RUNNING','COMPLETED']
    after = store.report('UNKNOWN')
    for key in ('active_fault_count', 'alert_groups', 'incidents'):
        assert after[key] == before[key]


def test_fast_job_preserves_started_and_completed(store, spool, job):
    write(spool, job, state='COMPLETED', heartbeat=1002, sequence=3, finished_at=1002, outcome='NO_CODE_CHANGE')
    operator_jobs.sync(store, spool, 1010)
    assert kinds(store) == ['STARTED','COMPLETED']


def test_stall_once_recovery_then_next_stall_and_terminal(store, spool, job):
    write(spool, job)
    for stamp in (1001,1182,1200,1400):
        operator_jobs.sync(store, spool, stamp)
    assert kinds(store) == ['STARTED','STALLED']
    write(spool, job, heartbeat=1401, sequence=2)
    operator_jobs.sync(store, spool, 1401)
    operator_jobs.sync(store, spool, 1582)
    assert kinds(store) == ['STARTED','STALLED','STALLED']
    write(spool, job, state='TIMEOUT', heartbeat=1700, sequence=3, finished_at=1700, outcome='TIMEOUT', failure='TIMEOUT')
    operator_jobs.sync(store, spool, 1700)
    assert kinds(store)[-1] == 'TIMEOUT'


def test_untrusted_status_extra_text_regression_future_rejected(store, spool, job):
    value = status(job)
    atomic_json(spool/'status'/(job['job_id']+'.json'), {**value,'message':'token secret'})
    assert operator_jobs.sync(store, spool, 1001) == 0
    write(spool, job, heartbeat=1200)
    assert operator_jobs.sync(store, spool, 1001) == 0
    write(spool, job, sequence=4)
    assert operator_jobs.sync(store, spool, 1001) == 1
    write(spool, job, sequence=3, state='COMPLETED', finished_at=1002, outcome='PATCH_READY')
    assert operator_jobs.sync(store, spool, 1002) == 0
    assert kinds(store) == ['STARTED']


class Fake:
    def __init__(self, failure=None):
        self.sent=[]
        self.failure=failure
    def validate(self):
        pass
    def send(self, text):
        self.sent.append(text)
        if self.failure:
            raise self.failure
        return {'message_id':len(self.sent), 'chat':{'id':123, 'type':'private'}}


def sender():
    return SenderConfig(enabled=True, bot_id=42, bot_username='admin_bot',
                        private_chat_id=123, operator_confirmed_start=True)


def test_receipt_persistence_restart_replay_once(store, spool, job):
    write(spool, job, state='COMPLETED', heartbeat=1002, sequence=3, finished_at=1002, outcome='NO_CODE_CHANGE')
    operator_jobs.sync(store, spool, 1002)
    fake=Fake()
    assert operator_jobs.dispatch(store, sender(), fake, 1002) == 2
    operator_jobs.sync(store, spool, 1003)
    assert operator_jobs.dispatch(store, sender(), fake, 1003) == 0
    from app.admin_alerts.store import Store
    reopened=Store(store.root)
    try:
        assert operator_jobs.dispatch(reopened, sender(), fake, 1004) == 0
        assert reopened.db.execute("SELECT count(*) FROM operator_outbox WHERE receipt IS NOT NULL").fetchone()[0] == 2
    finally:
        reopened.close()
    assert len(fake.sent)==2


@pytest.mark.parametrize('crash', [True,False])
def test_uncertain_never_replayed(store, spool, job, crash):
    write(spool, job)
    operator_jobs.sync(store, spool, 1001)
    fake=Fake(DeliveryError('TRANSPORT_UNCERTAIN',uncertain=True))
    if crash:
        with store.db:
            store.db.execute("UPDATE operator_outbox SET state='ATTEMPTING',attempts=1")
    else:
        assert operator_jobs.dispatch(store, sender(), fake, 1001) == 0
    operator_jobs.sync(store, spool, 1100)
    assert operator_jobs.dispatch(store, sender(), Fake(), 1200) == 0
    assert store.db.execute('SELECT state FROM operator_outbox').fetchone()[0]=='UNCERTAIN'


def test_global_budget_includes_incident_attempts(store, spool, job):
    write(spool, job)
    operator_jobs.sync(store, spool, 1001)
    with store.db:
        for _ in range(20):
            store.db.execute("INSERT INTO attempts(outbox,started,result) VALUES ('synthetic',1000,'ATTEMPTED')")
    assert operator_jobs.dispatch(store, sender(), Fake(), 1001)==0
    assert operator_jobs.dispatch(store, sender(), Fake(), 5000, scan_remaining=0)==0


def test_definite_retry_is_bounded(store, spool, job):
    write(spool, job)
    operator_jobs.sync(store, spool, 1001)
    fake=Fake(DeliveryError('RATE_LIMIT', retry_after=30))
    stamp=1001
    for _ in range(5):
        operator_jobs.dispatch(store,sender(),fake,stamp)
        stamp+=2000
    assert len(fake.sent)==5
    assert store.db.execute('SELECT state FROM operator_outbox').fetchone()[0]=='EXHAUSTED'
