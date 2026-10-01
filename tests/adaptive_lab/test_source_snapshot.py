"""Reader stability must not block the authoritative ledger writer."""
import json
import sqlite3
import pytest
from app.adaptive_lab.contracts import digest
from app.adaptive_lab.observations import ReadOnlyLedger


def source(path):
    db = sqlite3.connect(path, timeout=.05)
    db.execute("CREATE TABLE evidence(kind,identity,document,fingerprint)")
    value = {"status": "BEFORE"}
    db.execute("INSERT INTO evidence VALUES(?,?,?,?)",
               ("item", "1", json.dumps(value), digest(value)))
    db.commit()
    return db


def test_snapshot_releases_source_lock_and_keeps_consistent_view(tmp_path):
    path = tmp_path / "ledger.db"
    writer = source(path)
    reader = ReadOnlyLedger(path)
    try:
        assert reader.get("item", "1") == {"status": "BEFORE"}
        value = {"status": "AFTER"}
        writer.execute("UPDATE evidence SET document=?,fingerprint=?",
                       (json.dumps(value), digest(value)))
        writer.commit()  # fails with database locked under the former BEGIN reader
        assert reader.all("item") == [{"status": "BEFORE"}]
        assert writer.execute("SELECT document FROM evidence").fetchone()[0] == json.dumps(value)
        with pytest.raises(sqlite3.OperationalError):
            reader.connection.execute("DELETE FROM evidence")
    finally:
        reader.close()
        writer.close()


def test_snapshot_limit_fails_closed_without_leaking_source_lock(tmp_path):
    path = tmp_path / "ledger.db"
    writer = source(path)
    with pytest.raises(ValueError, match="SOURCE_SNAPSHOT_TOO_LARGE"):
        ReadOnlyLedger(path, max_snapshot_bytes=1)
    writer.execute("DELETE FROM evidence")
    writer.commit()
    writer.close()


def test_snapshot_preserves_fingerprint_validation(tmp_path):
    path = tmp_path / "ledger.db"
    writer = source(path)
    writer.execute("UPDATE evidence SET fingerprint='corrupt'")
    writer.commit()
    reader = ReadOnlyLedger(path)
    with pytest.raises(ValueError, match="SOURCE_INTEGRITY_FAILURE"):
        reader.get("item", "1")
    reader.close()
    writer.close()
