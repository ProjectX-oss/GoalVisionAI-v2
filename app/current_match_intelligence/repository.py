"""Append-only SQLite persistence and cross-run provider cache."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from app.database import Database

from .canonical import canonical_json, fingerprint
from .models import CurrentMatchIntelligenceSnapshot


class IntelligenceConflictError(RuntimeError):
    pass


class SQLiteCurrentMatchIntelligenceRepository:
    """Owns only storage; normalization and freshness remain service concerns."""

    def __init__(self, database: Database) -> None:
        self.connection = database.connection
        self._migrate()

    def _migrate(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS current_match_intelligence_cache (
                    observation_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    query_fingerprint TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    provider_timestamp TEXT,
                    payload_fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(endpoint, query_fingerprint, retrieved_at, payload_fingerprint)
                );
                CREATE INDEX IF NOT EXISTS idx_cmi_cache_lookup
                    ON current_match_intelligence_cache(endpoint, query_fingerprint, expires_at, retrieved_at);
                CREATE TABLE IF NOT EXISTS current_match_intelligence_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    fixture_id TEXT NOT NULL,
                    snapshot_version INTEGER NOT NULL,
                    kickoff_utc TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL UNIQUE,
                    snapshot_json TEXT NOT NULL,
                    UNIQUE(fixture_id, snapshot_version)
                );
                CREATE INDEX IF NOT EXISTS idx_cmi_snapshot_fixture
                    ON current_match_intelligence_snapshots(fixture_id, snapshot_version DESC);
                CREATE TRIGGER IF NOT EXISTS current_match_intelligence_cache_no_update
                    BEFORE UPDATE ON current_match_intelligence_cache
                    BEGIN SELECT RAISE(ABORT, 'current intelligence cache is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS current_match_intelligence_cache_no_delete
                    BEFORE DELETE ON current_match_intelligence_cache
                    BEGIN SELECT RAISE(ABORT, 'current intelligence cache is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS current_match_intelligence_snapshot_no_update
                    BEFORE UPDATE ON current_match_intelligence_snapshots
                    BEGIN SELECT RAISE(ABORT, 'current intelligence snapshots are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS current_match_intelligence_snapshot_no_delete
                    BEFORE DELETE ON current_match_intelligence_snapshots
                    BEGIN SELECT RAISE(ABORT, 'current intelligence snapshots are immutable'); END;
                """
            )

    def cached(
        self, endpoint: str, query: dict[str, object], *, now: datetime
    ) -> dict | None:
        query_fp = fingerprint(query)
        row = self.connection.execute(
            """SELECT * FROM current_match_intelligence_cache
            WHERE endpoint=? AND query_fingerprint=? AND expires_at>=?
            ORDER BY retrieved_at DESC, observation_id DESC LIMIT 1""",
            (endpoint, query_fp, now.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return {
            "payload": json.loads(row["payload_json"]),
            "retrieved_at": datetime.fromisoformat(row["retrieved_at"]),
            "expires_at": datetime.fromisoformat(row["expires_at"]),
            "provider_timestamp": (
                datetime.fromisoformat(row["provider_timestamp"])
                if row["provider_timestamp"] else None
            ),
        }

    def append_cache(
        self,
        *,
        provider: str,
        endpoint: str,
        query: dict[str, object],
        retrieved_at: datetime,
        expires_at: datetime,
        provider_timestamp: datetime | None,
        payload: object,
    ) -> None:
        payload_fp = fingerprint(payload)
        query_fp = fingerprint(query)
        observation_id = "cmi-cache-" + fingerprint(
            (provider, endpoint, query_fp, retrieved_at, payload_fp)
        )
        with self.connection:
            self.connection.execute(
                """INSERT OR IGNORE INTO current_match_intelligence_cache
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    observation_id, provider, endpoint, query_fp,
                    canonical_json(query), retrieved_at.isoformat(),
                    expires_at.isoformat(),
                    provider_timestamp.isoformat() if provider_timestamp else None,
                    payload_fp, canonical_json(payload),
                ),
            )

    def append_snapshot(
        self, material: dict[str, object]
    ) -> CurrentMatchIntelligenceSnapshot:
        from .serialization import snapshot_from_document

        content_fp = fingerprint(material)
        existing = self.connection.execute(
            "SELECT snapshot_json FROM current_match_intelligence_snapshots WHERE content_fingerprint=?",
            (content_fp,),
        ).fetchone()
        if existing:
            return snapshot_from_document(json.loads(existing[0]))
        fixture_id = str(material["fixture_id"])
        row = self.connection.execute(
            "SELECT COALESCE(MAX(snapshot_version), 0) FROM current_match_intelligence_snapshots WHERE fixture_id=?",
            (fixture_id,),
        ).fetchone()
        version = int(row[0]) + 1
        snapshot_id = "cmi-snapshot-" + fingerprint((fixture_id, version, content_fp))
        document = {
            **material,
            "snapshot_id": snapshot_id,
            "version": version,
            "content_fingerprint": content_fp,
        }
        try:
            with self.connection:
                self.connection.execute(
                    """INSERT INTO current_match_intelligence_snapshots
                    VALUES (?,?,?,?,?,?,?)""",
                    (
                        snapshot_id, fixture_id, version,
                        str(material["kickoff_utc"]), str(material["evaluated_at"]),
                        content_fp, canonical_json(document),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise IntelligenceConflictError("CURRENT_INTELLIGENCE_VERSION_CONFLICT") from exc
        return snapshot_from_document(document)

    def load(self, snapshot_id: str) -> CurrentMatchIntelligenceSnapshot | None:
        from .serialization import snapshot_from_document

        row = self.connection.execute(
            "SELECT snapshot_json FROM current_match_intelligence_snapshots WHERE snapshot_id=?",
            (snapshot_id,),
        ).fetchone()
        return snapshot_from_document(json.loads(row[0])) if row else None

    def latest_for_fixture(
        self, fixture_id: str, *, at_or_before: datetime | None = None
    ) -> CurrentMatchIntelligenceSnapshot | None:
        from .serialization import snapshot_from_document

        clause = "AND evaluated_at<=?" if at_or_before else ""
        values: tuple[object, ...] = (
            (fixture_id, at_or_before.isoformat()) if at_or_before else (fixture_id,)
        )
        row = self.connection.execute(
            f"""SELECT snapshot_json FROM current_match_intelligence_snapshots
            WHERE fixture_id=? {clause}
            ORDER BY snapshot_version DESC LIMIT 1""",
            values,
        ).fetchone()
        return snapshot_from_document(json.loads(row[0])) if row else None
