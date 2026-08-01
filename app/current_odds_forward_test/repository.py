"""Append-only SQLite repository for forward-test evidence."""

from __future__ import annotations

import json
import sqlite3

from app.database import Database, MigrationManager
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

from .models import CurrentOddsSnapshot, ForwardTestObservation, ForwardTestResult, ForwardTestSettlement


class ForwardTestConflictError(RuntimeError): pass


class SQLiteForwardTestRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self.connection = database.connection
        if migrate: MigrationManager(self.connection).migrate()

    def append_odds_snapshot(self, value: CurrentOddsSnapshot) -> tuple[sqlite3.Row, bool]:
        existing = self.connection.execute("SELECT * FROM forward_test_odds_snapshots WHERE odds_snapshot_id=?", (value.snapshot_id,)).fetchone()
        if existing:
            if existing["snapshot_fingerprint"] != value.snapshot_fingerprint: raise ForwardTestConflictError("ODDS_QUOTE_REPLACEMENT_CONFLICT")
            return existing, True
        with self.connection:
            self.connection.execute("INSERT INTO forward_test_odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (value.snapshot_id, value.canonical_fixture_id, value.kickoff_utc.isoformat(), value.provider_source_id, value.provider_type.value, value.bookmaker_name, value.source_selected_at_utc.isoformat(), value.captured_at_utc.isoformat(), value.sealed_at_utc.isoformat(), value.freshness_status, value.snapshot_fingerprint, canonical_json(value)))
        return self.load_odds(value.snapshot_id), False

    def append_observation(self, value: ForwardTestObservation) -> tuple[sqlite3.Row, bool]:
        existing = self.connection.execute("SELECT * FROM forward_test_observations WHERE request_id=?", (value.request_id,)).fetchone()
        if existing:
            if existing["request_fingerprint"] != value.request_fingerprint or existing["observation_fingerprint"] != value.observation_fingerprint: raise ForwardTestConflictError("Conflicting forward-test replay rejected.")
            return existing, True
        try:
            with self.connection:
                self.connection.execute("INSERT INTO forward_test_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (value.observation_id, value.request_id, value.request_fingerprint, value.analysis_id, value.odds_snapshot_id, value.canonical_fixture_id, value.evidence_tier, value.status.value, int(value.actionable), int(value.preview_available), int(value.lab_send_eligible), int(value.official_eligible), value.observation_fingerprint, canonical_json(value), value.created_at_utc.isoformat()))
                self._event(value.observation_id, 0, "FORWARD_TEST_RECORDED", value.created_at_utc.isoformat(), {"observation_fingerprint": value.observation_fingerprint})
            return self.load_observation(value.observation_id), False
        except sqlite3.IntegrityError as exc: raise ForwardTestConflictError("Forward-test observation violates immutable identity constraints.") from exc

    def append_result(self, value: ForwardTestResult) -> tuple[sqlite3.Row, bool]:
        existing = self.connection.execute("SELECT * FROM forward_test_results WHERE observation_id=?", (value.observation_id,)).fetchone()
        if existing:
            if existing["result_fingerprint"] != value.result_fingerprint: raise ForwardTestConflictError("Forward-test result conflict rejected.")
            return existing, True
        with self.connection:
            self.connection.execute("INSERT INTO forward_test_results VALUES (?,?,?,?,?,?,?,?,?)", (value.result_id, value.observation_id, value.canonical_fixture_id, value.final_home_score, value.final_away_score, value.final_status, value.result_retrieval_timestamp_utc.isoformat(), value.result_fingerprint, canonical_json(value)))
            sequence = self._next_sequence(value.observation_id)
            self._event(value.observation_id, sequence, "FINAL_RESULT_RECORDED", value.result_retrieval_timestamp_utc.isoformat(), {"result_fingerprint": value.result_fingerprint})
        return self.load_result(value.observation_id), False

    def append_settlement(self, value: ForwardTestSettlement) -> tuple[sqlite3.Row, bool]:
        existing = self.connection.execute("SELECT * FROM forward_test_settlements WHERE observation_id=?", (value.observation_id,)).fetchone()
        if existing:
            if existing["settlement_fingerprint"] != value.settlement_fingerprint: raise ForwardTestConflictError("Forward-test settlement conflict rejected.")
            return existing, True
        with self.connection:
            self.connection.execute("INSERT INTO forward_test_settlements VALUES (?,?,?,?,?,?,?,?)", (value.settlement_id, value.observation_id, value.result_id, value.outcome.value, value.market, value.settlement_fingerprint, canonical_json(value), value.settled_at_utc.isoformat()))
            self._event(value.observation_id, self._next_sequence(value.observation_id), "SETTLEMENT_RECORDED", value.settled_at_utc.isoformat(), {"settlement_fingerprint": value.settlement_fingerprint})
        return self.load_settlement(value.observation_id), False

    def load_odds(self, identifier): return self.connection.execute("SELECT * FROM forward_test_odds_snapshots WHERE odds_snapshot_id=?", (identifier,)).fetchone()
    def load_observation(self, identifier): return self.connection.execute("SELECT * FROM forward_test_observations WHERE observation_id=?", (identifier,)).fetchone()
    def load_result(self, observation_id): return self.connection.execute("SELECT * FROM forward_test_results WHERE observation_id=?", (observation_id,)).fetchone()
    def load_settlement(self, observation_id): return self.connection.execute("SELECT * FROM forward_test_settlements WHERE observation_id=?", (observation_id,)).fetchone()
    def observations(self): return self.connection.execute("SELECT * FROM forward_test_observations ORDER BY created_at_utc,observation_id").fetchall()
    def events(self, observation_id): return self.connection.execute("SELECT * FROM forward_test_events WHERE observation_id=? ORDER BY event_sequence", (observation_id,)).fetchall()
    def append_rejection(self, request_fingerprint: str, stage: str, reason_code: str, occurred_at_utc: str):
        material = {"request_fingerprint": request_fingerprint, "stage": stage, "reason_code": reason_code, "occurred_at_utc": occurred_at_utc}; value_fp = fingerprint(material)
        with self.connection:
            self.connection.execute("INSERT OR IGNORE INTO forward_test_rejections VALUES (?,?,?,?,?,?,?)", ("forward-test-rejection-" + value_fp, request_fingerprint, stage, reason_code, value_fp, canonical_json(material), occurred_at_utc))
        return self.connection.execute("SELECT * FROM forward_test_rejections WHERE request_fingerprint=? AND stage=? AND reason_code=?", (request_fingerprint, stage, reason_code)).fetchone()
    def _next_sequence(self, observation_id): return self.connection.execute("SELECT COALESCE(MAX(event_sequence),-1)+1 FROM forward_test_events WHERE observation_id=?", (observation_id,)).fetchone()[0]
    def _event(self, observation_id, sequence, kind, occurred, detail):
        material = {"observation_id": observation_id, "sequence": sequence, "event_type": kind, "detail": detail, "occurred_at_utc": occurred}; fp = fingerprint(material)
        self.connection.execute("INSERT INTO forward_test_events VALUES (?,?,?,?,?,?,?)", ("forward-test-event-" + fp, observation_id, sequence, kind, fp, canonical_json(material), occurred))


def decode(row: sqlite3.Row | None, field: str) -> object | None:
    return json.loads(row[field]) if row is not None else None
