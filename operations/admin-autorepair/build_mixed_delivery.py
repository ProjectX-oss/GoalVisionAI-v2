"""Build a pinned monitor-only package and import its assembled runtime."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess


def import_smoke(root):
    code = """import sys,json,socket,pathlib
root=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
def forbidden(*args,**kwargs): raise RuntimeError('NETWORK_FORBIDDEN_IN_PACKAGE_SMOKE')
socket.socket.connect=forbidden
socket.socket.connect_ex=forbidden
socket.create_connection=forbidden
from app.admin_alerts import sources,rules
loaded={name:pathlib.Path(value.__file__).resolve() for name,value in sys.modules.items()
        if (name=='app' or name.startswith('app.')) and getattr(value,'__file__',None)}
if not loaded or any(not path.is_relative_to(root) for path in loaded.values()):
    raise RuntimeError('SOURCE_CHECKOUT_FALLBACK_FORBIDDEN')
print(json.dumps({'status':'ISOLATED_MONITOR_IMPORT_PASS','app_modules':len(loaded),
 'monitor_scans':0,'provider_calls':0,'telegram_sends':0}))
"""
    result = subprocess.run(["/usr/bin/python3", "-I", "-B", "-c", code, str(root)],
        cwd="/tmp", check=True, capture_output=True, text=True, timeout=10,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    proof = json.loads(result.stdout)
    if proof.get("status") != "ISOLATED_MONITOR_IMPORT_PASS":
        raise ValueError("IMPORT_PROOF_FAILED")
    return proof


def main():
    os.umask(0o077)
    root = Path(__file__).resolve().parents[2]
    source = Path(__file__).with_name("update_mixed_delivery.py")
    helper = Path(__file__).with_name("update_compat.py")
    spec = importlib.util.spec_from_file_location("health_wrapper", source)
    wrapper = importlib.util.module_from_spec(spec); spec.loader.exec_module(wrapper)
    spec = importlib.util.spec_from_file_location("health_transaction", helper)
    transaction = importlib.util.module_from_spec(spec); spec.loader.exec_module(transaction)
    wrapper.configure(transaction)
    transaction.verify_route(transaction.SPECS["monitor"], wrapper.BASE)
    wrapper.require_codex_runtime_disabled(transaction)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tracked = (*wrapper.MODULES, str(source.relative_to(root)), str(helper.relative_to(root)),
               str(Path(__file__).resolve().relative_to(root)))
    for name in tracked:
        if subprocess.check_output(["git", "show", commit+":"+name], cwd=root) != (root/name).read_bytes():
            raise ValueError("UNCOMMITTED_SOURCE:"+name)
    base_manifest = json.loads((wrapper.BASE/"manifest.json").read_text())
    if transaction.tree(wrapper.BASE) != base_manifest:
        raise ValueError("INSTALLED_BASE_HASH_DRIFT")
    for file in (root/"app/admin_alerts").glob("*.py"):
        name = str(file.relative_to(root))
        if name not in wrapper.MODULES and file.read_bytes() != (wrapper.BASE/name).read_bytes():
            raise ValueError("UNREVIEWED_ADMIN_SOURCE_DIFFERENCE")
    operations = Path("/home/arvis/goalvision-operations")
    entry = operations/"admin-mixed-delivery.py"
    if entry.exists():
        raise ValueError("EXISTING_WRAPPER_REVIEW_REQUIRED")
    package = operations/("admin-mixed-delivery-"+commit[:7]+"-20261004")
    package.mkdir(exist_ok=False)
    shutil.copyfile(source, package/"update.py")
    shutil.copyfile(helper, package/"update_compat.py")
    assembled = package/"assembled"
    shutil.copytree(wrapper.BASE, assembled, ignore=shutil.ignore_patterns("__pycache__"))
    for name in wrapper.MODULES:
        target = package/"overlay/monitor"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, target)
        shutil.copyfile(root/name, assembled/name)
    overlay = {name: transaction.sha(package/"overlay/monitor"/name) for name in wrapper.MODULES}
    expected = dict(base_manifest, **overlay)
    if transaction.tree(assembled) != expected:
        raise ValueError("ASSEMBLED_RUNTIME_DRIFT")
    (assembled/"manifest.json").write_text(json.dumps(expected, indent=2, sort_keys=True)+"\n")
    smoke = import_smoke(assembled)
    meta = {"source_commit": commit, "updater_sha256": transaction.sha(package/"update.py"),
        "helper_sha256": transaction.sha(package/"update_compat.py"),
        "base_manifests": {"monitor": base_manifest}, "files": {"monitor": overlay},
        "protected_routes_at_preparation": transaction.protected_routes(),
        "protected_timers_at_preparation": wrapper.protected_timers(transaction),
        "runtime_import_smoke": smoke, "deployment": "NOT_PERFORMED"}
    approved = Path('/home/arvis/goalvision-operations/combo-aggregate-cb6b7c6-20261004')
    if transaction.sha(approved/'metadata.json') != '894064a07dd94a535b5f935d087a014e8ac2e746ae53866fad3dc7167ed9267a':
        raise ValueError('REVIEWED_PREMATCH_PACKAGE_DRIFT')
    approved_meta = json.loads((approved/'metadata.json').read_text())
    target = Path('/opt/goalvision-prematch-combo-aggregate-cb6b7c6-20261004')
    old_env = Path('/opt/goalvision-prematch-private-single-170-cdcb526-20261004/release.env').read_bytes()
    new_env = old_env.replace(b'/opt/goalvision-prematch-private-single-170-cdcb526-20261004/application',
                             str(target/'application').encode())
    import hashlib
    meta['reviewed_prematch'] = {'target':str(target),
        'manifest':dict(approved_meta['base_manifest'],**approved_meta['files']),
        'environment_sha256':hashlib.sha256(new_env).hexdigest()}
    (package/"metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True)+"\n")
    engine = wrapper.engine(package)
    _, targets = engine.validate(package)
    wrapper.verify_preparation(engine, meta, targets)
    pins = {name: transaction.sha(package/name) for name in ("update.py", "metadata.json")}
    entry.write_text('"""Pinned ADMIN-only mixed delivery classification repair."""\n'
        'import hashlib\nfrom pathlib import Path\nimport runpy\n'
        'PACKAGE=Path('+repr(str(package))+')\nPINS='+repr(pins)+'\n'
        'for name,digest in PINS.items():\n'
        '    path=PACKAGE/name\n'
        '    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:\n'
        '        raise SystemExit("PINNED_PACKAGE_HASH_MISMATCH")\n'
        'runpy.run_path(str(PACKAGE/"update.py"),run_name="__main__")\n')
    hashes = {str(p.relative_to(package)): transaction.sha(p) for p in package.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    (package/"SHA256SUMS").write_text("".join(f"{fp}  {name}\n" for name,fp in sorted(hashes.items())))
    print("ADMIN_MIXED_DELIVERY_PACKAGE_PREPARED="+str(package))
    print("OPERATOR_APPLY: sudo python3 ~/goalvision-operations/admin-mixed-delivery.py --apply")


if __name__ == "__main__":
    main()
