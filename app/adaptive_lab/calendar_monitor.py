"""Optional compact calibration readiness for the existing PREMATCH observer.

Reads verified snapshots only; never fits, sends, queries a provider or changes
selection/champion state. Progress counts economic fixture/market opportunities;
readiness counts retain the exact frozen calendar research contract.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path

from .calendar_audit import read_snapshot
from .calendar_research import CalendarPlan, COHORT_KEYS, PARTITIONS, calendar_dataset
from .contracts import canonical, digest, utc
from .policy import POLICY

ENVIRONMENT_FLAG = "GOALVISION_LAB_CALIBRATION_READINESS"
PLAN_PATH = Path(__file__).with_name("calendar_plan_20261002.json")
PLAN_FINGERPRINT = "9b154abc5b1ca4f18187150c2ca0a8d4d37b93b9c3893e97b2e61457329ca439"
VERSION = "PREMATCH_CALIBRATION_READINESS_OBSERVER_V1"
MAX_OUTPUT_BYTES = 8192


def load_plan() -> CalendarPlan:
    """Accept only the previously declared research plan, never rebase its dates."""
    if PLAN_PATH.is_symlink() or PLAN_PATH.stat().st_size > 65536:
        raise ValueError("CALENDAR_PLAN_INVALID")
    plan = CalendarPlan.from_document(json.loads(PLAN_PATH.read_text()))
    if plan.document()["plan_fingerprint"] != PLAN_FINGERPRINT:
        raise ValueError("CALENDAR_PLAN_NOT_REVIEWED")
    return plan


def _key(row: dict) -> tuple[str, str]:
    fixture = row["fixture_id"]
    if isinstance(fixture, bool) or not str(fixture).isdigit() or int(fixture) <= 0:
        raise ValueError("FORECAST_FIXTURE_INVALID")
    return str(int(fixture)), str(row["market"])


def _view(row: dict, *, learning: bool, state: str, reason: str | None = None) -> dict:
    created = utc(row["prediction_created_at"] if learning else row["prepared_at_utc"])
    kickoff = utc(row["kickoff_utc"])
    if created >= kickoff:
        raise ValueError("FORECAST_NOT_PREMATCH")
    cohort = {k: row.get(k) for k in COHORT_KEYS}
    if not learning:
        cohort["policy_version"] = row.get("profile_policy_version", row.get("policy"))
    return {"key": _key(row), "created": created, "kickoff": kickoff,
            "cohort": cohort, "state": state, "reason": reason}


def _bounded(rows: list[dict]) -> list[dict]:
    if len(rows) > POLICY.training_rows_limit:
        raise ValueError("CALENDAR_FORECAST_BOUND")
    return rows


def build_report(snapshot: dict, ledger: object, plan: CalendarPlan, *, now: datetime) -> dict:
    """Deterministic descriptive progress; settled audit rows remain authoritative."""
    now = utc(now)
    dataset = calendar_dataset(snapshot["rows"], plan, now=now,
                               consumed_holdout_fixtures=snapshot["consumed_fixtures"])
    windows = plan.windows()
    # One representative per economic opportunity; raw canonical forecasts are
    # superseded by acknowledged SINGLEs, then by immutable learning evidence.
    views: dict[tuple[str, str], dict] = {}
    result_keys = {(str(r["fixture_id"]), str(r["market"]))
                   for r in _bounded(snapshot["canonical_results"])
                   if utc(r["retrieved_at_utc"]) <= now}
    for row in _bounded(snapshot["canonical_opportunities"]):
        key = _key(row)
        value = _view(row, learning=False, state="RESULT_AWAITING_LINKAGE" if key in result_keys else "PENDING")
        if value["created"] <= now:
            views[key] = value
    # Only accepted SINGLE publications count. COMBO legs never add observations.
    for row in sorted(_bounded(ledger.all("single_prediction")), key=lambda r: r["prediction_id"]):
        if row.get("stream", "PREMATCH") != "PREMATCH":
            continue
        pid = row["prediction_id"]
        receipt = ledger.get("receipt", "single_prediction:" + pid)
        if not receipt or receipt.get("status") != "SENT" or utc(receipt["sent_at_utc"]) > now:
            continue
        settled = ledger.get("single_settlement", pid)
        linked = settled is not None and utc(settled["settled_at_utc"]) <= now
        value = _view(row, learning=False, state="RESULT_AWAITING_LINKAGE" if linked else "PENDING")
        if value["created"] <= now:
            old = views.get(value["key"])
            # Earliest acknowledged SINGLE wins deterministically until an audit
            # observation resolves the exact accepted learning provenance.
            if old is None or old.get("source") != "SINGLE" or value["created"] < old["created"]:
                views[value["key"]] = dict(value, source="SINGLE")
    learned = set()
    for row in sorted(snapshot["rows"], key=lambda r: (utc(r["prediction_created_at"]), r["observation_id"])):
        if row.get("source_product") not in {"SINGLE", "SHADOW"} or row.get("settled_at") is None or utc(row["settled_at"]) > now:
            continue
        key = _key(row)
        if key in learned:
            continue
        learned.add(key)
        views[key] = _view(row, learning=True, state="RESOLVED",
                           reason=dataset["purge_reasons"].get(row["observation_id"]))

    groups: dict[str, list[dict]] = defaultdict(list)
    for value in views.values():
        groups[value["key"][0]].append(value)
    progress = {name: Counter() for name in PARTITIONS}
    excluded = Counter()
    consumed, reserved = snapshot["consumed_fixtures"], set(plan.reserved_holdout_fixtures)
    for fixture, group in sorted(groups.items()):
        phases = {next((name for name, (start, end) in windows.items() if start <= r["created"] < end), None)
                  for r in group}
        if len(phases) != 1 or None in phases:
            excluded["OUTSIDE_OR_CROSSING_WINDOWS"] += 1
            continue
        name = next(iter(phases))
        p = progress[name]
        p["observed_fixtures"] += 1
        p["observed_opportunities"] += len(group)
        reason = None
        if any(any(r["cohort"][k] != getattr(plan, k) for k in COHORT_KEYS) for r in group):
            reason = "COHORT_MISMATCH_OR_MIXED_FIXTURE"
        elif fixture in consumed:
            reason = "HOLDOUT_ALREADY_CONSUMED"
        elif fixture in reserved and name != "SEALED_HOLDOUT":
            reason = "SEALED_HOLDOUT_RESERVATION"
        elif any(r["reason"] for r in group):
            reason = "RESOLVED_EVIDENCE_EXCLUDED"
        if reason:
            p["excluded_fixtures"] += 1
            excluded[reason] += 1
        elif any(r["state"] == "RESULT_AWAITING_LINKAGE" for r in group):
            p["result_awaiting_linkage_fixtures"] += 1
        elif any(r["state"] == "PENDING" for r in group):
            p["pending_fixtures"] += 1
            if any(r["state"] == "PENDING" and r["kickoff"] <= now for r in group):
                p["awaiting_result_fixtures"] += 1
            else:
                p["upcoming_fixtures"] += 1
        else:
            p["completed_fixtures"] += 1
    phases = {}
    for name, (start, end) in windows.items():
        minimum = dataset["minimum_observations_and_fixtures"][name]
        phases[name] = {"start": start.isoformat(), "end_exclusive": end.isoformat(),
            "window_state": "FUTURE" if now < start else "OPEN" if now < end else "CLOSED",
            "eligible_resolved_observations": dataset["counts"][name],
            "eligible_resolved_fixtures": dataset["independent_fixture_counts"][name],
            "required_observations_and_fixtures": minimum,
            "missing_observations": max(0, minimum-dataset["counts"][name]),
            "missing_independent_fixtures": max(0, minimum-dataset["independent_fixture_counts"][name]),
            "progress": {k: progress[name][k] for k in ("observed_fixtures", "observed_opportunities",
                "completed_fixtures", "pending_fixtures", "upcoming_fixtures", "awaiting_result_fixtures",
                "result_awaiting_linkage_fixtures", "excluded_fixtures")}}
    value = {"version": VERSION, "as_of": now.isoformat(),
        "status": "BLOCKED" if dataset["blocked_by"] else "READY_FOR_OFFLINE_REVIEW",
        "plan_fingerprint": plan.document()["plan_fingerprint"],
        "dataset_fingerprint": dataset["dataset_fingerprint"],
        "learning_snapshot_fingerprint": snapshot["snapshot_fingerprint"],
        "windows": phases, "blocked_by": dataset["blocked_by"],
        "excluded_observation_reasons": dataset["reason_counts"],
        "excluded_forecast_fixture_reasons": dict(sorted(excluded.items())),
        "selection_effect": "NONE", "training_invoked": False, "holdout_evaluated": False,
        "promotion_allowed": False}
    value["snapshot_fingerprint"] = digest(value)
    if len(canonical(value).encode()) > MAX_OUTPUT_BYTES:
        raise ValueError("CALENDAR_OUTPUT_BOUND")
    return value


def observed_readiness(repository: object, ledger: object, *, now: datetime) -> dict:
    """Read a separate bounded transaction, close it before calculating progress."""
    plan = load_plan()
    rows = repository.connection.execute("PRAGMA database_list").fetchall()
    filename = next(row[2] for row in rows if row[1] == "main")
    if not filename:
        raise ValueError("CALENDAR_FILE_DATABASE_REQUIRED")
    snapshot = read_snapshot(Path(filename), include_forecasts=True)
    return build_report(snapshot, ledger, plan, now=now)
