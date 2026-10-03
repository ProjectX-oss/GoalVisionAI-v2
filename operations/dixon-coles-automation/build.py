"""Build from committed source; no systemd mutations or research executions."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

def main() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("dc_install", Path(__file__).with_name("update.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tracked = subprocess.check_output(["git", "ls-files", "app"], cwd=root, text=True).splitlines()
    application = {name: module.sha(root/name) for name in tracked if
                   name.endswith(".py") or name in
                   ("app/adaptive_lab/calendar_plan_20261002.json", module.PLAN)}
    for name in (*application, "operations/dixon-coles-automation/update.py",
                 "operations/dixon-coles-automation/build.py"):
        if subprocess.check_output(["git", "show", commit+":"+name], cwd=root) != (root/name).read_bytes():
            raise ValueError("UNCOMMITTED_SOURCE:"+name)
    baseline = module.tree(module.BASE/"application")
    if {k:v for k,v in application.items() if not k.startswith("app/dixon_coles_research/")} != baseline:
        raise ValueError("PRODUCTION_APPLICATION_DIFFERENCE")
    module.disabled_admin()
    observed_routes = module.routes()
    for unit in module.PRODUCTION:
        if observed_routes[unit]["EnvironmentFiles"] != str(module.BASE/"release.env")+" (ignore_errors=no)":
            raise ValueError("PREMATCH_RELEASE_MISMATCH")
    seed = module.records(module.SEED)
    if len(seed) != 10:
        raise ValueError("SEED_REVIEW_REQUIRED")
    package = Path("/home/arvis/goalvision-operations")/("dixon-coles-automation-"+commit[:7]+"-20261003")
    wrapper = package.parent/"dixon-coles-automation.py"
    if wrapper.exists():
        raise ValueError("EXISTING_WRAPPER_REVIEW_REQUIRED")
    package.mkdir(exist_ok=False)
    shutil.copyfile(Path(__file__).with_name("update.py"), package/"update.py")
    for name in application:
        destination = package/"application"/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, destination)
    meta = {"source_commit": commit, "updater_sha256": module.sha(package/"update.py"),
            "application": application, "base_manifest": baseline,
            "environment_sha256": module.sha(module.BASE/"release.env"),
            "routes": observed_routes, "seed_records": seed,
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
    print("OPERATOR_APPLY: sudo python3 ~/goalvision-operations/dixon-coles-automation.py --apply")
    print("PAUSE: sudo python3 ~/goalvision-operations/dixon-coles-automation.py --apply --rollback")

if __name__ == "__main__":
    main()
