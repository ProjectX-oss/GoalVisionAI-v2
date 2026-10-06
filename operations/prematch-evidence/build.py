"""Prepare a checksummed operator package without installing or running services."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess


def verify_imports(application):
    """Validate the exact assembled package with isolated imports and network denied."""
    code = """import sys,json,socket,pathlib
root=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
def denied(*args,**kwargs): raise RuntimeError('NETWORK_FORBIDDEN')
socket.socket.connect=denied
socket.socket.connect_ex=denied
socket.create_connection=denied
from app.lab_v2_shadow import cli,accuracy_combo,combo_agreement,combo_agreement_sources,combo_market,combo_market_sources
from app.lab_combo import service,bot_delivery
from app.lab_private_single import policy,routing,runtime,repository
from app.dixon_coles_forward.contracts import load_plan
from app.dixon_coles_constrained.model import load_protocol
from app.lab_v2_shadow.competition_registry import REGISTRY_FINGERPRINT
from app.lab_v2_shadow.runner import _final_review_queue
from app.lab_v2_shadow.global_evaluation import provider_probability_diagnostic
from app.adaptive_lab.performance import VERSION, probability_metrics
from app.dixon_coles_forward.incremental import load_plan as load_incremental_plan,report as incremental_report
assert VERSION=='LAB_PERFORMANCE_SNAPSHOT_V2'
assert abs(probability_metrics([(0.7,1),(0.5,0)])['calibration_bias_predicted_minus_observed']-0.1)<1e-10
assert callable(provider_probability_diagnostic)
from datetime import datetime,timedelta,timezone
clock=datetime(2026,10,4,19,tzinfo=timezone.utc)
class ReadOnlyEvidence:
    def all(self,kind):
        assert kind=='enrichment_service'
        return []
fixtures=[dict(fixture_id=1,kickoff_utc=clock+timedelta(hours=1)),
          dict(fixture_id=2,kickoff_utc=clock+timedelta(minutes=30),league_id=999,country='Testland')]
assert [f['fixture_id'] for f in _final_review_queue(fixtures,ReadOnlyEvidence(),now=clock,tracked_ids={2})]==[2]
incremental=incremental_report([],plan=load_incremental_plan(),forward=load_plan(),now=clock)
assert incremental['promotion_eligibility']=='NOT_ELIGIBLE'
loaded={name:pathlib.Path(module.__file__).resolve() for name,module in sys.modules.items()
        if (name=='app' or name.startswith('app.')) and getattr(module,'__file__',None)}
if not loaded or any(not path.is_relative_to(root) for path in loaded.values()):
    raise RuntimeError('SOURCE_CHECKOUT_FALLBACK_FORBIDDEN')
print(json.dumps({'status':'ISOLATED_PREMATCH_EVIDENCE_IMPORT_PASS','modules':len(loaded),
    'plan_fingerprint':load_plan()['fingerprint'],'protocol_fingerprint':load_protocol()['fingerprint'],
    'registry_fingerprint':REGISTRY_FINGERPRINT,
    'incremental_plan_sha256':__import__('hashlib').sha256((root/'app/dixon_coles_forward/incremental_plan_20261004.json').read_bytes()).hexdigest(),
    'provider_calls':0,'telegram_sends':0}))
"""
    result = subprocess.run(['/home/arvis/GoalVisionAI/.venv/bin/python','-I','-B','-c',code,str(application)],
        cwd='/tmp', capture_output=True, text=True, timeout=20, check=True,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
    return json.loads(result.stdout)


def main():
    root = Path(__file__).resolve().parents[2]
    updater = Path(__file__).with_name('update.py')
    spec = importlib.util.spec_from_file_location('private_upgrade', updater)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.disabled_worker()
    mod.verify_routes()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    files = (*mod.FILES, 'operations/prematch-evidence/update.py', 'operations/prematch-evidence/build.py', )
    for name in files:
        committed = subprocess.check_output(['git', 'show', commit+':'+name], cwd=root)
        if committed != (root/name).read_bytes():
            raise ValueError('UNCOMMITTED_PACKAGE_SOURCE:'+name)
    manifest = mod.tree(mod.BASE/'application')
    expected = dict(manifest, **{name: mod.sha(root/name) for name in mod.FILES})
    actual = {'app/'+name: digest for name, digest in mod.tree(root/'app').items()}
    if actual != expected:
        raise ValueError('UNREVIEWED_SOURCE_BASE_DIFFERENCE')
    package = Path('/home/arvis/goalvision-operations') / ('prematch-evidence-'+commit[:7]+'-20261006')
    package.mkdir(exist_ok=False)
    shutil.copyfile(updater, package/'update.py')
    for name in mod.FILES:
        destination = package/'overlay'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, destination)
    meta = {'source_commit': commit, 'updater_sha256': mod.sha(package/'update.py'),
            'files': {name: mod.sha(package/'overlay'/name) for name in mod.FILES},
            'base_manifest': manifest,
            'route_sources': mod.expected_route_sources(manifest,
                {name: mod.sha(package/'overlay'/name) for name in mod.FILES}),
            'expected_commands': mod.stable_commands(mod.SERVICES+mod.PROTECTED),
            'protected_routes': mod.routes(mod.PROTECTED),
            'rollback_semantics': 'NOT_PREPARED_NO_AUTOMATIC_ROLLBACK'}
    assembled = package/'application-smoke'
    shutil.copytree(mod.BASE/'application', assembled, ignore=shutil.ignore_patterns('__pycache__'))
    for name in mod.FILES:
        destination = assembled/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.chmod(0o644)  # Only our disposable smoke copy; installed source stays read-only.
        shutil.copyfile(package/'overlay'/name, destination)
    if mod.tree(assembled) != expected:
        raise ValueError('ASSEMBLED_MANIFEST_MISMATCH')
    meta['runtime_import_smoke'] = verify_imports(assembled)
    shutil.rmtree(assembled)
    (package/'metadata.json').write_text(json.dumps(meta, indent=2, sort_keys=True)+'\n')
    mod.validate(package)
    hashes = {str(p.relative_to(package)): mod.sha(p) for p in package.rglob('*') if p.is_file()}
    (package/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(hashes.items())))
    wrapper = Path('/home/arvis/goalvision-operations/prematch-evidence.py')
    if wrapper.exists():
        raise ValueError('EXISTING_WRAPPER_REVIEW_REQUIRED')
    wrapper.write_text('''"""Pinned GoalVision PREMATCH evidence/observability update operator entry point."""
import hashlib
from pathlib import Path
import runpy
PACKAGE = Path('''+repr(str(package))+''')
PINS = '''+repr({name: hashes[name] for name in ('update.py','metadata.json')})+'''
for name, digest in PINS.items():
    path = PACKAGE / name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit('PINNED_PACKAGE_HASH_MISMATCH')
runpy.run_path(str(PACKAGE/'update.py'), run_name='__main__')
''')
    print('PACKAGE_PREPARED='+str(package))
    print('READ_ONLY: python3 ~/goalvision-operations/prematch-evidence.py')
    print('OPERATOR_APPLY: sudo python3 ~/goalvision-operations/prematch-evidence.py --apply')


if __name__ == '__main__':
    main()
