"""Offline incident replay and bounded scans beside active synthetic producers."""
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest

from app.admin_alerts import cli, sources
from app.admin_alerts.rules import compact
from app.admin_alerts.store import Store
from test_monitor import NOW, props, record


def rejected(**changes: object) -> dict:
    return dict(prediction_id='accuracy-single', status='SELECTION_ORIGIN_OR_APPROVAL_INVALID',
                stage='REJECTED_BEFORE_TRANSPORT', transport_attempted=False,
                acknowledgement_received=False, receipt_persisted=False,
                reconciliation_required=False, **changes)


@pytest.mark.parametrize('status', ['SELECTION_ORIGIN_OR_APPROVAL_INVALID', 'STALE_CURRENT_ODDS', 'FAILED', 'DEGRADED'])
def test_pure_pretransport_rejection_is_not_delivery_failure(status):
    items = [{**rejected(), 'prediction_id': str(index), 'status': status} for index in range(3)]
    events = compact(record(delivery_status='DEGRADED', telegram_sends=0,
                           controlled_publication={'deliveries': items}), 'compact', NOW)
    assert not [e for e in events if e.rule in {'DELIVERY_FAILURE', 'DELIVERY_UNCERTAIN'} and not e.healthy]
    integrity = [e for e in events if e.rule == 'INTEGRITY_FAILURE']
    assert len(integrity) == (3 if status == 'SELECTION_ORIGIN_OR_APPROVAL_INVALID' else 0)


