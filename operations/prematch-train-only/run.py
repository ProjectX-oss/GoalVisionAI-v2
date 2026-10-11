"""One-shot detached TRAIN fit using the existing reviewed model registry.

No worker/coordinator, database writer, calibration fit, selection or activation.
This dated recipe intentionally accepts only private research snapshots.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import socket
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

def denied(*args, **kwargs):
    raise RuntimeError("RESEARCH_OUTBOUND_NETWORK_DENIED")

def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")

def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    private_root = Path("/home/arvis/goalvision-research").resolve()
    source = args.snapshot_directory.resolve()
    output = args.output.resolve()
    if not source.is_relative_to(private_root) or not output.is_relative_to(private_root):
        raise ValueError("DETACHED_RESEARCH_PATH_REQUIRED")
    if output.exists():
        raise ValueError("NEW_OUTPUT_DIRECTORY_REQUIRED")
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    os.umask(0o077)
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))

    from app.adaptive_lab.calendar_audit import read_snapshot
    from app.adaptive_lab.calendar_monitor import load_plan
    from app.adaptive_lab.calendar_research import calendar_dataset, PARTITIONS
    from app.adaptive_lab.contracts import digest, utc
    from app.adaptive_lab.features import BASE_FEATURES, FEATURE_SCHEMA
    from app.adaptive_lab.models import candidate_specs, train, predict, validate_training_rows
    from app.adaptive_lab.comparison import evaluated
    from app.adaptive_lab.metrics import metrics
    from app.adaptive_lab.policy import POLICY
    from app.adaptive_lab.repository import AuditRepository

    started = datetime.now(timezone.utc)
    plan = load_plan()
    source_time = utc(json.loads((source / "snapshot.json").read_text())["as_of"])
    if not source_time <= started < plan.windows()["SEALED_HOLDOUT"][0]:
        raise ValueError("RECIPE_ONLY_BEFORE_SEALED_HOLDOUT")
    database = source / "audit.db"
    if database.is_symlink() or not database.is_file():
        raise ValueError("DETACHED_SNAPSHOT_REQUIRED")
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("SELECT count(*) FROM holdout_results").fetchone()[0]:
            raise ValueError("RECIPE_REQUIRES_NO_HOLDOUT_RESULTS")
    source_sha = file_sha256(database)
    snapshot = read_snapshot(database)
    # Reject a mislabeled future snapshot before calendar allocation.
    if any(utc(r["prediction_created_at"]) > source_time or
           (r.get("settled_at") and utc(r["settled_at"]) > source_time)
           for r in snapshot["rows"]):
        raise ValueError("SOURCE_SNAPSHOT_TIME_MISMATCH")
    allocation = calendar_dataset(snapshot["rows"], plan, now=started,
                                  consumed_holdout_fixtures=snapshot["consumed_fixtures"])
    rows = allocation["partitions"]["TRAIN"]
    validate_training_rows(rows)
    if len(rows) < POLICY.research_min or any(
            utc(r["prediction_created_at"]) >= utc(r["kickoff_utc"]) for r in rows):
        raise ValueError("TRAIN_MINIMUM_OR_PREMATCH_CHRONOLOGY")
    fixtures = {str(r["fixture_id"]) for r in rows}
    overlaps = {name: len(fixtures & {str(r["fixture_id"]) for r in allocation["partitions"][name]})
                for name in PARTITIONS if name != "TRAIN"}
    if any(overlaps.values()) or allocation["counts"]["SEALED_HOLDOUT"]:
        raise ValueError("TRAIN_PARTITION_SEPARATION")
    if started < plan.windows()["TRAIN"][1]:
        raise ValueError("TRAIN_WINDOW_NOT_CLOSED")

    # Fixed before fitting; no metric-based choice or hyperparameter search.
    specs = [next(s for s in candidate_specs("PREMATCH")
                  if s["family"] == family and s["features"] == list(BASE_FEATURES)
                  and s["scope"] == "GLOBAL" and s["l2"] == .1
                  and s["half_life_days"] == 0 and s["history_days"] == 0
                  and not s["interactions"])
             for family in ("LOGISTIC", "REGULARIZED_LOGISTIC", "STUMP_ENSEMBLE")]
    estimated_operations = sum(4 * len(rows) * s["iterations"] * len(s["features"]) for s in specs)
    if estimated_operations > POLICY.operation_budget:
        raise ValueError("RESEARCH_OPERATION_BUDGET")
    repo = AuditRepository(database, readonly=True)
    try:
        champion = repo.champion("PREMATCH")
        champion_artifact = repo.get("model_artifacts", champion["artifact_id"])
        previous = repo.all("model_artifacts", "PREMATCH")
    finally:
        repo.close()
    known_fingerprints = {r.get("artifact_fingerprint") for r in previous}
    training_fingerprint = digest([(r["observation_id"], r["observation_fingerprint"]) for r in rows])
    manifest = {
        "version": "DETACHED_PREMATCH_TRAIN_ONLY_20261011",
        "started_at": started.isoformat(), "snapshot_as_of": source_time.isoformat(),
        "source_snapshot_sha256": source_sha,
        "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
        "dataset_fingerprint": allocation["dataset_fingerprint"],
        "training_fingerprint": training_fingerprint,
        "plan": plan.document(), "feature_schema": FEATURE_SCHEMA,
        "champion_generation": snapshot["champion_generation"],
        "champion_artifact_id": champion["artifact_id"],
        "champion_artifact_fingerprint": champion_artifact["artifact_fingerprint"],
        "train_observations": len(rows), "train_independent_fixtures": len(fixtures),
        "train_wins": sum(r["target"] for r in rows),
        "train_losses": sum(1-r["target"] for r in rows),
        "cross_partition_fixture_intersections": overlaps,
        "current_calendar_blocked_by": allocation["blocked_by"],
        "specs": specs, "estimated_operations": estimated_operations,
        "operation_budget": POLICY.operation_budget,
        "created_after_validation_opened": started >= plan.windows()["VALIDATION_EVALUATION"][0],
        "calibration_fitted": False, "validation_scored": False, "holdout_opened": False,
        "production_eligible": False, "candidate_selected": None,
        "source_files": {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (
            "app/adaptive_lab/models.py", "app/adaptive_lab/features.py",
            "app/adaptive_lab/calendar_research.py", "app/adaptive_lab/policy.py")},
        "recipe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    output.mkdir(mode=0o700)
    write_new(output/"manifest.json", manifest)
    write_new(output/"train_rows.json", rows)
    print(json.dumps({"status":"TRAINING_STARTED", "at":started.isoformat(),
                      "observations":len(rows), "fixtures":len(fixtures),
                      "candidates":len(specs)}), flush=True)
    results = []
    for spec in specs:
        timer = time.monotonic()
        artifact = train(spec, rows)
        reproduced = train(spec, rows)
        if artifact != reproduced or artifact["training_fingerprint"] != training_fingerprint:
            raise ValueError("TRAIN_REPRODUCTION_MISMATCH")
        probabilities = [predict(artifact, r) for r in rows]
        scored = metrics(evaluated(rows, probabilities), "PREMATCH")
        diagnostic = {k: scored[k] for k in (
            "brier", "log_loss", "ece", "calibration_bias", "reliability_bins")}
        result = {"family":spec["family"], "artifact_fingerprint":artifact["artifact_fingerprint"],
                  "already_present_in_source_registry":artifact["artifact_fingerprint"] in known_fingerprints,
                  "reproduced":True, "seconds":time.monotonic()-timer,
                  "probability_min":min(probabilities), "probability_max":max(probabilities),
                  "train_only_diagnostics":diagnostic}
        write_new(output/(spec["family"]+".json"), artifact)
        results.append(result)
        print(json.dumps({k:v for k,v in result.items() if k != "train_only_diagnostics"}), flush=True)
    if file_sha256(database) != source_sha:
        raise ValueError("SOURCE_SNAPSHOT_CHANGED")
    result = {
        "status":"TRAIN_ONLY_COMPLETED_NEEDS_FUTURE_INDEPENDENT_EVALUATION",
        "started_at":started.isoformat(), "finished_at":datetime.now(timezone.utc).isoformat(),
        "manifest_fingerprint":digest(manifest), "candidates":results,
        "source_snapshot_unchanged":True, "production_writes":0, "model_activation":"NONE",
        "provider_calls":0, "telegram_sends":0, "validation_scored":False,
        "holdout_opened":False, "calibration_fitted":False, "selected_candidate":None,
        "limitations":[
            "TRAIN diagnostics are in-sample, not evidence of predictive improvement.",
            "No frozen calendar boundary was moved; the existing calibration experiment is unchanged.",
            "Artifacts created after validation opened are not retroactively prospective predictions.",
            "These detached artifacts require a separately reviewed future evaluation protocol.",
            "Production model-artifact counts do not include this detached research run."
        ]
    }
    write_new(output/"result.json", result)
    print(json.dumps({"status":result["status"],"finished_at":result["finished_at"],
                      "output":str(output)}), flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
