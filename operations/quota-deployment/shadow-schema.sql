
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
                CREATE TABLE IF NOT EXISTS lab_v2_final_review_pending (
                    fixture_id INTEGER NOT NULL,
                    market TEXT NOT NULL,
                    state TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    PRIMARY KEY (fixture_id, market)
                );
                CREATE INDEX IF NOT EXISTS lab_v2_early_candidate_kickoff
                ON lab_v2_shadow_evidence(json_extract(document_json, '$.kickoff_utc'))
                WHERE kind='candidate' AND json_extract(document_json, '$.stage')='EARLY_CANDIDATE';
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
