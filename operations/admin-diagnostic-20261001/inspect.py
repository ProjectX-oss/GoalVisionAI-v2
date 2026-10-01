"""Read-only, bounded diagnostics for two operator-reported ADMIN incidents."""
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

INCIDENTS = ('5551793c5b77956d7db042f5', '421c8977ff14a1c4c99ebc27')
JOB = '48cab99a1c6591528428427c'
ROW_KEYS = ('id', 'service', 'rule', 'object_id', 'state', 'count',
            'first_seen', 'last_seen', 'invocation', 'episode', 'generation')
EVENT_KEYS = ('service', 'rule', 'object_id', 'source', 'observed', 'healthy',
              'invocation', 'cycle', 'facts')
STATUS_KEYS = ('job_id', 'state', 'outcome', 'failure', 'source_commit',
               'started_at', 'finished_at', 'elapsed_seconds', 'changed_files')
BUNDLE_KEYS = ('job_id', 'incident_id', 'service', 'rule', 'mode', 'target',
               'created_at', 'invocation', 'facts')


def safe(value, depth=0):
    """Retain machine codes/counts only; never export free text or credentials."""
    if depth > 6:
        return 'OMITTED'
    if value is None or type(value) in (bool, int, float):
        return value
    if isinstance(value, str):
        return value if (re.fullmatch(r'[a-zA-Z0-9_.-]{0,128}', value)
                         and 'token' not in value.lower()) else 'REDACTED'
    if isinstance(value, dict):
        return {key: safe(item, depth+1) for key, item in list(value.items())[:50]
                if re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', str(key))
                and not any(word in str(key).lower() for word in ('token', 'secret', 'password', 'credential', 'api_key', 'authorization', 'headers'))}
    if isinstance(value, list):
        return [safe(item, depth+1) for item in value[:30]]
    return 'OMITTED'


def select(value, keys):
    return safe({key: value[key] for key in keys if key in value})


def read_object(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024*1024:
            raise ValueError('DOCUMENT_BOUND')
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError('DOCUMENT_TYPE')
    return value


def collect(admin, spool):
    result = {'mode': 'READ_ONLY', 'incidents': []}
    database = admin / 'admin.sqlite'
    if database.is_symlink():
        raise ValueError('DATABASE_SYMLINK')
    connection = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True,
                                 timeout=.2, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        for identity in INCIDENTS:
            row = connection.execute('SELECT * FROM incidents WHERE id=?', (identity,)).fetchone()
            if row is None:
                result['incidents'].append({'id': identity, 'found': False})
                continue
            record = select(dict(row), ROW_KEYS)
            record['evidence'] = select(json.loads(row['evidence']), EVENT_KEYS)
            result['incidents'].append(record)
    finally:
        connection.close()
    for label, path, keys in (
        ('source_access', admin/'incident-report.json', ('source_access',)),
        ('worker_status', spool/'status'/(JOB+'.json'), STATUS_KEYS),
        ('worker_incident', spool/'done'/(JOB+'.json'), BUNDLE_KEYS),
    ):
        try:
            result[label] = select(read_object(path), keys)
        except (OSError, ValueError) as exc:
            result[label] = {'unavailable': type(exc).__name__}
    result['worker_job_directory_exists'] = (spool/'jobs'/JOB).is_dir()
    return result


if __name__ == '__main__':
    try:
        value = collect(Path('/var/lib/goalvision-admin-alerts'),
                        Path('/var/lib/goalvision-admin-autorepair'))
        print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'mode': 'READ_ONLY', 'error': type(exc).__name__}))
        raise SystemExit(1)
