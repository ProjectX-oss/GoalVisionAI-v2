"""Pinned GoalVision quota/ADMIN repair. Default preflight; --apply requires root."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True
PACKAGE = Path('/home/arvis/goalvision-operations/quota-admin-repair-34a487d-20261010')
METADATA_SHA256 = '3e8553f61be762b3d09c087a79024080c98d5ed77247e530ec6e38ed957c1eb1'
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
