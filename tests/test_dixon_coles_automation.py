"""Scheduler and operator safety checks, entirely offline with disposable state."""
import argparse
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
from types import SimpleNamespace
import pytest
from app.dixon_coles_research import worker, cli
from app.dixon_coles_research.contracts import seal, canonical, digest, utc
from app.dixon_coles_research.repository import ResearchStore
from tests.test_dixon_coles_research import PLAN, START, result
from tests.test_dixon_coles_sources import databases

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dc_update_test", ROOT/"operations/dixon-coles-automation/update.py")
install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install)

def arguments(tmp_path):
    shadow, audit = databases(tmp_path, cache_list=True)
    ledger = tmp_path/"ledger.db"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE evidence(kind TEXT,identity TEXT,fingerprint TEXT,document TEXT)")
    return argparse.Namespace(shadow_database=shadow, audit_database=audit, ledger_database=ledger,
                              research_database=tmp_path/"research.db", limit=12)

@pytest.mark.parametrize("minute,second,expected",[(10,30,True),(40,59,True),(10,29,False),
    (11,0,False),(40,0,False),(0,30,False),(15,30,False),(38,30,False)])
def test_late_or_missed_timer_has_no_catchup(minute,second,expected):
    assert worker.in_slot(START.replace(minute=minute,second=second)) is expected

@pytest.mark.parametrize("state,pid,missing,expected",[
    ("inactive","0",False,True),("active","42",False,False),("activating","0",False,False),
    ("failed","0",False,False),("inactive","42",False,False),("inactive","0",True,False)])
def test_busy_or_unknown_production_fails_closed(monkeypatch,state,pid,missing,expected):
    names = worker.SERVICES[:-1] if missing else worker.SERVICES
    text = "\n\n".join(f"Id={name}\nLoadState=loaded\nActiveState={state}\nMainPID={pid}" for name in names)
    def run(command, **kwargs):
        assert command[:2] == ["/usr/bin/systemctl","show"]
        assert kwargs["timeout"] == 3
        return SimpleNamespace(stdout=text)
    monkeypatch.setattr(worker.subprocess,"run",run)
    assert worker.production_idle() is expected

def test_busy_skip_never_opens_database_or_calls_pipeline(tmp_path):
    args = argparse.Namespace(research_database=tmp_path/"missing.db")
    def fail(*a,**k):
        raise AssertionError("pipeline must not run")
    report = worker.cycle(args,now=lambda:START.replace(minute=10,second=30),
                          idle=lambda:False,execute=fail)
    assert report["reason"] == "PRODUCTION_BUSY_OR_UNKNOWN"
    assert not args.research_database.exists()

def test_automated_capture_replay_and_settlement_only_existing_sources(tmp_path,monkeypatch):
    args = arguments(tmp_path)
    monkeypatch.setattr(worker,"in_slot",lambda now:True)
    before = {p:p.read_bytes() for p in (args.shadow_database,args.audit_database,args.ledger_database)}
    report = worker.cycle(args,now=lambda:START,idle=lambda:True)
    assert report["capture"]["counts"] == {"forecast":1}
    assert report["evaluation"]["lifecycle"] == {"PENDING":1,"VOID":0,"RESOLVED":0}
    assert all(p.read_bytes() == content for p,content in before.items())
    repeated = worker.cycle(args,now=lambda:START+timedelta(seconds=1),idle=lambda:True)
    assert repeated["capture"]["counts"] == {"already_forecast":1}
    # An existing source receives its natural canonical result; no research write to it.
    row = {"fixture_id":9000,"status":"WON","provider_status":"FT",
           "fulltime_home":1,"fulltime_away":0,"settled_at_utc":result()["settled_at"],
           "source_fingerprint":"controlled-result"}
    with sqlite3.connect(args.audit_database) as db:
        db.execute("INSERT INTO canonical_results VALUES(?,?,?,?,?)",
                   ("c","PREMATCH",row["settled_at_utc"],digest(row),canonical(row)))
    report = worker.cycle(args,now=lambda:utc(PLAN["evaluation_end"])+timedelta(days=2),idle=lambda:True)
    assert report["capture"]["reason"] == "OUTSIDE_FROZEN_CAPTURE_WINDOW"
    assert report["evaluation"]["lifecycle"]["RESOLVED"] == 1
    assert report["evaluation"]["market_rows"] == 3
    assert report["evaluation"]["quality_verdict"] == "NEEDS_MORE_EVIDENCE"
    store = ResearchStore(args.research_database,readonly=True)
    assert len(store.all("forecast")) == 1
    store.close()

