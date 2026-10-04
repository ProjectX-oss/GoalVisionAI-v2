"""Mixed successful/rejected delivery accounting, including retained incident recovery."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import pytest
from app.admin_alerts.model import DISCOVERY, Event
from app.admin_alerts.rules import compact, completed_health
from app.admin_alerts.store import Store
from test_monitor import NOW, record


def mixed():
    success = dict(prediction_id="confirmed-single", kind="single_prediction",
        status="SENT", stage="RECEIPT_PERSISTED", claim_persisted=True,
        transport_attempted=True, acknowledgement_received=True, receipt_persisted=True,
        sent=True, reconciliation_required=False, persistence_failure=None,
        transport_failure_kind=None, unknown_marker_persisted=False)
    rejected = dict(prediction_id="rejected-combo", kind="combo_prediction",
        status="LAB_PUBLICATION_POLICY_REJECTED", stage="REJECTED_BEFORE_TRANSPORT",
        claim_persisted=False, transport_attempted=False, acknowledgement_received=False,
        receipt_persisted=False, sent=False, reconciliation_required=False,
        persistence_failure=None, transport_failure_kind=None, unknown_marker_persisted=False)
    return record(delivery_status="DEGRADED", telegram_sends=1, publication_attempt_count=1,
        controlled_publication=dict(status="DEGRADED", failure=None, deliveries=[success,rejected],
            send_attempted=True, publication_attempt_count=1, singles_sent=1, combos_sent=0))


def test_mixed_receipt_and_rejection_do_not_create_false_transport_failure():
    events=compact(mixed(),"synthetic",NOW)
    assert not [e for e in events if e.rule in {"DELIVERY_FAILURE","DELIVERY_UNCERTAIN"} and not e.healthy]
    assert any(e.rule=="DELIVERY_FAILURE" and e.object_id=="UNKNOWN" and e.healthy for e in events)


@pytest.mark.parametrize("fault",["missing_receipt","ack_missing","uncertain","persistence","transport_error",
    "unknown_marker","sent_false","transport_missing","duplicate_identity","missing_counter",
    "extra_attempt","extra_send","combo_count","private_count","unknown_aggregate","failed_aggregate",
    "failure_object","terminal_error","truncated","bool_counter"])
def test_incomplete_or_contradictory_proof_retains_alert(fault):
    r=mixed();p=r["controlled_publication"];s=p["deliveries"][0]
    changes={"missing_receipt":("receipt_persisted",False),"ack_missing":("acknowledgement_received",False),
        "uncertain":("reconciliation_required",True),"persistence":("persistence_failure","RECEIPT"),
        "transport_error":("transport_failure_kind","TIMEOUT"),"unknown_marker":("unknown_marker_persisted",True),
        "sent_false":("sent",False),"transport_missing":("transport_attempted",None)}
    if fault in changes:s[changes[fault][0]]=changes[fault][1]
    if fault=="duplicate_identity":p["deliveries"][1]["prediction_id"]=s["prediction_id"]
    if fault=="missing_counter":p.pop("publication_attempt_count")
    if fault=="extra_attempt":r["publication_attempt_count"]=2
    if fault=="extra_send":r["telegram_sends"]=2
    if fault=="combo_count":p["combos_sent"]=1
    if fault=="private_count":p["private_singles_sent"]=1
    if fault=="unknown_aggregate":r["delivery_status"]="UNKNOWN"
    if fault=="failed_aggregate":r["delivery_status"]="FAILED"
    if fault=="failure_object":p["failure"]={"code":"DELIVERY_FAILED"}
    if fault=="terminal_error":r["terminal_error"]={"code":"CYCLE_FAILED"}
    if fault=="truncated":p["deliveries"]*=101
    if fault=="bool_counter":p["publication_attempt_count"]=True
    events=compact(r,"synthetic",NOW)
    assert any(e.rule in {"DELIVERY_FAILURE","DELIVERY_UNCERTAIN","CYCLE_PERSISTENCE"} and not e.healthy for e in events)
    assert not any(e.rule=="DELIVERY_FAILURE" and e.object_id=="UNKNOWN" and e.healthy for e in events)


def test_health_projection_has_same_mixed_delivery_result():
    r=mixed()
    events=completed_health({"result":"HEALTHY","completed_at":r["evaluated_at_utc"],
        "publication":r["controlled_publication"]},DISCOVERY,"cycle",NOW,"health-cycle")
    assert not any(e.rule in {"DELIVERY_FAILURE","DELIVERY_UNCERTAIN"} and not e.healthy for e in events)
    assert any(e.rule=="DELIVERY_FAILURE" and e.object_id=="UNKNOWN" and e.healthy for e in events)


def test_integrity_rejection_keeps_its_own_incident():
    r=mixed()
    r["controlled_publication"]["deliveries"][1]["status"]="SELECTION_ORIGIN_OR_APPROVAL_INVALID"
    events=compact(r,"synthetic",NOW)
    assert any(e.rule=="INTEGRITY_FAILURE" and not e.healthy for e in events)


def test_new_healthy_evidence_recovers_mapped_incident_without_erasing_history(tmp_path):
    store=Store(tmp_path)
    try:
        old=Event(DISCOVERY,"DELIVERY_FAILURE","UNKNOWN","old",NOW-120,"old")
        store.ingest([old],{},NOW-120)
        with store.db:
            store.db.execute("UPDATE incidents SET state='INVALIDATED' WHERE id=?",(old.signature,))
            store.db.execute("INSERT INTO invalidations VALUES(?,?,?,?,?)",(old.signature,NOW-100,
                json.dumps({"reason":"PRETRANSPORT_REJECTION_NOT_DELIVERY_FAILURE_V1","health_proofs":[]}),"{}","[]"))
        recent=Event(DISCOVERY,"DELIVERY_FAILURE","UNKNOWN","recent",NOW-60,"recent")
        store.ingest([recent],{},NOW-60)
        target="4f3832ebaf241e92b8d3ad51"
        assert store.db.execute("SELECT state FROM incidents WHERE id=?",(target,)).fetchone()[0]=="OPEN"
        before=store.db.execute("SELECT COUNT(*) FROM source_evidence").fetchone()[0]
        store.ingest(compact(mixed(),"next-natural-cycle",NOW),{},NOW)
        assert store.db.execute("SELECT state FROM incidents WHERE id=?",(target,)).fetchone()[0]=="RECOVERED"
        assert store.db.execute("SELECT state FROM incidents WHERE id=?",(old.signature,)).fetchone()[0]=="INVALIDATED"
        assert store.db.execute("SELECT COUNT(*) FROM source_evidence").fetchone()[0]>=before
    finally:store.close()
