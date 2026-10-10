"""Keep immutable-history verification from blocking independent quota commits."""
from datetime import timedelta

import pytest

from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.quota import SharedQuota
from .conftest import START
from .test_quota_cli import quota


def populate(repository):
    for identity, stream, offset in (("b", "PREMATCH", 0), ("a", "PREMATCH", 0),
                                     ("live", "LIVE", 1), ("c", "PREMATCH", 2)):
        repository.append("source_records", identity, stream, {"id": identity},
                          (START + timedelta(seconds=offset)).isoformat())


@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("stream,expected", [(None, ["a", "b", "live", "c"]),
                                            ("PREMATCH", ["a", "b", "c"])])
def test_quota_commits_during_history_verification(tmp_path, monkeypatch, readonly, stream, expected):
    path = tmp_path / "audit.db"
    writer = AuditRepository(path)
    populate(writer)
    reader = AuditRepository(path, readonly=readonly)
    original = reader.get
    attempts = []
    def verify(table, identity):
        # The slow part (JSON decode/hash in get) must not keep the ID cursor open.
        if not attempts:
            claim, stage = SharedQuota(writer)._attempt("SETTLEMENT", now=START, provider=quota())
            attempts.append((claim, stage))
            assert claim is not None, "history reader blocks unrelated durable quota COMMIT"
        return original(table, identity)
    monkeypatch.setattr(reader, "get", verify)
    try:
        assert [row["id"] for row in reader.all("source_records", stream)] == expected
        assert len(writer.all("quota_claims")) == 1
        assert not reader.connection.in_transaction
        assert not writer.connection.in_transaction
    finally:
        reader.close()
        writer.close()


def test_legacy_open_cursor_reproduces_commit_busy(tmp_path):
    path = tmp_path / "audit.db"
    writer = AuditRepository(path)
    populate(writer)
    reader = AuditRepository(path, readonly=True)
    cursor = reader.connection.execute("SELECT id FROM source_records ORDER BY created_at,id")
    try:
        cursor.fetchone()  # Leaves more rows active in rollback-journal mode.
        claim, stage = SharedQuota(writer)._attempt("SETTLEMENT", now=START, provider=quota())
        assert claim is None and stage == "RESERVE_COMMIT"
        assert not writer.connection.in_transaction
        assert writer.all("quota_claims") == []
        cursor.close()
        assert SharedQuota(writer)._attempt("SETTLEMENT", now=START, provider=quota())[0] is not None
    finally:
        cursor.close()
        reader.close()
        writer.close()


def test_membership_frozen_before_verification_and_integrity_retained(tmp_path, monkeypatch):
    path = tmp_path / "audit.db"
    writer = AuditRepository(path)
    populate(writer)
    reader = AuditRepository(path, readonly=True)
    original = reader.get
    inserted = []
    def verify(table, identity):
        if not inserted:
            writer.append("source_records", "later", "PREMATCH", {"id": "later"}, START.isoformat())
            inserted.append(True)
        return original(table, identity)
    monkeypatch.setattr(reader, "get", verify)
    try:
        assert [r["id"] for r in reader.all("source_records")] == ["a", "b", "live", "c"]
        writer.connection.execute("DROP TRIGGER source_records_no_update")
        writer.connection.execute("UPDATE source_records SET fingerprint='corrupt' WHERE id='a'")
        with pytest.raises(ValueError, match="ARTIFACT_INTEGRITY_FAILURE"):
            reader.all("source_records")
    finally:
        reader.close()
        writer.close()


def test_explicit_transaction_remains_owned_by_caller(tmp_path):
    path = tmp_path / "audit.db"
    writer = AuditRepository(path)
    populate(writer)
    reader = AuditRepository(path, readonly=True)
    try:
        reader.connection.execute("BEGIN")
        assert len(reader.all("source_records")) == 4
        assert reader.connection.in_transaction
        claim, stage = SharedQuota(writer)._attempt("SETTLEMENT", now=START, provider=quota())
        assert claim is None and stage == "RESERVE_COMMIT"
        reader.connection.rollback()
        assert SharedQuota(writer)._attempt("SETTLEMENT", now=START, provider=quota())[0] is not None
    finally:
        reader.close()
        writer.close()