def test_budget_interrupt_restores_signal_handler():
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(worker.BudgetExceeded):
        with worker.deadline(45):
            signal.getsignal(signal.SIGALRM)(signal.SIGALRM,None)
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0,0)

def test_storage_limit_prevents_more_work(tmp_path,monkeypatch):
    path = tmp_path/"research.db"
    path.write_bytes(b"xxx")
    monkeypatch.setattr(worker,"MAX_DATABASE_BYTES",2)
    report = worker.cycle(argparse.Namespace(research_database=path),
        now=lambda:START.replace(minute=10,second=30),idle=lambda:True)
    assert report["reason"] == "RESEARCH_STORAGE_BUDGET"
    assert path.read_bytes() == b"xxx"

def test_seed_backup_preserves_first_forecasts_and_later_records(tmp_path):
    source, target = tmp_path/"source.db", tmp_path/"target.db"
    store = ResearchStore(source)
    store.append("plan",PLAN["fingerprint"],PLAN)
    store.append("forecast","first",seal({"fixture_id":9000}))
    store.close()
    before = source.read_bytes()
    expected = install.records(source)
    install.seed_database(source,target,expected)
    assert install.records(target) == expected and source.read_bytes() == before
    store = ResearchStore(target)
    later = seal({"fixture_id":9001})
    store.append("forecast","later",later);store.close()
    install.seed_database(source,target,expected)
    assert len(install.records(target)) == 3
    with sqlite3.connect(target) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM dc_research_records")

@pytest.mark.parametrize("mode",["drift","foreign","symlink","conflict"])
def test_seed_refuses_drift_aliases_and_foreign_state(tmp_path,mode):
    source, target = tmp_path/"source.db", tmp_path/"target.db"
    store=ResearchStore(source);store.append("plan",PLAN["fingerprint"],PLAN);store.close()
    expected=install.records(source)
    if mode=="drift":
        expected={"wrong":"wrong"}
    elif mode=="foreign":
        with sqlite3.connect(target) as db: db.execute("CREATE TABLE production(x)")
    elif mode=="symlink":
        target.symlink_to(source)
    else:
        store=ResearchStore(target);store.append("other","x",seal({"x":1}));store.close()
    before=source.read_bytes()
    with pytest.raises(ValueError):
        install.seed_database(source,target,expected)
    assert source.read_bytes()==before

def test_service_sandbox_and_timer_are_independent():
    units=install.units(Path("/opt/research-test"))
    service=units[install.SERVICE].decode();timer=units[install.TIMER].decode()
    for value in ("Nice=10","CPUQuota=25%","TimeoutStartSec=50","MemoryMax=256M",
                  "RestrictAddressFamilies=AF_UNIX","PrivateNetwork=true","ProtectSystem=strict",
                  "ProtectHome=read-only","ReadWritePaths=/var/lib/goalvision-dixon-coles"):
        assert value in service
    assert "EnvironmentFile=" not in service
    assert "Persistent=false" in timer and "*:10,40:30 Europe/Riga" in timer
    assert not any("After="+name in service or "Before="+name in service for name in install.PRODUCTION)

@pytest.mark.parametrize("failure",[None,"write","enable","verify"])
def test_activation_failure_never_controls_production(tmp_path,monkeypatch,failure):
    monkeypatch.setattr(install,"SYSTEM",tmp_path)
    calls=[]
    def control(*args):
        calls.append(args)
        if failure=="enable" and args[0]=="enable":
            raise RuntimeError("injected enable failure")
        return ""
    monkeypatch.setattr(install,"control",control)
    monkeypatch.setattr(install,"prop",lambda unit,key:
                        ("inactive" if failure=="verify" else "active") if key=="ActiveState" else "enabled")
    if failure=="write":
        monkeypatch.setattr(install,"atomic",lambda *a: (_ for _ in ()).throw(OSError("injected")))
    if failure:
        with pytest.raises((ValueError,RuntimeError,OSError)):
            install.activate(Path("/opt/fake"))
        assert ("disable","--now",install.TIMER) in calls
        assert ("stop",install.SERVICE) in calls
    else:
        install.activate(Path("/opt/fake"))
        assert ("enable","--now",install.TIMER) in calls
    assert not any(name in str(calls) for name in install.PRODUCTION+install.PROTECTED)
    assert ("start",install.SERVICE) not in calls

