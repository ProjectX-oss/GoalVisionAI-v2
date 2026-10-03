"""Query-only integration evidence; never calls observe or a scheduled entry point."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from app.adaptive_lab.calendar_monitor import observed_readiness, PLAN_PATH
from app.adaptive_lab.calendar_audit import PROTECTED_TABLES
from app.adaptive_lab.contracts import canonical, digest
from app.adaptive_lab.observations import ReadOnlyLedger
from app.adaptive_lab.performance import operator_summary
from app.adaptive_lab.repository import AuditRepository

ROOT=Path(__file__).resolve().parents[3]
EVIDENCE=Path(__file__).resolve().parent
DATABASE=Path("/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db")
LEDGER=Path("/home/arvis/GoalVisionAI/var/lab_combo/ledger.db")
ADMIN=Path("/opt/goalvision-admin-alerts-releases/admin-rotation-alerts-6a37787-20261002")
sys.path.insert(0,str(ADMIN/"app"))
from admin_alerts.output_contracts import expected_document
from admin_alerts.sources import MAX_LINE

def protected(repo):
    return {"champion_generation":repo.pointer("PREMATCH"),
            "counts":{name:repo.connection.execute("SELECT count(*) FROM "+name).fetchone()[0]
                      for name in PROTECTED_TABLES}}

def main():
    now=datetime.now(timezone.utc)
    started=time.monotonic()
    repo=AuditRepository(DATABASE,readonly=True)
    ledger=ReadOnlyLedger(LEDGER)
    try:
        before=protected(repo)
        report=observed_readiness(repo,ledger,now=now)
        # Read an existing natural-cycle document, never run the observer.
        identity=repo.connection.execute("SELECT id FROM observer_runs WHERE stream='PREMATCH' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
        existing=repo.get("observer_runs",identity)
        natural_created=existing["created_at"]
        existing["PERFORMANCE"]=operator_summary(existing["PERFORMANCE"])
        existing["CALIBRATION_READINESS"]=report
        size=len(canonical(existing).encode())
        contract=expected_document("goalvision-adaptive-learning-observer.service",existing)
        after=protected(repo)
        assert before==after
        assert contract and size<=MAX_LINE
    finally:
        ledger.close();repo.close()
    state={"as_of":now.isoformat(),"read_only":True,"production_runtime_changed":False,
        "operational_cycles_invoked":0,"provider_calls":0,"telegram_sends":0,
        "duration_seconds":round(time.monotonic()-started,3),"protected_before":before,
        "protected_after":after,
        "admin_output_contract_compatible":contract,"projected_stdout_bytes":size,
        "admin_max_line_bytes":MAX_LINE,"existing_natural_observer_created_at":natural_created,
        "plan_sha256":hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest(),"readiness":report}
    state["evidence_fingerprint"]=digest(state)
    (EVIDENCE/"readonly_snapshot.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:state[k] for k in ("as_of","duration_seconds","admin_output_contract_compatible",
        "projected_stdout_bytes","existing_natural_observer_created_at","evidence_fingerprint")},sort_keys=True))
    print("FIT_PROGRESS",json.dumps(report["windows"]["CALIBRATION_FIT"],sort_keys=True))
    print("PROTECTED",json.dumps(after,sort_keys=True))

if __name__=="__main__":
    main()
