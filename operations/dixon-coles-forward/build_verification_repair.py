"""Build and preflight a pinned operator package; never deploy or run workers."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'operations/dixon-coles-forward'
DEST=Path('/home/arvis/goalvision-operations/dc-forward-verification-20261012')
WRAPPER=DEST.with_suffix('.py')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if DEST.exists() or WRAPPER.exists():raise ValueError('EXISTING_PACKAGE_REVIEW_REQUIRED')
    spec=importlib.util.spec_from_file_location('repair',SOURCE/'repair_evaluation.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    if m.override().exists() or m.TARGET.exists():raise ValueError('BASE_STATE_REQUIRED')
    files={'repair_evaluation.py':SOURCE/'repair_evaluation.py','update.py':SOURCE/'update.py',
           'service.py':ROOT/m.PATCH}
    code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    meta={'version':'DC_FORWARD_VERIFICATION_REPAIR_20261012_V1',
          'code_commit':code_commit,'application_commit':'dd2e1c142ac75d418676cae3255ad7faa7e66711',
          'base':str(m.BASE),'target':str(m.TARGET),'patch':m.PATCH,
          'base_manifest':m.manifest(m.BASE/'application'),'patch_sha256':sha(files['service.py']),
          'package_files':{k:sha(v) for k,v in files.items()},
          'configuration_files':m.configs(),'routes':m.routes(),
          'forward_environment':m.h.prop(m.SERVICE,'Environment'),
          'timer_unit_file_state':m.h.prop(m.TIMER,'UnitFileState')}
    if meta['routes'][m.SERVICE]['DropInPaths']:raise ValueError('UNREVIEWED_FORWARD_DROPIN')
    if meta['routes'][m.SERVICE]['WorkingDirectory'] != str(m.BASE/'application'):
        raise ValueError('UNREVIEWED_FORWARD_ROUTE')
    DEST.mkdir(mode=0o700)
    for name,path in files.items():shutil.copyfile(path,DEST/name)
    (DEST/'metadata.json').write_text(json.dumps(meta,sort_keys=True,indent=2)+'\n')
    m.validate(DEST)
    hashes={name:sha(DEST/name) for name in (*files,'metadata.json')}
    wrapper='''"""Pinned operator entry point; no production action without --apply."""
import hashlib
import os
from pathlib import Path
import sys
PACKAGE=Path(%r)
EXPECTED=%r
for name,expected in EXPECTED.items():
    path=PACKAGE/name
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise SystemExit('SYMLINK_REVIEW_REQUIRED')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise SystemExit('PACKAGE_HASH_MISMATCH')
if any(arg not in ('--apply',) for arg in sys.argv[1:]):
    raise SystemExit('ONLY_APPLY_FLAG_ALLOWED')
os.execv('/usr/bin/python3',['/usr/bin/python3','-I',str(PACKAGE/'repair_evaluation.py'),
                          '--package',str(PACKAGE),*sys.argv[1:]])
''' % (str(DEST),hashes)
    WRAPPER.write_text(wrapper);WRAPPER.chmod(0o500)
    for path in DEST.iterdir():path.chmod(0o400)
    print(json.dumps({'package':str(DEST),'wrapper':str(WRAPPER),'wrapper_sha256':sha(WRAPPER),
                      'metadata_sha256':hashes['metadata.json'],'mode':'PREFLIGHT_ONLY'},sort_keys=True))

if __name__=='__main__':main()
