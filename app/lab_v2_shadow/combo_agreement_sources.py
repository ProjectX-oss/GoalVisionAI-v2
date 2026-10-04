"""Bounded read-only inputs for the explicitly enabled COMBO experiment."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from time import monotonic

from app.dixon_coles_forward.contracts import load_plan
from app.dixon_coles_forward.model import verify_artifact
from app.dixon_coles_research.repository import ResearchStore
from app.real_match_lab_analysis.fingerprint import fingerprint
from .combo_agreement import evidence

MODEL_DB = Path("/var/lib/goalvision-dixon-coles-forward/research.db")
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 600
BUDGET_SECONDS = 10

class Inputs:
    """One preparation-local cache; no writes, network, training, or global state."""
    def __init__(self, repository: object, *, model_path: Path | None = None) -> None:
        self.repository = repository
        self.model_path = MODEL_DB if model_path is None else model_path
        self.models: dict = {}
        self.deadline = monotonic() + BUDGET_SECONDS

    def score(self, candidate: dict, *, now: datetime) -> dict:
        if monotonic() > self.deadline:
            raise ValueError("COMBO_AGREEMENT_BUDGET_EXHAUSTED")
        league = int(candidate["league_id"])
        if league not in self.models:
            try:
                store = ResearchStore(self.model_path, readonly=True)
                try:
                    store.connection.set_progress_handler(lambda: int(monotonic() > self.deadline), 1000)
                    row = store.connection.execute("""
                        SELECT identity,CASE WHEN length(document)<=2097152 THEN document END,length(document) FROM dc_research_records
                        WHERE kind='model' AND json_extract(document,'$.league_id')=?
                        AND json_extract(document,'$.input_as_of')<=?
                        ORDER BY json_extract(document,'$.input_as_of') DESC,identity DESC LIMIT 1
                    """, (league, now.isoformat())).fetchone()
                    if row is None:
                        raise ValueError("COMBO_DC_MODEL_UNAVAILABLE")
                    if row[2] > MAX_DOCUMENT_BYTES:
                        raise ValueError("COMBO_DC_MODEL_CAPACITY")
                    artifact = json.loads(row[1])
                    if row[0] != artifact["fingerprint"]:
                        raise ValueError("COMBO_DC_MODEL_IDENTITY_MISMATCH")
                    verify_artifact(artifact, plan=load_plan())
                    self.models[league] = artifact
                finally:
                    store.close()
            except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError):
                self.models[league] = None
        artifact = self.models[league]
        if monotonic() > self.deadline:
            raise ValueError("COMBO_AGREEMENT_BUDGET_EXHAUSTED")
        if artifact is None:
            raise ValueError("COMBO_DC_MODEL_UNAVAILABLE")
        fid = int(candidate["fixture_id"])
        prefix = str(fid) + ":"
        row = self.repository.connection.execute("""
            SELECT content_fingerprint,CASE WHEN length(document_json)<=2097152 THEN document_json END,length(document_json)
            FROM lab_v2_shadow_evidence
            WHERE kind='market_consensus' AND identity>=? AND identity<?
            AND json_extract(document_json,'$.retrieved_at_utc')=?
            AND EXISTS (SELECT 1 FROM json_each(document_json,'$.quotes') q
                WHERE json_extract(q.value,'$.provenance_fingerprint')=?)
            AND created_at_utc<=? ORDER BY created_at_utc DESC,identity DESC LIMIT 1
        """, (prefix, prefix + "\uffff", candidate["goalvision_retrieved_at_utc"],
              candidate["quote_provenance_fingerprint"], now.isoformat())).fetchone()
        if row is None or row[2] > MAX_DOCUMENT_BYTES:
            raise ValueError("COMBO_CURRENT_CONSENSUS_UNAVAILABLE")
        consensus = json.loads(row[1])
        if fingerprint(consensus) != row[0]:
            raise ValueError("COMBO_CURRENT_CONSENSUS_HASH_MISMATCH")
        result = evidence(candidate, artifact, consensus, now=now, verified=True)
        if monotonic() > self.deadline:
            raise ValueError("COMBO_AGREEMENT_BUDGET_EXHAUSTED")
        return result
