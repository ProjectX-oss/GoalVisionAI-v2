"""Pinned PREMATCH recovery overlay; default read-only, operator --apply only."""
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
helper = HERE / "runtime_helpers.py"
if not helper.exists() and HERE.name == "calibration-live-recovery":
    helper = HERE.parent / "live-evening/update.py"
spec = importlib.util.spec_from_file_location("recovery_runtime_helpers", helper)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
BASE = Path("/opt/goalvision-prematch-quota-reader-3d4f5c5-20261010")
TARGET = Path("/opt/goalvision-prematch-recovery-380bcf7-20261011")
SYSTEMD = Path("/etc/systemd/system")
JOURNALS = Path("/var/lib/goalvision-operator-recovery")
SERVICES = h.SERVICES
PROTECTED = h.PROTECTED + ("goalvision-lab-live-evening.service",)
ALL_UNITS = SERVICES + PROTECTED
TIMERS = tuple(u.replace(".service", ".timer") for u in SERVICES)
ALL_TIMERS = tuple(u.replace(".service", ".timer") for u in ALL_UNITS)
OVERRIDE = "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-recovery-20261011.conf"
FILES = ("app/adaptive_lab/calendar_audit.py", "app/adaptive_lab/health.py",
         "app/adaptive_lab/observer.py", "app/lab_v2_shadow/combo_agreement_sources.py")
DRAIN_SECONDS = 180
SCHEMA = "PREMATCH_RECOVERY_OPERATOR_PACKAGE_V1"

def manifest(root: Path) -> dict:
    h.reject_symlinks(root)
    return {str(p.relative_to(root)): h.sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}

def configuration_files() -> dict:
    return {str(p): h.sha(p) for p in sorted(SYSTEMD.rglob("*"))
            if p.is_file() and (p.name.startswith("goalvision") or
                               p.parent.name.startswith("goalvision"))}

def configured_units() -> dict:
    return {u: {**h.routes((u,))[u], **h.stable_commands((u,))[u]} for u in ALL_UNITS}

def timer_configurations() -> dict:
    return {u: {"configuration": h.control("cat", u),
                "UnitFileState": h.property_of(u, "UnitFileState")} for u in ALL_TIMERS}

def override(unit: str) -> Path:
    return SYSTEMD / (unit + ".d") / OVERRIDE

def dropin() -> bytes:
    return h.dropin(TARGET)

def mode() -> str:
    present = []
    for unit in SERVICES:
        p = override(unit)
        if p.is_symlink() or p.parent.is_symlink():
            raise ValueError("OVERRIDE_SYMLINK")
        present.append(p.exists())
        if p.exists() and p.read_bytes() != dropin():
            raise ValueError("OVERRIDE_DRIFT")
    if any(present) and not all(present):
        raise ValueError("PARTIAL_DEPLOYMENT_OPERATOR_REVIEW")
    return "ENABLED" if all(present) else "BASE"

def release_environment(meta: dict) -> bytes:
    old = meta["base_environment"].encode()
    prefix = ("PYTHONPATH=" + str(BASE / "application") + "\n").encode()
    if not old.startswith(prefix) or old.count(prefix) != 1:
        raise ValueError("BASE_ENVIRONMENT_CONTRACT")
    return ("PYTHONPATH=" + str(TARGET / "application") + "\n").encode() + old[len(prefix):]

def verify_configuration(meta: dict, state: str) -> None:
    expected = copy.deepcopy(meta["units"])
    files = dict(meta["systemd_files"])
    if state == "ENABLED":
        for unit in SERVICES:
            expected[unit]["EnvironmentFiles"] = str(TARGET / "release.env") + " (ignore_errors=no)"
            expected[unit]["DropInPaths"] = " ".join(filter(None, (
                expected[unit]["DropInPaths"], str(override(unit)))))
            files[str(override(unit))] = hashlib.sha256(dropin()).hexdigest()
    if configuration_files() != files:
        raise ValueError("SYSTEMD_CONFIGURATION_DRIFT")
    if configured_units() != expected:
        raise ValueError("LOADED_ROUTE_OR_COMMAND_DRIFT")
    if timer_configurations() != meta["timer_configurations"]:
        raise ValueError("TIMER_CONFIGURATION_DRIFT")
    h.disabled_worker()

