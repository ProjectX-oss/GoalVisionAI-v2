"""Lab daypart and LIVE API-feed integration. Default read-only; root operator apply only."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

BASE = Path('/opt/goalvision-prematch-combo-double-170-6489f92-20261006')
SERVICES = ('goalvision-lab-v2-discover.service', 'goalvision-adaptive-learning-observer.service',
            'goalvision-lab-combo-settle.service', 'goalvision-adaptive-learning.service')
ROUTE_BASES = {unit: BASE / 'release.env' for unit in SERVICES}
TIMERS = tuple(u.replace('.service', '.timer') for u in SERVICES)
OVERRIDES = {u: Path('/etc/systemd/system') / (u + '.d') / 'zzzzzzzzzzzzzzzzzzzzzz-live-evening-20261007.conf' for u in SERVICES}
PROTECTED = ('goalvision-lab-weekly-stats.service', 'goalvision-admin-alerts.service',
             'goalvision-admin-autorepair.service', 'goalvision-lab-combo-discover.service',
             'goalvision-dixon-coles-research.service', 'goalvision-dixon-coles-forward.service')
PLAN_ASSET = 'app/adaptive_lab/calendar_plan_20261002.json'
FILES = ('app/adaptive_lab/daypart.py', 'app/adaptive_lab/quota.py', 'app/adaptive_lab/worker.py', 'app/football/client.py', 'app/lab_combo/publication_window.py', 'app/lab_v2_shadow/quota.py', 'app/live_lab/provider.py', 'app/live_lab/engine.py', 'app/live_lab/service.py', 'app/live_lab/runner.py', 'app/live_lab/presentation.py')
ADMIN_CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
ADMIN_DISABLED = Path('/var/lib/goalvision-admin-autorepair/DISABLED')
BUSY = {'active', 'activating', 'deactivating', 'reloading'}
ROUTE_KEYS = ('EnvironmentFiles', 'WorkingDirectory', 'DropInPaths')
INVARIANT_KEYS = ('WorkingDirectory', 'ExecStart', 'User', 'Group')
DRAIN_SECONDS = 180

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree(root):
    return {str(p.relative_to(root)): sha(p) for p in root.rglob('*') if p.suffix in {'.py', '.json'}}

def reject_symlinks(root):
    if root.is_symlink() or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('SYMLINK_REVIEW_REQUIRED')

def control(*args):
    return subprocess.run(['/usr/bin/systemctl', *args], check=True, capture_output=True,
                          text=True, timeout=15).stdout.strip()

def property_of(unit, key):
    return control('show', unit, '-p', key, '--value')

def routes(units):
    return {u: {k: property_of(u, k) for k in ROUTE_KEYS} for u in units}

def stable_commands(units):
    # ExecStart includes transient pid/start/exit data: compare the configured argv only.
    values = {}
    for unit in units:
        props = {k: property_of(unit, k) for k in INVARIANT_KEYS}
        if props['ExecStart'].count('{ path=') != 1 or ' ; ignore_errors=' not in props['ExecStart']:
            raise ValueError('UNREVIEWED_COMMAND_REPRESENTATION')
        props['ExecStart'] = props['ExecStart'].split(' ; ignore_errors=')[0]
        values[unit] = props
    return values

def base_environment(target):
    return ('PYTHONPATH=' + str(target / 'application') + '\n'
            'GOALVISION_LAB_ACCURACY_COMBOS=1\nGOALVISION_LAB_TODAY_ONLY=1\n'
            'GOALVISION_LAB_EARLY_COMBO_LOSS=1\nGOALVISION_LAB_SINGLE_MIN_ODDS_130=1\n'
            'GOALVISION_LAB_DEVIG_RESEARCH=1\nGOALVISION_LAB_CALIBRATION_READINESS=1\n'
            'GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130=1\nGOALVISION_COMBO_BOT_ROUTING=1\n'
            'GOALVISION_LAB_SETTLEMENT_REPLIES=1\nGOALVISION_LAB_SINGLE_MIN_ODDS_150=1\n'
            'GOALVISION_COMBO_CONSERVATIVE_AGREEMENT=1\nGOALVISION_COMBO_MARKET_PARALLEL=0\n'
            'GOALVISION_PRIVATE_SINGLE_170=1\nGOALVISION_COMBO_DOUBLE_170=1\n').encode()

def expected_route_sources(base_manifest, files):
    return {str(BASE / 'release.env'): {
        'environment_sha256': hashlib.sha256(base_environment(BASE)).hexdigest(),
        'manifest': dict(base_manifest)}}

def environment(target, rollback=False):
    if rollback:
        raise ValueError('ROLLBACK_NOT_PREPARED')
    return base_environment(target) + b'GOALVISION_LAB_EVENING_MODE=1\nGOALVISION_LIVE_API_FEED_QUOTES=1\n'


def dropin(target, rollback=False):
    env = target / ('rollback.env' if rollback else 'release.env')
    return ('[Service]\nEnvironmentFile=\nEnvironmentFile=' + str(env) + '\n').encode()

def disabled_worker():
    timer = 'goalvision-admin-autorepair.timer'
    worker = 'goalvision-admin-autorepair.service'
    if (property_of(timer, 'ActiveState') != 'inactive'
            or property_of(timer, 'UnitFileState') != 'disabled'
            or property_of(worker, 'ActiveState') != 'inactive'
            or property_of(worker, 'MainPID') != '0'):
        raise ValueError('ADMIN_CODEX_DISABLED_GUARD')

    # Root apply can additionally inspect the installed root-owned guard files.
    # A normal-user plan validates systemd only and reports this limitation.
    if os.geteuid() == 0:
        config = json.loads(ADMIN_CONFIG.read_text())
        if config.get('autorepair', {}).get('enabled') is not False or not ADMIN_DISABLED.is_file():
            raise ValueError('ADMIN_CODEX_ROOT_GUARD')

def atomic(path, data):
    if path.is_symlink():
        raise ValueError('SYMLINK_DESTINATION')
    fd, temporary = tempfile.mkstemp(prefix='.live-evening-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            os.fchmod(out.fileno(), 0o644)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

def validate(package):
    disabled_worker()
    reject_symlinks(package)
    meta = json.loads((package / 'metadata.json').read_text())
    if meta.get("runtime_import_smoke", {}).get("status") != "ISOLATED_LIVE_EVENING_IMPORT_PASS":
        raise ValueError("PACKAGE_IMPORT_PROOF_REQUIRED")
    commit = meta['source_commit']
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('INVALID_COMMIT')
    if set(meta['files']) != set(FILES) or sha(package / 'update.py') != meta['updater_sha256']:
        raise ValueError('PACKAGE_CONTRACT_MISMATCH')
    for name in FILES:
        if sha(package / 'overlay' / name) != meta['files'][name]:
            raise ValueError('PACKAGE_HASH_MISMATCH')
    reject_symlinks(BASE)
    if tree(BASE / 'application') != meta['base_manifest'] or (BASE / 'release.env').read_bytes() != base_environment(BASE):
        raise ValueError('BASE_SOURCE_OR_ENV_DRIFT')
    # Pin the installed evidence release, existing flags and frozen resource files.
    expected_sources = {str(p) for p in ROUTE_BASES.values()}
    if set(meta['route_sources']) != expected_sources:
        raise ValueError('ROUTE_SOURCE_SET_MISMATCH')
    if meta['route_sources'] != expected_route_sources(meta['base_manifest'], meta['files']):
        raise ValueError('ROUTE_SOURCE_CONTRACT_MISMATCH')
    for env_path, expected in meta['route_sources'].items():
        env = Path(env_path)
        app = env.parent / ('research' if env.name == 'research.env' else 'application')
        reject_symlinks(env.parent)
        if sha(env) != expected['environment_sha256'] or tree(app) != expected['manifest']:
            raise ValueError('ROLLBACK_SOURCE_DRIFT')
    if stable_commands(SERVICES) != {u: meta['expected_commands'][u] for u in SERVICES}:
        raise ValueError('PREPARED_CONFIGURATION_DRIFT')
    verify_protected_configuration(meta)
    for override in (*OVERRIDES.values(), DISCOVERY_OVERRIDE, LIVE_UNIT_PATH, LIVE_TIMER_PATH):
        if override.is_symlink() or override.parent.is_symlink():
            raise ValueError('OVERRIDE_SYMLINK')
    return meta, BASE.parent / ('goalvision-live-evening-' + commit[:7] + '-20261007')

def verify_routes(target=None, rollback=False):
    for unit, original in ROUTE_BASES.items():
        expected = str(target / ('rollback.env' if rollback else 'release.env')) if target else str(original)
        if property_of(unit, 'EnvironmentFiles') != expected + ' (ignore_errors=no)':
            raise ValueError('PREMATCH_ROUTE_MISMATCH:' + unit)

def verify_release(target, expected):
    reject_symlinks(target)
    if (tree(target / 'application') != expected
            or (target / 'release.env').read_bytes() != environment(target)
):
        raise ValueError('RELEASE_DRIFT')

def restore_timers(states):
    failures = []
    for timer, was_active in states.items():
        try:
            if was_active:
                control('start', timer)
            elif property_of(timer, 'ActiveState') != 'inactive':
                control('stop', timer)
            expected = 'active' if was_active else 'inactive'
            if property_of(timer, 'ActiveState') != expected:
                failures.append(timer)
        except BaseException:
            failures.append(timer)
    if failures:
        raise RuntimeError('TIMER_RESTORE_FAILED:' + ','.join(failures))

LIVE_SERVICE = 'goalvision-lab-live-evening.service'
LIVE_TIMER = 'goalvision-lab-live-evening.timer'
LIVE_UNIT_PATH = Path('/etc/systemd/system') / LIVE_SERVICE
LIVE_TIMER_PATH = Path('/etc/systemd/system') / LIVE_TIMER
DISCOVERY_TIMER = 'goalvision-lab-v2-discover.timer'
DISCOVERY_OVERRIDE = Path('/etc/systemd/system') / (DISCOVERY_TIMER + '.d') / 'zzzzzzzzzzzzzzzzzzzzzz-live-evening-20261007.conf'


def discovery_timer():
    return b'[Timer]\nOnCalendar=\nOnCalendar=*-*-* 10..17:00,30:00 Europe/Riga\nPersistent=false\n'


def live_service(target):
    return ("[Unit]\nDescription=GoalVision LIVE Lab evening discovery and ongoing results\nAfter=network-online.target\n"
            "[Service]\nType=oneshot\nUser=arvis\nGroup=arvis\nWorkingDirectory=/home/arvis/GoalVisionAI\n"
            "Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\nEnvironmentFile="+str(target/'release.env')+"\n"
            "ExecStart=/usr/bin/flock -n -E 75 /home/arvis/GoalVisionAI/var/adaptive_lab/live-evening.lock "
            "/home/arvis/GoalVisionAI/.venv/bin/python -P -m app.adaptive_lab.worker live-cycle "
            "--database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --enable-lab-automation --send\n"
            "SuccessExitStatus=75\nTimeoutStartSec=120\nNice=10\nCPUQuota=25%\n"
            "NoNewPrivileges=true\nPrivateTmp=true\n").encode()


def live_timer():
    # Timer wakes for results all day; the application performs zero HTTP when
    # outside 18–23 and no LIVE results remain. No catch-up/manual service start.
    return ("[Unit]\nDescription=GoalVision LIVE Lab demand and results timer\n"
            "[Timer]\nOnCalendar=*-*-* *:02/5:00 Europe/Riga\nAccuracySec=1s\nPersistent=false\n"
            "Unit="+LIVE_SERVICE+"\n[Install]\nWantedBy=timers.target\n").encode()


def configuration(target):
    return {**{path:dropin(target) for path in OVERRIDES.values()},
            DISCOVERY_OVERRIDE:discovery_timer(),LIVE_UNIT_PATH:live_service(target),LIVE_TIMER_PATH:live_timer()}


def verify_schedule(target):
    if any(not path.is_file() or path.is_symlink() or path.read_bytes()!=value
           for path,value in configuration(target).items()):
        raise ValueError('EVENING_CONFIGURATION_DRIFT')
    for unit,expected in ((DISCOVERY_TIMER,'10..17:00,30:00 Europe/Riga'),(LIVE_TIMER,'02/5:00 Europe/Riga')):
        calendar=property_of(unit,'TimersCalendar')
        if expected not in calendar or calendar.count('OnCalendar=')!=1:
            raise ValueError('EVENING_TIMER_ROUTE_MISMATCH:'+unit)
    if property_of(LIVE_SERVICE,'EnvironmentFiles')!=str(target/'release.env')+' (ignore_errors=no)':
        raise ValueError('LIVE_ENVIRONMENT_ROUTE_MISMATCH')
    if property_of(LIVE_SERVICE,'User')!='arvis':
        raise ValueError('LIVE_SERVICE_USER_MISMATCH')


def route(target):
    settings=configuration(target)
    previous={path:path.read_bytes() if path.exists() else None for path in settings}
    old_routes=routes(SERVICES)
    invariants=stable_commands(SERVICES+PROTECTED)
    protected=routes(PROTECTED)
    states={timer:property_of(timer,'ActiveState')=='active' for timer in TIMERS}
    changed=[]
    try:
        for timer in TIMERS:
            control('stop',timer)
        deadline=time.monotonic()+DRAIN_SECONDS
        while any(property_of(unit,'ActiveState') in BUSY for unit in SERVICES):
            if time.monotonic()>=deadline:
                raise TimeoutError('PREMATCH_RUNNING_RETRY_AFTER_COMPLETION')
            time.sleep(.2)
        if routes(SERVICES)!=old_routes or stable_commands(SERVICES+PROTECTED)!=invariants:
            raise ValueError('CONCURRENT_ROUTE_CHANGE')
        for path,value in settings.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.parent.is_symlink():
                raise ValueError('CONFIGURATION_PARENT_SYMLINK')
            changed.append(path)
            atomic(path,value)
        control('daemon-reload')
        verify_routes(target)
        verify_schedule(target)
        if stable_commands(SERVICES+PROTECTED)!=invariants or routes(PROTECTED)!=protected:
            raise ValueError('UNRELATED_CONFIGURATION_CHANGED')
        disabled_worker()
        restore_timers(states)
        control('enable','--now',LIVE_TIMER)
        if property_of(LIVE_TIMER,'ActiveState')!='active' or property_of(LIVE_TIMER,'UnitFileState')!='enabled':
            raise ValueError('LIVE_TIMER_ENABLE_FAILED')
    except BaseException:
        # Installation failure recovery only. No model rollback or historical writes.
        errors=[]
        if LIVE_TIMER_PATH in changed:
            try: control('disable','--now',LIVE_TIMER)
            except BaseException: errors.append('LIVE_TIMER_DISABLE')
        for timer in TIMERS:
            try: control('stop',timer)
            except BaseException: errors.append('TIMER_PAUSE')
        for path in reversed(changed):
            try:
                if previous[path] is None: path.unlink(missing_ok=True)
                else: atomic(path,previous[path])
            except BaseException: errors.append('CONFIG_RESTORE')
        try:
            control('daemon-reload')
            if routes(SERVICES)!=old_routes: errors.append('ROUTE_RESTORE')
        except BaseException: errors.append('RELOAD')
        try: restore_timers(states)
        except BaseException: errors.append('TIMER_RESTORE')
        if errors: raise RuntimeError('RECOVERY_REVIEW_REQUIRED:'+','.join(errors)) from None
        raise


def current_mode(target):
    settings=configuration(target)
    if not any(path.exists() for path in settings):
        verify_routes()
        if property_of(LIVE_SERVICE,'ActiveState') not in ('inactive',''):
            raise ValueError('UNREVIEWED_LIVE_SERVICE')
        return 'BASE'
    if all(path.is_file() and not path.is_symlink() and path.read_bytes()==value for path,value in settings.items()):
        verify_routes(target)
        verify_schedule(target)
        return 'ENABLED'
    raise ValueError('PARTIAL_OR_UNREVIEWED_OVERRIDE')


def apply(package):
    meta,target=validate(package)
    expected=dict(meta['base_manifest'],**meta['files'])
    reject_symlinks(target)
    mode=current_mode(target)
    if mode=='ENABLED':
        verify_release(target,expected)
        print('LIVE_EVENING_ALREADY_ENABLED')
        return
    if target.exists():
        verify_release(target,expected)
    else:
        stage=Path(tempfile.mkdtemp(prefix='.live-evening-',dir=BASE.parent))
        try:
            shutil.copytree(BASE/'application',stage/'application',ignore=shutil.ignore_patterns('__pycache__'))
            for name in FILES:
                destination=stage/'application'/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(package/'overlay'/name,destination)
            atomic(stage/'release.env',environment(target))
            atomic(stage/'LIVE_EVENING_DEPLOYMENT.json',(json.dumps(meta,sort_keys=True)+'\n').encode())
            reject_symlinks(stage)
            if tree(stage/'application')!=expected: raise ValueError('STAGE_HASH_MISMATCH')
            os.chmod(stage,0o755)
            os.rename(stage,target)
        finally:
            if stage.exists(): shutil.rmtree(stage)
    route(target)
    print('LAB_LIVE_EVENING_DEPLOYED')
    print('lab_release='+str(target))
    print('PREMATCH/SINGLE/COMBO discovery=10:00-18:00 Europe/Riga; results=24h.')
    print('LIVE Lab discovery=18:00-23:00 Riga; existing Lab destination; at most one pick per natural cycle.')
    print('LIVE API-Football feed quotes explicitly labeled; bookmaker unknown; quote freshness remains 20s.')
    print('Shared 7500/day and 300/min limits; dynamic PREMATCH result reserve; remaining quota available to LIVE.')
    print('No automatic training/promotion/rollback; PREMATCH champion and all odds/probability floors retained.')
    print('Official untouched; ADMIN Codex disabled. No manual cycle/provider call/test send.')


def verify_protected_configuration(meta):
    if (stable_commands(PROTECTED) != {u: meta['expected_commands'][u] for u in PROTECTED}
            or routes(PROTECTED) != meta['protected_routes']):
        raise ValueError('PREPARED_CONFIGURATION_DRIFT')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--accept-api-feed-quotes',action='store_true',
                        help='Explicitly accept labeled provider quotes with unknown bookmaker for LIVE Lab only')
    args=parser.parse_args()
    package=Path(__file__).resolve().parent
    if not args.apply:
        meta,target=validate(package)
        mode=current_mode(target)
        if mode!='BASE': verify_release(target,dict(meta['base_manifest'],**meta['files']))
        print('LIVE_EVENING_PLAN_VALIDATED='+str(target))
        print('current_mode='+mode+'; ADMIN_CODEX_SYSTEMD_DISABLED=PASS')
        print('LIVE_QUOTE_CONTRACT=API_FOOTBALL_FEED_UNKNOWN_BOOKMAKER; FRESHNESS_MAX=20s')
        print('ROOT_GUARD=PASS' if os.geteuid()==0 else 'ROOT_GUARD=CHECKED_AT_APPLY')
        return
    if not args.accept_api_feed_quotes:
        raise SystemExit('EXPLICIT_API_FEED_QUOTE_ACCEPTANCE_REQUIRED')
    if os.geteuid()!=0: raise SystemExit('ROOT_REQUIRED')
    def interrupted(signum,frame): raise KeyboardInterrupt('Interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    with open('/run/lock/goalvision-prematch-accuracy-combo.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        apply(package)


if __name__=='__main__':
    main()
