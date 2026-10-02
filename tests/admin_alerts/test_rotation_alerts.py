"""Offline regression for the operator-reported historical rotation reminder."""
from dataclasses import replace
import json
from unittest.mock import Mock
import pytest

from app.admin_alerts.model import Event, coverage, alert, rotation_gap_reason
from app.admin_alerts.sources import tail
from app.admin_alerts.store import Store
from app.admin_alerts.delivery import SenderConfig, dispatch, delivery_work, DeliveryError
from app.admin_alerts.activation import prepare_epoch
from test_monitor import NOW, FakeTransport

CONFIG=SenderConfig(True,"",99,"AdminBot",123,True)

@pytest.fixture
def store(tmp_path):
    root=tmp_path/"admin";root.mkdir()
    value=Store(root)
    prepare_epoch(value.db,NOW-10)
    yield value
    value.close()

def gap(reason="ROTATED_INODE_LOST"):
    return coverage("stdout",NOW,reason,object_id="stdout-rotation")

def seed(store,event):
    store.ingest([event],{},NOW)
    store.enqueue(NOW)
    assert dispatch(store,CONFIG,FakeTransport(),NOW+1)==1

def row(store,event):
    return dict(store.db.execute("SELECT * FROM incidents WHERE id=?",(event.signature,)).fetchone())

@pytest.mark.parametrize("reason",["ROTATED_INODE_LOST","FILE_TRUNCATED","FILE_REWRITTEN"])
def test_acknowledged_gap_has_no_clock_only_reminder_but_new_gap_alerts(store,reason):
    event=gap(reason)
    assert event.signature=="c7df1386cf441d629cbc83b9"
    seed(store,event)
    before=row(store,event)
    histories={table:list(map(tuple,store.db.execute("SELECT * FROM "+table))) for table in
        ["outbox","attempts","notification_epochs","epoch_incidents"]}
    for offset in [1802,3602,86400]:
        store.ingest([event],{},NOW+offset)
        store.enqueue(NOW+offset)
        transport=Mock()
        assert dispatch(store,CONFIG,transport,NOW+offset)==0
        transport.validate.assert_not_called();transport.send.assert_not_called()
    assert row(store,event)==before
    assert histories=={table:list(map(tuple,store.db.execute("SELECT * FROM "+table))) for table in histories}
    assert store.report("release")["monitoring_state"]=="DEGRADED" # no invented recovery
    later=replace(event,occurrence="new-physical-gap",observed=NOW+90000)
    store.ingest([later],{},NOW+90000);store.enqueue(NOW+90000)
    assert row(store,event)["count"]==2
    assert dispatch(store,CONFIG,FakeTransport(),NOW+90001)==1

@pytest.mark.parametrize("state,attempts",[("PENDING",0),("UNCERTAIN",1),("PERMANENT",1),("EXHAUSTED",5)])
def test_old_queued_reminder_is_not_resent_and_attempt_history_is_retained(store,state,attempts):
    event=gap();seed(store,event)
    original=dict(store.db.execute("SELECT * FROM outbox").fetchone())
    with store.db:
        store.db.execute("INSERT INTO outbox(id,incident,generation,body,state,created,due,attempts,episode) "
            "VALUES (?,?,?,?,?,?,?,?,?)",("legacy-reminder",event.signature,1,"old-body",state,NOW+1801,NOW+1801,attempts,1))
        if attempts:
            store.db.execute("INSERT INTO attempts(outbox,started,result) VALUES (?,?,?)",
                ("legacy-reminder",NOW+1801,"TRANSPORT_UNCERTAIN"))
    history=dict(store.db.execute("SELECT * FROM outbox WHERE id='legacy-reminder'").fetchone())
    assert not delivery_work(store,NOW+1802)
    store.enqueue(NOW+1802)
    after=dict(store.db.execute("SELECT * FROM outbox WHERE id='legacy-reminder'").fetchone())
    if attempts:assert after==history
    else:
        assert after["state"]=="SUPERSEDED"
        assert store.db.execute("SELECT 1 FROM notification_audit WHERE outbox='legacy-reminder'").fetchone()
    assert dict(store.db.execute("SELECT * FROM outbox WHERE id=?",(original["id"],)).fetchone())==original
    # New physical evidence cannot revive an old uncertain body or be blocked by it.
    new=replace(event,occurrence="new-gap",observed=NOW+4000)
    store.ingest([new],{},NOW+4000);store.enqueue(NOW+4000)
    work=delivery_work(store,NOW+4001)
    assert len(work)==1 and work[0]["id"]!="legacy-reminder"
    assert work[0]["generation"]==row(store,event)["generation"]==2
    fake=FakeTransport()
    assert dispatch(store,CONFIG,fake,NOW+4001)==1 and "old-body" not in fake.messages[0]

