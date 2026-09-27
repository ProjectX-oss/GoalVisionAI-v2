#!/usr/bin/env python3
"""Five-service PREMATCH code/route controller. No application imports or transport."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterator

sys.dont_write_bytecode = True
MANIFEST_SHA = 'f24738b05fef5f71f3ebcaead3c791233d94fcc38cee21e96a59f2f23493fff2'
ARCHIVE_SHA = '024972a084a68966c535f73fd9c4307b075b917e9d1277f88103b5e3f9d3e517'
SOURCE = '557d5af2c05d78404b5e86368e72ec5671dcf737'
PACKAGE = Path('/home/arvis/goalvision-operations/prematch-quota-lock-hardening-package-20260927')
RELEASE = Path('/opt/goalvision-prematch-quota-557d5af2-f24738b05fef')
STATE = Path('/var/lib/goalvision-quota-deployment')
LOCK = Path('/run/lock/goalvision-prematch-v2-installer.lock')
GATE_NAME = '91-quota-deployment-fence.conf'
SERVICES = ('goalvision-lab-v2-discover.service', 'goalvision-lab-combo-settle.service',
            'goalvision-adaptive-learning-observer.service', 'goalvision-lab-weekly-stats.service',
            'goalvision-adaptive-learning.service')
ADMIN_CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
ADMIN_DB = Path('/var/lib/goalvision-admin-alerts/admin.sqlite')
SHADOW_PATH = '/home/arvis/GoalVisionAI/var/lab_v2/shadow.db'
SHADOW_CHECK = 'SHADOW_COMPATIBILITY_CHECK_V1'
SHADOW_NOTICE = 'Full physical integrity of the 11 GB shadow database was not established by this bounded deployment preflight.'
SHADOW_READS = (
    ("SELECT kind,identity,substr(document_json,1,256) FROM lab_v2_shadow_evidence WHERE kind>=? LIMIT 1", ('',)),
    ("SELECT cache_id,substr(payload_json,1,256) FROM lab_v2_provider_cache WHERE cache_id>=? LIMIT 1", ('',)),
    ("SELECT endpoint,query_fingerprint,expires_at_utc,retrieved_at_utc FROM lab_v2_provider_cache INDEXED BY lab_v2_provider_cache_lookup WHERE endpoint>=? LIMIT 1", ('',)),
    ("SELECT fixture_id,market,state,substr(document_json,1,256) FROM lab_v2_final_review_pending WHERE fixture_id>=? LIMIT 1", (0,)),
    ("SELECT identity,substr(document_json,1,256) FROM lab_v2_shadow_evidence INDEXED BY lab_v2_early_candidate_kickoff WHERE kind='candidate' AND json_extract(document_json,'$.stage')='EARLY_CANDIDATE' AND json_extract(document_json,'$.kickoff_utc')>=? LIMIT 1", ('',)),
)


def schema_fingerprint(db: sqlite3.Connection) -> str:
    """Pin exact DDL, including columns, constraints, indexes and triggers."""
    rows = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                      "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
    return digest(json.dumps(rows, separators=(',', ':')).encode())



class Blocked(RuntimeError):
    """Safe, fixed diagnostic code; never includes secret data or subprocess output."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Blocked(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> bytes:
    require(not path.is_symlink() and path.is_file(), 'FILE_MISSING_OR_SYMLINK:' + str(path))
    require(path.resolve() == path.absolute(), 'SYMLINK_PARENT:' + str(path))
    return path.read_bytes()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Fsync content and parent before returning; never follow a target symlink."""
    require(not path.is_symlink(), 'UNSAFE_WRITE_TARGET')
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    for directory in reversed(missing):
        fsync_dir(directory.parent)
    require(path.parent.resolve() == path.parent.absolute(), 'UNSAFE_WRITE_PARENT')
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            os.fchmod(handle.fileno(), mode)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        fsync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def remove(path: Path, expected: bytes) -> None:
    if path.exists() or path.is_symlink():
        require(read(path) == expected, 'REFUSE_REMOVE_CHANGED_FILE:' + str(path))
        path.unlink()
        fsync_dir(path.parent)


def run(args: list[str], timeout: float = 5) -> str:
    """Only callers' fixed local admin/read commands; redact stdout on failure."""
    try:
        result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout,
                                env={**os.environ, 'LC_ALL': 'C', 'SYSTEMD_COLORS': '0'})
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError) as error:
        raise Blocked('LOCAL_COMMAND_FAILED:' + Path(args[0]).name) from error


def normalize(key: str, value: str) -> str:
    if key == 'ExecStart':
        match = re.fullmatch(r'\{ path=[^;]+ ; argv\[\]=(.*?) ; ignore_errors=no ; .* \}', value)
        require(match is not None, 'UNREVIEWED_EXECSTART_SHAPE')
        return match.group(1)
    if key == 'Environment':
        return digest(value.encode())
    if key == 'TimersCalendar':
        return re.sub(r' ; next_elapse=[^}]*', '', value)
    return value


