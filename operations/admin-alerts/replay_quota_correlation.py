"""Read-only replay of a sanitized ADMIN export; no runtime DB or transports."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.admin_alerts.correlation import groups


def replay(document: dict) -> dict:
    """Project retained incidents without ingest, enqueue, dispatch or mutation."""
    if document.get("mode") != "READ_ONLY" or document.get("truncated") is not False:
        raise ValueError("COMPLETE_READ_ONLY_EXPORT_REQUIRED")
    rows = document["incidents"]
    since, as_of = document["since_epoch"], document["as_of_epoch"]
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    try:
        db.execute("""CREATE TABLE incidents(
            id TEXT PRIMARY KEY, rule TEXT, service TEXT, invocation TEXT,
            first_seen REAL, state TEXT, evidence TEXT)""")
        for row in rows:
            db.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?,?)",
                       (row["id"], row["rule"], row["service"], row["invocation"],
                        row["first_seen"], row["state"], json.dumps(row["evidence"], sort_keys=True)))
        before = list(map(tuple, db.execute("SELECT * FROM incidents ORDER BY id")))
        projected = groups(db)
        assert before == list(map(tuple, db.execute("SELECT * FROM incidents ORDER BY id")))
    finally:
        db.close()
    recent = [row for row in rows if since <= row["last_seen"] <= as_of]
    historical = [row for row in rows if row["last_seen"] < since]
    recent_ids = {row["id"] for row in recent}
    projected_recent = [group for group in projected
                        if recent_ids.intersection(row["id"] for row in group["members"])]
    receipts = sum(item["rows"] for row in recent
                   for item in row["outbox_created_in_window"]
                   if item["state"] == "SENT" and item["acknowledged"])
    return {
        "schema": "ADMIN_QUOTA_CORRELATION_REPLAY_V1",
        "as_of_epoch": as_of, "since_epoch": since,
        "exported_incidents": len(rows),
        "state_counts": dict(sorted(Counter(row["state"] for row in rows).items())),
        "recent_incidents": len(recent), "historical_without_recent_recurrence": len(historical),
        "recent_rules": dict(sorted(Counter(row["rule"] for row in recent).items())),
        "historical_rules": dict(sorted(Counter(row["rule"] for row in historical).items())),
        "recent_acknowledged_outbox_rows": receipts,
        "delivery_attempts_in_window": document["delivery_attempts_in_window"],
        "recent_execution_groups": len(projected_recent),
        "recent_groups": sorted([
            {"invocation": group["invocation"], "service": group["service"],
             "primary_incident": group["primary_incident"],
             "members": sorted(row["id"] for row in group["members"]),
             "associations": group["associations"]}
            for group in projected_recent], key=lambda group: group["primary_incident"]),
        "source_rows_unchanged": True, "source_writes": 0, "monitor_scans": 0,
        "provider_calls": 0, "telegram_calls": 0, "telegram_sends": 0,
        "note": "Correlation projection only; historical sends are retained, not undone."
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise ValueError("SOURCE_OVERWRITE_FORBIDDEN")
    source = args.input.read_bytes()
    result = replay(json.loads(source))
    result["source_sha256"] = hashlib.sha256(source).hexdigest()
    result["correlation_source_sha256"] = hashlib.sha256(
        (Path(__file__).resolve().parents[2]/"app/admin_alerts/correlation.py").read_bytes()).hexdigest()
    with args.output.open("x") as handle:
        json.dump(result, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print("ADMIN_QUOTA_CORRELATION_REPLAY_SAVED=" + str(args.output))


if __name__ == "__main__":
    main()
