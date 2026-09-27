"""Read-only exact package verification. No install or rollback action exists."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def verify(root: Path, expected: str) -> dict:
    """Verify pinned manifest, exact payload file set, and every file SHA-256."""
    def sha(path: Path) -> str:
        if path.is_symlink() or not path.is_file():
            raise ValueError('PACKAGE_FILE_INVALID')
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(root/'manifest.json') != expected:
        raise ValueError('MANIFEST_HASH_MISMATCH')
    manifest = json.loads((root/'manifest.json').read_text())
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(manifest['files']) | {'manifest.json'}:
        raise ValueError('PACKAGE_FILE_SET_MISMATCH')
    for name, digest in manifest['files'].items():
        path = root/name
        if path.resolve().is_relative_to(root.resolve()) is False or sha(path) != digest:
            raise ValueError('PAYLOAD_HASH_MISMATCH')
    return {'status': 'VERIFIED', 'files': len(manifest['files']),
            'application_commit': manifest['application_commit'], 'installation_executed': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.package.resolve(), args.sha256), sort_keys=True))


if __name__ == '__main__':
    main()