class Host:
    """Injectable filesystem/systemd boundary. Production CLI never exposes a fake root."""
    def __init__(self, root: Path = Path('/'), command: Callable[..., str] = run,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.root, self.command, self.monotonic, self.sleep = root, command, monotonic, sleep

    def path(self, path: str | Path) -> Path:
        return self.root / str(path).lstrip('/')

    def show(self, unit: str, keys: list[str]) -> dict[str, str]:
        raw = self.command(['/usr/bin/systemctl', 'show', unit, '--property=' + ','.join(keys)])
        values = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
        return {key: normalize(key, values.get(key, '')) for key in keys}

    def reload(self) -> None:
        self.command(['/usr/bin/systemctl', 'daemon-reload'])

    def no_reload_drift(self) -> None:
        names = self.command(['/usr/bin/systemctl', 'list-units', '--all', '--plain',
                              '--no-legend', '--type=service,timer'])
        units = [line.split()[0] for line in names.splitlines() if line.strip()]
        require(bool(units), 'UNIT_INVENTORY_UNAVAILABLE')
        raw = self.command(['/usr/bin/systemctl', 'show', *units, '--property=Id,NeedDaemonReload'])
        require('NeedDaemonReload=no' in raw and 'NeedDaemonReload=yes' not in raw,
                'NEED_DAEMON_RELOAD_DRIFT')

    @contextmanager
    def lock(self) -> Iterator[None]:
        path = self.path(LOCK)
        path.parent.mkdir(parents=True, exist_ok=True)
        require(not path.is_symlink(), 'UNSAFE_LOCK')
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise Blocked('DEPLOYMENT_LOCK_BUSY') from error
            yield

    @contextmanager
    def database(self, path: str | Path, seconds: float = 15,
                 max_steps: int | None = None) -> Iterator[sqlite3.Connection]:
        """Live SQLite read transaction, no migration, backup, restore or recovery."""
        target = self.path(path)
        require(target.is_file() and not target.is_symlink(), 'DATABASE_UNREADABLE')
        require(target.resolve() == target.absolute(), 'DATABASE_SYMLINK_PARENT')
        require(stat.S_ISREG(target.stat().st_mode) and target.stat().st_size >= 512,
                'DATABASE_SIZE_OR_TYPE')
        # DELETE-journal production only. Refuse recovery/sidecar creation on read.
        require(not any(Path(str(target) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')),
                'DATABASE_SIDECAR_REQUIRES_REVIEW')
        with target.open('rb') as handle:
            header = handle.read(100)
        require(len(header) == 100 and header[:16] == b'SQLite format 3\x00', 'DATABASE_INVALID_HEADER')
        require(header[18:20] == b'\x01\x01', 'DATABASE_MODE_REQUIRES_REVIEW')
        page_size = int.from_bytes(header[16:18], 'big')
        page_size = 65536 if page_size == 1 else page_size
        require(512 <= page_size <= 65536 and page_size & (page_size - 1) == 0
                and target.stat().st_size % page_size == 0, 'DATABASE_INVALID_SIZE')
        db = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True, timeout=1)
        deadline = self.monotonic() + seconds
        steps = 0
        def guard() -> int:
            nonlocal steps
            steps += 1000
            return int(self.monotonic() >= deadline or (max_steps is not None and steps >= max_steps))
        db.set_progress_handler(guard, 1000)
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA busy_timeout=1000')
            db.execute('BEGIN')
            yield db
            require(self.monotonic() < deadline, 'DATABASE_READ_DEADLINE')
        finally:
            db.close()


class Controller:
    """Deterministic two-lineage transaction with independently callable recovery."""
    def __init__(self, host: Host, package: Path, contract: dict[str, Any],
                 hook: Callable[[str], None] = lambda _: None) -> None:
        self.h, self.package, self.c, self.hook = host, package, contract, hook
        self.manifest: dict[str, Any] = {}
        self.last_check: dict[str, Any] = {}

    def verify_package(self) -> None:
        require(digest(read(self.package / 'manifest.json')) == MANIFEST_SHA, 'FROZEN_MANIFEST_MISMATCH')
        m = json.loads(read(self.package / 'manifest.json'))
        require(m['application_commit'] == SOURCE and self.c['package_manifest_sha256'] == MANIFEST_SHA,
                'SOURCE_IDENTITY_MISMATCH')
        require(tuple(r['service'] for r in m['configuration']) == SERVICES, 'SERVICE_SCOPE_MISMATCH')
        require(self.c['routes'] == m['configuration'], 'FROZEN_ROUTES_MISMATCH')
        verify_tree(self.package, {**m['files'], 'manifest.json': MANIFEST_SHA})
        archive = self.package.with_suffix('.tar.gz')
        if archive.exists():
            require(digest(read(archive)) == ARCHIVE_SHA, 'ARCHIVE_IDENTITY_MISMATCH')
        self.manifest = m
        require(self.c.get('release_root') == str(RELEASE), 'UNAPPROVED_RELEASE_ROOT')
        require(self.c.get('route_relocation_approved') is True, 'RELOCATED_ROUTE_REVIEW_REQUIRED')
        for row in self.c['routes']:
            self.route_bytes(row, 'after')
        for name in ('release.env', 'research.env'):
            self.relocated(name)
        proof = self.c['shadow_migration_proof']
        require(proof['migration_required'] is False, 'SHADOW_MIGRATION_REQUIRED')
        require(set(proof['repository_sha256']) == {
            label + '/app/lab_v2_shadow/repository.py' for label in ('application', 'research')},
            'SHADOW_MIGRATION_PROOF_INCOMPLETE')
        for name, sha in proof['repository_sha256'].items():
            label, relative = name.split('/', 1)
            require(m['files'].get(name) == sha == self.c['releases'][label]['files'].get(relative),
                    'SHADOW_REPOSITORY_CONTRACT_MISMATCH')
        require(proof['ddl_schema_sha256'] == self.c['databases']['shadow']['schema_sha256'],
                'SHADOW_MIGRATION_REQUIRED')

    def relocated(self, name: str) -> bytes:
        """Only the reviewed frozen-package prefix may change, byte for byte."""
        require(self.c.get('release_root') == str(RELEASE), 'UNAPPROVED_RELEASE_ROOT')
        old = read(self.package / name)
        require(str(PACKAGE).encode() in old, 'FROZEN_ROUTE_PREFIX_MISSING')
        new = old.replace(str(PACKAGE).encode(), str(RELEASE).encode())
        expected = self.c['relocated_files'][name]
        require(new == base64.b64decode(expected['bytes_b64'], validate=True)
                and digest(new) == expected['sha256'], 'RELOCATED_BYTES_MISMATCH')
        return new

    def route_bytes(self, row: dict[str, Any], state: str) -> bytes | None:
        name = row['before' if state == 'before' else 'after']
        if name is None:
            return None
        content = read(self.package / name)
        if state == 'after':
            # Only relocation. The standalone operations manifest pins these derived bytes.
            content = self.relocated(name)
        return content

    def gate(self, service: str) -> Path:
        return self.h.path('/etc/systemd/system/' + service + '.d/' + GATE_NAME)

    def gate_bytes(self) -> bytes:
        return ('[Unit]\nConditionPathExists=!' + str(STATE / 'blocked') + '\n').encode()

    def journal(self) -> dict[str, Any] | None:
        path = self.h.path(STATE / 'transaction.json')
        return json.loads(read(path)) if path.exists() else None

    def record(self, transaction: dict[str, Any], phase: str) -> None:
        transaction['phase'] = phase
        transaction['events'].append(phase)
        atomic(self.h.path(STATE / 'transaction.json'),
               (json.dumps(transaction, sort_keys=True, indent=2) + '\n').encode(), 0o600)
        self.hook('journal:' + phase)

    def route_state(self) -> str:
        states = []
        for row in self.c['routes']:
            target = self.h.path(row['target'])
            actual = read(target) if target.exists() or target.is_symlink() else None
            matched = [s for s in ('before', 'after') if actual == self.route_bytes(row, s)]
            require(len(matched) == 1, 'CURRENT_ROUTE_DRIFT:' + row['service'])
            states.append(matched[0])
        require(len(set(states)) == 1, 'MIXED_ROUTES_RECOVERY_REQUIRED')
        return states[0]

    def configuration(self, state: str, fenced: bool = False) -> dict[str, Any]:
        """Compare pinned bytes, loaded properties and all applicable drop-in directories."""
        for path, expected in self.c['static_files'].items():
            require(digest(read(self.h.path(path))) == expected, 'STATIC_FILE_DRIFT:' + path)
        require(self.route_state() == state, 'UNEXPECTED_ROUTE_STATE')
        for directory, expected in self.c['configuration_directories'].items():
            names = set(expected)
            for row in self.c['routes']:
                if str(Path(row['target']).parent) == directory:
                    if state == 'after':
                        names.add(Path(row['target']).name)
                    if fenced:
                        names.add(GATE_NAME)
            path = self.h.path(directory)
            actual = {p.name for p in path.iterdir()} if path.exists() else set()
            require(actual == names, 'UNEXPECTED_DROPIN:' + directory)
        loaded = {}
        for service in SERVICES:
            expected = dict(self.c['services'][service])
            row = next(r for r in self.c['routes'] if r['service'] == service)
            if state == 'after':
                env = 'research.env' if service == SERVICES[-1] else 'release.env'
                expected['EnvironmentFiles'] = str(RELEASE / env) + ' (ignore_errors=no)'
                expected['DropInPaths'] = row['target']
            if fenced:
                require(read(self.gate(service)) == self.gate_bytes(), 'FENCE_BYTES_MISMATCH')
                expected['DropInPaths'] = ' '.join(filter(None, [expected['DropInPaths'],
                    '/etc/systemd/system/' + service + '.d/' + GATE_NAME]))
            actual = self.h.show(service, list(expected) + ['NeedDaemonReload', 'LoadState'])
            require(actual.pop('NeedDaemonReload') == 'no', 'NEED_DAEMON_RELOAD_DRIFT')
            require(actual.pop('LoadState') == 'loaded', 'UNIT_NOT_LOADED')
            require(actual == expected, 'LOADED_ROUTE_MISMATCH:' + service)
            loaded[service] = {'environment': actual['EnvironmentFiles'], 'exec_start': actual['ExecStart']}
        timers = self.timers()
        command = loaded[SERVICES[0]]['exec_start'].split()
        return {'routes': loaded, 'timers': timers, 'capabilities': {
            'new_picks': '--send' in command, 'publication': '--send' in command,
            'observe': '--football-context-root' in command and '--football-context-registry' in command,
            'labels': '--label-v2-selections' in command,
            'telegram_and_api_configuration': 'EXACT_HASH_UNCHANGED',
            'quota_max_calls': command[command.index('--max-calls') + 1] if '--max-calls' in command else None,
            'settlement_reserve': command[command.index('--settlement-reserve') + 1] if '--settlement-reserve' in command else None}}

    def timers(self) -> dict[str, Any]:
        result = {}
        for unit, expected in self.c['timers'].items():
            actual = self.h.show(unit, list(expected) + ['NeedDaemonReload'])
            require(actual.pop('NeedDaemonReload') == 'no', 'TIMER_RELOAD_DRIFT')
            require(actual == expected, 'TIMER_STATE_OR_SCHEDULE_DRIFT:' + unit)
            result[unit] = actual
        return result

    def sources(self, state: str) -> None:
        for label, info in self.c['releases'].items():
            root = self.h.path(info['before'])
            # Check full source bytes against git-derived, reviewed hashes, including extra files.
            verify_tree(root / 'app', {k[4:]: v for k, v in info['files'].items() if k.startswith('app/')},
                        allow_bytecode=True)
            require(digest(read(root / 'requirements.txt')) == info['files']['requirements.txt'],
                    'OLD_REQUIREMENTS_DRIFT')
            head = self.h.command(['/usr/bin/git', '-c', 'safe.directory=' + str(root),
                                   '-C', str(root), 'rev-parse', 'HEAD'])
            require(head == info['commit'], 'OLD_RELEASE_IDENTITY_DRIFT')
        if state == 'after':
            self.verify_staged()

    def shadow_compatibility(self, info: dict[str, Any]) -> dict[str, Any]:
        """Bounded compatibility only; physical integrity is deliberately unestablished."""
        require(info['path'] == SHADOW_PATH, 'UNEXPECTED_SHADOW_PATH')
        require(info['check_version'] == SHADOW_CHECK, 'UNKNOWN_SHADOW_CHECK_VERSION')
        start = self.h.monotonic()
        with self.h.database(info['path'], seconds=3, max_steps=100000) as db:
            require(db.execute('PRAGMA user_version').fetchone() == (info['user_version'],),
                    'SHADOW_UNKNOWN_SCHEMA_VERSION')
            require(db.execute('PRAGMA application_id').fetchone() == (0,), 'SHADOW_UNKNOWN_APPLICATION')
            require(schema_fingerprint(db) == info['schema_sha256'], 'SCHEMA_OR_MIGRATION_REQUIRED:shadow')
            plans = []
            for query, parameters in SHADOW_READS:
                plan = [row[3] for row in db.execute('EXPLAIN QUERY PLAN ' + query, parameters)]
                require(len(plan) == 1 and plan[0].startswith('SEARCH ') and 'INDEX' in plan[0],
                        'SHADOW_UNBOUNDED_READ_PLAN')
                db.execute(query, parameters).fetchall()
                plans.append(plan[0])
        return {'check': SHADOW_CHECK, 'status': 'COMPATIBLE', 'schema': 'EXACT_MATCH',
                'schema_sha256': info['schema_sha256'], 'user_version': info['user_version'],
                'migration_required': False, 'access': 'mode=ro/query_only',
                'size_bytes': self.h.path(info['path']).stat().st_size,
                'elapsed_seconds': round(self.h.monotonic() - start, 4),
                'deadline_seconds': 3, 'busy_timeout_ms': 1000, 'max_vm_steps': 100000,
                'indexed_read_plans': plans,
                'FULL_SHADOW_INTEGRITY': 'NOT_COMPLETED_DUE_TO_SIZE_AND_BOUND',
                'physical_integrity_notice': SHADOW_NOTICE}

    def databases(self, integrity: bool = True) -> dict[str, Any]:
        result = {}
        for label, info in self.c['databases'].items():
            if label == 'shadow':
                result[label] = self.shadow_compatibility(info)
                continue
            with self.h.database(info['path']) as db:
                if integrity:
                    require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'DATABASE_INTEGRITY:' + label)
                    require(not db.execute('PRAGMA foreign_key_check').fetchmany(1), 'DATABASE_FOREIGN_KEYS:' + label)
                require(schema_fingerprint(db) == info['schema_sha256'], 'SCHEMA_OR_MIGRATION_REQUIRED:' + label)
                if label == 'audit':
                    require(db.execute('SELECT max(version) FROM adaptive_schema').fetchone() == (5,),
                            'MIGRATION_REQUIRED')
                result[label] = {'integrity': 'ok' if integrity else 'VERIFIED_BEFORE_FENCE',
                                 'schema': 'EXACT_MATCH', 'access': 'mode=ro/query_only'}
        return result

    def admin(self) -> dict[str, Any]:
        """Fresh readback every time; pending diagnostics are allowed with sender disabled."""
        try:
            config = json.loads(read(self.h.path(ADMIN_CONFIG)))
            require(config.get('sender', {}).get('enabled') is False, 'ADMIN_SENDER_ENABLED')
            with self.h.database(ADMIN_DB) as db:
                attempts = db.execute('SELECT count(*) FROM attempts').fetchone()[0]
                sent = db.execute("SELECT count(*) FROM outbox WHERE state='SENT'").fetchone()[0]
                pending = db.execute("SELECT count(*) FROM outbox WHERE state!='SENT'").fetchone()[0]
        except PermissionError as error:
            raise Blocked('ADMIN_PRIVILEGED_CHECK_REQUIRES_OPERATOR') from error
        return {'sender_enabled': False, 'delivery_attempt_rows': attempts, 'sent_outbox': sent,
                'pending_outbox': pending, 'fresh_readback': True, 'access': 'mode=ro/query_only'}

    def disk(self) -> None:
        needed = sum(p.stat().st_size for p in self.package.rglob('*') if p.is_file()) * 2 + 64 * 1024 * 1024
        for path in (self.h.path(RELEASE).parent, self.h.path(STATE).parent, self.h.path('/etc/systemd/system')):
            while not path.exists():
                path = path.parent
            require(shutil.disk_usage(path).free >= needed, 'INSUFFICIENT_DISK_SPACE')

    def check(self, state: str | None = None, fenced: bool = False) -> dict[str, Any]:
        """Strictly read-only, including on failures; never creates a lock/journal."""
        self.verify_package()
        require(self.c.get('route_relocation_approved') is True, 'RELOCATED_ROUTE_REVIEW_REQUIRED')
        if not fenced:
            journal = self.journal()
            require(journal is None or journal['phase'] == 'DONE', 'RECOVERY_REQUIRED')
            require(not self.h.path(STATE / 'blocked').exists(), 'RECOVERY_FENCE_PRESENT')
        self.h.no_reload_drift()
        state = state or self.route_state()
        result = self.configuration(state, fenced)
        self.sources(state)
        result['databases'] = self.databases(integrity=not fenced)
        self.disk()
        self.last_check = result
        try:
            result['admin'] = self.admin()
        except (Blocked, OSError, ValueError, sqlite3.Error) as error:
            result['admin'] = {'status': 'BLOCKED', 'reason': safe_error(error)}
            raise
        result.update(status='CHECK_PASSED', route_state=state, package_manifest=MANIFEST_SHA,
                      api_calls=0, telegram_sends=0, database_writes=0)
        return result

    def stage_contents(self) -> dict[str, bytes]:
        data = {name: read(self.package / name) for name in self.manifest['files']
                if name.startswith(('application/', 'research/'))}
        for name in ('release.env', 'research.env'):
            data[name] = self.relocated(name)
        return data

    def verify_staged(self) -> None:
        data = self.stage_contents()
        root = self.h.path(RELEASE)
        verify_tree(root, {k: digest(v) for k, v in data.items()})
        for path in [root, *root.rglob('*')]:
            st = path.stat()
            require(st.st_uid == 0 if self.h.root == Path('/') else True, 'RELEASE_NOT_ROOT_OWNED')
            require(st.st_mode & 0o222 == 0, 'WRITABLE_RELEASE')
        if self.h.root == Path('/'):
            for parent in root.parents:
                require(parent.stat().st_uid == 0 and not parent.stat().st_mode & 0o022,
                        'UNTRUSTED_RELEASE_PARENT')

    def stage(self) -> None:
        """Stage/fsync before fence. Never mutate a pre-existing release tree."""
        root = self.h.path(RELEASE)
        if root.exists() or root.is_symlink():
            self.verify_staged()
            return
        data = self.stage_contents()
        root.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.quota-stage-', dir=root.parent))
        for name, content in data.items():
            atomic(stage / name, content, 0o600)
        verify_tree(stage, {k: digest(v) for k, v in data.items()})
        for path in stage.rglob('*'):
            if path.is_file():
                path.chmod(0o444)
                with path.open('rb') as handle:
                    os.fsync(handle.fileno())
        for directory in sorted([p for p in stage.rglob('*') if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
            directory.chmod(0o555)
            fsync_dir(directory)
        stage.chmod(0o555)
        fsync_dir(stage)
        require(not root.exists(), 'RELEASE_APPEARED_DURING_STAGE')
        os.rename(stage, root)
        fsync_dir(root.parent)
        self.verify_staged()

    def fence(self) -> None:
        atomic(self.h.path(STATE / 'blocked'), (MANIFEST_SHA + '\n').encode(), 0o600)
        for service in SERVICES:
            path = self.gate(service)
            if path.exists():
                require(read(path) == self.gate_bytes(), 'FOREIGN_FENCE')
            else:
                atomic(path, self.gate_bytes())
            self.hook('fence:' + service)
        self.h.reload()

    def drain(self, deadline: float | None = None) -> None:
        deadline = deadline if deadline is not None else self.h.monotonic() + 60
        while True:
            idle = True
            for service in SERVICES:
                remaining = deadline - self.h.monotonic()
                require(remaining > 0, 'DRAIN_TIMEOUT_60_SECONDS')
                raw = self.h.command(['/usr/bin/systemctl', 'show', service,
                    '--property=ActiveState,SubState,MainPID,ControlPID,Job'], timeout=min(5, remaining))
                values = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
                idle &= (values.get('ActiveState') in {'inactive', 'failed'}
                         and values.get('MainPID') == '0' and values.get('ControlPID') == '0'
                         and values.get('Job', '') == '')
            if idle:
                return
            remaining = deadline - self.h.monotonic()
            require(remaining > 0, 'DRAIN_TIMEOUT_60_SECONDS')
            self.h.sleep(min(0.25, remaining))

    def replace_routes(self, target_state: str) -> None:
        for index, row in enumerate(self.c['routes']):
            path = self.h.path(row['target'])
            current = read(path) if path.exists() else None
            allowed = [self.route_bytes(row, s) for s in ('before', 'after')]
            require(current in allowed, 'REFUSE_OVERWRITE_ROUTE_DRIFT')
            target = self.route_bytes(row, target_state)
            if target is None:
                remove(path, self.route_bytes(row, 'after'))
            elif current != target:
                atomic(path, target)
            self.hook('route:' + str(index + 1))

    def unfence(self, state: str) -> None:
        # Verify homogeneous routes before making the condition true. Subsequent
        # cleanup failure must NOT roll back underneath a newly scheduled worker.
        self.configuration(state, fenced=True)
        remove(self.h.path(STATE / 'blocked'), (MANIFEST_SHA + '\n').encode())
        self.hook('unfence:marker')
        for service in SERVICES:
            remove(self.gate(service), self.gate_bytes())
        self.h.reload()
        self.configuration(state)

    def execute(self, action: str) -> dict[str, Any]:
        """Worker entry; launched under a systemd recovery supervisor in production."""
        require(action in {'install', 'rollback'}, 'INVALID_ACTION')
        with self.h.lock():
            origin, target = ('before', 'after') if action == 'install' else ('after', 'before')
            self.check(origin)
            if action == 'install':
                require(self.c.get('route_relocation_approved') is True, 'RELOCATED_ROUTE_REVIEW_REQUIRED')
                self.stage()
            previous = self.journal()
            tx = {'manifest': MANIFEST_SHA, 'origin': origin, 'target': target, 'events': [],
                  'previous': previous, 'origin_bytes_b64': {r['service']: (base64.b64encode(self.route_bytes(r, origin)).decode()
                      if self.route_bytes(r, origin) is not None else None) for r in self.c['routes']},
                  'before_sha256': {r['service']: r['before_sha256'] for r in self.c['routes']}}
            try:
                self.record(tx, 'PREPARED')
                self.fence()
                self.record(tx, 'FENCED')
                drain_deadline = self.h.monotonic() + 60
                self.drain(drain_deadline)
                self.check(origin, fenced=True)
                self.verify_staged()
                # Check idle again immediately before mutation after potentially slow reads.
                self.drain(drain_deadline)
                self.record(tx, 'CHANGING')
                self.replace_routes(target)
                self.h.reload()  # exactly one reload for the route transaction
                self.configuration(target, fenced=True)
                self.admin()
                self.record(tx, 'COMMITTED')
                self.unfence(target)
                self.record(tx, 'DONE')
            except BaseException:
                try:
                    self.recover_locked()
                except BaseException as error:
                    raise Blocked('RECOVERY_UNPROVEN:FIVE_SERVICES_FENCED:' + str(STATE / 'transaction.json')) from error
                raise
        return {'status': 'INSTALLED_WAITING_FOR_SCHEDULED_EVIDENCE' if action == 'install' else 'ROLLED_BACK',
                'api_calls': 0, 'telegram_sends': 0, 'database_writes': 0, 'workers_killed': 0}

    def recover_locked(self) -> None:
        """Resume durable transaction; never unprotect unverified mixed routes."""
        tx = self.journal()
        if not tx or tx['phase'] == 'DONE':
            return
        require(tx['manifest'] == MANIFEST_SHA, 'FOREIGN_RECOVERY_JOURNAL')
        self.verify_package()
        if tx['phase'] == 'COMMITTED':
            # Route state was proven before the durable commit decision. Some gates
            # may already be removed. Reinserting conditions here could skip timers,
            # but cannot kill work; never restore origin after the commit decision.
            self.fence()
            self.configuration(tx['target'], fenced=True)
            self.unfence(tx['target'])
        elif tx['phase'] in {'PREPARED', 'FENCED'}:
            # No route write was authorized. Do not wait a second 60s on timeout.
            self.fence()
            self.configuration(tx['origin'], fenced=True)
            tx['target'] = tx['origin']
            self.record(tx, 'COMMITTED')
            self.unfence(tx['origin'])
        else:
            self.fence()
            self.drain()
            self.replace_routes(tx['origin'])
            self.h.reload()
            self.configuration(tx['origin'], fenced=True)
            tx['target'] = tx['origin']
            self.record(tx, 'COMMITTED')
            self.unfence(tx['origin'])
        self.record(tx, 'DONE')

    def recover(self) -> None:
        with self.h.lock():
            self.recover_locked()

    def recovery_summary(self) -> dict[str, Any]:
        """Expose the durable decision and fence state without payload/secret values."""
        tx = self.journal()
        return {'phase': tx['phase'] if tx else 'NO_TRANSACTION',
                'origin': tx.get('origin') if tx else None, 'target': tx.get('target') if tx else None,
                'blocked_marker': self.h.path(STATE / 'blocked').exists(),
                'fence_files': [s for s in SERVICES if self.gate(s).exists()],
                'journal': str(STATE / 'transaction.json')}

    def status(self) -> dict[str, Any]:
        """Report bounded read-only health; scheduled provenance is not inferred."""
        result: dict[str, Any] = {'status': 'READ_ONLY_STATUS', 'api_calls': 0, 'telegram_sends': 0}
        try:
            result['preflight'] = self.check()
        except (Blocked, OSError, sqlite3.Error) as error:
            result['preflight'] = {'status': 'BLOCKED', 'reason': safe_error(error)}
        result['transaction'] = self.recovery_summary()
        for name, inspect in [('admin', self.admin), ('timers', self.timers), ('databases', self.databases)]:
            try:
                result[name] = inspect()
            except (Blocked, OSError, sqlite3.Error) as error:
                result[name] = {'status': 'BLOCKED', 'reason': safe_error(error)}
        result['services'] = {s: self.h.show(s, ['ActiveState', 'SubState', 'Result', 'ExecMainStatus',
                                               'InvocationID', 'ExecMainStartTimestamp', 'ExecMainExitTimestamp'])
                              for s in SERVICES}
        with self.h.database(self.c['databases']['audit']['path']) as db:
            row = db.execute('SELECT document FROM cycle_health ORDER BY rowid DESC LIMIT 1').fetchone()
            health = json.loads(row[0]) if row else {}
            result['latest_discovery_health'] = {k: health[k] for k in (
                'cycle_id', 'started_at', 'completed_at', 'result', 'provider_calls',
                'published', 'evidence_at') if k in health}
        with self.h.database(self.c['databases']['ledger']['path']) as db:
            result['publication_delivery'] = dict(db.execute("SELECT kind,count(*) FROM evidence "
                "WHERE kind IN ('single_prediction','receipt','claim','delivery_unknown') GROUP BY kind").fetchall())
            row = db.execute("SELECT kind,identity FROM evidence WHERE kind IN ('receipt','claim','delivery_unknown') "
                             "ORDER BY rowid DESC LIMIT 1").fetchone()
            result['latest_delivery'] = dict(zip(('kind', 'identity'), row)) if row else None
        try:
            raw = self.h.command(['/usr/bin/journalctl', '--no-pager', '-o', 'json', '-n', '2000',
                                  '-u', SERVICES[0]], timeout=5)
            rows = [json.loads(line) for line in raw.splitlines() if line]
            result['contention_in_visible_last_2000_journal_entries'] = {
                code: sum(code in str(r.get('MESSAGE', '')) for r in rows)
                for code in ('QUOTA_DB_CONTENTION_RETRY', 'QUOTA_DB_CONTENTION_EXHAUSTED')}
            result['journal_coverage'] = 'BOUNDED_VISIBLE_ENTRIES_ONLY'
        except (Blocked, ValueError):
            result['contention_in_visible_last_2000_journal_entries'] = 'NOT_OBSERVABLE'
        result['discovery_timer'] = self.h.show(SERVICES[0].replace('.service', '.timer'),
            ['ActiveState', 'UnitFileState', 'LastTriggerUSec', 'NextElapseUSecRealtime'])
        result['scheduled_cycle_provenance'] = 'TIMER_TRIGGER_AND_SERVICE_TIMESTAMPS_PROVIDED; EXACT_JOIN_NOT_PERSISTED'
        result['production_validation'] = 'NOT_ASSERTED'
        return result


def verify_tree(root: Path, expected: dict[str, str], allow_bytecode: bool = False) -> None:
    require(root.is_dir() and not root.is_symlink(), 'TREE_MISSING_OR_SYMLINK:' + str(root))
    actual = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'TREE_SYMLINK')
        if path.is_dir():
            continue
        require(path.is_file(), 'TREE_SPECIAL_FILE')
        name = str(path.relative_to(root))
        if allow_bytecode and '__pycache__' in path.parts and path.suffix == '.pyc':
            continue
        actual.add(name)
    require(actual == set(expected), 'TREE_FILE_SET_MISMATCH:' + str(root))
    for name, expected_sha in expected.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'UNSAFE_MANIFEST_PATH')
        require(digest(read(root / name)) == expected_sha, 'PAYLOAD_HASH_MISMATCH:' + name)


def safe_error(error: BaseException) -> str:
    return str(error) if isinstance(error, Blocked) else type(error).__name__


def load_contract(root: Path, expected: str) -> dict[str, Any]:
    data = read(root / 'host-contract.json')
    require(digest(data) == expected, 'OPERATOR_CONTRACT_PIN_MISMATCH')
    checksums = json.loads(read(root / 'controller-checksums.json'))
    for name, expected_sha in checksums.items():
        require(name in {'controller.py', 'host-contract.json'}, 'UNEXPECTED_CONTROLLER_FILE')
        require(digest(read(root / name)) == expected_sha, 'CONTROLLER_FILE_MISMATCH')
    require(set(checksums) == {'controller.py', 'host-contract.json'}, 'CONTROLLER_MANIFEST_INCOMPLETE')
    contract = json.loads(data)
    require(contract.get('controller_sha256') == digest(read(root / 'controller.py')),
            'PINNED_CONTROLLER_MISMATCH')
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'status', 'rollback', '_worker', '_recover'])
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--confirm')
    parser.add_argument('--operation', choices=['install', 'rollback'])
    parser.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    controller = None
    try:
        contract = load_contract(root, args.contract_sha256)
        frozen = root / 'frozen' if (root / 'frozen').is_dir() else PACKAGE
        controller = Controller(Host(), frozen, contract)
        if args.action in {'check', 'status'}:
            output = controller.check() if args.action == 'check' else controller.status()
        else:
            operation = args.operation if args.action.startswith('_') else args.action
            require(operation in {'install', 'rollback'}, 'OPERATION_REQUIRED')
            expected = operation.upper() + ':' + MANIFEST_SHA + ':' + args.contract_sha256
            require(args.confirm == expected, 'EXACT_CONFIRMATION_REQUIRED')
            require(os.geteuid() == 0, 'ROOT_REQUIRED')
            if args.action == '_worker':
                require(bool(os.environ.get('INVOCATION_ID')), 'SYSTEMD_SUPERVISOR_REQUIRED')
                output = controller.execute(operation)
            elif args.action == '_recover':
                require(bool(os.environ.get('INVOCATION_ID')), 'SYSTEMD_SUPERVISOR_REQUIRED')
                controller.recover()
                output = {'status': 'RECOVERY_COMPLETED_OR_NOT_NEEDED'}
            else:
                # Read-only preflight happens before starting even the controller service.
                if not args.recover:
                    controller.check('before' if operation == 'install' else 'after')
                else:
                    require(operation == 'rollback', 'RECOVERY_USES_ROLLBACK_COMMAND')
                    controller.verify_package()
                # Recovery code is secured before systemd gets any executable reference.
                secure = Path('/var/lib/goalvision-quota-controller-' + args.contract_sha256[:16])
                with controller.h.lock():
                    if not secure.exists():
                        secure.mkdir(mode=0o700)
                        shutil.copytree(controller.package, secure / 'frozen')
                        archived = controller.package.with_suffix('.tar.gz')
                        if archived.exists():
                            shutil.copyfile(archived, secure / 'frozen.tar.gz')
                        for name in ('controller.py', 'host-contract.json', 'controller-checksums.json'):
                            atomic(secure / name, read(root / name), 0o400)
                        for item in (secure / 'frozen').rglob('*'):
                            item.chmod(0o500 if item.is_dir() else 0o400)
                        (secure / 'frozen').chmod(0o500)
                        if (secure / 'frozen.tar.gz').exists():
                            (secure / 'frozen.tar.gz').chmod(0o400)
                        secure.chmod(0o500)
                    require(secure.stat().st_uid == 0 and secure.stat().st_mode & 0o022 == 0,
                            'UNSAFE_RECOVERY_CODE')
                    for name in ('controller.py', 'host-contract.json', 'controller-checksums.json'):
                        require(read(secure / name) == read(root / name), 'RECOVERY_CODE_DRIFT')
                Controller(Host(), secure / 'frozen', contract).verify_package()
                common = ['--operation', operation, '--contract-sha256', args.contract_sha256,
                          '--confirm', args.confirm]
                command = ['/usr/bin/python3', '-I', '-B', str(secure / 'controller.py')]
                recovery = ' '.join(command + ['_recover'] + common)
                output_text = run(['/usr/bin/systemd-run', '--unit=goalvision-quota-deployment-controller',
                    '--wait', '--pipe', '--collect', '--service-type=exec',
                    '--property=TimeoutStopSec=180s', '--property=RuntimeMaxSec=300s',
                    '--property=ExecStopPost=' + recovery,
                    *command, '_recover' if args.recover else '_worker', *common], timeout=600)
                print(output_text)
                return
        print(json.dumps(output, sort_keys=True, indent=2))
    except (Blocked, OSError, ValueError, sqlite3.Error) as error:
        recovery = {'journal': str(STATE / 'transaction.json'), 'phase': 'UNREADABLE'}
        if controller is not None:
            try:
                recovery = controller.recovery_summary()
            except (Blocked, OSError, ValueError):
                pass
        print(json.dumps({'status': 'BLOCKED', 'reason': safe_error(error), 'recovery_state': recovery,
                          'preflight_findings': controller.last_check if controller else {}}))
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
