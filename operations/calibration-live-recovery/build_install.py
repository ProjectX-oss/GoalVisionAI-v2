"""Build a pinned four-file PREMATCH package; no production writes or worker calls."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
INSTALL = Path(__file__).with_name("install.py")
HELPER = ROOT / "operations/live-evening/update.py"
OPERATIONS = Path("/home/arvis/goalvision-operations")
PYTHON = "/home/arvis/GoalVisionAI/.venv/bin/python"

def smoke(application: Path) -> dict:
    code = """import sys,pathlib,socket,json
root=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
def deny(*a,**k):raise RuntimeError('NETWORK_DENIED')
socket.socket.connect=socket.socket.connect_ex=socket.create_connection=deny
from app.adaptive_lab import calendar_audit,health,observer
from app.lab_v2_shadow import cli,combo_agreement_sources,combo_double
from app.lab_combo import service,bot_delivery
from app.adaptive_lab.calendar_monitor import load_plan
from types import SimpleNamespace
assert combo_agreement_sources.Inputs(SimpleNamespace(connection=None)).deadline is None
assert combo_agreement_sources.BUDGET_SECONDS == 10
assert str(combo_double.MIN_ODDS)=='1.70'
assert str(combo_double.MIN_P)=='0.70' and str(combo_double.MAX_P)=='0.80'
modules={name:pathlib.Path(m.__file__).resolve() for name,m in sys.modules.items()
 if (name=='app' or name.startswith('app.')) and getattr(m,'__file__',None)}
assert modules and all(p.is_relative_to(root) for p in modules.values())
print(json.dumps({'status':'EXACT_BASE_RECOVERY_PASS','modules':len(modules),
 'calendar_plan_fingerprint':load_plan().document()['plan_fingerprint'],
 'provider_calls':0,'telegram_sends':0,'worker_invoked':False}))
"""
    completed = subprocess.run([PYTHON,"-I","-B","-c",code,str(application)],
        cwd="/tmp",capture_output=True,text=True,check=True,timeout=30,
        env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","PYTHONDONTWRITEBYTECODE":"1"})
    return json.loads(completed.stdout)

def main() -> None:
    spec=importlib.util.spec_from_file_location("prepared_recovery_install",INSTALL)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    names=(*mod.FILES,"operations/calibration-live-recovery/install.py",
           "operations/calibration-live-recovery/build_install.py",
           "operations/live-evening/update.py")
    for name in names:
        committed=subprocess.check_output(["git","show",commit+":"+name],cwd=ROOT)
        if committed != (ROOT/name).read_bytes():
            raise ValueError("UNCOMMITTED_PACKAGE_SOURCE:"+name)
    mod.h.disabled_worker()
    if mod.mode() != "BASE":
        raise ValueError("BASE_MODE_REQUIRED_FOR_BUILD")
    for u in mod.SERVICES:
        if mod.h.property_of(u,"EnvironmentFiles") != str(mod.BASE/"release.env")+" (ignore_errors=no)":
            raise ValueError("INSTALLED_ROUTE_DRIFT")
    wrapper=OPERATIONS/"calibration-live-recovery-20261011.py"
    package=OPERATIONS/("calibration-live-recovery-"+commit[:7]+"-20261011")
    if wrapper.exists() or wrapper.is_symlink() or package.exists() or package.is_symlink():
        raise ValueError("EXISTING_PACKAGE_REVIEW_REQUIRED")
    base_manifest=mod.manifest(mod.BASE/"application")
    package.mkdir()
    shutil.copyfile(INSTALL,package/"install.py")
    shutil.copyfile(HELPER,package/"runtime_helpers.py")
    for name in mod.FILES:
        p=package/"overlay"/name;p.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,p)
    meta={"schema":mod.SCHEMA,"source_commit":commit,"base":str(mod.BASE),"target":str(mod.TARGET),
        "scripts":{n:mod.h.sha(package/n) for n in ("install.py","runtime_helpers.py")},
        "files":{n:mod.h.sha(package/"overlay"/n) for n in mod.FILES},
        "base_manifest":base_manifest,"base_environment":(mod.BASE/"release.env").read_text(),
        "units":mod.configured_units(),"systemd_files":mod.configuration_files(),
        "timer_configurations":mod.timer_configurations(),
        "scope":"FOUR_PREMATCH_FILES_ONLY; NO_MODEL_OR_RESEARCH_ACTIVATION",
        "automatic_rollback":False}
    with tempfile.TemporaryDirectory(prefix="recovery-smoke-") as temporary:
        stage=Path(temporary)
        mod.assemble(package,meta,stage)
        actual=mod.manifest(stage/"application")
        changed={n for n in actual if actual[n] != base_manifest.get(n)}
        if set(actual) != set(base_manifest) or changed != set(mod.FILES):
            raise ValueError("UNREVIEWED_OVERLAY_DIFFERENCE")
        meta["smoke"]=smoke(stage/"application")
    (package/"metadata.json").write_text(json.dumps(meta,sort_keys=True,indent=2)+"\n")
    mod.validate(package)
    hashes={str(p.relative_to(package)):mod.h.sha(p) for p in package.rglob("*") if p.is_file()}
    (package/"SHA256SUMS").write_text("".join(d+"  "+n+"\n" for n,d in sorted(hashes.items())))
    pins={n:hashes[n] for n in ("metadata.json","install.py","runtime_helpers.py")}
    wrapper.write_text('''"""Pinned GoalVision PREMATCH recovery; default read-only."""
import hashlib
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode=True
PACKAGE=Path('''+repr(str(package))+''')
PINS='''+repr(pins)+'''
if PACKAGE.is_symlink() or PACKAGE.resolve()!=PACKAGE:
    raise SystemExit("PACKAGE_PATH_DRIFT")
for name,digest in PINS.items():
    p=PACKAGE/name
    if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
        raise SystemExit("PINNED_PACKAGE_HASH_MISMATCH")
runpy.run_path(str(PACKAGE/"install.py"),run_name="__main__")
''')
    print(json.dumps({"package":str(package),"wrapper":str(wrapper),
        "source_commit":commit,"metadata_sha256":hashes["metadata.json"],
        "overlay_files":list(mod.FILES),"smoke":meta["smoke"],
        "installed":False,"provider_calls":0,"telegram_sends":0},indent=2))

if __name__=="__main__":
    main()
