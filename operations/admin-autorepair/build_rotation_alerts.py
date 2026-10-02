"""Prepare the pinned ADMIN-only rotation-alert operator package; no deployment."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

def main():
    root=Path(__file__).resolve().parents[2]
    source=Path(__file__).with_name("update_rotation_alerts.py")
    helper=Path(__file__).with_name("update_compat.py")
    spec=importlib.util.spec_from_file_location("rotation_wrapper",source)
    wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
    spec=importlib.util.spec_from_file_location("rotation_transaction",helper)
    transaction=importlib.util.module_from_spec(spec);spec.loader.exec_module(transaction)
    wrapper.configure(transaction)
    transaction.verify_route(transaction.SPECS["monitor"],wrapper.BASE)
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
    for name in (*wrapper.MODULES,str(source.relative_to(root)),str(helper.relative_to(root))):
        if subprocess.check_output(["git","show",commit+":"+name],cwd=root)!=(root/name).read_bytes():
            raise ValueError("UNCOMMITTED_SOURCE:"+name)
    expected_base=json.loads((wrapper.BASE/"manifest.json").read_text())
    if transaction.tree(wrapper.BASE)!=expected_base:
        raise ValueError("INSTALLED_BASE_HASH_DRIFT")
    for source_file in (root/"app/admin_alerts").glob("*.py"):
        name=str(source_file.relative_to(root))
        if name not in wrapper.MODULES and source_file.read_bytes()!=(wrapper.BASE/name).read_bytes():
            raise ValueError("UNREVIEWED_ADMIN_SOURCE_DIFFERENCE")
    operations=Path("/home/arvis/goalvision-operations")
    entry=operations/"admin-rotation-fix.py"
    if entry.exists():
        raise ValueError("EXISTING_WRAPPER_REVIEW_REQUIRED")
    package=operations/("admin-rotation-alerts-"+commit[:7]+"-20261002")
    package.mkdir(exist_ok=False)
    shutil.copyfile(source,package/"update.py")
    shutil.copyfile(helper,package/"update_compat.py")
    for name in wrapper.MODULES:
        output=package/"overlay/monitor"/name;output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,output)
    meta={"source_commit":commit,"updater_sha256":transaction.sha(package/"update.py"),
        "helper_sha256":transaction.sha(package/"update_compat.py"),
        "base_manifests":{"monitor":expected_base},
        "files":{"monitor":{name:transaction.sha(package/"overlay/monitor"/name) for name in wrapper.MODULES}},
        "protected_routes_at_preparation":transaction.protected_routes(),
        "incident":wrapper.INCIDENT,"deployment":"NOT_PERFORMED"}
    (package/"metadata.json").write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n")
    wrapper.engine(package).validate(package)
    pins={name:transaction.sha(package/name) for name in ("update.py","metadata.json")}
    entry.write_text('"""Pinned ADMIN-only rotation alert correction."""\n'
        'import hashlib\nfrom pathlib import Path\nimport runpy\n'
        'PACKAGE=Path('+repr(str(package))+')\nPINS='+repr(pins)+'\n'
        'for name,digest in PINS.items():\n'
        '    path=PACKAGE/name\n'
        '    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:\n'
        '        raise SystemExit("PINNED_PACKAGE_HASH_MISMATCH")\n'
        'runpy.run_path(str(PACKAGE/"update.py"),run_name="__main__")\n')
    hashes={str(p.relative_to(package)):transaction.sha(p) for p in package.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts}
    (package/"SHA256SUMS").write_text("".join(f"{fp}  {name}\n" for name,fp in sorted(hashes.items())))
    print("ADMIN_ROTATION_PACKAGE_PREPARED="+str(package))
    print("READ_ONLY: python3 "+str(entry))
    print("OPERATOR_APPLY: sudo python3 "+str(entry)+" --apply")

if __name__=="__main__":
    main()