@pytest.mark.parametrize("event",[
    coverage("stdout",NOW,"READ_UNAVAILABLE"),
    coverage("health",NOW,"OVERSIZED_RECORD"),
    coverage("journal",NOW,"READ_OR_CURSOR_UNAVAILABLE"),
    coverage("stdout",NOW,"UNKNOWN_REASON",object_id="stdout-rotation"),
    Event("producer","MONITORING_COVERAGE_DEGRADED","stdout-rotation","x",NOW,"stdout",
          facts={"reason":"ROTATED_INODE_LOST"}),
])
def test_real_ongoing_or_unknown_coverage_faults_keep_reminders(store,event):
    seed(store,event);store.enqueue(NOW+1802)
    assert dispatch(store,CONFIG,FakeTransport(),NOW+1803)==1

def test_initial_uncertain_rotation_notification_keeps_its_retry(store):
    event=gap();store.ingest([event],{},NOW);store.enqueue(NOW)
    fake=FakeTransport(DeliveryError("TIMEOUT",uncertain=True))
    assert dispatch(store,CONFIG,fake,NOW)==0
    assert delivery_work(store,NOW+31)
    fake.failure=None
    assert dispatch(store,CONFIG,fake,NOW+31)==1

@pytest.mark.parametrize("kind",["lost","truncated","rewritten"])
def test_rotation_occurrences_replay_stably_and_detect_later_identical_gap(tmp_path,kind):
    path=tmp_path/"stdout.jsonl"
    content=json.dumps({"value":"aaaa"})+"\n"
    path.write_text(content)
    _,_,state,_=tail(path,{},NOW,running=False)
    events=[]
    for n in range(2):
        if kind=="lost":
            path.rename(tmp_path/("away"+str(n)));path.write_text(content)
        elif kind=="truncated":path.write_text("")
        else:path.write_text(json.dumps({"value":"bbbb" if n==0 else "cccc"})+"\n")
        _,issues,next_state,_=tail(path,state,NOW+10+n,running=False)
        issue=next(e for e in issues if e.object_id=="stdout-rotation")
        _,again,_,_=tail(path,state,NOW+20+n,running=False)
        assert next(e for e in again if e.object_id=="stdout-rotation").occurrence==issue.occurrence
        assert next_state["rotation_serial"]==n+1
        events.append(issue);state=next_state
        if kind=="truncated":
            path.write_text(content)
            _,_,state,_=tail(path,state,NOW+30+n,running=False)
    assert events[0].signature==events[1].signature
    assert events[0].occurrence!=events[1].occurrence

def test_normal_rotations_drain_without_false_gap(tmp_path):
    path=tmp_path/"stdout.jsonl";path.write_text("{}\n")
    _,_,state,_=tail(path,{},NOW,running=False)
    path.rename(tmp_path/"stdout.jsonl.1");path.write_text("{}\n")
    _,issues,state,_=tail(path,state,NOW+1,running=False)
    assert not any(e.object_id=="stdout-rotation" for e in issues)
    records,issues,state,_=tail(path,state,NOW+2,running=False)
    assert len(records)==1 and not issues

def test_gap_message_explains_source_and_does_not_render_arbitrary_reason(store):
    event=gap();store.ingest([event],{},NOW)
    text=alert(row(store,event))
    assert "ROTATED_INODE_LOST" in text and "agrākās izvades" in text
    changed=row(store,event)
    changed["evidence"]=json.dumps({"source":"stdout","facts":{"reason":"token:SECRET"}})
    assert rotation_gap_reason(changed) is None
    assert "SECRET" not in alert(changed)
