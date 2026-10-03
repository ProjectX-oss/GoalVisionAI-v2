"""Pinned operator-only installation of a separate, offline research timer."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import shutil
import sqlite3
import subprocess
import tempfile

BASE = Path("/opt/goalvision-prematch-single-floor-150-e1263e7-20261003")
BASE_ENV_SHA256 = "365272111a6ad43dd11cb9f554f179b3dddc809ba9ce6253448ec61028fc73d2"
STATE = Path("/var/lib/goalvision-dixon-coles")
SEED = Path("/home/arvis/goalvision-worktrees/dixon-coles-research-20261003/var/dixon_coles_forward.db")
INSTALL_LOCK = Path("/run/lock/goalvision-dixon-coles-install.lock")
SYSTEM = Path("/etc/systemd/system")
SERVICE = "goalvision-dixon-coles-research.service"
TIMER = SERVICE.replace(".service", ".timer")
PRODUCTION = ("goalvision-lab-v2-discover.service", "goalvision-adaptive-learning-observer.service",
              "goalvision-lab-combo-settle.service", "goalvision-adaptive-learning.service")
PROTECTED = ("goalvision-lab-weekly-stats.service", "goalvision-admin-alerts.service",
             "goalvision-admin-autorepair.service", "goalvision-lab-combo-discover.service")
PYTHON = "/home/arvis/GoalVisionAI/.venv/bin/python"
PLAN = "app/dixon_coles_research/plan_20261003.json"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe(path: Path) -> None:
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("SYMLINK_REVIEW_REQUIRED")

def tree(root: Path) -> dict:
    safe(root)
    output = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("SYMLINK_REVIEW_REQUIRED")
        if path.is_file() and (path.suffix == ".py" or path.name in
                              ("calendar_plan_20261002.json", "plan_20261003.json")):
            output[path.relative_to(root).as_posix()] = sha(path)
    return output

def control(*args: str) -> str:
    return subprocess.run(["/usr/bin/systemctl", *args], check=True,
                          capture_output=True, text=True, timeout=15).stdout.strip()

def prop(unit: str, key: str) -> str:
    return control("show", unit, "-p", key, "--value")

def routes() -> dict:
    output = {}
    for unit in PRODUCTION + PROTECTED:
        values = {key: prop(unit, key) for key in
                  ("EnvironmentFiles", "WorkingDirectory", "DropInPaths", "User", "Group", "ExecStart")}
        if values["ExecStart"].count("{ path=") != 1 or " ; ignore_errors=" not in values["ExecStart"]:
            raise ValueError("UNREVIEWED_COMMAND")
        values["ExecStart"] = values["ExecStart"].split(" ; ignore_errors=")[0]
        output[unit] = values
    return output

def disabled_admin() -> None:
    unit = "goalvision-admin-autorepair"
    if (prop(unit+".timer", "ActiveState") != "inactive"
            or prop(unit+".timer", "UnitFileState") != "disabled"
            or prop(unit+".service", "ActiveState") != "inactive"
            or prop(unit+".service", "MainPID") != "0"):
        raise ValueError("ADMIN_CODEX_DISABLED_GUARD")
    if os.geteuid() == 0:
        config = json.loads(Path("/etc/goalvision-admin-alerts/admin-alerts.json").read_text())
        if config.get("autorepair", {}).get("enabled") is not False or not Path(
                "/var/lib/goalvision-admin-autorepair/DISABLED").is_file():
            raise ValueError("ADMIN_CODEX_ROOT_GUARD")

def records(path: Path) -> dict:
    safe(path)
    with sqlite3.connect(path.absolute().as_uri()+"?mode=ro", uri=True, timeout=.1) as db:
        db.execute("PRAGMA query_only=ON")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != {"dc_research_records"}:
            raise ValueError("DEDICATED_RESEARCH_DATABASE_REQUIRED")
        rows = db.execute("SELECT kind,identity,document FROM dc_research_records ORDER BY kind,identity LIMIT 50001").fetchall()
    if len(rows) > 50000:
        raise ValueError("RESEARCH_CAPACITY")
    return {json.dumps([kind, identity]): hashlib.sha256(document.encode()).hexdigest()
            for kind, identity, document in rows}

def seed_database(source: Path, destination: Path, expected: dict) -> None:
    """SQLite consistent backup; reruns preserve every later append-only record."""
    safe(destination)
    if destination.exists():
        actual = records(destination)
        if not expected.items() <= actual.items():
            raise ValueError("EXISTING_RESEARCH_HISTORY_CONFLICT")
        return
    if records(source) != expected:
        raise ValueError("SEED_DRIFT")
    temporary = destination.with_suffix(".seed-tmp")
    safe(temporary)
    if temporary.exists():
        raise ValueError("INCOMPLETE_SEED_REVIEW_REQUIRED")
    try:
        with sqlite3.connect(source.absolute().as_uri()+"?mode=ro", uri=True, timeout=.1) as src:
            src.execute("PRAGMA query_only=ON")
            with sqlite3.connect(temporary) as dst:
                src.backup(dst, pages=128)
        if records(temporary) != expected:
            raise ValueError("SEED_COPY_MISMATCH")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

def units(target: Path) -> dict:
    sources = Path("/home/arvis/GoalVisionAI/var")
    command = (f"{PYTHON} -B -m app.dixon_coles_research.worker"
               f" --shadow-database {sources}/lab_v2/shadow.db"
               f" --audit-database {sources}/adaptive_lab/audit.db"
               f" --ledger-database {sources}/lab_combo/ledger.db"
               f" --research-database {STATE}/research.db --limit 12")
    service = f"""[Unit]
