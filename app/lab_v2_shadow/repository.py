"""Append-only persistence for LAB_V2_SHADOW evidence only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint


class ShadowEvidenceRepository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS lab_v2_shadow_evidence (
                    kind TEXT NOT NULL,
                    identity TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (kind, identity)
                );
                CREATE TABLE IF NOT EXISTS lab_v2_provider_cache (
                    cache_id TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    query_fingerprint TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    retrieved_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    payload_fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(endpoint, query_fingerprint, retrieved_at_utc, payload_fingerprint)
                );
                CREATE INDEX IF NOT EXISTS lab_v2_provider_cache_lookup
                ON lab_v2_provider_cache(endpoint, query_fingerprint, expires_at_utc, retrieved_at_utc);
                CREATE TRIGGER IF NOT EXISTS lab_v2_shadow_no_update
                BEFORE UPDATE ON lab_v2_shadow_evidence
                BEGIN SELECT RAISE(ABORT, 'LAB V2 shadow evidence is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS lab_v2_shadow_no_delete
                BEFORE DELETE ON lab_v2_shadow_evidence
                BEGIN SELECT RAISE(ABORT, 'LAB V2 shadow evidence is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS lab_v2_provider_cache_no_update
                BEFORE UPDATE ON lab_v2_provider_cache
                BEGIN SELECT RAISE(ABORT, 'LAB V2 provider cache is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS lab_v2_provider_cache_no_delete
                BEFORE DELETE ON lab_v2_provider_cache
                BEGIN SELECT RAISE(ABORT, 'LAB V2 provider cache is immutable'); END;
                """
            )

    def append(self, kind: str, identity: str, document: dict[str, object], *, created_at: datetime) -> bool:
        clock = created_at.astimezone(timezone.utc)
        content = canonical_json(document)
        content_fingerprint = fingerprint(document)
        existing = self.connection.execute(
            "SELECT content_fingerprint FROM lab_v2_shadow_evidence WHERE kind=? AND identity=?",
            (kind, identity),
        ).fetchone()
        if existing is not None:
            if existing[0] != content_fingerprint:
                raise ValueError("LAB_V2_SHADOW_EVIDENCE_CONFLICT")
            return False
        with self.connection:
            self.connection.execute(
                "INSERT INTO lab_v2_shadow_evidence VALUES (?,?,?,?,?)",
                (kind, identity, clock.isoformat(), content_fingerprint, content),
            )
        return True

    def all(self, kind: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT document_json FROM lab_v2_shadow_evidence WHERE kind=? ORDER BY created_at_utc, identity",
            (kind,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def cached(self, endpoint: str, query: dict[str, object], *, now: datetime) -> dict | None:
        query_fingerprint = fingerprint(query)
        row = self.connection.execute(
            """SELECT payload_json,retrieved_at_utc FROM lab_v2_provider_cache
            WHERE endpoint=? AND query_fingerprint=? AND expires_at_utc>=?
            ORDER BY retrieved_at_utc DESC LIMIT 1""",
            (endpoint, query_fingerprint, now.astimezone(timezone.utc).isoformat()),
        ).fetchone()
        return ({"payload": json.loads(row[0]), "retrieved_at": datetime.fromisoformat(row[1])}
                if row else None)

    def append_cache(
        self, endpoint: str, query: dict[str, object], payload: object, *,
        retrieved_at: datetime, ttl: timedelta,
    ) -> None:
        clock = retrieved_at.astimezone(timezone.utc)
        query_fingerprint, payload_fingerprint = fingerprint(query), fingerprint(payload)
        identity = "lab-v2-cache-" + fingerprint((endpoint, query_fingerprint, clock, payload_fingerprint))
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO lab_v2_provider_cache VALUES (?,?,?,?,?,?,?,?)",
                (identity, endpoint, query_fingerprint, canonical_json(query), clock.isoformat(),
                 (clock + ttl).isoformat(), payload_fingerprint, canonical_json(payload)),
            )

    def close(self) -> None:
        self.connection.close()
