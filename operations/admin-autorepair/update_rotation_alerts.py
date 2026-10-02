"""Monitor-only historical rotation reminder fix; no incident deletion or manual scan."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal

OVERRIDE = Path('/etc/systemd/system/goalvision-admin-alerts.service.d/zzzzzz-admin-rotation-alerts-20261002.conf')
CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
MARKER = Path('/var/lib/goalvision-admin-autorepair/DISABLED')
WORKER = 'goalvision-admin-autorepair.service'
TIMER = 'goalvision-admin-autorepair.timer'
BASE = Path('/opt/goalvision-admin-alerts-releases/admin-monitor-compat-a28f2a6-20261002')
MODULES = ('app/admin_alerts/model.py', 'app/admin_alerts/sources.py',
           'app/admin_alerts/store.py', 'app/admin_alerts/delivery.py')
INCIDENT = 'c7df1386cf441d629cbc83b9'



def require_codex_disabled(module) -> None:
    if CONFIG.is_symlink() or MARKER.is_symlink():
        raise ValueError('AUTOREPAIR_STATE_SYMLINK')
    config = json.loads(CONFIG.read_text())
    if (config.get('autorepair', {}).get('enabled') is not False
            or not MARKER.is_file()
            or module.prop(TIMER, 'ActiveState') != 'inactive'
            or module.prop(TIMER, 'UnitFileState') not in ('disabled', 'masked')
            or module.prop(WORKER, 'ActiveState') not in ('inactive', 'failed')
            or module.prop(WORKER, 'MainPID') != '0'):
        raise ValueError('ADMIN_CODEX_NOT_DISABLED')


def configure(module):
    module.SPECS = {'monitor': dict(module.SPECS['monitor'], override=OVERRIDE,
        base=BASE, route_base=BASE, modules=MODULES)}
    module.PROTECTED = (*module.PROTECTED, WORKER)
    module.RELEASE_PREFIX = 'admin-rotation-alerts'
    module.STATUS_PREFIX = 'ADMIN_ROTATION_ALERTS'
    module.UNCHANGED_MESSAGE = 'Acknowledged rotation gaps no longer repeat without new evidence; history retained. ADMIN Codex remains DISABLED. PREMATCH and worker routes unchanged. No manual cycle or test send.'
    module.post_route = lambda targets: require_codex_disabled(module)
    return module


def engine(package: Path):
    meta = json.loads((package/'metadata.json').read_text())
    helper = package/'update_compat.py'
    for path, key in ((package/'update.py','updater_sha256'), (helper,'helper_sha256')):
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != meta[key]:
            raise ValueError('PACKAGE_CODE_HASH_MISMATCH')
    spec = importlib.util.spec_from_file_location('admin_monitor_transaction', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return configure(module)


def incident_diagnostic(path: Path = Path('/var/lib/goalvision-admin-alerts/admin.sqlite')) -> dict:
    """Read exact incident and delivery counts only, never bodies or credentials."""
    import sqlite3
    import time
    connection = None
    try:
        if path.is_symlink():
            raise ValueError("SYMLINK_DATABASE")
        connection = sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True, timeout=.2)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        deadline = time.monotonic()+2
        connection.set_progress_handler(lambda: int(time.monotonic()>deadline), 1000)
        row = connection.execute(
            "SELECT id,service,rule,object_id,state,count,first_seen,last_seen,last_sent,generation,episode,"
            "CASE WHEN length(evidence)<=131072 AND json_valid(evidence) THEN evidence END AS evidence "
            "FROM incidents WHERE id=?", (INCIDENT,)).fetchone()
        if row is None:
            return {"mode":"READ_ONLY","found":False,"id":INCIDENT}
        event = json.loads(row["evidence"] or "{}")
        reason = event.get("facts",{}).get("reason")
        reasons = {"ROTATED_INODE_LOST","FILE_TRUNCATED","FILE_REWRITTEN"}
        states = {"OPEN","REPEATED","ESCALATED","PENDING","RECOVERED","INVALIDATED"}
        result = {"mode":"READ_ONLY","found":True,"id":INCIDENT,
            "identity_verified":(row["service"]=="monitor" and row["rule"]=="MONITORING_COVERAGE_DEGRADED"
                and row["object_id"]=="stdout-rotation"),
            "state":row["state"] if row["state"] in states else "OTHER",
            "reason":reason if isinstance(reason,str) and reason in reasons else "OTHER_OR_UNAVAILABLE",
            "source":"stdout" if event.get("source")=="stdout" else "OTHER"}
        result.update({k:row[k] for k in ("count","first_seen","last_seen","last_sent","generation","episode")})
        safe_states = {"PENDING","SENT","UNCERTAIN","ATTEMPTING","PERMANENT","EXHAUSTED","SUPERSEDED"}
        counts = {}
        for state,count,ack in connection.execute(
                "SELECT state,count(*),sum(acknowledged) FROM outbox WHERE incident=? GROUP BY state",(INCIDENT,)):
            counts[state if state in safe_states else "OTHER"] = {"rows":count,"acknowledged":ack}
        result["notification_counts"]=counts
        return result
    except (OSError,ValueError,TypeError,AttributeError,sqlite3.Error):
        return {"mode":"READ_ONLY","status":"READ_UNAVAILABLE","id":INCIDENT}
    finally:
        if connection is not None:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--diagnostic', action='store_true')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    module = engine(package)
    if args.diagnostic:
        print('ADMIN_ROTATION_INCIDENT='+json.dumps(incident_diagnostic(),sort_keys=True))
        return
    if not args.apply:
        _, targets = module.validate(package)
        print('PLAN_VALIDATED='+json.dumps({k:str(v) for k,v in targets.items()},sort_keys=True))
        return
    if os.geteuid() != 0:
        raise SystemExit('ROOT_REQUIRED')
    def interrupted(signum, frame):
        raise KeyboardInterrupt('OPERATOR_INTERRUPTED')
    signal.signal(signal.SIGTERM, interrupted)
    with open('/run/lock/goalvision-admin-status-update.lock','a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        require_codex_disabled(module)
        module.apply(package, args.rollback)
        require_codex_disabled(module)
        print('ADMIN_CODEX_STILL_DISABLED')
        print('ADMIN_ROTATION_INCIDENT='+json.dumps(incident_diagnostic(),sort_keys=True))


if __name__ == '__main__':
    main()
