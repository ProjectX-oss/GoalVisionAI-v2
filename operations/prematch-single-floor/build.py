"""Prepare a checksummed operator package without installing or running services."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    updater = Path(__file__).with_name('update.py')
    spec = importlib.util.spec_from_file_location('settlement_upgrade', updater)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.disabled_worker()
    mod.verify_routes()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    files = (*mod.FILES, 'operations/prematch-single-floor/update.py')
    for name in files:
        committed = subprocess.check_output(['git', 'show', commit+':'+name], cwd=root)
        if committed != (root/name).read_bytes():
            raise ValueError('UNCOMMITTED_PACKAGE_SOURCE:'+name)
    manifest = mod.tree(mod.BASE/'application')
    expected = dict(manifest, **{name: mod.sha(root/name) for name in mod.FILES})
    actual = {'app/'+name: digest for name, digest in mod.tree(root/'app').items()}
    if actual != expected:
        raise ValueError('UNREVIEWED_SOURCE_BASE_DIFFERENCE')
    package = Path('/home/arvis/goalvision-operations') / ('prematch-single-floor-'+commit[:7]+'-20261002')
    package.mkdir(exist_ok=False)
    shutil.copyfile(updater, package/'update.py')
    for name in mod.FILES:
        destination = package/'overlay'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, destination)
    meta = {'source_commit': commit, 'updater_sha256': mod.sha(package/'update.py'),
            'files': {name: mod.sha(package/'overlay'/name) for name in mod.FILES},
            'base_manifest': manifest,
            'route_sources': {str(mod.BASE/'release.env'): {
                'environment_sha256': mod.sha(mod.BASE/'release.env'), 'manifest': manifest}},
            'expected_commands': mod.stable_commands(mod.SERVICES+mod.PROTECTED),
            'protected_routes': mod.routes(mod.PROTECTED),
            'rollback_semantics': 'DISABLE_SINGLE_FLOOR_AND_NEW_EARLY_LOSSES_RETAIN_COMPATIBLE_READERS'}
    (package/'metadata.json').write_text(json.dumps(meta, indent=2, sort_keys=True)+'\n')
    mod.validate(package)
    hashes = {str(p.relative_to(package)): mod.sha(p) for p in package.rglob('*') if p.is_file()}
    (package/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(hashes.items())))
    wrapper = Path('/home/arvis/goalvision-operations/prematch-policy-fix.py')
    if wrapper.exists():
        raise ValueError('EXISTING_WRAPPER_REVIEW_REQUIRED')
    wrapper.write_text('''"""Pinned GoalVision SINGLE floor and settlement operator entry point."""
import hashlib
from pathlib import Path
import runpy
PACKAGE = Path('''+repr(str(package))+''')
PINS = '''+repr({name: hashes[name] for name in ('update.py','metadata.json')})+'''
for name, digest in PINS.items():
    path = PACKAGE / name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit('PINNED_PACKAGE_HASH_MISMATCH')
runpy.run_path(str(PACKAGE/'update.py'), run_name='__main__')
''')
    print('PACKAGE_PREPARED='+str(package))
    print('READ_ONLY: python3 ~/goalvision-operations/prematch-policy-fix.py')
    print('OPERATOR_APPLY: sudo python3 ~/goalvision-operations/prematch-policy-fix.py --apply')
    print('COMPAT_ROLLBACK: sudo python3 ~/goalvision-operations/prematch-policy-fix.py --apply --rollback')


if __name__ == '__main__':
    main()

