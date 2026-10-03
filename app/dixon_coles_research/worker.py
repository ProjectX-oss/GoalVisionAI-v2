"""Bounded, offline research cycle, activated only by the reviewed operator timer."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
from typing import Callable
from . import cli
from .contracts import load_plan, seal, utc
from .repository import ResearchStore

SERVICES = ("goalvision-lab-v2-discover.service",
            "goalvision-adaptive-learning-observer.service",
            "goalvision-lab-combo-settle.service", "goalvision-adaptive-learning.service")
BUDGET_SECONDS = 45
MAX_DATABASE_BYTES = 512 * 1024 * 1024

class BudgetExceeded(RuntimeError):
    pass

def clock() -> datetime:
    return datetime.now(timezone.utc)

def in_slot(now: datetime) -> bool:
    """Do not catch up missed starts; finish before the next production slot."""
    value = utc(now)
    return value.minute in (10, 40) and 30 <= value.second < 60

def production_idle(services: tuple[str, ...] = SERVICES) -> bool:
    """Unknown, failed or busy services fail closed without changing their state."""
    result = subprocess.run(
        ["/usr/bin/systemctl", "show", *services, "-p", "Id", "-p", "LoadState",
         "-p", "ActiveState", "-p", "MainPID"], capture_output=True, text=True,
        timeout=3, check=True)
    states = {}
    for block in result.stdout.strip().split("\n\n"):
        values = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if values.get("Id") in states:
            return False
        states[values.get("Id")] = values
    return set(states) == set(services) and all(
        v.get("LoadState") == "loaded" and v.get("ActiveState") == "inactive"
        and v.get("MainPID") == "0" for v in states.values())

@contextmanager
def deadline(seconds: int):
    def expired(signum, frame):
        raise BudgetExceeded("RESEARCH_TIME_BUDGET")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)

def cycle(args: argparse.Namespace, *, now: Callable[[], datetime] = clock,
          idle: Callable[[], bool] = production_idle,
          execute: Callable = cli.run_report, plan_loader: Callable | None = None,
          slot: Callable | None = None, record_version: str = "DC_AUTOMATION_V1",
          extra_protected_paths: tuple[Path, ...] = ()) -> dict:
    """Execute serial capture/evaluation; preserve successful partial writes on retry."""
    started = now()
    report = {"version": record_version, "started_at": utc(started).isoformat(),
              "selection_effect": "NONE", "provider_calls": 0, "telegram_sends": 0,
              "automatic_promotion": False, "priority": "NORMAL"}
    if not (slot or in_slot)(started):
        return seal({**report, "status": "SKIPPED", "reason": "OUTSIDE_TIMER_SLOT"})
    if not idle():
        return seal({**report, "status": "SKIPPED", "reason": "PRODUCTION_BUSY_OR_UNKNOWN"})
    plan = (plan_loader or load_plan)()
    total = sum(p.stat().st_size for p in (
        args.research_database, Path(str(args.research_database)+"-wal")) if p.exists())
    if total > MAX_DATABASE_BYTES:
        return seal({**report, "status": "BLOCKED", "reason": "RESEARCH_STORAGE_BUDGET"})
    with deadline(BUDGET_SECONDS):
        if utc(plan["evaluation_start"]) <= utc(started) < utc(plan["evaluation_end"]):
            try:
                capture = execute(argparse.Namespace(**{**vars(args), "command": "capture"}), now)
                report["capture"] = {key: capture[key] for key in
                                     ("counts", "source_diagnostics", "details", "fingerprint")}
                if "combo_shadow" in capture:
                    report["capture"]["combo_shadow"] = capture["combo_shadow"]
            except (ValueError, KeyError, TypeError, ArithmeticError, OSError, sqlite3.Error):
                report["capture"] = {"status": "BLOCKED", "reason": "CAPTURE_INPUT_UNAVAILABLE"}
        else:
            report["capture"] = {"status": "SKIPPED", "reason": "OUTSIDE_FROZEN_CAPTURE_WINDOW"}
        # A missing/new DB can be enrolled after capture closes, but never creates forecasts.
        protected = (args.shadow_database, args.audit_database, args.ledger_database) + extra_protected_paths
        store = ResearchStore(args.research_database, protected_paths=protected)
        try:
            store.append("plan", plan["fingerprint"], plan)
        finally:
            store.close()
        metrics = execute(argparse.Namespace(**{**vars(args), "command": "evaluate"}), now)
        report["evaluation"] = {key: metrics[key] for key in
                                ("lifecycle", "counts", "quality_verdict", "fingerprint")}
        if "combo_shadow" in metrics:
            report["evaluation"]["combo_shadow"] = metrics["combo_shadow"]
        report["evaluation"]["market_rows"] = metrics["overall"]["market_rows"]
        report["evaluation"]["fixtures"] = metrics["overall"]["fixtures"]
        report["evaluation"]["kickoff_dates"] = metrics["overall"]["kickoff_dates"]
    return seal({**report, "status": ("PARTIAL" if report["capture"].get("status") == "BLOCKED"
                                     else "COMPLETED"), "finished_at": utc(now()).isoformat()})

def main(argv: list[str] | None = None, *, cycle_function: Callable | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("shadow", "audit", "ledger", "research"):
        parser.add_argument("--"+name+"-database", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 12:
        parser.error("--limit must be between 1 and 12")
    current = os.getpriority(os.PRIO_PROCESS, 0)
    if current < 10:
        os.nice(10-current)
    folder = args.research_database.absolute().parent
    if folder.is_symlink() or any(p.is_symlink() for p in folder.parents):
        raise ValueError("RESEARCH_SYMLINK")
    folder.mkdir(parents=True, exist_ok=True)
    # O_NOFOLLOW protects status/lock destinations independently of the DB check.
    descriptor = os.open(folder/"cycle.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "SKIPPED", "reason": "RESEARCH_ALREADY_RUNNING"}))
            return 0
        try:
            report = (cycle_function or cycle)(args)
        except (BudgetExceeded, ValueError, KeyError, TypeError, ArithmeticError,
                OSError, sqlite3.Error, subprocess.SubprocessError):
            report = seal({"status": "BLOCKED", "reason": "RESEARCH_INPUT_OR_BUDGET_UNAVAILABLE",
                           "observed_at": clock().isoformat(), "selection_effect": "NONE"})
        temporary = folder/"latest.json.tmp"
        fd = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(report, output, sort_keys=True, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, folder/"latest.json")
        print(json.dumps(report, sort_keys=True, allow_nan=False))
        return 2 if report["status"] in {"BLOCKED", "PARTIAL"} else 0

if __name__ == "__main__":
    raise SystemExit(main())