def release_manifest(meta: dict) -> dict:
    files = {"application/" + n: v for n, v in meta["base_manifest"].items()}
    files.update({"application/" + n: v for n, v in meta["files"].items()})
    files["release.env"] = hashlib.sha256(release_environment(meta)).hexdigest()
    files["RECOVERY_PACKAGE.json"] = hashlib.sha256(
        (json.dumps(meta, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
    return files

def verify_release(target: Path, meta: dict) -> None:
    if manifest(target) != release_manifest(meta):
        raise ValueError("RELEASE_HASH_DRIFT")

def assemble(package: Path, meta: dict, stage: Path) -> None:
    shutil.copytree(BASE / "application", stage / "application",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for name in FILES:
        destination = stage / "application" / name
        destination.chmod(0o644)
        shutil.copyfile(package / "overlay" / name, destination)
    h.atomic(stage / "release.env", release_environment(meta))
    h.atomic(stage / "RECOVERY_PACKAGE.json",
             (json.dumps(meta, sort_keys=True, indent=2) + "\n").encode())
    verify_release(stage, meta)

def validate(package: Path) -> tuple[dict, str]:
    h.reject_symlinks(package)
    meta = json.loads((package / "metadata.json").read_text())
    commit = meta.get("source_commit", "")
    if (meta.get("schema") != SCHEMA or meta.get("base") != str(BASE)
            or meta.get("target") != str(TARGET) or len(commit) != 40
            or any(c not in "0123456789abcdef" for c in commit)
            or meta.get("smoke", {}).get("status") != "EXACT_BASE_RECOVERY_PASS"):
        raise ValueError("PACKAGE_CONTRACT")
    if set(meta["scripts"]) != {"install.py", "runtime_helpers.py"} or set(meta["files"]) != set(FILES):
        raise ValueError("PACKAGE_FILE_SET")
    for name, value in meta["scripts"].items():
        if h.sha(package / name) != value:
            raise ValueError("SCRIPT_HASH_MISMATCH")
    for name, value in meta["files"].items():
        if h.sha(package / "overlay" / name) != value:
            raise ValueError("OVERLAY_HASH_MISMATCH")
    h.reject_symlinks(BASE)
    if manifest(BASE / "application") != meta["base_manifest"] or (BASE / "release.env").read_text() != meta["base_environment"]:
        raise ValueError("BASE_RELEASE_DRIFT")
    state = mode()
    verify_configuration(meta, state)
    if TARGET.exists() or TARGET.is_symlink() or state == "ENABLED":
        verify_release(TARGET, meta)
    return meta, state

def stage_release(package: Path, meta: dict) -> None:
    if TARGET.exists() or TARGET.is_symlink():
        verify_release(TARGET, meta)
        return
    stage = Path(tempfile.mkdtemp(prefix=".prematch-recovery-", dir=TARGET.parent))
    try:
        assemble(package, meta, stage)
        for p in stage.rglob("*"):
            p.chmod(0o444 if p.is_file() else 0o755)
        stage.chmod(0o755)
        os.rename(stage, TARGET)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

def route(meta: dict) -> None:
    states = {}
    for timer in TIMERS:
        value = h.property_of(timer, "ActiveState")
        if value not in {"active", "inactive"}:
            raise ValueError("TIMER_STATE_REVIEW_REQUIRED:" + timer)
        states[timer] = value == "active"
    JOURNALS.mkdir(mode=0o700, parents=True, exist_ok=True)
    if JOURNALS.is_symlink():
        raise ValueError("JOURNAL_SYMLINK")
    journal = JOURNALS / ("recovery-20261011-" + str(time.time_ns()) + ".json")
    record = {"phase": "PREPARED", "timer_states": states, "base": str(BASE),
              "target": str(TARGET), "changed_overrides": [], "automatic_rollback": False}
    def checkpoint(phase):
        record["phase"] = phase
        h.atomic(journal, (json.dumps(record, indent=2) + "\n").encode())
    checkpoint("PREPARED")
    changed = False
    try:
        for timer in TIMERS:
            h.control("stop", timer)
        deadline = time.monotonic() + DRAIN_SECONDS
        while any(h.property_of(u, "ActiveState") in h.BUSY for u in SERVICES):
            if time.monotonic() >= deadline:
                raise TimeoutError("WAIT_FOR_NATURAL_COMPLETION_AND_RETRY")
            time.sleep(.2)
        verify_configuration(meta, "BASE")
        if mode() != "BASE":
            raise ValueError("CONCURRENT_ROUTE_CHANGE")
        checkpoint("TIMERS_PAUSED_SERVICES_IDLE")
        for unit in SERVICES:
            path = override(unit)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.parent.is_symlink():
                raise ValueError("OVERRIDE_PARENT_SYMLINK")
            changed = True  # Atomic write could finish before interruption.
            h.atomic(path, dropin())
            record["changed_overrides"].append(str(path))
            checkpoint("ROUTING")
        h.control("daemon-reload")
        verify_configuration(meta, "ENABLED")
        if mode() != "ENABLED":
            raise ValueError("ROUTE_NOT_LOADED")
        checkpoint("ROUTES_VERIFIED")
        h.restore_timers(states)
        checkpoint("COMPLETED")
    except BaseException:
        if changed:
            for timer in TIMERS:
                try:
                    h.control("stop", timer)
                except BaseException:
                    pass
            checkpoint("OPERATOR_REVIEW_REQUIRED_TIMERS_PAUSED")
            raise RuntimeError("PARTIAL_INSTALL_NO_AUTOMATIC_ROLLBACK; journal=" + str(journal)) from None
        # No route was written: restore only prior timer activity, never enable.
        h.restore_timers(states)
        checkpoint("ABORTED_BEFORE_ROUTE_CHANGE")
        raise

def apply(package: Path) -> None:
    meta, state = validate(package)
    if state == "ENABLED":
        print("PREMATCH_RECOVERY_ALREADY_DEPLOYED")
        return
    print("[1/3] Building and verifying immutable PREMATCH successor...", flush=True)
    stage_release(package, meta)
    validate(package)
    print("[2/3] Pausing PREMATCH timers; waiting for natural completion...", flush=True)
    route(meta)
    print("[3/3] Verifying loaded routes and unchanged configurations...", flush=True)
    validate(package)
    print("PREMATCH_RECOVERY_DEPLOYED")
    print("prematch_release=" + str(TARGET))
    print("DC reader: shared 10 seconds from first use; calendar reader lock fixed.")
    print("Observer/health diagnostics corrected; LIVE routes and timer untouched.")
    print("Champion, models, thresholds, settlement, Official and ADMIN unchanged.")
    print("No manual worker, provider call, Telegram test or automatic rollback.")

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if not args.apply:
        _, state = validate(HERE)
        print("PREMATCH_RECOVERY_PREFLIGHT_PASS; mode=" + state)
        print("ROOT_GUARD=PASS" if os.geteuid() == 0 else "ROOT_GUARD=CHECKED_AT_APPLY")
        return
    if os.geteuid() != 0:
        raise SystemExit("ROOT_REQUIRED")
    def interrupted(signum, frame):
        raise KeyboardInterrupt("OPERATOR_INTERRUPTED")
    signal.signal(signal.SIGTERM, interrupted)
    with ExitStack() as stack:
        lock = stack.enter_context(open("/run/lock/goalvision-prematch-accuracy-combo.lock", "a"))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        apply(HERE)

if __name__ == "__main__":
    main()