@pytest.mark.parametrize('status', ['FAILED', 'DEGRADED', 'UNKNOWN', 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'])
def test_attempted_transport_is_still_alerted(status):
    item = {**rejected(), 'status': status, 'transport_attempted': True, 'stage': 'TRANSPORT'}
    events = compact(record(delivery_status='DEGRADED', controlled_publication={'deliveries': [rejected(), item]}), 'compact', NOW)
    assert any(e.rule == 'DELIVERY_UNCERTAIN' and not e.healthy for e in events)


@pytest.mark.parametrize('change', [
    {'persistence_failure': 'RECEIPT'}, {'reconciliation_required': True},
    {'acknowledgement_received': True}, {'transport_failure_kind': 'TIMEOUT'},
    {'unknown_marker_persisted': True}, {'sent': True}, {'transport_attempted': None},
])
def test_uncertainty_or_persistence_cannot_be_hidden_by_stage(change):
    events = compact(record(delivery_status='DEGRADED', controlled_publication={
        'deliveries': [{**rejected(), **change}]}), 'compact', NOW)
    assert any(e.rule in {'DELIVERY_FAILURE', 'DELIVERY_UNCERTAIN', 'CYCLE_PERSISTENCE'} and not e.healthy for e in events)


@pytest.mark.parametrize('publication', [
    {}, {'deliveries': []}, {'deliveries': [None]},
    {'deliveries': [rejected()] * 201},
    {'deliveries': [rejected()], 'failure': {'code': 'LAB_DELIVERY_PERSISTENCE_FAILED'}},
])
def test_aggregate_failure_without_complete_no_transport_proof_is_preserved(publication):
    events = compact(record(delivery_status='FAILED', controlled_publication=publication), 'compact', NOW)
    assert any(e.rule == 'DELIVERY_FAILURE' and not e.healthy for e in events)


def databases(root: Path) -> tuple[Path, Path]:
    ledger, health = root/'ledger.db', root/'health.db'
    with sqlite3.connect(ledger) as db:
        db.execute('CREATE TABLE evidence(kind TEXT,identity TEXT,document TEXT,PRIMARY KEY(kind,identity))')
        db.execute("INSERT INTO evidence VALUES ('claim','single:unresolved','{}')")
    db.close()
    with sqlite3.connect(health) as db:
        for table in ('cycle_health', 'observer_runs'):
            db.execute(f'CREATE TABLE {table}(id TEXT,created_at TEXT,stream TEXT,document TEXT)')
            db.execute(f'CREATE INDEX {table}_stream_time ON {table}(stream,created_at,id)')
        for table in ('weekly_claims', 'weekly_receipts'):
            db.execute(f'CREATE TABLE {table}(id TEXT PRIMARY KEY,stream TEXT)')
        db.execute("INSERT INTO weekly_claims VALUES ('week1','PREMATCH')")
    db.close()
    return ledger, health


@pytest.mark.parametrize('producer', ['running', 'unknown', 'reserved_lock', 'exclusive_lock', 'unsafe_wal'])
def test_active_producers_do_not_defer_real_readonly_scans(tmp_path, producer):
    source = tmp_path/'producer'; source.mkdir()
    ledger, health = databases(source)
    writer = None
    if producer in {'reserved_lock', 'exclusive_lock', 'unsafe_wal'}:
        writer = sqlite3.connect(ledger)
        if producer == 'unsafe_wal':
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute("INSERT INTO evidence VALUES ('claim','single:wal','{}')")
            writer.commit()
        else:
            writer.execute('BEGIN EXCLUSIVE' if producer == 'exclusive_lock' else 'BEGIN IMMEDIATE')
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    hashes = {key: hashlib.sha256(data).hexdigest() for key, data in before.items()}
    stdout = tmp_path/'output'; stdout.write_text('')
    config = dict(stdout=str(stdout), ledger_database=str(ledger), health_database=str(health),
                  release_environment=str(tmp_path/'absent'))
    admin = tmp_path/'admin'; admin.mkdir()
    store = Store(admin)
    # Previously this made a running producer generate the false alert immediately.
    with store.db:
        store.put('ledger_deferred_since', 1)
    store.close()
    seen = []
    original = sources.readonly

    def readonly(path: Path) -> sqlite3.Connection:
        seen.append(path)
        connection = original(path)
        assert connection.execute('PRAGMA query_only').fetchone()[0] == 1
        assert connection.execute('PRAGMA busy_timeout').fetchone()[0] == 100
        with pytest.raises(sqlite3.OperationalError):
            connection.execute('CREATE TABLE forbidden_write(x)')
        return connection

    try:
        with patch.object(cli, 'systemd', side_effect=OSError() if producer == 'unknown' else None,
                          return_value=props(running=True)), \
             patch.object(cli, 'journal', return_value=([], {})), \
             patch.object(cli, 'invocation_output', return_value=[]), \
             patch.object(sources, 'readonly', side_effect=readonly), \
             patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('NO NETWORK')):
            result = cli.scan(config, admin, no_send=True)
        assert result['telegram_sends'] == result['football_api_calls'] == 0
        assert ledger in seen and seen.count(health) == 2  # health and weekly scans
        report = json.loads((admin/'incident-report.json').read_text())
        assert 'CLAIM_REVIEW_DEFERRED_ACTIVE_OR_UNKNOWN_PRODUCER' not in json.dumps(report)
        store = Store(admin)
        try:
            state = store.get('ledger')
            assert store.get('weekly')['read_available'] is True
            assert state['read_available'] is (producer not in {'exclusive_lock', 'unsafe_wal'})
            if state['read_available']:
                assert store.db.execute("SELECT 1 FROM incidents WHERE rule='DELIVERY_UNCERTAIN' AND object_id='unresolved'").fetchone()
                assert not store.db.execute("SELECT 1 FROM incidents WHERE rule='MONITORING_COVERAGE_DEGRADED' AND object_id='ledger' AND state!='RECOVERED'").fetchone()
            else:
                assert 'READ_SCHEMA_OR_CURSOR_UNAVAILABLE' in json.dumps(report)
        finally:
            store.close()
        after = {p.name: p.read_bytes() for p in source.iterdir()}
        assert after == before
        assert {key: hashlib.sha256(data).hexdigest() for key, data in after.items()} == hashes
    finally:
        if writer:
            writer.close()


@pytest.mark.parametrize('field', ['telegram_sends', 'publication_attempt_count', 'send_attempted', 'singles_sent', 'combos_sent'])
def test_aggregate_transport_evidence_overrides_pretransport_items(field):
    publication = {'deliveries': [rejected()]}
    fields = {}
    if field in {'telegram_sends', 'publication_attempt_count'}:
        fields[field] = 1
    else:
        publication[field] = 1
    events = compact(record(delivery_status='DEGRADED', controlled_publication=publication, **fields), 'compact', NOW)
    assert any(e.rule == 'DELIVERY_FAILURE' and not e.healthy for e in events)
