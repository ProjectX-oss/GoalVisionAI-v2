"""Reviewed, explicit root installer/rollback. Default command only prints a plan.

No PREMATCH control, credential access, database rollback, or in-place source edit.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import sqlite3
import subprocess
import tempfile

SPOOL = Path('/var/lib/goalvision-admin-autorepair')
ADMIN_CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
ADMIN_STATE = Path('/var/lib/goalvision-admin-alerts')
ADMIN_RELEASES = Path('/opt/goalvision-admin-alerts-releases')
WORKER_RELEASES = Path('/opt/goalvision-admin-autorepair-releases')
SOURCE_RELEASES = Path('/opt/goalvision-admin-autorepair-sources')
WORKER_CONFIG = Path('/etc/goalvision-admin-autorepair.json')
OVERRIDE = Path('/etc/systemd/system/goalvision-admin-alerts.service.d/40-autorepair.conf')
UNIT_ROOT = Path('/etc/systemd/system')
WORKER_LINK = Path('/opt/goalvision-admin-autorepair')
UNITS = ('goalvision-admin-autorepair.service', 'goalvision-admin-autorepair.timer')
TRANSACTION = Path('/opt/goalvision-admin-autorepair-install-v1.json')


def systemctl(*args: str) -> subprocess.CompletedProcess:
    """The only permitted service operations name ADMIN units explicitly."""
    allowed = {'goalvision-admin-alerts.timer', 'goalvision-admin-alerts.service', *UNITS}
    if any(arg.endswith(('.service', '.timer')) and arg not in allowed for arg in args):
        raise ValueError('NON_ADMIN_UNIT_FORBIDDEN')
    return subprocess.run(['/usr/bin/systemctl', *args], check=True, stdout=subprocess.PIPE)


def write(path: Path, content: str, mode: int = 0o644, gid: int = 0) -> None:
    """Atomic root-owned installation; never use existing symlink destinations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('SYMLINK_DESTINATION')
    fd, name = tempfile.mkstemp(prefix='.install-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            os.fchmod(handle.fileno(), mode)
            os.fchown(handle.fileno(), 0, gid)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def stage(source: Path, destination: Path, runner: Path) -> None:
    """Ship only the independent ADMIN modules; no application config or secrets."""
    destination.mkdir(parents=True)
    for package in ('admin_alerts', 'admin_autorepair'):
        target = destination/'app'/package
        target.mkdir(parents=True)
        for path in sorted((source/'app'/package).glob('*.py')):
            if path.is_symlink():
                raise ValueError('SOURCE_SYMLINK')
            shutil.copyfile(path, target/path.name)
    (destination/'app'/'__init__.py').write_text('')
    shutil.copyfile(runner, destination/'run.py')
    manifest = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(destination.rglob('*.py'))}
    write(destination/'manifest.json', json.dumps(manifest, sort_keys=True, indent=2)+'\n')
    for path in destination.rglob('*'):
        os.chmod(path, 0o755 if path.is_dir() else 0o644)


