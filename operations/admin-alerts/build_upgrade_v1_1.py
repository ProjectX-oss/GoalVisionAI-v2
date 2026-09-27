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
    operations = Path(__file__).resolve().parent
    repo = operations.parents[1]
    output = args.output.resolve()
    output.mkdir(mode=0o755)  # never overwrite an existing package
    (output/'app/admin_alerts').mkdir(parents=True)
    shutil.copyfile(args.v1_package/'app/__init__.py', output/'app/__init__.py')
    for source in (repo/'app/admin_alerts').glob('*.py'):
        shutil.copyfile(source, output/'app/admin_alerts'/source.name)
    for name in ('run.py', 'upgrade_v1_1.py', 'disable-admin-alerts'):
        shutil.copyfile(operations/name, output/name)
    shutil.copyfile(args.v1_package/'SHA256SUMS', output/'v1-SHA256SUMS')
    old = json.loads((args.v1_package/'host-baseline.json').read_text())
    baseline = {'protected_sha256': old['protected_sha256'], 'admin_units': {
        name: hashlib.sha256((args.v1_package/name).read_bytes()).hexdigest()
        for name in ('goalvision-admin-alerts.service', 'goalvision-admin-alerts.timer')}}
    (output/'upgrade-baseline.json').write_text(json.dumps(baseline, indent=2, sort_keys=True)+'\n')
    manifest = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output)}\n'
                       for p in sorted(output.rglob('*')) if p.is_file())
    (output/'SHA256SUMS').write_text(manifest)
    print(json.dumps({'package': str(output), 'sha256sums_sha256': hashlib.sha256(manifest.encode()).hexdigest()}))


if __name__ == '__main__':
    main()
