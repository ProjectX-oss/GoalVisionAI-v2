from __future__ import annotations
import sqlite3
import pytest
from app.adaptive_lab.repository import AuditRepository,TABLES,SCHEMA_VERSION
from app.adaptive_lab.observations import ingest
from .conftest import frozen,START


def test_fresh_upgrade_replay_and_integrity(tmp_path):
    path=tmp_path/'db.sqlite'
    repo=AuditRepository(path)
    repo.connection.execute('DELETE FROM adaptive_schema WHERE version=2')
    repo.close()
    repo=AuditRepository(path)
    assert repo.connection.execute('SELECT max(version) FROM adaptive_schema').fetchone()[0]==SCHEMA_VERSION
    repo.migrate()
    assert list(repo.connection.execute('PRAGMA foreign_key_check'))==[]
    assert repo.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    repo.close()


def test_foreign_keys_and_stream_links(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.append('learning_observations','bad','LIVE',{},START.isoformat(),source_id='missing')
    repo.append('source_records','source','PREMATCH',{},START.isoformat())
    with pytest.raises(sqlite3.IntegrityError):
        repo.append('learning_observations','bad','LIVE',{},START.isoformat(),source_id='source')
    with pytest.raises(ValueError,match='COMBO'):
        repo.append('learning_observations','bad','COMBO',{},START.isoformat(),source_id='source')


@pytest.mark.parametrize('action',['UPDATE','DELETE'])
def test_all_tables_have_append_only_guards(repo,action):
    triggers={r[0] for r in repo.connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert all(t+'_no_'+action.lower() in triggers for t in TABLES)
    p,r,s=frozen(); ingest(repo,p,r,s,stream='PREMATCH',publication_id='p')
    command="UPDATE learning_observations SET document='{}'" if action=='UPDATE' else 'DELETE FROM learning_observations'
    with pytest.raises(sqlite3.IntegrityError,match='immutable'):
        repo.connection.execute(command)


def test_readonly_never_creates_or_mutates(tmp_path):
    with pytest.raises(sqlite3.OperationalError): AuditRepository(tmp_path/'missing',readonly=True)
    path=tmp_path/'audit'; AuditRepository(path).close()
    repo=AuditRepository(path,readonly=True)
    with pytest.raises(ValueError,match='READ_ONLY'): repo.append('source_records','x','LIVE',{},START.isoformat())
    repo.close()


def test_transaction_rolls_back_all_rows(repo):
    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.append('source_records','one','LIVE',{},START.isoformat())
            raise RuntimeError('injected crash')
    assert repo.all('source_records')==[]


def test_authoritative_or_official_database_never_migrated(tmp_path):
    path=tmp_path/'official.db'
    conn=sqlite3.connect(path);conn.execute('CREATE TABLE official_statistics(id INTEGER)');conn.commit();conn.close()
    before=path.read_bytes()
    with pytest.raises(ValueError,match='DEDICATED_LAB'):
        AuditRepository(path)
    assert path.read_bytes()==before
