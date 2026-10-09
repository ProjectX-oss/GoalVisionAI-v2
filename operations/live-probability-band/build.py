"""Build only the six reviewed LIVE probability overlays on the pinned installed release."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_imports(application, root):
    previous=load('age_smoke',root/'operations/live-quote-age/build.py')
    result=previous.verify_imports(application,root)
    code="""import sys,pathlib,json,socket,os
from datetime import datetime,timezone,timedelta
root=pathlib.Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
def denied(*args,**kwargs): raise RuntimeError('NETWORK_FORBIDDEN')
socket.socket.connect=denied;socket.create_connection=denied;socket.socket.connect_ex=denied
from app.live_lab.selection import PROBABILITY_POLICY,in_probability_band,select_candidates
from app.live_lab.engine import state_snapshot,attach_events,readiness
from app.adaptive_lab.contracts import digest
from app.adaptive_lab import daypart
os.environ['GOALVISION_LIVE_PROBABILITY_60_70']='1'
assert daypart.probability_band_enabled()
assert in_probability_band('.60') and in_probability_band('.70')
assert not in_probability_band('.5999999999999999999') and not in_probability_band('.7000000000000000001')
at=datetime(2026,10,9,16,tzinfo=timezone.utc)
state=attach_events(state_snapshot({'fixture':{'id':7,'date':(at-timedelta(hours=1)).isoformat(),'status':{'short':'2H','elapsed':60}},
'goals':{'home':0,'away':0},'teams':{'home':{'id':1},'away':{'id':2}}},retrieved_at=at),{'response':[]},retrieved_at=at)
quote={'fixture_id':7,'state_fingerprint':state['state_fingerprint'],'market':'OVER_1_5','decimal_odds':'1.4',
'bookmaker_id':1,'bookmaker':'Synthetic','market_identity':'synthetic','origin_timestamp':(at-timedelta(seconds=60)).isoformat(),
'retrieved_at':at.isoformat(),'provider_type':'API_FOOTBALL_LIVE_ODDS','endpoint':'/odds/live',
'blocked':False,'stopped':False,'finished':False,'suspended':False}
quote['quote_fingerprint']=digest(quote)
kw=dict(uncertainty=.07,now=at,allow_provider_feed=True,quote_age_diagnostic=True)
assert readiness(state,quote,.65,probability_band=True,**kw)==[]
assert 'NON_POSITIVE_EV' in readiness(state,quote,.65,**kw)
assert 'LIVE_PROBABILITY_OUTSIDE_60_70' in readiness(state,quote,.71,probability_band=True,**kw)
rows=[{'prediction_id':'a','ensemble_probability':'.61','expected_value':100,'policy':PROBABILITY_POLICY,'blockers':[]},
{'prediction_id':'b','ensemble_probability':'.69','expected_value':-.1,'policy':PROBABILITY_POLICY,'blockers':[]}]
assert select_candidates(rows,probability_band=True)[0]['prediction_id']=='b'
for name,module in sys.modules.items():
 if (name=='app' or name.startswith('app.')) and getattr(module,'__file__',None):
  assert pathlib.Path(module.__file__).resolve().is_relative_to(root)