Description=GoalVision isolated Dixon-Coles research (no publication)
[Service]
Type=oneshot
User=arvis
Group=arvis
WorkingDirectory={target}/application
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart={command}
UMask=0077
Nice=10
CPUQuota=25%
CPUWeight=10
IOWeight=10
IOSchedulingClass=idle
MemoryMax=256M
TasksMax=16
TimeoutStartSec=50
TimeoutStopSec=5
KillMode=control-group
Restart=no
NoNewPrivileges=true
PrivateTmp=true
PrivateNetwork=true
RestrictAddressFamilies=AF_UNIX
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={STATE}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
"""
    timer = f"""[Unit]
Description=GoalVision research after the natural observer, no catch-up
[Timer]
OnCalendar=*-*-* *:10,40:30 Europe/Riga
AccuracySec=1s
RandomizedDelaySec=0
Persistent=false
Unit={SERVICE}
[Install]
WantedBy=timers.target
"""
    return {SERVICE: service.encode(), TIMER: timer.encode()}

def atomic(path: Path, data: bytes) -> None:
    safe(path)
    fd, name = tempfile.mkstemp(prefix=".dc-research-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), 0o644)
            out.write(data); out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def validate(package: Path, *, rollback: bool = False) -> tuple[dict, Path]:
    safe(package)
    meta = json.loads((package/"metadata.json").read_text())
    commit = meta["source_commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("INVALID_SOURCE_COMMIT")
    if sha(package/"update.py") != meta["updater_sha256"]:
        raise ValueError("UPDATER_DRIFT")
    for name in meta["application"]:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not name.startswith("app/"):
            raise ValueError("INVALID_MANIFEST_PATH")
    if tree(package/"application") != meta["application"]:
        raise ValueError("PACKAGE_APPLICATION_DRIFT")
    if not rollback:
        if (tree(BASE/"application") != meta["base_manifest"] or sha(BASE/"release.env") != meta["environment_sha256"]
                or meta["environment_sha256"] != BASE_ENV_SHA256):
            raise ValueError("PREMATCH_SOURCE_DRIFT")
        observed = routes()
        if observed != meta["routes"]:
            raise ValueError("PRODUCTION_ROUTE_DRIFT")
        for unit in PRODUCTION:
            if observed[unit]["EnvironmentFiles"] != str(BASE/"release.env")+" (ignore_errors=no)":
                raise ValueError("PREMATCH_RELEASE_MISMATCH")
        disabled_admin()
    target = Path("/opt")/("goalvision-dixon-coles-"+commit[:7]+"-20261003")
    safe(target); safe(STATE)
    if not rollback and target.exists() and tree(target/"application") != meta["application"]:
        raise ValueError("RESEARCH_RELEASE_DRIFT")
    for unit, contents in units(target).items():
        path = SYSTEM/unit
        safe(path)
        if path.exists() and path.read_bytes() != contents:
            raise ValueError("EXISTING_RESEARCH_UNIT_CONFLICT")
        if prop(unit, "DropInPaths"):
            raise ValueError("UNREVIEWED_RESEARCH_OVERRIDE")
        fragment = prop(unit, "FragmentPath")
        if fragment and fragment != str(path):
            raise ValueError("UNREVIEWED_RESEARCH_UNIT")
    if not rollback:
        if (STATE/"research.db").exists():
            if not meta["seed_records"].items() <= records(STATE/"research.db").items():
                raise ValueError("EXISTING_RESEARCH_HISTORY_CONFLICT")
        elif records(SEED) != meta["seed_records"]:
            raise ValueError("SEED_DRIFT")
    return meta, target

def activate(target: Path) -> None:
    """Only this new timer is changed. Any activation failure leaves it disabled."""
    try:
        for unit, contents in units(target).items():
            path = SYSTEM/unit
            if not path.exists():
                atomic(path, contents)
        control("daemon-reload")
        control("enable", "--now", TIMER)
        if prop(TIMER, "ActiveState") != "active" or prop(TIMER, "UnitFileState") != "enabled":
            raise ValueError("RESEARCH_TIMER_NOT_ACTIVE")
    except BaseException:
        # Preserve release/database, disable only this research automation.
        control("disable", "--now", TIMER)
        control("stop", SERVICE)
        raise

def apply(package: Path, *, rollback: bool = False) -> None:
    if os.geteuid() != 0:
        raise ValueError("OPERATOR_SUDO_REQUIRED")
    lock_path = INSTALL_LOCK
    safe(lock_path)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        meta, target = validate(package, rollback=rollback)
        if rollback:
            control("disable", "--now", TIMER)
            control("stop", SERVICE)
            print("DIXON_COLES_RESEARCH_PAUSED; history retained; production unchanged")
            return
        if not target.exists():
            temporary = target.with_name(target.name+".preparing")
            safe(temporary)
            if temporary.exists():
                raise ValueError("INCOMPLETE_RELEASE_REVIEW_REQUIRED")
            temporary.mkdir(mode=0o755)
            for name in meta["application"]:
                destination = temporary/"application"/name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(package/"application"/name, destination)
                os.chmod(destination, 0o644)
            if tree(temporary/"application") != meta["application"]:
                raise ValueError("RESEARCH_COPY_MISMATCH")
            os.replace(temporary, target)
        owner = pwd.getpwnam("arvis")
        STATE.mkdir(mode=0o700, exist_ok=True)
        seed_database(SEED, STATE/"research.db", meta["seed_records"])
        os.chown(STATE/"research.db", owner.pw_uid, owner.pw_gid)
        os.chmod(STATE/"research.db", 0o600)
        os.chown(STATE, owner.pw_uid, owner.pw_gid)
        os.chmod(STATE, 0o700)
        # Recheck production after preparation and before activation.
        validate(package)
        activate(target)
        try:
            if routes() != meta["routes"]:
                raise ValueError("CONCURRENT_PRODUCTION_ROUTE_CHANGE")
            disabled_admin()
        except BaseException:
            control("disable", "--now", TIMER)
            control("stop", SERVICE)
            raise
        print("DIXON_COLES_RESEARCH_TIMER_DEPLOYED")
        print("research_release="+str(target))
        print("Research only; SINGLE=1.50; COMBO legs=1.30; champion unchanged.")
        print("Schedule=:10:30/:40:30 Riga; CPU=25%; nice=10; budget=45s.")
        print("Existing research preserved; ADMIN Codex disabled; no manual cycle/provider call/test send.")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    if args.apply:
        apply(package, rollback=args.rollback)
    else:
        meta, target = validate(package)
        print(json.dumps({"status": "READ_ONLY_PREFLIGHT_PASS", "target": str(target),
                          "source_commit": meta["source_commit"], "seed_records": len(meta["seed_records"]),
                          "root_guard_checked": os.geteuid() == 0, "no_deployment": True}, sort_keys=True))

if __name__ == "__main__":
    main()
