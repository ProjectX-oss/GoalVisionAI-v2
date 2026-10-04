"""Health diagnostic projection preserves the monitor's full event semantics."""
from dataclasses import asdict
import hashlib
import json
import sqlite3

import pytest

from app.admin_alerts.model import UNITS, identity
from app.admin_alerts.rules import completed_health
from app.admin_alerts.sources import MAX_LINE, health_rows

NOW = 1791040260.0
STAMP = "2026-10-03T15:10:00+00:00"
DIAGNOSTICS = ("publication_blockers", "publication_reviews",
               "single_publication_blockers", "single_publication_reviews")


def database(path, document):
    with sqlite3.connect(path) as db:
        for table in ("cycle_health", "observer_runs"):
            db.execute(f"CREATE TABLE {table}(id TEXT,created_at TEXT,stream TEXT,document TEXT)")
            db.execute(f"CREATE INDEX {table}_stream_time ON {table}(stream,created_at,id)")
            db.execute(f"INSERT INTO {table} VALUES (?,?,?,?)",
                       ("00001", STAMP, "PREMATCH", json.dumps(document, ensure_ascii=False)))


CASES = [
    {"result": "HEALTHY", "publication": {"status": "NOT_REQUESTED"}},
    {"result": "FAILED", "failure": {"code": "AUTHENTICATION_FAILED"}},
    {"result": "FAILED", "quota": {"status": "QUOTA_UNAVAILABLE_STOP_AFTER_STATUS"}},
    {"result": "FAILED", "code": "QUOTA_DB_CONTENTION_EXHAUSTED"},
    {"publication": {"status": "FAILED", "failure": {"code": "DATABASE_LOCKED", "prediction_id": "pick-a"}}},
    {"publication": {"status": "UNKNOWN", "deliveries": [{"prediction_id": "pick-a",
         "transport_attempted": True, "acknowledgement_received": True, "receipt_persisted": False}]}},
    {"publication": {"status": "OK", "deliveries": [{"prediction_id": "pick-a", "receipt_persisted": True}]}},
    {"publication": {"status": "DEGRADED", "deliveries": [{"prediction_id": "pick-a",
         "persistence_failure": True, "transport_attempted": False}]}},
    {"publication": {"status": "FAILED", "deliveries": [{"prediction_id": "pick-a",
         "status": "SELECTION_ORIGIN_OR_APPROVAL_INVALID", "transport_attempted": False}]}},
    {"publication": {"status": "FAILED", "deliveries": [{"prediction_id": "pick-a",
         "status": "FAILED", "stage": "REJECTED_BEFORE_TRANSPORT", "transport_attempted": False}]}},
    {"publication": {"status": "FAILED", "deliveries": ["malformed", {"status": "FAILED"}]}},
    {"publication": {"status": "FAILED", "deliveries": [{"status": "FAILED"}] * 201}},
]


@pytest.mark.parametrize("diagnostic", DIAGNOSTICS)
@pytest.mark.parametrize("case", CASES)
def test_projected_event_stream_equals_full_report(tmp_path, diagnostic, case):
    document = json.loads(json.dumps(case))
    document.update(created_at=STAMP, completed_at=STAMP, evidence_at=STAMP)
    document.setdefault("publication", {})[diagnostic] = [{"review": "ž" * MAX_LINE}]
    document["PERFORMANCE"] = {"segments": "x" * MAX_LINE}
    path = tmp_path / "producer.db"
    database(path, document)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    events, state = health_rows(path, {}, NOW)
    expected = [event for unit in (UNITS[0], UNITS[2])
                for event in completed_health(document, unit, identity("00001"), NOW,
                                               "health-" + identity("00001"))]
    assert list(map(asdict, events)) == list(map(asdict, expected))
    assert not any(e.facts.get("reason") == "OVERSIZED_RECORD" for e in events)
    assert all(cursor == [STAMP, "00001"] for cursor in state.values())
    assert health_rows(path, state, NOW + 1)[0] == []
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["producer.db"]


@pytest.mark.parametrize("publication", [
    {"failure": {"code": "x" * (MAX_LINE + 1)}},
    {"deliveries": [{"prediction_id": "x" * (MAX_LINE + 1), "status": "FAILED"}]},
    {"unknown_evidence": "x" * (MAX_LINE + 1)},
    {"status": "x" * (MAX_LINE + 1)},
])
def test_required_and_unknown_oversize_remains_visible(tmp_path, publication):
    document = {"result": "HEALTHY", "created_at": STAMP, "publication": {
        **publication, "single_publication_reviews": "x" * MAX_LINE}}
    path = tmp_path / "producer.db"
    database(path, document)
    events, _ = health_rows(path, {}, NOW)
    assert len(events) == 2
    assert all(e.rule == "MONITORING_COVERAGE_DEGRADED"
               and e.facts["reason"] == "OVERSIZED_RECORD" and not e.healthy for e in events)


def test_other_namespaces_are_not_pruned(tmp_path):
    document = {"created_at": STAMP, "result": "HEALTHY",
                "single_publication_reviews": "x" * (MAX_LINE + 1),
                "publication": {"single_publication_reviews": []}}
    path = tmp_path / "producer.db"
    database(path, document)
    events, _ = health_rows(path, {}, NOW)
    assert len(events) == 2
    assert all(e.facts["reason"] == "OVERSIZED_RECORD" for e in events)