def test_install_requires_operator_root_before_any_mutation(tmp_path,monkeypatch):
    monkeypatch.setattr(install.os,"geteuid",lambda:1000)
    with pytest.raises(ValueError,match="OPERATOR_SUDO_REQUIRED"):
        install.apply(tmp_path)
    assert list(tmp_path.iterdir())==[]

def test_capture_failure_still_evaluates_prior_predictions(tmp_path,monkeypatch):
    args=arguments(tmp_path)
    monkeypatch.setattr(worker,"in_slot",lambda now:True)
    worker.cycle(args,now=lambda:START,idle=lambda:True)
    def execute(operation,clock):
        if operation.command=="capture":
            raise sqlite3.OperationalError("busy source")
        return cli.run_report(operation,clock)
    report=worker.cycle(args,now=lambda:START,idle=lambda:True,execute=execute)
    assert report["status"]=="PARTIAL"
    assert report["evaluation"]["lifecycle"]["PENDING"]==1

def fake_package(tmp_path,monkeypatch):
    base=tmp_path/"base";state=tmp_path/"state";system=tmp_path/"system";package=tmp_path/"package"
    for folder in (base/"application"/"app",system,package/"application"/"app"):
        folder.mkdir(parents=True)
    monkeypatch.setattr(install,"BASE",base)
    monkeypatch.setattr(install,"STATE",state)
    monkeypatch.setattr(install,"SYSTEM",system)
    seed=tmp_path/"seed.db";monkeypatch.setattr(install,"SEED",seed)
    store=ResearchStore(seed);store.append("plan",PLAN["fingerprint"],PLAN);store.close()
    (base/"application"/"app"/"base.py").write_text("# base\n")
    (base/"release.env").write_text("SINGLE=1.50\n")
    monkeypatch.setattr(install,"BASE_ENV_SHA256",install.sha(base/"release.env"))
    (package/"application"/"app"/"base.py").write_text("# base\n")
    (package/"update.py").write_text("# pinned updater\n")
    routes={u:{"EnvironmentFiles":str(base/"release.env")+" (ignore_errors=no)"} for u in install.PRODUCTION}
    monkeypatch.setattr(install,"routes",lambda:routes)
    monkeypatch.setattr(install,"disabled_admin",lambda:None)
    monkeypatch.setattr(install,"prop",lambda *a:"")
    meta={"source_commit":"a"*40,"updater_sha256":install.sha(package/"update.py"),
          "application":install.tree(package/"application"),"base_manifest":install.tree(base/"application"),
          "environment_sha256":install.sha(base/"release.env"),"routes":routes,"seed_records":install.records(seed)}
    (package/"metadata.json").write_text(json.dumps(meta))
    return package,meta,routes