print(json.dumps({'probability_band':'60-70_INCLUSIVE','ev_selection':'DISABLED','provider_calls':0,'telegram_sends':0}))
"""
    probe=subprocess.run(['/home/arvis/GoalVisionAI/.venv/bin/python','-I','-B','-c',code,str(application)],
                         cwd='/tmp',capture_output=True,text=True,timeout=20,check=True,
                         env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
    return {**result,**json.loads(probe.stdout),'status':'ISOLATED_LIVE_PROBABILITY_BAND_PASS'}


def main():
    root=Path(__file__).resolve().parents[2]
    up=load('live_probability_update',Path(__file__).with_name('update.py'))
    up.h.disabled_worker()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    sources=(*up.FILES,'operations/live-probability-band/update.py','operations/live-probability-band/build.py',
             'operations/live-quote-age/update.py','operations/live-quote-age/build.py',
             'operations/live-evening/update.py','operations/live-evening/build.py')
    for name in sources:
        if subprocess.check_output(['git','show',commit+':'+name],cwd=root)!=(root/name).read_bytes():
            raise ValueError('UNCOMMITTED_SOURCE:'+name)
    package=Path('/home/arvis/goalvision-operations')/('live-probability-band-'+commit[:7]+'-20261009')
    wrapper=package.parent/'live-probability-band.py'
    if package.exists() or wrapper.exists():
        raise ValueError('EXISTING_PACKAGE_REVIEW_REQUIRED')
    up.h.reject_symlinks(up.BASE)
    if (up.BASE/'release.env').read_bytes()!=up.q.environment(up.BASE):
        raise ValueError('BASE_ENVIRONMENT_DRIFT')
    manifest=up.h.tree(up.BASE/'application')
    overlays={name:up.h.sha(root/name) for name in up.FILES}
    meta={'source_commit':commit,'base_manifest':manifest,'files':overlays,
          'base_route':up.h.routes((up.SERVICE,))[up.SERVICE],
          'protected_routes':up.h.routes(up.PROTECTED),
          'expected_commands':up.h.stable_commands((up.SERVICE,)+up.PROTECTED),
          'timer_configuration':up.timer_configuration(),
          'policy':'LAB_LIVE_PROBABILITY_60_70_V1',
          'provider_calls':0,'telegram_sends':0}
    package.mkdir()
    shutil.copyfile(root/'operations/live-probability-band/update.py',package/'update.py')
    shutil.copyfile(root/'operations/live-quote-age/update.py',package/'quote_age_update.py')
    shutil.copyfile(root/'operations/live-evening/update.py',package/'base_update.py')
    meta['scripts']={name:up.h.sha(package/name) for name in ('update.py','quote_age_update.py','base_update.py')}
    for name in up.FILES:
        dest=package/'overlay'/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,dest)
    assembled=package/'application-smoke'
    try:
        shutil.copytree(up.BASE/'application',assembled,ignore=shutil.ignore_patterns('__pycache__'))
        for name in up.FILES:
            (assembled/name).parent.mkdir(parents=True,exist_ok=True)
            if (assembled/name).exists():
                (assembled/name).chmod(0o644)
            shutil.copyfile(package/'overlay'/name,assembled/name)
        if up.h.tree(assembled)!=dict(manifest,**overlays):
            raise ValueError('ASSEMBLY_HASH_MISMATCH')
        meta['runtime_import_smoke']=verify_imports(assembled,root)
    finally:
        if assembled.exists():
            shutil.rmtree(assembled)
    (package/'metadata.json').write_text(json.dumps(meta,indent=2,sort_keys=True)+'\n')
    up.validate(package)
    hashes={str(p.relative_to(package)):up.h.sha(p) for p in package.rglob('*') if p.is_file()}
    (package/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(hashes.items())))
    pins={name:hashes[name] for name in ('update.py','quote_age_update.py','base_update.py','metadata.json')}
    wrapper.write_text('"""Pinned LIVE probability-band operator update; default read-only."""\n'
        'import hashlib,runpy\nfrom pathlib import Path\nPACKAGE=Path('+repr(str(package))+')\n'
        'PINS='+repr(pins)+'\n'
        'for name,digest in PINS.items():\n'
        ' p=PACKAGE/name\n'
        ' if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:\n'
        '  raise SystemExit("PINNED_PACKAGE_HASH_MISMATCH")\n'
        'runpy.run_path(str(PACKAGE/"update.py"),run_name="__main__")\n')
    print('LIVE_PROBABILITY_BAND_PACKAGE_PREPARED='+str(package))
    print(json.dumps(meta['runtime_import_smoke'],sort_keys=True))
    print('READ_ONLY: python3 ~/goalvision-operations/live-probability-band.py')
    print('OPERATOR: sudo python3 ~/goalvision-operations/live-probability-band.py --apply')


if __name__=='__main__':
    main()
