"""Stage an exact-commit operator tool. Does not change installed application or ledger."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def build(root, commit, destination):
    full = subprocess.check_output(['git', 'rev-parse', commit + '^{commit}'], cwd=root, text=True).strip()
    name = 'combo-receipt-' + full[:7] + '-20261006'
    package = destination / name
    files = {name: subprocess.check_output(['git', 'show', full + ':operations/combo-receipt-recovery/' + name],
             cwd=root) for name in ('recover.py', 'case.json')}
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
    manifest = {'source_commit': full, 'purpose': 'OPERATOR_RECEIPT_RECONCILIATION_ONLY', 'files': hashes}
    files['manifest.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    hashes['manifest.json'] = hashlib.sha256(files['manifest.json']).hexdigest()
    if package.exists():
        if package.is_symlink() or set(p.name for p in package.iterdir()) != set(files):
            raise ValueError('EXISTING_PACKAGE_DRIFT')
        if any((package/name).is_symlink() or (package/name).read_bytes() != body for name,body in files.items()):
            raise ValueError('EXISTING_PACKAGE_DRIFT')
    else:
        package.mkdir(mode=0o700)
        for name, body in files.items():
            (package/name).write_bytes(body)
            (package/name).chmod(0o600)
    wrapper = f'''"""Pinned one-COMBO recovery; default read-only, --apply is operator-only."""
import hashlib
from pathlib import Path
import runpy
PACKAGE = Path({str(package)!r})
PINS = {hashes!r}
if PACKAGE.is_symlink():
    raise SystemExit('PINNED_PACKAGE_HASH_MISMATCH')
for name, expected in PINS.items():
    path = PACKAGE/name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('PINNED_PACKAGE_HASH_MISMATCH')
runpy.run_path(str(PACKAGE/'recover.py'), run_name='__main__')
'''
    launcher = destination/'combo-receipt.py'
    if launcher.exists() or launcher.is_symlink():
        if launcher.is_symlink() or launcher.read_text() != wrapper:
            raise ValueError('EXISTING_LAUNCHER_DRIFT')
    else:
        launcher.write_text(wrapper)
        launcher.chmod(0o600)
    print('COMBO_RECEIPT_OPERATOR_TOOL_PREPARED=' + str(package))
    print('No deployment, ledger write, provider call or Telegram call.')


if __name__ == '__main__':
    build(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
