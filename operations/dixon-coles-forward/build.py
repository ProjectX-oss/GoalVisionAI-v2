"""Build from committed source; no systemd mutations or research executions."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

def verify_imports(application: Path, python: str) -> dict:
    """Import the built artifact in isolation; no worker main, source DB or network."""
    code = """import sys,json,socket,pathlib
root=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
def forbidden(*args,**kwargs): raise RuntimeError('NETWORK_FORBIDDEN_IN_IMPORT_SMOKE')
socket.socket.connect=forbidden
socket.socket.connect_ex=forbidden
socket.create_connection=forbidden
from app.dixon_coles_forward import worker,cli,combo,model,service
from app.dixon_coles_forward.contracts import load_plan
from app.lab_v2_shadow.competition_registry import REGISTRY_FINGERPRINT
loaded={name:pathlib.Path(module.__file__).resolve() for name,module in sys.modules.items()
        if (name=='app' or name.startswith('app.')) and getattr(module,'__file__',None)}
if not loaded or any(not path.is_relative_to(root) for path in loaded.values()):
    raise RuntimeError('SOURCE_CHECKOUT_FALLBACK_FORBIDDEN')
print(json.dumps({'status':'ISOLATED_PACKAGE_IMPORT_PASS','app_modules':len(loaded),
 'plan_fingerprint':load_plan()['fingerprint'],'registry_fingerprint':REGISTRY_FINGERPRINT,
 'worker_main_called':False,'provider_calls':0,'telegram_sends':0}))
"""
    result = subprocess.run([python, "-I", "-B", "-c", code, str(application.resolve())],
        cwd="/tmp", capture_output=True, text=True, timeout=20, check=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"})
    value = json.loads(result.stdout)
    if value.get("status") != "ISOLATED_PACKAGE_IMPORT_PASS":
        raise ValueError("PACKAGE_IMPORT_FAILED")
    return value

def main() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("dc_install", Path(__file__).with_name("update.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tracked = subprocess.check_output(["git", "ls-files", "app"], cwd=root, text=True).splitlines()
    application = {name: module.sha(root/name) for name in tracked if
                   name.endswith(".py") or name in
                   ("app/adaptive_lab/calendar_plan_20261002.json", module.PLAN,
                    "app/dixon_coles_research/plan_20261003.json",
                    "app/dixon_coles_constrained/protocol_20261003.json",
                    "app/lab_v2_shadow/reviewed_competitions.json")}
    for name in (*application, "operations/dixon-coles-forward/update.py",
                 "operations/dixon-coles-forward/build.py"):
        if subprocess.check_output(["git", "show", commit+":"+name], cwd=root) != (root/name).read_bytes():
            raise ValueError("UNCOMMITTED_SOURCE:"+name)
    baseline = module.tree(module.BASE/"application")
    if {k:v for k,v in application.items() if not k.startswith(("app/dixon_coles_research/", "app/dixon_coles_constrained/", "app/dixon_coles_forward/"))} != baseline:
        raise ValueError("PRODUCTION_APPLICATION_DIFFERENCE")
    module.disabled_admin()
    observed_routes = module.routes()
    for unit in module.PRODUCTION:
        if observed_routes[unit]["EnvironmentFiles"] != str(module.BASE/"release.env")+" (ignore_errors=no)":
            raise ValueError("PREMATCH_RELEASE_MISMATCH")
    original_manifest = module.tree(module.ORIGINAL/"application")
    original_units = {unit: module.sha(module.SYSTEM/unit) for unit in
                      (module.ORIGINAL_SERVICE, module.ORIGINAL_SERVICE.replace(".service", ".timer"))}
    original_records = module.records(module.ORIGINAL_STATE)
    previous_metadata = Path('/home/arvis/goalvision-operations/dixon-coles-forward-1183e35-20261003/metadata.json')
    if module.sha(previous_metadata) != '13e7ff81ff14d757afd53ab13cb62ebf48713017c4431167b58ca22b0139aa0a':
        raise ValueError("PREVIOUS_PACKAGE_METADATA_DRIFT")
    previous_manifest = json.loads(previous_metadata.read_text())["application"]
    if module.tree(module.PREVIOUS/"application") != previous_manifest:
        raise ValueError("PREVIOUS_FORWARD_APPLICATION_DRIFT")
    package = Path("/home/arvis/goalvision-operations")/("dixon-coles-forward-"+commit[:7]+"-20261004")
    wrapper = package.parent/"dixon-coles-forward-r2.py"
    if wrapper.exists():
        raise ValueError("EXISTING_WRAPPER_REVIEW_REQUIRED")
    package.mkdir(exist_ok=False)
    shutil.copyfile(Path(__file__).with_name("update.py"), package/"update.py")
    for name in application:
        destination = package/"application"/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, destination)
    smoke = verify_imports(package/"application", module.PYTHON)
    meta = {"source_commit": commit,
            "previous_manifest": previous_manifest,
            "runtime_import_smoke": smoke, "updater_sha256": module.sha(package/"update.py"),
            "application": application, "base_manifest": baseline,
            "environment_sha256": module.sha(module.BASE/"release.env"),
            "routes": observed_routes, "original_manifest": original_manifest,
            "original_units": original_units, "original_records": original_records,
            "rollback": "PAUSE_ONLY_RETAIN_ALL_RESEARCH_AND_PRODUCTION"}
    (package/"metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True)+"\n")
    module.validate(package)
    hashes = {p.relative_to(package).as_posix(): module.sha(p)
              for p in package.rglob("*") if p.is_file()}
    (package/"SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name,digest in sorted(hashes.items())))
    pins = {name: hashes[name] for name in ("update.py", "metadata.json")}
    wrapper.write_text('"""Pinned Dixon-Coles automation operator entry point."""\n'
        'import hashlib\nfrom pathlib import Path\nimport runpy\n'
        +'PACKAGE = Path('+repr(str(package))+')\nPINS = '+repr(pins)+'\n'
        +'for name, digest in PINS.items():\n'
        +'    path = PACKAGE/name\n'
        +'    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:\n'
        +'        raise SystemExit("PINNED_PACKAGE_HASH_MISMATCH")\n'
        +'runpy.run_path(str(PACKAGE/"update.py"), run_name="__main__")\n')
    print("PACKAGE_PREPARED="+str(package))
    print("OPERATOR_APPLY: sudo python3 ~/goalvision-operations/dixon-coles-forward-r2.py --apply")
    print("PAUSE: sudo python3 ~/goalvision-operations/dixon-coles-forward-r2.py --apply --rollback")

if __name__ == "__main__":
    main()
