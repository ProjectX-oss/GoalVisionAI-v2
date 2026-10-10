"""Pinned GoalVision quota/ADMIN repair. Default preflight; --apply requires root."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True
PACKAGE = Path('/home/arvis/goalvision-operations/quota-admin-repair-ce09949-20261010')
METADATA_SHA256 = '26ea452e27b1f1428d2a09f50ada16de271368f36f01b18a1bf23535069bdbb0'
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
