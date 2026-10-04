"""Reproduce the shipped resource omission, then verify the isolated package."""
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import pytest
from tests.test_dixon_coles_forward_install import install, package

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value

build=module("forward_repair_build",ROOT/"operations/dixon-coles-forward/build.py")
diagnostic=module("admin_recent_diagnostic",ROOT/"operations/admin-diagnostics/inspect_recent.py")

def test_shipped_missing_resource_fails_isolated_import_then_complete_package_passes(tmp_path):
    application=tmp_path/"application"
    shutil.copytree(ROOT/"app",application/"app",ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    resource=application/"app/lab_v2_shadow/reviewed_competitions.json"
    contents=resource.read_bytes();resource.unlink()
    with pytest.raises(subprocess.CalledProcessError) as error:
        build.verify_imports(application,sys.executable)
    assert "reviewed_competitions.json" in error.value.stderr
    resource.write_bytes(contents)
    smoke=build.verify_imports(application,sys.executable)
    assert smoke["status"]=="ISOLATED_PACKAGE_IMPORT_PASS"
    assert smoke["app_modules"]>10 and smoke["worker_main_called"] is False
    assert smoke["provider_calls"]==smoke["telegram_sends"]==0
    manifest=install.tree(application)
    assert "app/lab_v2_shadow/reviewed_competitions.json" in manifest
    assert not (application/"var").exists()
    resource.write_text("{}")
    with pytest.raises(subprocess.CalledProcessError):
        build.verify_imports(application,sys.executable)

@pytest.mark.parametrize("mode",["previous","new","unreviewed","missing_import_proof","previous_drift","resource_tamper"])
def test_upgrade_only_accepts_reviewed_units_and_complete_package(tmp_path,monkeypatch,mode):
    pkg,meta,routes=package(tmp_path,monkeypatch)
    target=install.validate(pkg)[1]
    for unit,data in install.units(install.PREVIOUS if mode=="previous" else target).items():
        (install.SYSTEM/unit).write_bytes(data)
    if mode=="unreviewed": (install.SYSTEM/install.SERVICE).write_text("ExecStart=unexpected")
    if mode=="missing_import_proof":
        meta.pop("runtime_import_smoke");(pkg/"metadata.json").write_text(json.dumps(meta))
    if mode=="previous_drift": (install.PREVIOUS/"application/app/base.py").write_text("bad")
    if mode=="resource_tamper":
        extra=pkg/"application/app/lab_v2_shadow/reviewed_competitions.json"
        extra.parent.mkdir();extra.write_text("{}")
    if mode in {"previous","new"}: install.validate(pkg)
    else:
        with pytest.raises(ValueError): install.validate(pkg)

def test_activation_replaces_old_unit_after_operator_drain_only(tmp_path,monkeypatch):
    pkg,meta,routes=package(tmp_path,monkeypatch)
    for unit,data in install.units(install.PREVIOUS).items(): (install.SYSTEM/unit).write_bytes(data)
    monkeypatch.setattr(install,"control",lambda *args:"")
    monkeypatch.setattr(install,"prop",lambda unit,key:"active" if key=="ActiveState" else "enabled")
    target=tmp_path/"new"
    install.activate(target)
    assert all((install.SYSTEM/u).read_bytes()==v for u,v in install.units(target).items())

def make_admin(root):
    root.mkdir()
    path=root/"admin.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE incidents(id TEXT,service TEXT,rule TEXT,object_id TEXT,state TEXT,
            severity INTEGER,count INTEGER,first_seen REAL,last_seen REAL,last_sent REAL,
            invocation TEXT,episode INTEGER,generation INTEGER,notified_state TEXT,evidence TEXT)""")
        db.execute("CREATE TABLE outbox(incident TEXT,state TEXT,created REAL,acknowledged INTEGER,body TEXT,receipt TEXT)")
        db.execute("CREATE TABLE attempts(started REAL,result TEXT)")
        db.execute("CREATE INDEX attempt_time ON attempts(started)")
        evidence={"facts":{"reason":"ROTATED_INODE_LOST","token":"fictional-secret",
                            "error":"https://private.example","header":{"Authorization":"secret"}},
                  "source":"stdout","service":"monitor","rule":"MONITORING_COVERAGE_DEGRADED"}
        db.execute("INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("case","monitor","MONITORING_COVERAGE_DEGRADED","stdout-rotation","OPEN",2,1,
             100,100,100,"UNKNOWN",1,1,"OPEN",json.dumps(evidence)))
        db.execute("INSERT INTO outbox VALUES(?,?,?,?,?,?)",("case","SENT",100,1,"private body","private receipt"))
        db.execute("INSERT INTO attempts VALUES(?,?)",(100,"SENT"))
    return path

def test_admin_export_never_mutates_or_exposes_credentials(tmp_path):
    root=tmp_path/"admin";path=make_admin(root)
    before={p:p.read_bytes() for p in root.iterdir()}
    report=diagnostic.collect(root,now=200,hours=24)
    assert report["mode"]=="READ_ONLY" and report["source_writes"]==0
    assert len(report["incidents"])==1 and report["incidents"][0]["evidence"]["facts"]["reason"]=="ROTATED_INODE_LOST"
    wire=json.dumps(report)
    assert all(s not in wire for s in ("fictional-secret","private.example","private body","private receipt","Authorization"))
    assert before=={p:p.read_bytes() for p in root.iterdir()}

def test_admin_export_missing_symlink_and_invalid_window_fail_closed(tmp_path):
    root=tmp_path/"admin";path=make_admin(root)
    for hours in (0,73):
        with pytest.raises(ValueError): diagnostic.collect(root,now=200,hours=hours)
    alias=tmp_path/"alias";alias.symlink_to(root)
    with pytest.raises(ValueError,match="SYMLINK"): diagnostic.collect(alias,now=200)
    absent=tmp_path/"missing"
    with pytest.raises(OSError): diagnostic.collect(absent,now=200)
    assert not absent.exists()

def test_admin_export_requires_safe_wal_mount(tmp_path):
    root=tmp_path/"admin";path=make_admin(root)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        with pytest.raises(ValueError,match="READONLY_MOUNT"):
            diagnostic.collect(root,now=200)
