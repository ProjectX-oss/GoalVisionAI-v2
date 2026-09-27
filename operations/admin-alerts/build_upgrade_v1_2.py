"""Build a separate ADMIN-only upgrade payload; never deploy it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--v1-package', type=Path, required=True)
    args = parser.parse_args()
    # Pin the reviewed installed-v1 distribution, not an intermediate v1.1 tree.
    manifest = (args.v1_package/'SHA256SUMS').read_bytes()
    if hashlib.sha256(manifest).hexdigest() != '3a27a9f75996698a5576cff2f3e889d3a5c20d091fb0c891de704b462ac9b7a0':
        raise ValueError('REVIEWED_V1_PACKAGE_REQUIRED')
    for line in manifest.decode().splitlines():
        digest, name = line.split('  ', 1)
        if hashlib.sha256((args.v1_package/name).read_bytes()).hexdigest() != digest:
            raise ValueError('V1_PACKAGE_HASH_MISMATCH')
    operations = Path(__file__).resolve().parent
    repo = operations.parents[1]
    output = args.output.resolve()
    output.mkdir(mode=0o755)  # never overwrite an existing package
    (output/'app/admin_alerts').mkdir(parents=True)
    shutil.copyfile(args.v1_package/'app/__init__.py', output/'app/__init__.py')
    for source in (repo/'app/admin_alerts').glob('*.py'):
        shutil.copyfile(source, output/'app/admin_alerts'/source.name)
    for name in ('run.py', 'upgrade_v1_2.py', 'disable-admin-alerts'):
        shutil.copyfile(operations/name, output/name)
    shutil.copyfile(args.v1_package/'SHA256SUMS', output/'v1-SHA256SUMS')
    old = json.loads((args.v1_package/'host-baseline.json').read_text())
    baseline = {'operator_observed_incidents': ['7f2cfe2a621b163f2367ac94', 'd9f68a79d28d17a4bcb88d10'], 'source_commit': '7acdec28bb759ab89c6f0a913d0856fbe8c885c8', 'base_commit': 'cf91784f3c4618e553c57e9d0f9aebe8ec946a12', 'protected_sha256': old['protected_sha256'], 'admin_units': {
        name: hashlib.sha256((args.v1_package/name).read_bytes()).hexdigest()
        for name in ('goalvision-admin-alerts.service', 'goalvision-admin-alerts.timer')}}
    (output/'upgrade-baseline.json').write_text(json.dumps(baseline, indent=2, sort_keys=True)+'\n')
    manifest = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output)}\n'
                       for p in sorted(output.rglob('*')) if p.is_file())
    (output/'SHA256SUMS').write_text(manifest)
    print(json.dumps({'package': str(output), 'sha256sums_sha256': hashlib.sha256(manifest.encode()).hexdigest()}))


if __name__ == '__main__':
    main()