def snapshot(source: Path, destination: Path) -> None:
    """Root-owned bare snapshot pinned to the reviewed worktree HEAD.

    Linked Git worktrees expose .git as a pointer file, which is not a robust
    local-clone source under a root installer. Resolve the shared common Git
    directory explicitly, clone only committed repository data from there, then
    repoint snapshot HEAD to the exact reviewed worktree commit.
    """
    if not source.is_absolute() or not source.is_dir() or destination.exists():
        raise ValueError('INVALID_SOURCE_REPO')
    source = source.resolve()
    env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
    base=['git','-c','safe.directory='+str(source),'-c','core.hooksPath=/dev/null',
          '-c','protocol.allow=never','-c','protocol.file.allow=always','-C',str(source)]
    commit = subprocess.check_output([*base,'rev-parse','--verify','HEAD'], env=env).decode().strip()
    common_raw = subprocess.check_output([*base,'rev-parse','--git-common-dir'], env=env).decode().strip()
    common = Path(common_raw)
    if not common.is_absolute():
        common = (source/common).resolve()
    if (not common.is_dir() or len(commit) not in (40,64)
            or any(char not in '0123456789abcdef' for char in commit)):
        raise ValueError('INVALID_SOURCE_REPO')
    clone = ['git','-c','safe.directory='+str(common),'-c','core.hooksPath=/dev/null',
             '-c','protocol.allow=never','-c','protocol.file.allow=always',
             'clone','--bare','--no-local',str(common),str(destination)]
    try:
        result = subprocess.run(clone, check=False, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True)
        if result.returncode:
            detail = ' '.join((result.stderr or '').strip().splitlines())[:500] or 'NO_STDERR'
            raise ValueError('SOURCE_SNAPSHOT_CLONE_FAILED:'+detail)
        subprocess.run(['git','--git-dir='+str(destination),'remote','remove','origin'],
                       check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        branch='refs/heads/goalvision-reviewed-source'
        subprocess.run(['git','--git-dir='+str(destination),'update-ref',branch,commit],
                       check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        subprocess.run(['git','--git-dir='+str(destination),'symbolic-ref','HEAD',branch],
                       check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        actual = subprocess.check_output(['git','--git-dir='+str(destination),'rev-parse','HEAD'],
                                         env=env).decode().strip()
        if actual != commit:
            raise ValueError('SOURCE_SNAPSHOT_COMMIT_MISMATCH')
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    for path in (destination, *destination.rglob('*')):
        os.chmod(path, 0o755 if path.is_dir() else 0o644)


def rollback() -> None:
    """Keep SQLite/spool/history and releases. Restore only this install's files."""
    transaction = json.loads(TRANSACTION.read_text())
    if transaction.get('rolled_back'):
        return
    if (UNIT_ROOT/'goalvision-admin-autorepair.timer').exists():
        systemctl('disable', '--now', 'goalvision-admin-autorepair.timer')
    if (UNIT_ROOT/'goalvision-admin-autorepair.service').exists():
        systemctl('stop', 'goalvision-admin-autorepair.service')
    systemctl('stop', 'goalvision-admin-alerts.timer')
    # Do not kill an ADMIN send. Wait for the existing serialized scan to finish.
    drain_admin()
    write(ADMIN_CONFIG, transaction['admin_config'], 0o640, grp.getgrnam('goalvision-admin-alerts').gr_gid)
    OVERRIDE.unlink(missing_ok=True)
    WORKER_CONFIG.unlink(missing_ok=True)
    for name in UNITS:
        (UNIT_ROOT/name).unlink(missing_ok=True)
    link = WORKER_LINK
    if link.is_symlink() and str(link.resolve()) == transaction['worker_release']:
        link.unlink()
    systemctl('daemon-reload')
    if transaction['admin_timer_active']:
        systemctl('start','goalvision-admin-alerts.timer')
    transaction['rolled_back'] = True
    write(TRANSACTION, json.dumps(transaction, sort_keys=True, indent=2)+'\n', 0o600)


def drain_admin() -> None:
    import time
    for _ in range(60):
        result = subprocess.run(['/usr/bin/systemctl','is-active','goalvision-admin-alerts.service'],
                                stdout=subprocess.PIPE, check=False)
        if result.stdout.strip() in (b'inactive', b'failed'):
            return
        time.sleep(1)
    raise ValueError('ADMIN_DRAIN_TIMEOUT')


def verify_empty_spool() -> None:
    """Reject any pending work, including partial files and symlink directories."""
    for name in ('queue', 'running'):
        path = SPOOL/name
        if path.is_symlink() or not path.is_dir() or any(path.iterdir()):
            raise ValueError('ACTIVATION_SPOOL_NOT_EMPTY')


def baseline_scan(admin_release: Path) -> None:
    """Create and verify activation while both timers and the worker are stopped.

    Use the routed release, normal ADMIN identity/config/state and no sender.
    Inspect SQLite read-only; never repair or reset existing activation history.
    """
    verify_empty_spool()
    database = ADMIN_STATE/'admin.sqlite'
    if database.is_symlink() or not database.is_file():
        raise ValueError('ACTIVATION_ADMIN_STORE_REQUIRED')
    uri = database.as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        has_jobs = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='repair_jobs'").fetchone()
        previous_jobs = set(db.execute('SELECT id FROM repair_jobs')) if has_jobs else set()
    result = subprocess.run(['/usr/sbin/runuser', '-u', 'goalvision-admin-alerts', '--',
        '/usr/bin/python3', '-I', str(admin_release/'run.py'),
        '--config', str(ADMIN_CONFIG), '--state', str(ADMIN_STATE), '--no-send'],
        cwd=admin_release, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
        check=True, timeout=60, stdout=subprocess.PIPE)
    report = json.loads(result.stdout)
    if report.get('no_send') is not True or report.get('telegram_sends') != 0:
        raise ValueError('ACTIVATION_SCAN_NOT_COMPLETED')
    with closing(sqlite3.connect(uri, uri=True)) as db:
        if not db.execute('SELECT 1 FROM repair_activation WHERE id=1').fetchone():
            raise ValueError('ACTIVATION_BASELINE_MISSING')
        # Stronger than checking only baseline members: no new reservation at all
        # may appear during activation, even if its physical job has disappeared.
        if set(db.execute('SELECT id FROM repair_jobs')) != previous_jobs:
            raise ValueError('ACTIVATION_CREATED_REPAIR_JOBS')
        if db.execute('''SELECT 1 FROM repair_jobs j JOIN repair_exclusions x
            ON x.incident=j.incident AND x.episode=j.episode
            WHERE x.reason='ACTIVATION_BASELINE' LIMIT 1''').fetchone():
            raise ValueError('ACTIVATION_BASELINE_HAS_REPAIR_JOBS')
        if db.execute('''SELECT 1 FROM incidents i
            WHERE state IN ('PENDING','OPEN','REPEATED','ESCALATED')
            AND NOT EXISTS (SELECT 1 FROM repair_exclusions x
                WHERE x.incident=i.id AND x.episode=i.episode) LIMIT 1''').fetchone():
            raise ValueError('ACTIVATION_EPISODE_NOT_EXCLUDED')
    verify_empty_spool()


def install(args: argparse.Namespace) -> None:
    source = args.source.resolve()
    version = args.release
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', version):
        raise ValueError('INVALID_RELEASE')
    account = pwd.getpwnam('arvis')
    group = grp.getgrnam('goalvision-admin-alerts')
    admin_release = ADMIN_RELEASES/version
    worker_release = WORKER_RELEASES/version
    sources = SOURCE_RELEASES/version
    destinations = (TRANSACTION, WORKER_CONFIG, OVERRIDE, admin_release, worker_release, sources,
                    WORKER_LINK, *(UNIT_ROOT/n for n in UNITS))
    if any(path.exists() or path.is_symlink() for path in destinations):
        raise ValueError('EXISTING_INSTALL_REQUIRES_REVIEW')
    admin_config_text = ADMIN_CONFIG.read_text()  # Token path only; never open the token.
    admin_config = json.loads(admin_config_text)
    active = subprocess.run(['/usr/bin/systemctl','is-active','--quiet','goalvision-admin-alerts.timer'],check=False).returncode == 0
    # Prepare all release files while ADMIN/PREMATCH continue running. Until the
    # transaction file exists these paths belong only to this attempt, so clean
    # them if preparation fails instead of leaving a non-retryable half-release.
    prepared = (admin_release, worker_release, sources)
    try:
        stage(source, admin_release, source/'operations/admin-alerts/run.py')
        stage(source, worker_release, source/'operations/admin-autorepair/run.py')
        sources.mkdir(parents=True)
        snapshot(args.admin_source, sources/'ADMIN.git')
        snapshot(args.prematch_source, sources/'PREMATCH.git')
    except BaseException:
        for path in reversed(prepared):
            if path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.exists():
                shutil.rmtree(path)
        raise
    for path in (SPOOL, *(SPOOL/name for name in ('queue','running','status','jobs','done'))):
        if path.is_symlink():
            raise ValueError('SPOOL_SYMLINK')
        path.mkdir(exist_ok=True)
        os.chown(path, account.pw_uid, group.gr_gid)
        os.chmod(path, 0o2770)
    config = {'source_repos': {'ADMIN':str(sources/'ADMIN.git'), 'PREMATCH':str(sources/'PREMATCH.git')},
              'spool':str(SPOOL), 'codex':'/home/arvis/.local/bin/codex',
              'timeout_seconds':2700, 'heartbeat_seconds':30}
    transaction = {'admin_config':admin_config_text, 'admin_timer_active':active,
                   'worker_release':str(worker_release), 'admin_release':str(admin_release)}
    write(TRANSACTION,json.dumps(transaction,sort_keys=True,indent=2)+'\n',0o600)
    systemctl('stop','goalvision-admin-alerts.timer')
    try:
        drain_admin()
        write(WORKER_CONFIG,json.dumps(config,sort_keys=True,indent=2)+'\n',0o640,group.gr_gid)
        for name in UNITS:
            write(UNIT_ROOT/name, (source/'operations/admin-autorepair'/name).read_text())
        WORKER_LINK.symlink_to(worker_release)
        write(OVERRIDE, '[Service]\nWorkingDirectory='+str(admin_release)+'\nExecStart=\n'
              'ExecStart=/usr/bin/python3 -I '+str(admin_release)+'/run.py --config '+str(ADMIN_CONFIG)+'\n'
              'ReadWritePaths='+str(SPOOL)+'\n')
        admin_config['autorepair']={'enabled':bool(args.enable_autorepair),'spool':str(SPOOL)}
        write(ADMIN_CONFIG,json.dumps(admin_config,indent=2)+'\n',0o640,group.gr_gid)
        systemctl('daemon-reload')
        if args.enable_autorepair:
            systemctl('disable', '--now', 'goalvision-admin-autorepair.timer')
            systemctl('stop', 'goalvision-admin-autorepair.service')
            baseline_scan(admin_release)
            systemctl('enable','--now','goalvision-admin-autorepair.timer')
    except BaseException:
        # Also cover a partially successful enable. Keep ADMIN stopped so a
        # failed baseline cannot create work before explicit rollback/review.
        if (UNIT_ROOT/'goalvision-admin-autorepair.timer').exists():
            systemctl('disable', '--now', 'goalvision-admin-autorepair.timer')
        if (UNIT_ROOT/'goalvision-admin-autorepair.service').exists():
            systemctl('stop', 'goalvision-admin-autorepair.service')
        raise
    else:
        if active:
            systemctl('start','goalvision-admin-alerts.timer')


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--release',default='autorepair-v1-20260930')
    parser.add_argument('--admin-source',type=Path)
    parser.add_argument('--prematch-source',type=Path)
    parser.add_argument('--enable-autorepair',action='store_true')
    parser.add_argument('--rollback',action='store_true')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        print('PLAN ONLY: versioned ADMIN/worker releases, bare source snapshots, shared spool, ADMIN override; no PREMATCH changes.')
        return 0
    if os.geteuid()!=0:
        raise SystemExit('Explicit root operator session required; installer never escalates itself.')
    if not args.rollback and (not args.admin_source or not args.prematch_source):
        raise SystemExit('Both reviewed local source repos are required.')
    with open('/run/lock/goalvision-admin-autorepair-install.lock','a') as handle:
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        rollback() if args.rollback else install(args)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
