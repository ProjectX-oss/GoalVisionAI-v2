"""Batch quota reads preserve verified evidence and leave room for contention retries."""
from datetime import timedelta
import pytest
from app.adaptive_lab import repository as module
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.quota import SharedQuota
from .conftest import START
from .test_quota_cli import quota

def seed(repo):
    for identity, stream, seconds in (("old","PREMATCH",-61),("b","LIVE",0),
                                      ("a","PREMATCH",0),("later","LIVE",1)):
        repo.append("quota_claims",identity,stream,
                    {"id":identity,"category":"SETTLEMENT","created_at":(START+timedelta(seconds=seconds)).isoformat()},
                    (START+timedelta(seconds=seconds)).isoformat())

def test_batch_same_order_boundary_and_single_select(tmp_path):
    repo=AuditRepository(tmp_path/"audit.db");seed(repo)
    try:
        expected=[r for r in repo.all("quota_claims") if r["created_at"]>=START.isoformat()]
        statements=[];repo.connection.set_trace_callback(statements.append)
        assert repo.quota_since(START.isoformat())==expected
        assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")])==1
        assert [r["id"] for r in expected]==["a","b","later"]
    finally:repo.close()

def test_cursor_closed_before_hashing_and_membership_frozen(tmp_path,monkeypatch):
    path=tmp_path/"audit.db";writer=AuditRepository(path);seed(writer)
    reader=AuditRepository(path,readonly=True);original=module.digest;claims=[]
    def hashing(value):
        if not claims:
            claims.append("inside")
            claim,stage=SharedQuota(writer)._attempt("SETTLEMENT",now=START,provider=quota())
            assert claim is not None,stage
            claims.append(claim)
        return original(value)
    monkeypatch.setattr(module,"digest",hashing)
    try:
        assert [r["id"] for r in reader.quota_since(START.isoformat())]==["a","b","later"]
        assert len(claims)==2 and not reader.connection.in_transaction
    finally:reader.close();writer.close()

def test_corruption_is_rejected(tmp_path):
    repo=AuditRepository(tmp_path/"audit.db");seed(repo)
    try:
        repo.connection.execute("DROP TRIGGER quota_claims_no_update")
        repo.connection.execute("UPDATE quota_claims SET fingerprint='bad' WHERE id='a'")
        with pytest.raises(ValueError,match="ARTIFACT_INTEGRITY_FAILURE"):
            repo.quota_since(START.isoformat())
    finally:repo.close()

def test_explicit_snapshot_stays_owned_by_caller(tmp_path):
    path=tmp_path/"audit.db";writer=AuditRepository(path);seed(writer)
    reader=AuditRepository(path,readonly=True)
    try:
        reader.connection.execute("BEGIN")
        assert len(reader.quota_since(START.isoformat()))==3
        assert reader.connection.in_transaction
        claim,stage=SharedQuota(writer)._attempt("SETTLEMENT",now=START,provider=quota())
        assert claim is None and stage=="RESERVE_COMMIT"
        reader.connection.rollback()
        assert SharedQuota(writer)._attempt("SETTLEMENT",now=START,provider=quota())[0] is not None
    finally:reader.close();writer.close()
