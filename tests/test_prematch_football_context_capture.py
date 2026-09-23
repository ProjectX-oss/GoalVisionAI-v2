"""Phase C: fake transports, synthetic football facts and disposable databases only."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import httpx
import pytest

from app.football.client import FootballClient
from app.prematch_football_context import calculate_context, result_fingerprint
from app.prematch_football_context.capture.adapter import CaptureAdapter, CaptureScope, prepare_source
from app.prematch_football_context.capture.repository import DecisionReceipt, EvidenceRepository, ImmutableConflict
from app.prematch_football_context.capture.schema import initialize
from app.prematch_football_context.evidence import EvidenceUnavailable, replay_evidence, retain_evidence
from app.prematch_football_context.fingerprint import canonical_bytes
from app.prematch_football_context.source_adapter import FormatEvidence, legacy_cache_candidate, target_state, TargetState
from app.prematch_football_context.sources import SourceKind, digest, history_query, select_source, target_query
from tests.test_prematch_football_context_sources import T, binding, raw

CURRENT = CaptureScope(history_query(10, 2026), SourceKind.CURRENT, timedelta(hours=6))
PREVIOUS = CaptureScope(history_query(10, 2025), SourceKind.PREVIOUS, timedelta(hours=24))
TARGET = CaptureScope(target_query(9999), SourceKind.TARGET, timedelta(minutes=2))
END = T - timedelta(minutes=1)


@pytest.fixture(autouse=True)
def no_live_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('LIVE_IO_FORBIDDEN')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


@pytest.fixture
def store(tmp_path):
    path = tmp_path / 'capture.sqlite'
    initialize(path)
    repo = EvidenceRepository(path, writable=True, clock=lambda: END + timedelta(seconds=1))
    yield repo
    repo.close()


def material(*, scope=CURRENT, end=END, payload=None):
    rows = payload if payload is not None else [raw(i) for i in range(1, 9)]
    return prepare_source(scope, rows, end)


async def client_with_transport(observer, handler, *, clock=lambda: END):
    client = FootballClient(api_key='SYNTHETIC_SECRET', response_observer=observer, completion_clock=clock)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.BASE_URL)
    client.MIN_REQUEST_INTERVAL_SECONDS = 0
    return client


def select(candidate, cutoff=T):
    return select_source((candidate,), candidate.header.query, cutoff=cutoff, source_kind=candidate.header.kind)


def test_completion_after_body_before_parsing_and_injected_clock(store):
    events = []
    start = END - timedelta(seconds=3)
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            events.append(('request_start', start))
            yield b'{"response":'
            yield json.dumps([raw()]).encode()
            yield b'}'
            events.append(('body_complete', END))
    class Response(httpx.Response):
        def json(self, **kwargs):
            events.append(('parse', END + timedelta(seconds=2)))
            return super().json(**kwargs)
    async def handler(request):
        return Response(200, stream=Body(), request=request)
    def clock():
        assert events[-1][0] == 'body_complete'
        events.append(('clock', END))
        return END.astimezone(timezone(timedelta(hours=3)))
    adapter = CaptureAdapter(store, (CURRENT,))
    async def run():
        client = await client_with_transport(adapter, handler, clock=clock)
        try:
            assert await client.finished_matches(10, 2026, last=99) == [raw()]
            assert client.request_count == 1
        finally:
            await client.close()
    asyncio.run(run())
    source = store.load(store.inspect()[0].source_id)
    assert source.header.timing.retrieval_completed_at == END > start
    assert [e[0] for e in events][:4] == ['request_start', 'body_complete', 'clock', 'parse']
    assert source.header.timing.registered_at > END
    assert adapter.diagnostics() == {'CAPTURED': 1}


@pytest.mark.parametrize('failure', ['http', 'transport', 'provider_error'])
def test_failed_provider_has_no_successful_evidence(store, failure, monkeypatch):
    adapter = CaptureAdapter(store, (CURRENT,))
    calls = []
    async def no_wait(*args):
        pass
    monkeypatch.setattr('app.football.client.asyncio.sleep', no_wait)
    def handler(request):
        calls.append(request)
        if failure == 'transport':
            raise httpx.ReadTimeout('SYNTHETIC_SECRET', request=request)
        return httpx.Response(503 if failure == 'http' else 200,
            json={'errors': {'test': 'SYNTHETIC_SECRET'}, 'response': []}, request=request)
    async def run():
        client = await client_with_transport(adapter, handler)
        try:
            if failure == 'provider_error':
                assert await client.finished_matches(10, 2026, last=99) == []
                assert client.request_count == 1
            else:
                with pytest.raises(httpx.HTTPError):
                    await client.finished_matches(10, 2026, last=99)
                assert client.request_count == 3
        finally:
            await client.close()
    asyncio.run(run())
    assert store.inspect() == ()
    assert store.connection.execute('SELECT count(*) FROM fc_sources').fetchone()[0] == 0
    assert len(calls) == (1 if failure == 'provider_error' else 3)


def test_transient_retry_captures_only_success_and_preserves_attempts(store, monkeypatch):
    calls = []
    async def no_wait(*args):
        pass
    monkeypatch.setattr('app.football.client.asyncio.sleep', no_wait)
    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, json={'response': [raw()]}, request=request)
    async def run():
        client = await client_with_transport(CaptureAdapter(store, (CURRENT,)), handler)
        try:
            await client.finished_matches(10, 2026, last=99)
            assert client.request_count == 2
            assert client.response_metadata()['attempts'] == 2
        finally:
            await client.close()
    asyncio.run(run())
    assert len(store.inspect()) == 1


@pytest.mark.parametrize('failure', ['observer', 'clock', 'naive_clock', 'persistence'])
def test_sidecar_failures_preserve_success_no_retry_no_secret_log(store, monkeypatch, caplog, failure):
    payload = {'response': [raw()]}
    def fail(*args):
        raise OSError('SYNTHETIC_SECRET')
    adapter = CaptureAdapter(store, (CURRENT,))
    observer = fail if failure == 'observer' else adapter
    clock = fail if failure == 'clock' else (lambda: END.replace(tzinfo=None)) if failure == 'naive_clock' else lambda: END
    if failure == 'persistence':
        monkeypatch.setattr(store, '_commit', fail)
    async def run():
        client = await client_with_transport(observer, lambda request: httpx.Response(200, json=payload), clock=clock)
        try:
            assert await client.finished_matches(10, 2026, last=99) == payload['response']
            assert client.request_count == 1
            assert client.response_metadata()['errors'] == {}
            assert client.evidence_capture_failures == (0 if failure == 'persistence' else 1)
        finally:
            await client.close()
    asyncio.run(run())
    assert store.inspect() == ()
    assert 'SYNTHETIC_SECRET' not in caplog.text
    if failure == 'persistence':
        assert adapter.diagnostics() == {'UNAVAILABLE_CAPTURE_FAILURE': 1}


def test_sanitization_identity_replay_conflict_and_later_correction(store):
    rows = [raw()]
    rows[0]['authorization'] = 'SYNTHETIC_SECRET'
    rows[0]['players'] = [{'secret': 'SYNTHETIC_SECRET'}]
    first = store.register(material(payload=rows))
    replay = store.register(material(payload=[raw()]))
    assert replay.replayed and replace(replay, replayed=False) == first
    with pytest.raises(ImmutableConflict):
        store.register(material(payload=[raw(gf=5)]))
    changed = store.register(material(payload=[raw(gf=5)], end=END + timedelta(microseconds=1)))
    assert changed.source_id != first.source_id and not changed.replayed
    assert select(store.load(first.source_id)).selected.content != select(store.load(changed.source_id)).selected.content
    assert len(store.inspect()) == 2
    assert 'SYNTHETIC_SECRET' not in '\n'.join(store.connection.iterdump())
    header = store.load(first.source_id).header
    assert header.timing.provider_updated_at is None
    assert header.timing.provider_freshness == 'UNKNOWN'
    assert header.namespace == 'FC_DURABLE_SOURCE_V1'
    assert header.source_id == digest(material(payload=[raw()]))


@pytest.mark.parametrize('change', ['expiry', 'provider_updated_at'])
def test_same_capture_material_metadata_conflicts(store, change):
    original = material()
    store.register(original)
    new = dict(original)
    new[change] = (END + timedelta(hours=1) if change == 'expiry' else END - timedelta(days=1)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    with pytest.raises(ImmutableConflict):
        store.register(new)


def test_clock_is_sampled_only_after_source_commit_and_before_receipt(store):
    def clock():
        assert not store.connection.execute('SELECT * FROM fc_receipts').fetchall()
        # A second read-only connection can see the ENTIRE source, but cannot use it.
        path = Path(store.connection.execute('PRAGMA database_list').fetchone()[2])
        reader = EvidenceRepository(path)
        try:
            assert reader.connection.execute('SELECT count(*) FROM fc_sources').fetchone()[0] == 1
            assert reader.inspect() == ()
            with pytest.raises(EvidenceUnavailable):
                reader.load(digest(material()))
        finally:
            reader.close()
        return END + timedelta(seconds=5)
    store.clock = clock
    reg = store.register(material())
    assert reg.registered_at == END + timedelta(seconds=5)
    assert select(store.load(reg.source_id), END + timedelta(seconds=4)).verdict == 'UNAVAILABLE'


def test_registered_time_before_completion_rejected_no_valid_unit(store):
    store.clock = lambda: END - timedelta(microseconds=1)
    with pytest.raises(ValueError, match='REGISTRATION_BEFORE_RETRIEVAL'):
        store.register(material())
    assert store.inspect() == ()
    with pytest.raises(EvidenceUnavailable):
        store.load(digest(material()))


@pytest.mark.parametrize('commit_number', [1, 2])
def test_atomic_failure_and_explicit_orphan_retry(store, monkeypatch, commit_number):
    real_commit, calls = store._commit, []
    def fail_commit():
        calls.append(1)
        if len(calls) == commit_number:
            raise sqlite3.OperationalError('SYNTHETIC_COMMIT_FAILURE')
        real_commit()
    monkeypatch.setattr(store, '_commit', fail_commit)
    with pytest.raises(sqlite3.OperationalError):
        store.register(material())
    assert not store.connection.in_transaction
    assert store.connection.execute('SELECT count(*) FROM fc_sources').fetchone()[0] == commit_number - 1
    assert store.connection.execute('SELECT count(*) FROM fc_receipts').fetchone()[0] == 0
    assert store.inspect() == ()
    with pytest.raises(EvidenceUnavailable):
        store.load(digest(material()))
    monkeypatch.setattr(store, '_commit', real_commit)
    store.clock = lambda: END + timedelta(seconds=20)
    reg = store.register(material())
    assert reg.registered_at == END + timedelta(seconds=20)
    assert reg.source_id == digest(material())
    assert len(store.inspect()) == 1


def test_receipt_insert_failure_leaves_only_unavailable_complete_source(store):
    store.connection.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON fc_receipts BEGIN SELECT RAISE(ABORT,'INJECTED'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.register(material())
    assert store.inspect() == ()
    assert store.connection.execute('SELECT count(*) FROM fc_sources').fetchone()[0] == 1
    assert store.connection.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('table', ['fc_sources', 'fc_receipts'])
@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE', 'REPLACE'])
def test_database_immutability_guards(store, table, operation):
    store.register(material())
    with pytest.raises(sqlite3.IntegrityError, match='FC_IMMUTABLE'):
        if operation == 'UPDATE':
            field = 'source_id' if table == 'fc_sources' else 'ordering'
            store.connection.execute(f'UPDATE {table} SET {field}={field}')
        elif operation == 'DELETE':
            store.connection.execute(f'DELETE FROM {table}')
        else:
            store.connection.execute(f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}')
    assert len(store.inspect()) == 1


def test_disposable_fresh_upgrade_repeat_integrity_and_foreign_keys(tmp_path):
    for name, preexisting in [('fresh', False), ('empty_upgrade', True)]:
        path = tmp_path / name
        if preexisting:
            with sqlite3.connect(path) as conn:
                assert conn.execute('PRAGMA user_version').fetchone()[0] == 0
        initialize(path)
        writer = EvidenceRepository(path, clock=lambda: T, writable=True)
        reg = writer.register(material())
        initialize(path)
        assert writer.register(material()).replayed
        assert writer.load(reg.source_id)
        assert writer.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert writer.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert writer.connection.execute('PRAGMA user_version').fetchone()[0] == 1
        assert writer.connection.execute('PRAGMA synchronous').fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError):
            writer.connection.execute("INSERT INTO fc_receipts VALUES (99,'SOURCE','missing','time','hash')")
        writer.close()
    other = tmp_path / 'unrelated'
    with sqlite3.connect(other) as conn:
        conn.execute('CREATE TABLE unrelated(id)')
    before = other.read_bytes()
    with pytest.raises(ValueError, match='DEDICATED'):
        initialize(other)
    assert other.read_bytes() == before


def test_readonly_no_creation_or_auto_migration(tmp_path, store):
    missing = tmp_path / 'does_not_exist'
    with pytest.raises(sqlite3.OperationalError):
        EvidenceRepository(missing)
    assert not missing.exists()
    path = Path(store.connection.execute('PRAGMA database_list').fetchone()[2])
    reg = store.register(material())
    before = path.read_bytes()
    reader = EvidenceRepository(path)
    try:
        assert reader.load(reg.source_id) == store.load(reg.source_id)
        with pytest.raises(ValueError, match='READ_ONLY'):
            reader.register(material())
        with pytest.raises(ValueError, match='READ_ONLY'):
            reader.capture_cutoff()
    finally:
        reader.close()
    assert path.read_bytes() == before


def test_equality_order_proven_unproven_and_later_source(store):
    store.clock = lambda: T
    first = store.register(material(end=T))
    assert select(store.load(first.source_id)).decisions[0].verdict == 'ASOF_UNPROVEN'
    marker = store.capture_cutoff()
    proven = store.load(first.source_id, decision=marker)
    assert first.ordering < marker.ordering
    assert select(proven).verdict == 'SELECTED'
    later = store.register(material(scope=PREVIOUS, end=T, payload=[raw(season=2025)]))
    assert later.ordering > marker.ordering
    assert select(store.load(later.source_id, decision=marker)).decisions[0].verdict == 'ASOF_UNPROVEN'
    assert store.load(first.source_id, decision=marker) == proven
    for bad in (replace(marker, cutoff=T + timedelta(seconds=1)), replace(marker, receipt_hash='0' * 64),
                DecisionReceipt(T, 123456, '0' * 64)):
        with pytest.raises(EvidenceUnavailable):
            store.load(first.source_id, decision=bad)


def test_clock_regression_and_rolled_back_decision_cannot_prove_order(store, monkeypatch):
    reg = store.register(material())
    store.clock = lambda: END
    with pytest.raises(ValueError, match='CLOCK_REGRESSED'):
        store.capture_cutoff()
    store.clock = lambda: T
    def fail():
        raise OSError('commit failure')
    monkeypatch.setattr(store, '_commit', fail)
    with pytest.raises(OSError):
        store.capture_cutoff()
    assert store.connection.execute('SELECT count(*) FROM fc_receipts').fetchone()[0] == 1
    assert store.load(reg.source_id).header.timing.before_capture is None


def test_concurrent_exact_capture_one_identity_one_registration(store):
    path = Path(store.connection.execute('PRAGMA database_list').fetchone()[2])
    def capture():
        repo = EvidenceRepository(path, writable=True, clock=lambda: T)
        try:
            return repo.register(material())
        finally:
            repo.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = tuple(pool.map(lambda _: capture(), range(2)))
    assert a.source_id == b.source_id and a.ordering == b.ordering
    assert sorted([a.replayed, b.replayed]) == [False, True]
    assert len(store.inspect()) == 1


@pytest.mark.parametrize('corruption', ['content', 'hash', 'query', 'key', 'receipt_time', 'receipt_hash'])
def test_corrupted_persisted_evidence_fails_closed(store, corruption):
    reg = store.register(material())
    store.connection.execute('DROP TRIGGER fc_sources_no_update')
    store.connection.execute('DROP TRIGGER fc_receipts_no_update')
    if corruption.startswith('receipt'):
        column, value = ('observed_at', '2000-01-01T00:00:00.000000Z') if corruption == 'receipt_time' else ('receipt_hash', '0' * 64)
        store.connection.execute(f'UPDATE fc_receipts SET {column}=?', (value,))
    elif corruption == 'key':
        store.connection.execute('UPDATE fc_sources SET capture_key=?', ('0' * 64,))
    else:
        doc = material()
        if corruption == 'content':
            doc['content'] = doc['content'].replace('"goals_home":1', '"goals_home":9')
        elif corruption == 'hash':
            doc['content_hash'] = '0' * 64
        else:
            doc['query']['parameters'][0][1] = 44
        store.connection.execute('UPDATE fc_sources SET material_json=?', (canonical_bytes(doc).decode(),))
    with pytest.raises(EvidenceUnavailable):
        store.load(reg.source_id)


@pytest.mark.parametrize('verified_format', [False, True])
def test_full_durable_offline_selection_bundle_phase_a_replay(store, verified_format, monkeypatch):
    original = []
    for scope, rows in ((CURRENT, [raw(i) for i in range(1, 9)]),
                        (PREVIOUS, [raw(20, season=2025)]),
                        (TARGET, [raw(9999, status='NS', kickoff=T + timedelta(hours=1), gf=None, ga=None)])):
        original.append(store.register(material(scope=scope, payload=rows)))
    path = Path(store.connection.execute('PRAGMA database_list').fetchone()[2])
    reader = EvidenceRepository(path)
    def forbidden(*args, **kwargs):
        raise AssertionError('NO_PROVIDER_DURING_REPLAY')
    monkeypatch.setattr(FootballClient, '_get', forbidden)
    bind = binding() if verified_format else binding(current_format=FormatEvidence(10, 2026), previous_format=FormatEvidence(10, 2025))
    def bundle():
        by_kind = {c.header.kind: c for c in (reader.load(r.source_id) for r in original)}
        selections = tuple(select(by_kind[k]) for k in (SourceKind.TARGET, SourceKind.CURRENT, SourceKind.PREVIOUS))
        assert all(s.verdict == 'SELECTED' for s in selections)
        return retain_evidence(bind, selections)
    try:
        first = bundle()
        replay = replay_evidence(first)
        assert replay.result == calculate_context(replay.inputs)
        assert result_fingerprint(replay.result) == first.result_hash
        assert bundle() == first
        assert replay_evidence(bundle()) == replay
        if verified_format:
            assert all(f.value is not None for f in replay.result.features)
        else:
            assert all(f.value is None and 'REGULATION_UNVERIFIED' in f.reasons for f in replay.result.features)
        # Later immutable correction does not alter old exact pins or fingerprints.
        store.register(material(end=END + timedelta(microseconds=1), payload=[raw(gf=8)]))
        assert bundle() == first
    finally:
        reader.close()


@pytest.mark.parametrize('status', ['NS', 'TBD', '1H', 'FT', 'PST', 'CANC', 'ZZZ'])
def test_target_status_preserved_without_broadening(store, status):
    reg = store.register(material(scope=TARGET, payload=[raw(9999, status=status, kickoff=T + timedelta(hours=1))]))
    loaded = store.load(reg.source_id)
    assert json.loads(loaded.content)['rows'][0]['status'] == status
    target = select(loaded)
    current = select_source((), CURRENT.query, cutoff=T, source_kind=SourceKind.CURRENT)
    previous = select_source((), PREVIOUS.query, cutoff=T, source_kind=SourceKind.PREVIOUS)
    if status == 'NS':
        assert target_state(status) == TargetState.NOT_STARTED
        retain_evidence(binding(), (target, current, previous))
    else:
        with pytest.raises(EvidenceUnavailable, match='TARGET_STATUS'):
            retain_evidence(binding(), (target, current, previous))


def test_legacy_stays_unproven_and_unscoped_does_not_fetch(store):
    legacy = legacy_cache_candidate(source_id='legacy', query=CURRENT.query, kind=CURRENT.kind,
        retrieved_at=END, expiry=T + timedelta(hours=1), payload=[raw()])
    assert select(legacy).decisions[0].verdict == 'ASOF_UNPROVEN'
    adapter = CaptureAdapter(store, (CURRENT,))
    for endpoint, query in [('/fixtures', {'date': '2026-09-23'}), ('/odds', {'fixture': 9999}),
                            ('/fixtures', {'league': 10, 'season': 2026, 'status': 'FT', 'last': 100})]:
        assert adapter(endpoint, query, {'response': [raw()]}, END).status == 'UNAVAILABLE_UNSCOPED_QUERY'
    assert store.inspect() == ()
    assert adapter.diagnostics() == {'UNAVAILABLE_UNSCOPED_QUERY': 3}


def test_adapter_failure_conflict_diagnostics(store):
    adapter = CaptureAdapter(store, (CURRENT,))
    args = ('/fixtures', dict(CURRENT.query.parameters))
    assert adapter(*args, [raw()], END).status == 'CAPTURED'
    assert adapter(*args, [raw()], END).status == 'REPLAY'
    conflict = adapter(*args, [raw(gf=9)], END)
    assert conflict.status == 'UNAVAILABLE_CONFLICT' and conflict.registration is None
    assert adapter.diagnostics() == {'CAPTURED': 1, 'REPLAY': 1, 'UNAVAILABLE_CONFLICT': 1}


def test_import_and_default_startup_inert_no_store_no_clock(tmp_path):
    script = '''
import os, socket, sqlite3, sys
from unittest.mock import patch

def fail(*a, **k): raise AssertionError('SIDE_EFFECT')
def audit(event, args):
    if event.startswith(('socket.connect', 'sqlite3.connect')): fail()
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND): fail()
sys.addaudithook(audit)
with patch.object(sqlite3, 'connect', fail), patch.object(socket, 'create_connection', fail):
    import app.prematch_football_context.capture.adapter
    import app.prematch_football_context.capture.repository
    import app.prematch_football_context.capture.schema
assert not any(n.startswith(('telegram', 'app.adaptive_lab', 'app.live_lab', 'app.reviewed_historical_odds')) for n in sys.modules)
print('INERT')
'''
    result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'INERT'
    def forbidden():
        raise AssertionError('disabled observer must not sample clock')
    async def run():
        client = await client_with_transport(None, lambda request: httpx.Response(200, json={'response': [raw()]}), clock=forbidden)
        try:
            assert await client.finished_matches(10, 2026, last=99) == [raw()]
            assert client.evidence_capture_failures == 0
        finally:
            await client.close()
    asyncio.run(run())
    assert list(tmp_path.iterdir()) == []


def test_real_prematch_fetch_history_prediction_and_cache_parity(tmp_path, monkeypatch):
    """Real client → _fetch → _histories → _evaluate, with no calculation patch."""
    from app.lab_v2_shadow.capability import LeagueCapabilityCache
    from app.lab_v2_shadow.market_consensus import current_market_consensus
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from app.lab_v2_shadow.runner import LabV2ShadowRunner, _fixture_rows
    from tests.test_lab_v2_shadow import coverage, odds_payload

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return T if tz is not None else T.replace(tzinfo=None)
    monkeypatch.setattr('app.football.client.datetime', FixedDatetime)
    # isinstance must accept the injected FixedDatetime when validating completion.
    end = FixedDatetime.fromisoformat(END.isoformat())
    kickoff = T + timedelta(hours=4)
    target_row = raw(9999, status='NS', kickoff=kickoff, gf=None, ga=None)
    target_row['league'].update(name='Premier League', country='England', type='League')
    capabilities = LeagueCapabilityCache.from_api_payload({'response': [coverage(league_id=10)]}, retrieved_at=T)
    fixture = _fixture_rows({'response': [target_row]}, capabilities, T)[0]
    fixture['competition_profile'] = 'SENIOR_MEN_PRO'  # Explicit synthetic classification.
    odds = odds_payload(T, fixture_id=9999)
    consensus = current_market_consensus(odds, fixture_id=9999, retrieved_at=T, now=T)
    records = []
    for mode in ('off', 'on', 'failure'):
        path = tmp_path / (mode + '.sqlite')
        initialize(path)
        evidence = EvidenceRepository(path, writable=True, clock=lambda: T)
        sidecar = CaptureAdapter(evidence, (CURRENT, PREVIOUS, TARGET)) if mode != 'off' else None
        if mode == 'failure':
            def fail():
                raise sqlite3.OperationalError('injected disk failure')
            monkeypatch.setattr(evidence, '_commit', fail)
        shadow = ShadowEvidenceRepository(tmp_path / (mode + '-cache.sqlite'))
        requests = []
        def handler(request):
            requests.append((request.url.path, tuple(request.url.params.multi_items())))
            params = dict(request.url.params)
            if 'id' in params:
                rows = [target_row]
            else:
                assert params == {'league': '10', 'season': '2026', 'status': 'FT', 'last': '99'}
                rows = [raw(i, home=1 if i % 2 else 2, away=2 if i % 2 else 1) for i in range(1, 17)]
            return httpx.Response(200, json={'response': rows}, headers={
                'x-ratelimit-requests-limit': '7500', 'x-ratelimit-requests-remaining': '7000',
                'x-ratelimit-limit': '300', 'x-ratelimit-remaining': '290'})
        async def run():
            client = await client_with_transport(sidecar, handler, clock=lambda: end)
            runner = LabV2ShadowRunner(client, shadow, capability_cache_path=tmp_path / 'never_created', maximum_calls=40)
            try:
                first_target, _ = await runner._fetch('/fixtures', {'id': 9999}, lambda: client.fixture(9999),
                    clock=T, ttl=timedelta(minutes=2), use_cache=False)
                histories, adapters, skipped = await runner._histories([fixture], T)
                predictions = runner._evaluate([fixture], {9999: (odds, T, consensus)}, histories, adapters,
                                              {}, {}, {}, {}, T)
                assert predictions and runner.analysis_evidence[9999]['probability_available']
                before = client.request_count
                # Cache hits cannot become new evidence, and cause no new provider calls.
                again, _, _ = await runner._histories([fixture], T)
                assert again == histories and client.request_count == before
                assert runner.calls[-1]['cache'] == 'HIT'
                assert 'adaptive_features' not in canonical_bytes(predictions).decode()
                return (first_target, canonical_bytes(predictions), canonical_bytes(runner.analysis_evidence[9999]),
                        client.request_count, tuple(requests), client.response_metadata())
            finally:
                await client.close()
        records.append(asyncio.run(run()))
        assert len(evidence.inspect()) == (2 if mode == 'on' else 0)
        if mode == 'failure':
            assert sidecar.diagnostics() == {'UNAVAILABLE_CAPTURE_FAILURE': 2}
        # Isolated sidecar owns exactly its two tables; never the product ledgers.
        assert {r[0] for r in evidence.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {'fc_sources', 'fc_receipts'}
        evidence.close()
        shadow.close()
    assert records[0] == records[1] == records[2]
    assert records[0][3] == 2


def test_acknowledgement_committed_before_process_interruption_recovers_exactly(store, monkeypatch):
    real_commit, calls = store._commit, []
    def interrupted_after_commit():
        real_commit()
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('process lost return after durable commit')
    monkeypatch.setattr(store, '_commit', interrupted_after_commit)
    with pytest.raises(RuntimeError):
        store.register(material())
    # This commit succeeded; the failure was in returning its result, not persistence.
    original = store.inspect()[0]
    monkeypatch.setattr(store, '_commit', real_commit)
    store.clock = lambda: T + timedelta(days=1)
    recovered = store.register(material())
    assert recovered.replayed
    assert replace(recovered, replayed=False) == original


@pytest.mark.parametrize('payload,verdict', [({'response': None}, 'MALFORMED'),
    ([raw()] * 100, 'OVERSIZED'), ({'response': [], 'paging': {'current': 1, 'total': 2}}, 'INCOMPLETE_RESPONSE')])
def test_successful_http_unusable_payload_retained_as_unavailable(store, payload, verdict):
    receipt = store.register(material(payload=payload))
    candidate = store.load(receipt.source_id)
    assert select(candidate).verdict == verdict
    assert 'SYNTHETIC_SECRET' not in candidate.content


def test_no_unauthorized_dependencies_or_runtime_composition():
    import ast
    root = Path(__file__).resolve().parents[1]
    for path in (root / 'app/prematch_football_context/capture').glob('*.py'):
        tree = ast.parse(path.read_text())
        imports = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(name.startswith(('app.football', 'app.lab', 'app.adaptive', 'app.live', 'telegram',
            'app.database', 'app.reviewed_historical_odds')) for name in imports)
    client_source = (root / 'app/football/client.py').read_text()
    assert 'prematch_football_context' not in client_source
    assert 'response_observer' in client_source


def test_equal_time_durable_restart_replay_chain(store):
    store.clock = lambda: T
    history = store.register(material(end=T))
    target = store.register(material(scope=TARGET, end=T,
        payload=[raw(9999, status='NS', kickoff=T + timedelta(hours=1), gf=None, ga=None)]))
    marker = store.capture_cutoff()
    path = Path(store.connection.execute('PRAGMA database_list').fetchone()[2])
    reader = EvidenceRepository(path)
    try:
        recovered = reader.load_cutoff(marker.receipt_hash)
        assert recovered == marker
        selections = (select(reader.load(target.source_id, decision=recovered)),
                      select(reader.load(history.source_id, decision=recovered)),
                      select_source((), PREVIOUS.query, cutoff=T, source_kind=SourceKind.PREVIOUS))
        bundle = retain_evidence(binding(), selections)
        replay = replay_evidence(bundle)
        assert replay.inputs.target.source.available_before_capture
        assert replay.inputs.current.source.available_before_capture
        assert result_fingerprint(replay.result) == bundle.result_hash
        with pytest.raises(EvidenceUnavailable):
            reader.load_cutoff(history.receipt_hash)
        with pytest.raises(EvidenceUnavailable):
            reader.load_cutoff('0' * 64)
    finally:
        reader.close()


def test_no_partial_source_when_insert_is_rolled_back(store):
    store.connection.execute("CREATE TRIGGER fail_source AFTER INSERT ON fc_sources BEGIN SELECT RAISE(ABORT,'INJECTED'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.register(material())
    assert store.connection.execute('SELECT count(*) FROM fc_sources').fetchone()[0] == 0
    assert store.connection.execute('SELECT count(*) FROM fc_receipts').fetchone()[0] == 0


def test_incomplete_schema_is_not_silently_repaired_or_used(store):
    path = Path(store.connection.execute('PRAGMA database_list').fetchone()[2])
    store.connection.execute('DROP TRIGGER fc_sources_no_update')
    before = path.read_bytes()
    with pytest.raises(ValueError, match='EVIDENCE_SCHEMA'):
        EvidenceRepository(path, writable=True, clock=lambda: T)
    with pytest.raises(ValueError, match='EVIDENCE_SCHEMA'):
        initialize(path)
    assert before == path.read_bytes()


def test_diagnostic_handler_failure_cannot_turn_success_into_provider_retry(monkeypatch):
    def observer(*args):
        raise httpx.TransportError('SYNTHETIC_SECRET')
    def broken_log(*args, **kwargs):
        raise OSError('SYNTHETIC_LOG_FAILURE')
    monkeypatch.setattr('logging.Logger.warning', broken_log)
    async def run():
        client = await client_with_transport(observer, lambda request: httpx.Response(200, json={'response': [raw()]}))
        try:
            assert await client.finished_matches(10, 2026, last=99) == [raw()]
            assert client.request_count == 1 and client.evidence_capture_failures == 1
        finally:
            await client.close()
    asyncio.run(run())
