"""Explicit query-only calendar readiness audit; never a research cycle.

python -m app.adaptive_lab.calendar_audit --database AUDIT_DB --plan PLAN_JSON
    --as-of ISO_TIMESTAMP
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import time

from .calendar_research import CalendarPlan, PARTITIONS, calendar_dataset
from .contracts import digest, learning_source, utc
from .datasets import chronological_dataset
from .policy import POLICY
from .repository import AuditRepository

PROTECTED_TABLES = ("learning_cycles", "training_runs", "model_artifacts", "holdout_results",
                    "shadow_runs", "activation_events", "champion_generations", "live_publications")


def read_snapshot(database: Path) -> dict:
    """One bounded SQLite read transaction; close before any dataset computation."""
    repo = AuditRepository(database, readonly=True)
    try:
        deadline = time.monotonic() + 5
        repo.connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        repo.connection.execute("BEGIN")
        n = repo.connection.execute("SELECT count(*) FROM learning_observations WHERE stream='PREMATCH'").fetchone()[0]
        if n > POLICY.training_rows_limit:
            raise ValueError("CALENDAR_DATASET_BOUND")
        rows = repo.all("learning_observations", "PREMATCH")
        holdouts = repo.all("holdout_results", "PREMATCH")
        consumed = {oid for h in holdouts for oid in h["observation_ids"]}
        by_id = {r["observation_id"]: str(r["fixture_id"]) for r in rows}
        if not consumed <= by_id.keys():
            raise ValueError("CONSUMED_HOLDOUT_PROVENANCE_MISSING")
        return {"rows": rows, "consumed_observations": consumed,
                "consumed_fixtures": {by_id[oid] for oid in consumed},
                "champion_generation": repo.pointer("PREMATCH"),
                "protected_counts": {table: repo.connection.execute("SELECT count(*) FROM " + table).fetchone()[0]
                                     for table in PROTECTED_TABLES},
                "snapshot_fingerprint": digest([[r["observation_id"], r["observation_fingerprint"]] for r in rows])}
    finally:
        repo.close()


def readiness_report(snapshot: dict, plan: CalendarPlan, *, now: datetime) -> dict:
    """Compare timestamp/sample allocation only; never score sealed outcomes."""
    result = calendar_dataset(snapshot["rows"], plan, now=now,
                              consumed_holdout_fixtures=snapshot["consumed_fixtures"])
    candidate = {k: v for k, v in result.items()
                 if k not in {"partitions", "calibration_split", "assignments", "purge_reasons"}}
    fixture_sets = {k: {r["fixture_id"] for r in result["partitions"][k]} for k in PARTITIONS}
    intersections = {a + "__" + b: len(fixture_sets[a] & fixture_sets[b])
                     for i, a in enumerate(PARTITIONS) for b in PARTITIONS[i + 1:]}
    try:
        old = chronological_dataset(snapshot["rows"], "PREMATCH", now=now,
                                    consumed_holdout=snapshot["consumed_observations"])
        legacy = {"counts": {k: len(v) for k, v in old["partitions"].items()},
                  "independent_fixture_counts": {k: len({r["fixture_id"] for r in v})
                                                  for k, v in old["partitions"].items()},
                  "dataset_fingerprint": old["dataset_fingerprint"],
                  "validation_start": old["validation_start"], "holdout_start": old["holdout_start"]}
    except ValueError as exc:
        legacy = {"status": "SPLIT_UNAVAILABLE", "reason": str(exc)}
    return {"version": "PREMATCH_CALENDAR_READINESS_AUDIT_V1", "as_of": utc(now).isoformat(),
            "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
            "retained_observations": len(snapshot["rows"]),
            "independent_source_observations": sum(learning_source(r) for r in snapshot["rows"]),
            "protected_counts": snapshot["protected_counts"],
            "champion_generation": snapshot["champion_generation"],
            "legacy_projection": legacy, "calendar_candidate": candidate,
            "cross_partition_fixture_intersections": intersections,
            "read_only": True, "training_invoked": False, "holdout_evaluated": False,
            "production_runtime_changed": False, "promotion_allowed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    plan = CalendarPlan.from_document(json.loads(args.plan.read_text()))
    report = readiness_report(read_snapshot(args.database), plan, now=utc(args.as_of))
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