@pytest.mark.parametrize("drift",["none","app","updater","base","env","route","seed","override","unit","escape"])
def test_preflight_readonly_rejects_tampering(tmp_path,monkeypatch,drift):
    package,meta,routes=fake_package(tmp_path,monkeypatch)
    if drift=="app": (package/"application"/"app"/"base.py").write_text("bad")
    elif drift=="updater": (package/"update.py").write_text("bad")
    elif drift=="base": (install.BASE/"application"/"app"/"base.py").write_text("bad")
    elif drift=="env": (install.BASE/"release.env").write_text("bad")
    elif drift=="route": routes[install.PRODUCTION[0]]["EnvironmentFiles"]="bad"
    elif drift=="seed":
        store=ResearchStore(install.SEED);store.append("extra","x",seal({"x":1}));store.close()
    elif drift=="override": monkeypatch.setattr(install,"prop",lambda *a:"unreviewed")
    elif drift=="unit": (install.SYSTEM/install.SERVICE).write_text("ExecStart=wrong")
    elif drift=="escape":
        meta["application"]["../escape.py"]="bad"
        (package/"metadata.json").write_text(json.dumps(meta))
    before={p:p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    if drift=="none":
        assert install.validate(package)[0]==meta
    else:
        with pytest.raises(ValueError): install.validate(package)
    assert before=={p:p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

def test_pause_validation_survives_production_route_change(tmp_path,monkeypatch):
    package,meta,routes=fake_package(tmp_path,monkeypatch)
    routes[install.PRODUCTION[0]]["EnvironmentFiles"]="later independently reviewed release"
    (install.BASE/"release.env").write_text("changed")
    install.validate(package,rollback=True)
    with pytest.raises(ValueError): install.validate(package)

def test_apply_reapply_and_pause_preserve_history_without_production_controls(tmp_path,monkeypatch):
    package,meta,routes=fake_package(tmp_path,monkeypatch)
    target=tmp_path/"release"
    monkeypatch.setattr(install.os,"geteuid",lambda:0)
    monkeypatch.setattr(install,"INSTALL_LOCK",tmp_path/"install.lock")
    monkeypatch.setattr(install,"validate",lambda *a,**k:(meta,target))
    calls=[]
    monkeypatch.setattr(install,"control",lambda *a:calls.append(a))
    monkeypatch.setattr(install,"activate",lambda p:calls.append(("activate",str(p))))
    install.apply(package)
    assert install.tree(target/"application")==meta["application"]
    assert install.records(install.STATE/"research.db")==meta["seed_records"]
    store=ResearchStore(install.STATE/"research.db")
    store.append("later","x",seal({"x":1}));store.close()
    install.apply(package)
    assert len(install.records(install.STATE/"research.db"))==2
    before=(install.STATE/"research.db").read_bytes()
    install.apply(package,rollback=True)
    assert (install.STATE/"research.db").read_bytes()==before
    assert calls[-2:]==[("disable","--now",install.TIMER),("stop",install.SERVICE)]
    assert not any(name in str(calls) for name in install.PRODUCTION+install.PROTECTED)

def test_seed_failure_does_not_activate_timer(tmp_path,monkeypatch):
    package,meta,routes=fake_package(tmp_path,monkeypatch)
    monkeypatch.setattr(install.os,"geteuid",lambda:0)
    monkeypatch.setattr(install,"INSTALL_LOCK",tmp_path/"install.lock")
    monkeypatch.setattr(install,"validate",lambda *a,**k:(meta,tmp_path/"release"))
    monkeypatch.setattr(install,"seed_database",lambda *a:(_ for _ in ()).throw(ValueError("seed conflict")))
    monkeypatch.setattr(install,"activate",lambda *a:pytest.fail("must not activate"))
    with pytest.raises(ValueError,match="seed conflict"): install.apply(package)

def worker_argv(tmp_path):
    return [value for name in ("shadow","audit","ledger","research")
            for value in ("--"+name+"-database",str(tmp_path/(name+".db")))]

def test_concurrent_worker_does_not_overwrite_status(tmp_path,monkeypatch,capsys):
    import fcntl
    monkeypatch.setattr(worker.os,"getpriority",lambda *a:10)
    monkeypatch.setattr(worker,"cycle",lambda *a:pytest.fail("concurrent work"))
    status=tmp_path/"latest.json";status.write_text("prior evidence")
    with (tmp_path/"cycle.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert worker.main(worker_argv(tmp_path))==0
    assert status.read_text()=="prior evidence"
    assert json.loads(capsys.readouterr().out)["reason"]=="RESEARCH_ALREADY_RUNNING"

def test_worker_sanitizes_failure_and_persists_status(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(worker.os,"getpriority",lambda *a:10)
    monkeypatch.setattr(worker,"cycle",lambda *a:(_ for _ in ()).throw(sqlite3.OperationalError("private detail")))
    assert worker.main(worker_argv(tmp_path))==2
    report=json.loads((tmp_path/"latest.json").read_text())
    assert report["status"]=="BLOCKED"
    assert "private detail" not in capsys.readouterr().out
