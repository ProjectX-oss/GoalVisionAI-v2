"""Pinned GoalVision observer/quota recovery. Default preflight; --apply requires root."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True
PACKAGE = Path('/home/arvis/goalvision-operations/observer-quota-recovery-20261012')
METADATA_SHA256 = 'aeee9d4a1300247bae57999baeb6477de3807efeca4fd493bac960e9f7d0e9f2'
if PACKAGE.is_symlink() or PACKAGE.resolve() != PACKAGE:
    raise SystemExit('PACKAGE_PATH_DRIFT')
meta_path = PACKAGE/'metadata.json'
if meta_path.is_symlink() or hashlib.sha256(meta_path.read_bytes()).hexdigest() != METADATA_SHA256:
    raise SystemExit('PINNED_METADATA_HASH_MISMATCH')
meta = json.loads(meta_path.read_text())
for name, expected in meta['scripts'].items():
    path = PACKAGE/name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('PINNED_SCRIPT_HASH_MISMATCH')
runpy.run_path(str(PACKAGE/'update.py'), run_name='__main__')
