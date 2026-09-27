"""Build a deterministic review bundle. No host configuration or database writes."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    target = args.target.absolute()
    if target.exists() or target.with_suffix('.tar.gz').exists():
        raise SystemExit('Refusing to replace an existing review bundle')
    frozen = Path('/home/arvis/goalvision-operations/prematch-quota-lock-hardening-package-20260927')
    expected = 'f24738b05fef5f71f3ebcaead3c791233d94fcc38cee21e96a59f2f23493fff2'
    if sha(frozen / 'manifest.json') != expected:
        raise SystemExit('Frozen manifest mismatch')
    spec = importlib.util.spec_from_file_location('controller', root / 'controller.py')
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    contract = controller.load_contract(root, sha(root / 'host-contract.json'))
    controller.Controller(controller.Host(), frozen, contract).verify_package()
    target.mkdir(parents=True)
    for name in ('controller.py', 'host-contract.json', 'controller-checksums.json', 'host-rehearsal.json',
                 'test_controller.py', 'test-results.json', 'OPERATIONS_COMMANDS.md',
                 'shadow-schema.sql', 'superseded-package.json', 'build_bundle.py', 'rehearse.py'):
        shutil.copyfile(root / name, target / name)
    shutil.copyfile(root.parents[1] / 'docs/operations/PREMATCH_QUOTA_HARDENING_DEPLOYMENT_CONTROLLER.md', target / 'REVIEW.md')
    shutil.copytree(frozen, target / 'frozen')
    shutil.copyfile(frozen.with_suffix('.tar.gz'), target / 'frozen.tar.gz')
    files = {str(p.relative_to(target)): sha(p) for p in sorted(target.rglob('*')) if p.is_file()}
    contract = json.loads((root / 'host-contract.json').read_text())
    manifest = {'version': 2, 'contract_sha256': sha(root / 'host-contract.json'),
                'route_relocation_approved': True,
                'route_derivation': {'operation': 'bytes.replace', 'from_prefix': str(frozen),
                                     'to_prefix': contract['release_root'],
                                     'fixed_subpaths': ['application', 'research', 'release.env', 'research.env'],
                                     'resulting_files': contract['relocated_files']},
                'shadow_migration_proof': contract['shadow_migration_proof'],
                'supersedes': json.loads((root / 'superseded-package.json').read_text()),
                'purpose': 'REVIEW_ONLY_NOT_DEPLOYED', 'source_commit': '557d5af2c05d78404b5e86368e72ec5671dcf737',
                'frozen_manifest_sha256': expected, 'files': files}
    (target / 'operations-manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    sums = ''.join(sha(p) + '  ' + str(p.relative_to(target)) + '\n' for p in sorted(target.rglob('*')) if p.is_file())
    (target / 'SHA256SUMS').write_text(sums)
    archive = target.with_suffix('.tar.gz')
    with archive.open('wb') as output:
        with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as tar:
                for path in sorted(target.rglob('*')):
                    if not path.is_file():
                        continue
                    data = path.read_bytes()
                    info = tarfile.TarInfo(target.name + '/' + str(path.relative_to(target)))
                    info.size = len(data)
                    info.mode = 0o444
                    info.mtime = 0
                    tar.addfile(info, io.BytesIO(data))
    print(json.dumps({'package': str(target), 'archive': str(archive), 'sha256': sha(archive),
                      'manifest_sha256': sha(target / 'operations-manifest.json')}, sort_keys=True))


if __name__ == '__main__':
    main()
