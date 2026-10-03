"""New operator package guards, history preservation and isolated activation."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import pytest
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research.contracts import seal
from app.dixon_coles_forward.contracts import load_plan
from tests.test_dixon_coles_research import PLAN as OLD_PLAN

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("forward_install",ROOT/"operations/dixon-coles-forward/update.py")
install=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(install)
PLAN=load_plan()

def package(tmp_path,monkeypatch):
    base=tmp_path/"base";original=tmp_path/"original";state=tmp_path/"state";system=tmp_path/"system";pkg=tmp_path/"package"
    for folder in (base/"application/app",original/"application/app",system,pkg/"application/app"):
        folder.mkdir(parents=True)
    for key,value in (("BASE",base),("ORIGINAL",original),("STATE",state),("SYSTEM",system),
                      ("ORIGINAL_STATE",tmp_path/"original.db"),("INSTALL_LOCK",tmp_path/"lock")):
        monkeypatch.setattr(install,key,value)
    (base/"application/app/base.py").write_text("# base\n")
    (original/"application/app/base.py").write_text("# original\n")
    (base/"release.env").write_text("SINGLE=1.50\n")
    monkeypatch.setattr(install,"BASE_ENV_SHA256",install.sha(base/"release.env"))
    (pkg/"application/app/base.py").write_text("# candidate\n")
    (pkg/"update.py").write_text("# pinned\n")
    store=ResearchStore(install.ORIGINAL_STATE);store.append("plan",OLD_PLAN["fingerprint"],OLD_PLAN);store.close()
    old_units=(install.ORIGINAL_SERVICE,install.ORIGINAL_SERVICE.replace(".service",".timer"))
    for unit in old_units: (system/unit).write_text("# protected old unit\n")
    routes={u:{"EnvironmentFiles":str(base/"release.env")+" (ignore_errors=no)"} for u in install.PRODUCTION}
    monkeypatch.setattr(install,"routes",lambda:routes)
    monkeypatch.setattr(install,"disabled_admin",lambda:None)
    def prop(unit,key):
        if unit in old_units:
            return {"FragmentPath":str(system/unit),"DropInPaths":"","UnitFileState":"enabled","ActiveState":"active"}.get(key,"")
        return ""
    monkeypatch.setattr(install,"prop",prop)
    meta={"source_commit":"b"*40,"updater_sha256":install.sha(pkg/"update.py"),
          "application":install.tree(pkg/"application"),"base_manifest":install.tree(base/"application"),
          "environment_sha256":install.sha(base/"release.env"),"routes":routes,
          "original_manifest":install.tree(original/"application"),
          "original_units":{u:install.sha(system/u) for u in old_units},
          "original_records":install.records(install.ORIGINAL_STATE)}
    (pkg/"metadata.json").write_text(json.dumps(meta))
    return pkg,meta,routes

@pytest.mark.parametrize("drift",["none","package","original_app","original_unit","original_history",
                                    "new_override","route","environment","wrong_cohort","path_escape"])
def test_readonly_preflight_pins_both_installed_releases(tmp_path,monkeypatch,drift):
    pkg,meta,routes=package(tmp_path,monkeypatch)
    if drift=="package": (pkg/"application/app/base.py").write_text("bad")
    if drift=="original_app": (install.ORIGINAL/"application/app/base.py").write_text("bad")
    if drift=="original_unit": (install.SYSTEM/install.ORIGINAL_SERVICE).write_text("bad")
    if drift=="original_history":
        meta["original_records"]["missing"]="missing";(pkg/"metadata.json").write_text(json.dumps(meta))
    if drift=="new_override":
        old=install.prop;monkeypatch.setattr(install,"prop",lambda unit,key:"bad" if unit==install.SERVICE and key=="DropInPaths" else old(unit,key))
    if drift=="route": routes[install.PRODUCTION[0]]["EnvironmentFiles"]="bad"
    if drift=="environment": (install.BASE/"release.env").write_text("bad")
    if drift=="wrong_cohort":
        install.STATE.mkdir();store=ResearchStore(install.STATE/"research.db")
        store.append("plan",OLD_PLAN["fingerprint"],OLD_PLAN);store.close()
    if drift=="path_escape":
        meta["application"]["../escape.py"]="bad";(pkg/"metadata.json").write_text(json.dumps(meta))
    before={p:p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    if drift=="none": assert install.validate(pkg)[0]==meta
    else:
        with pytest.raises(ValueError): install.validate(pkg)
    assert before=={p:p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

def test_empty_initialization_never_seeds_development_or_original(tmp_path,monkeypatch):
    pkg,meta,routes=package(tmp_path,monkeypatch)
    path=tmp_path/"forward.db";old=install.ORIGINAL_STATE.read_bytes()
    install.initialize_database(path)
    assert install.records(path)=={}
    store=ResearchStore(path);store.append("plan",PLAN["fingerprint"],PLAN)
    store.append("later","x",seal({"test":"future record"}));store.close()
    install.initialize_database(path)
    assert len(install.records(path))==2 and install.ORIGINAL_STATE.read_bytes()==old
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError): db.execute("DELETE FROM dc_research_records")
    alias=tmp_path/"alias.db";__import__("os").link(install.ORIGINAL_STATE,alias)
    with pytest.raises(ValueError,match="ORIGINAL"): install.initialize_database(alias)

@pytest.mark.parametrize("failure",[None,"enable","verify"])
def test_activation_only_controls_new_units(tmp_path,monkeypatch,failure):
    pkg,meta,routes=package(tmp_path,monkeypatch);calls=[]
    def control(*args):
        calls.append(args)
        if failure=="enable" and args[0]=="enable": raise RuntimeError("injected")
        return ""
    monkeypatch.setattr(install,"control",control)
    monkeypatch.setattr(install,"prop",lambda unit,key:
        ("inactive" if failure=="verify" else "active") if key=="ActiveState" else "enabled")
    if failure:
        with pytest.raises((ValueError,RuntimeError)): install.activate(Path("/opt/forward-test"))
        assert calls[-2:]==[("disable","--now",install.TIMER),("stop",install.SERVICE)]
    else: install.activate(Path("/opt/forward-test"))
    assert not any(name in str(calls) for name in install.PRODUCTION+install.PROTECTED)
    assert ("start",install.SERVICE) not in calls
    text=install.units(Path("/opt/forward-test"))[install.SERVICE].decode()
    assert "app.dixon_coles_forward.worker" in text and "ReadWritePaths="+str(install.STATE) in text
    assert "EnvironmentFile=" not in text and "PrivateNetwork=true" in text
    assert "CPUQuota=25%" in text and "Nice=10" in text
    assert "*:12,42:30 Europe/Riga" in install.units(Path("/opt/forward-test"))[install.TIMER].decode()

def test_apply_reapply_pause_retains_new_and_original_history(tmp_path,monkeypatch):
    pkg,meta,routes=package(tmp_path,monkeypatch);target=tmp_path/"release";calls=[]
    monkeypatch.setattr(install.os,"geteuid",lambda:0)
    monkeypatch.setattr(install,"validate",lambda *a,**k:(meta,target))
    monkeypatch.setattr(install,"activate",lambda p:calls.append(("activate",str(p))))
    monkeypatch.setattr(install,"control",lambda *a:calls.append(a))
    before=install.ORIGINAL_STATE.read_bytes()
    install.apply(pkg)
    store=ResearchStore(install.STATE/"research.db");store.append("plan",PLAN["fingerprint"],PLAN)
    store.append("future","x",seal({"fixture_id":9000}));store.close()
    install.apply(pkg)
    data=(install.STATE/"research.db").read_bytes()
    install.apply(pkg,rollback=True)
    assert data==(install.STATE/"research.db").read_bytes()
    assert before==install.ORIGINAL_STATE.read_bytes()
    assert calls[-2:]==[("disable","--now",install.TIMER),("stop",install.SERVICE)]
    assert not any(u in str(calls) for u in install.PRODUCTION+install.PROTECTED)

def test_pause_survives_later_routes_and_root_gate_precedes_mutations(tmp_path,monkeypatch):
    pkg,meta,routes=package(tmp_path,monkeypatch)
    routes[install.PRODUCTION[0]]["EnvironmentFiles"]="later reviewed release"
    (install.ORIGINAL/"application/app/base.py").write_text("later research")
    install.validate(pkg,rollback=True)
    monkeypatch.setattr(install.os,"geteuid",lambda:1000)
    with pytest.raises(ValueError,match="SUDO"): install.apply(pkg)
    assert not install.INSTALL_LOCK.exists() and not install.STATE.exists()
