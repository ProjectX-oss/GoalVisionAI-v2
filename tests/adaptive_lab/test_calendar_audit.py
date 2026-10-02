"""Query-only integration with disposable audit storage and real CLI."""
import json
import subprocess
import sys

import pytest

from app.adaptive_lab.calendar_audit import read_snapshot, readiness_report, main
from app.adaptive_lab.repository import AuditRepository
from .test_calendar_research import plan, populated, NOW


def seed(path):
    repo=AuditRepository(path)
    for row in populated():
        source_id="synthetic-source-"+row["observation_id"]
        repo.append("source_records",source_id,"PREMATCH",{"synthetic":True,"observation_id":row["observation_id"]},row["settled_at"])
        repo.append("learning_observations",row["observation_id"],"PREMATCH",row,row["settled_at"],source_id=source_id)
    repo.close()


def test_readonly_report_never_fits_writes_or_consumes_holdout(tmp_path,monkeypatch):
    path=tmp_path/"audit.db"
    seed(path)
    before=path.read_bytes()
    def forbidden(*args,**kwargs):
        pytest.fail("readiness audit tried to train or write")
    monkeypatch.setattr(AuditRepository,"append",forbidden)
    monkeypatch.setattr(AuditRepository,"set_champion",forbidden)
    monkeypatch.setattr("app.adaptive_lab.automl.train",forbidden)
    monkeypatch.setattr("app.adaptive_lab.calibration_research.research",forbidden)
    snapshot=read_snapshot(path)
    report=readiness_report(snapshot,plan(),now=NOW)
    assert report["calendar_candidate"]["status"]=="CALENDAR_READY_FOR_OFFLINE_REVIEW"
    assert not any(report["cross_partition_fixture_intersections"].values())
    assert report["holdout_evaluated"] is report["training_invoked"] is False
    assert all(n==0 for n in report["protected_counts"].values())
    assert report==readiness_report(snapshot,plan(),now=NOW)
    assert path.read_bytes()==before


def test_cli_reuses_exact_frozen_plan_and_does_not_create_missing_database(tmp_path,capsys):
    path=tmp_path/"audit.db"
    seed(path)
    plan_path=tmp_path/"plan.json"
    plan_path.write_text(json.dumps(plan().document()))
    before=path.read_bytes(),plan_path.read_bytes()
    assert main(["--database",str(path),"--plan",str(plan_path),"--as-of",NOW.isoformat()])==0
    report=json.loads(capsys.readouterr().out)
    assert report["calendar_candidate"]["plan"]==plan().document()
    assert (path.read_bytes(),plan_path.read_bytes())==before
    missing=tmp_path/"missing.db"
    with pytest.raises(Exception,match="unable to open database"):
        read_snapshot(missing)
    assert not missing.exists()
    completed=subprocess.run([sys.executable,"-m","app.adaptive_lab.calendar_audit", "--database",str(path),
        "--plan",str(plan_path),"--as-of",NOW.isoformat()],text=True,capture_output=True,check=True)
    assert json.loads(completed.stdout)==report
    assert path.read_bytes()==before[0]


def test_readonly_report_bounds_database_before_loading(tmp_path,monkeypatch):
    from dataclasses import replace
    path=tmp_path/"audit.db"
    seed(path)
    monkeypatch.setattr("app.adaptive_lab.calendar_audit.POLICY",replace(
        __import__("app.adaptive_lab.policy",fromlist=["POLICY"]).POLICY,training_rows_limit=10))
    with pytest.raises(ValueError,match="BOUND"):
        read_snapshot(path)
