"""Pinned quota-reader and ADMIN correlation repair; read-only unless --apply."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reviewed_runtime_helpers", HERE/"runtime_helpers.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

SYSTEMD = Path("/etc/systemd/system")
OVERRIDE_NAME = "zzzzzzzzzzzzzzzzzzzzzzzzzzz-quota-admin-repair-20261010.conf"
PREMATCH = h.SERVICES
LIVE = "goalvision-lab-live-evening.service"
ADMIN = "goalvision-admin-alerts.service"
AFFECTED = PREMATCH + (LIVE, ADMIN)
PROTECTED = tuple(u for u in h.PROTECTED if u != ADMIN)
ALL_UNITS = AFFECTED + PROTECTED
TIMERS = tuple(u.replace(".service", ".timer") for u in AFFECTED)
ALL_TIMERS = tuple(u.replace(".service", ".timer") for u in ALL_UNITS)
BASES = {
    "prematch": Path("/opt/goalvision-live-evening-4f547cf-20261007"),
    "live": Path("/opt/goalvision-live-final-review-budget-a4cdfa1-20261009"),
    "admin": Path("/opt/goalvision-admin-alerts-releases/admin-mixed-delivery-ab327dd-20261004"),
}
TARGETS = {
    "prematch": Path("/opt/goalvision-prematch-quota-reader-3d4f5c5-20261010"),
    "live": Path("/opt/goalvision-live-quota-reader-3d4f5c5-20261010"),
    "admin": Path("/opt/goalvision-admin-alerts-releases/admin-quota-correlation-9e321c3-20261010"),
}
SOURCE_COMMITS = {
    "reader": "3d4f5c541c79873208ec2bb8ca8c83a0118f546b",
    "admin": "9e321c397337e38f994b2dc424621af414acd58b",
}
OVERLAYS = {
    "reader": "app/adaptive_lab/repository.py",
    "admin": "app/admin_alerts/correlation.py",
}
LOCKS = ("/run/lock/goalvision-prematch-accuracy-combo.lock",
         "/run/lock/goalvision-admin-status-update.lock")
DRAIN_SECONDS = 180


def manifest(root: Path) -> dict:
    h.reject_symlinks(root)
    return {str(p.relative_to(root)): h.sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def configuration_files() -> dict:
    """Hash every GoalVision unit/drop-in, including enabled-unit symlink contents."""
    return {str(p): h.sha(p) for p in sorted(SYSTEMD.rglob("*"))
            if p.is_file() and (p.name.startswith("goalvision") or
                               p.parent.name.startswith("goalvision"))}


def configured_units() -> dict:
    return {unit: {**h.routes((unit,))[unit], **h.stable_commands((unit,))[unit]}
            for unit in ALL_UNITS}


def timer_configurations() -> dict:
    return {unit: {"configuration": h.control("cat", unit),
                   "UnitFileState": h.property_of(unit, "UnitFileState")}
            for unit in ALL_TIMERS}


def route_key(unit: str) -> str:
    return "admin" if unit == ADMIN else "live" if unit == LIVE else "prematch"


def override(unit: str) -> Path:
    return SYSTEMD/(unit+".d")/OVERRIDE_NAME


def dropin(unit: str) -> bytes:
    target = TARGETS[route_key(unit)]
    if unit == ADMIN:
        return ("[Service]\nWorkingDirectory="+str(target)+"\nExecStart=\n"
                "ExecStart=/usr/bin/python3 -I "+str(target/"run.py")+
                " --config /etc/goalvision-admin-alerts/admin-alerts.json\n").encode()
    return h.dropin(target)


def release_environment(key: str, meta: dict) -> bytes:
    old = meta["base_environments"][key].encode()
    prefix = ("PYTHONPATH="+str(BASES[key]/"application")+"\n").encode()
    if old.count(prefix) != 1 or not old.startswith(prefix):
        raise ValueError("BASE_ENVIRONMENT_CONTRACT")
    return ("PYTHONPATH="+str(TARGETS[key]/"application")+"\n").encode()+old[len(prefix):]


def mode() -> str:
    present = []
    for unit in AFFECTED:
        path = override(unit)
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("OVERRIDE_SYMLINK")
        present.append(path.exists())
        if path.exists() and path.read_bytes() != dropin(unit):
            raise ValueError("OVERRIDE_DRIFT")
    if any(present) and not all(present):
        raise ValueError("PARTIAL_DEPLOYMENT_OPERATOR_REVIEW")
    return "ENABLED" if all(present) else "BASE"


def expected_units(meta: dict, state: str) -> dict:
    expected = copy.deepcopy(meta["units"])
    if state == "ENABLED":
        for unit in AFFECTED:
            key = route_key(unit)
            target = TARGETS[key]
            row = expected[unit]
            row["DropInPaths"] = " ".join(filter(None, (row["DropInPaths"], str(override(unit)))))
            if unit == ADMIN:
                row["WorkingDirectory"] = str(target)
                row["ExecStart"] = row["ExecStart"].replace(str(BASES[key]), str(target))
            else:
                row["EnvironmentFiles"] = str(target/"release.env")+" (ignore_errors=no)"
    return expected


def verify_configuration(meta: dict, state: str) -> None:
    expected = dict(meta["systemd_files"])
    if state == "ENABLED":
        expected.update({str(override(u)): hashlib.sha256(dropin(u)).hexdigest() for u in AFFECTED})
    if configuration_files() != expected:
        raise ValueError("SYSTEMD_CONFIGURATION_DRIFT")
    if configured_units() != expected_units(meta, state):
        raise ValueError("LOADED_ROUTE_OR_COMMAND_DRIFT")
    if timer_configurations() != meta["timer_configurations"]:
        raise ValueError("TIMER_CONFIGURATION_DRIFT")
    h.disabled_worker()


def release_manifest(key: str, meta: dict) -> dict:
    result = dict(meta["base_manifests"][key])
    kind = "admin" if key == "admin" else "reader"
    module = OVERLAYS[kind]
    if key == "admin":
        result[module] = meta["overlay_hashes"][kind]
        py_manifest = {p: digest for p, digest in result.items() if p.endswith(".py")}
        result["manifest.json"] = hashlib.sha256(
            (json.dumps(py_manifest, sort_keys=True, indent=2)+"\n").encode()).hexdigest()
    else:
        result = {"application/"+p: digest for p, digest in result.items()}
        result["application/"+module] = meta["overlay_hashes"][kind]
        result["release.env"] = hashlib.sha256(release_environment(key, meta)).hexdigest()
    result["QUOTA_ADMIN_DEPLOYMENT.json"] = hashlib.sha256(
        (json.dumps(meta, sort_keys=True, indent=2)+"\n").encode()).hexdigest()
    return result


def verify_release(key: str, target: Path, meta: dict) -> None:
    if manifest(target) != release_manifest(key, meta):
        raise ValueError("RELEASE_HASH_DRIFT:"+key)


def assemble(package: Path, meta: dict, key: str, stage: Path) -> None:
    """Assemble in a disposable directory; preserve all runtime-relative assets."""
    base = BASES[key]
    root = stage if key == "admin" else stage/"application"
    shutil.copytree(base if key == "admin" else base/"application", root,
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    kind = "admin" if key == "admin" else "reader"
    dest = root/OVERLAYS[kind]
    dest.chmod(0o644)
    shutil.copyfile(package/"overlay"/kind/OVERLAYS[kind], dest)
    if key == "admin":
        py_manifest = {p: digest for p, digest in manifest(stage).items() if p.endswith(".py")}
        h.atomic(stage/"manifest.json", (json.dumps(py_manifest, sort_keys=True, indent=2)+"\n").encode())
    else:
        h.atomic(stage/"release.env", release_environment(key, meta))
    h.atomic(stage/"QUOTA_ADMIN_DEPLOYMENT.json", (json.dumps(meta, sort_keys=True, indent=2)+"\n").encode())
    verify_release(key, stage, meta)


def stage_releases(package: Path, meta: dict) -> None:
    for key, target in TARGETS.items():
        if target.exists() or target.is_symlink():
            verify_release(key, target, meta)
            continue
        stage = Path(tempfile.mkdtemp(prefix=".quota-admin-", dir=target.parent))
        try:
            assemble(package, meta, key, stage)
            # Root-owned immutable payload. Services never need to write release files.
            for path in stage.rglob("*"):
                if path.is_file():
                    path.chmod(0o444)
                elif path.is_dir():
                    path.chmod(0o755)
            stage.chmod(0o755)
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def validate(package: Path) -> tuple[dict, str]:
    h.reject_symlinks(package)
    meta = json.loads((package/"metadata.json").read_text())
    if (meta.get("schema") != "QUOTA_ADMIN_REPAIR_PACKAGE_V1"
            or meta.get("source_commits") != SOURCE_COMMITS
            or meta.get("bases") != {k:str(v) for k,v in BASES.items()}
            or meta.get("targets") != {k:str(v) for k,v in TARGETS.items()}
            or meta.get("smoke", {}).get("status") != "THREE_RELEASES_OFFLINE_PASS"):
        raise ValueError("PACKAGE_CONTRACT")
    if set(meta["scripts"]) != {"update.py", "runtime_helpers.py"}:
        raise ValueError("SCRIPT_SET_MISMATCH")
    for name, digest in meta["scripts"].items():
        if h.sha(package/name) != digest:
            raise ValueError("SCRIPT_HASH_MISMATCH")
    if set(meta["overlay_hashes"]) != set(OVERLAYS):
        raise ValueError("OVERLAY_SET_MISMATCH")
    for kind, name in OVERLAYS.items():
        if h.sha(package/"overlay"/kind/name) != meta["overlay_hashes"][kind]:
            raise ValueError("OVERLAY_HASH_MISMATCH")
    for key, base in BASES.items():
        h.reject_symlinks(base)
        if manifest(base if key == "admin" else base/"application") != meta["base_manifests"][key]:
            raise ValueError("BASE_RELEASE_HASH_DRIFT:"+key)
        if key != "admin" and (base/"release.env").read_text() != meta["base_environments"][key]:
            raise ValueError("BASE_ENVIRONMENT_DRIFT:"+key)
    state = mode()
    verify_configuration(meta, state)
    for key, target in TARGETS.items():
        if target.exists() or target.is_symlink() or state == "ENABLED":
            verify_release(key, target, meta)
    return meta, state


def restore_timers(states: dict) -> None:
    # Restore ADMIN last, after the monitored Lab timer states are restored.
    admin_timer = ADMIN.replace(".service", ".timer")
    # One helper call attempts every timer even if an earlier restore fails.
    ordered = {u:v for u,v in states.items() if u != admin_timer}
    ordered[admin_timer] = states[admin_timer]
    h.restore_timers(ordered)


def route(meta: dict) -> None:
    states = {u: h.property_of(u, "ActiveState") == "active" for u in TIMERS}
    if not states[LIVE.replace(".service", ".timer")]:
        raise ValueError("LIVE_TIMER_NOT_ACTIVE")
    changed = []
    try:
        for timer in reversed(TIMERS):
            h.control("stop", timer)
        deadline = time.monotonic()+DRAIN_SECONDS
        while any(h.property_of(unit, "ActiveState") in h.BUSY for unit in AFFECTED):
            if time.monotonic() >= deadline:
                raise TimeoutError("RUNNING_SERVICES_RETRY_AFTER_NATURAL_COMPLETION")
            time.sleep(.2)
        verify_configuration(meta, "BASE")
        if mode() != "BASE":
            raise ValueError("CONCURRENT_ROUTE_CHANGE")
        for unit in AFFECTED:
            path = override(unit)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.parent.is_symlink():
                raise ValueError("OVERRIDE_PARENT_SYMLINK")
            changed.append(path)
            h.atomic(path, dropin(unit))
        h.control("daemon-reload")
        verify_configuration(meta, "ENABLED")
        if mode() != "ENABLED":
            raise ValueError("ROUTE_NOT_LOADED")
        restore_timers(states)
    except BaseException:
        errors = []
        # Recovery of this interrupted installation only; no model rollback.
        if changed:
            for timer in reversed(TIMERS):
                try:
                    h.control("stop", timer)
                except BaseException:
                    errors.append("TIMER_PAUSE")
            for path in reversed(changed):
                try:
                    unit = path.parent.name.removesuffix(".d")
                    if path.exists():
                        if path.is_symlink() or path.read_bytes() != dropin(unit):
                            raise ValueError("CONCURRENT_OVERRIDE_CHANGE")
                        path.unlink()
                except BaseException:
                    errors.append("OVERRIDE_RESTORE")
            try:
                h.control("daemon-reload")
                verify_configuration(meta, "BASE")
            except BaseException:
                errors.append("ROUTE_RESTORE")
        try:
            restore_timers(states)
        except BaseException:
            errors.append("TIMER_RESTORE")
        if errors:
            raise RuntimeError("INSTALL_RECOVERY_REQUIRES_OPERATOR:"+",".join(errors)) from None
        raise


def apply(package: Path) -> None:
    meta, state = validate(package)
    if state == "ENABLED":
        print("QUOTA_ADMIN_REPAIR_ALREADY_DEPLOYED")
        return
    print("[1/3] Building and verifying three immutable releases...", flush=True)
    stage_releases(package, meta)
    validate(package)
    print("[2/3] Pausing affected timers; waiting for natural completion...", flush=True)
    route(meta)
    print("[3/3] Verifying loaded routes and restored timer states...", flush=True)
    validate(package)
    print("QUOTA_ADMIN_REPAIR_DEPLOYED")
    for key, target in TARGETS.items():
        print(key+"_release="+str(target))
    print("SQLite reader cursor released before document decoding; 500ms quota guard retained.")
    print("ADMIN typed quota health/journal correlation enabled; incident and delivery history retained.")
    print("PREMATCH SINGLE=1.50; DC COMBO legs=1.30; Double exactly two legs >=1.70, probability 70-80%.")
    print("Private SINGLE>=1.70, probability 70-80%; champion, settlement and publication policies retained.")
    print("LIVE=18:00-23:00 Riga; probability 60-70%; EV off; quote age diagnostic; final-review reserve retained.")
    print("Existing timer schedules/states restored; ADMIN Codex disabled; Official untouched.")
    print("No manual cycle/provider call/Telegram test send.")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if not args.apply:
        _, state = validate(HERE)
        print("QUOTA_ADMIN_REPAIR_PLAN_VALIDATED")
        print("current_mode="+state+"; ADMIN_CODEX_SYSTEMD_DISABLED=PASS")
        print("ROOT_GUARD=PASS" if os.geteuid() == 0 else "ROOT_GUARD=CHECKED_AT_APPLY")
        return
    if os.geteuid() != 0:
        raise SystemExit("ROOT_REQUIRED")
    def interrupted(signum, frame):
        raise KeyboardInterrupt("OPERATOR_INTERRUPTED")
    signal.signal(signal.SIGTERM, interrupted)
    with ExitStack() as stack:
        for name in LOCKS:
            lock = stack.enter_context(open(name, "a"))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        apply(HERE)


if __name__ == "__main__":
    main()
