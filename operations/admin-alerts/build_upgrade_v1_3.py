"""Build the reviewed direct v1.2 -> v1.3 standalone ADMIN payload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--v1-2-package', type=Path, required=True)
    args = parser.parse_args()
    base = args.v1_2_package
    manifest = (base/'SHA256SUMS').read_bytes()
    if hashlib.sha256(manifest).hexdigest() != 'e747128e373a237db2031085eef2b905af55e543488b23d7ef58e678e0e4575f':
        raise ValueError('REVIEWED_V1_2_PACKAGE_REQUIRED')
    for line in manifest.decode().splitlines():
        value, name = line.split('  ', 1)
        if hashlib.sha256((base/name).read_bytes()).hexdigest() != value:
            raise ValueError('BASELINE_HASH_MISMATCH')
    operations = Path(__file__).resolve().parent
    repo = operations.parents[1]
    output = args.output.resolve()
    output.mkdir(mode=0o755)
    (output/'app/admin_alerts').mkdir(parents=True)
    shutil.copyfile(base/'app/__init__.py', output/'app/__init__.py')
    for source in (repo/'app/admin_alerts').glob('*.py'):
        shutil.copyfile(source, output/'app/admin_alerts'/source.name)
    for name in ('run.py','control_v1_3.py','rehearse_v1_3.py'):
        shutil.copyfile(operations/name, output/name)
    shutil.copyfile(base/'SHA256SUMS', output/'v1-2-SHA256SUMS')
    baseline = json.loads((base/'upgrade-baseline.json').read_text())
    (output/'upgrade-baseline.json').write_text(json.dumps({
        'base_commit': 'd811177fdd11e25b087f036584d33c0e0328906b',
        'admin_units': baseline['admin_units'], 'unit_changes': False}, sort_keys=True, indent=2)+'\n')
    manifest = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output)}\n'
                       for p in sorted(output.rglob('*')) if p.is_file())
    (output/'SHA256SUMS').write_text(manifest)
    print(json.dumps({'package': str(output), 'manifest_sha256': hashlib.sha256(manifest.encode()).hexdigest()}))


if __name__ == '__main__':
    main()
