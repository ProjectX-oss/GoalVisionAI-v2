"""Bounded real-report replay: producer read-only, adapter runs on a disposable copy."""
import sys
import socket
from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile
from dataclasses import asdict
from collections import Counter

sys.path.insert(0, sys.argv[1])
def forbidden(*args, **kwargs):
    raise RuntimeError("NETWORK_FORBIDDEN_IN_REPLAY")
socket.socket.connect = forbidden
socket.create_connection = forbidden
from app.admin_alerts.sources import health_rows, readonly, MAX_LINE, HEALTH_DIAGNOSTIC_PATHS
from app.admin_alerts.rules import completed_health
from app.admin_alerts.model import UNITS, identity

SOURCE = Path("/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db")
START = "2026-10-03T06:03:29+00:00"
END = "2026-10-03T15:20:00+00:00"
NOW = 1791040800.0

def capture():
    connection = readonly(SOURCE)
    try:
        return {table: connection.execute(
            f"SELECT id,created_at,stream,document FROM {table} INDEXED BY {table}_stream_time "
            "WHERE stream='PREMATCH' AND created_at>=? AND created_at<? ORDER BY created_at,id LIMIT 128",
            (START, END)).fetchall() for table in ("cycle_health","observer_runs")}
    finally:
        connection.close()

rows = capture()
commitment = hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
with tempfile.TemporaryDirectory(prefix="goalvision-monitor-projection-") as tmp:
    path = Path(tmp)/"producer.db"
    with sqlite3.connect(path) as db:
        for table, values in rows.items():
            db.execute(f"CREATE TABLE {table}(id TEXT,created_at TEXT,stream TEXT,document TEXT)")
            db.execute(f"CREATE INDEX {table}_stream_time ON {table}(stream,created_at,id)")
            db.executemany(f"INSERT INTO {table} VALUES (?,?,?,?)", values)
        paths = ",".join("'" + p + "'" for p in HEALTH_DIAGNOSTIC_PATHS)
        sizes = db.execute(
            f"SELECT max(length(CAST(document AS BLOB))),"
            f"max(length(CAST(json_remove(document,{paths}) AS BLOB))) FROM cycle_health").fetchone()
        old_oversize = db.execute("SELECT count(*) FROM cycle_health WHERE "
            "length(CAST(json_remove(document,'$.PERFORMANCE') AS BLOB))>?",(MAX_LINE,)).fetchone()[0]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    previous = {table:[START,""] for table in rows}
    events,state = health_rows(path,previous,NOW)
    expected = [event for table,unit in (("cycle_health",UNITS[0]),("observer_runs",UNITS[2]))
                for key,stamp,stream,document in rows[table]
                for event in completed_health(json.loads(document),unit,identity(key),NOW,"health-"+identity(key))]
    assert list(map(asdict,events)) == list(map(asdict,expected))
    assert not any(e.rule=="MONITORING_COVERAGE_DEGRADED" for e in events)
    assert health_rows(path,state,NOW+1)[0] == []
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert len(list(Path(tmp).iterdir())) == 1
assert hashlib.sha256(json.dumps(capture(),sort_keys=True).encode()).hexdigest() == commitment
print(json.dumps({"status":"REAL_REPORT_EVENT_EQUIVALENCE_PASS","window_start":START,"window_end":END,
    "records":{table:len(values) for table,values in rows.items()},"source_content_sha256":commitment,
    "old_oversized_discovery_records":old_oversize,"new_coverage_errors":0,
    "max_discovery_source_bytes":sizes[0],"max_discovery_projected_bytes":sizes[1],
    "event_count":len(events),"event_counts":dict(Counter(e.rule+":"+str(e.healthy) for e in events)),
    "source_logical_content_unchanged":True,"disposable_database_bytes_unchanged":True,
    "store_ingest":False,"monitor_scan":False,"provider_calls":0,"telegram_sends":0},sort_keys=True))
