"""Phase D: synthetic facts, fake providers and disposable databases only."""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import ROUND_DOWN, Inexact, localcontext
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import httpx
import pytest

from app.prematch_football_context.capture.repository import EvidenceRepository, ImmutableConflict
from app.prematch_football_context.capture.schema import initialize as initialize_evidence
from app.prematch_football_context.evidence import EvidenceUnavailable
from app.prematch_football_context.fingerprint import canonical_bytes
from app.prematch_football_context.policy import FEATURE_NAMES
from app.prematch_football_context.source_adapter import FormatEvidence
from app.prematch_football_context.snapshot.contracts import Opportunity, Projection, snapshot_fingerprint
from app.prematch_football_context.snapshot.observer import SnapshotObserver, DecisionIdentity
from app.prematch_football_context.snapshot.repository import SnapshotRepository, initialize, decode
from app.prematch_football_context.snapshot.service import assemble, reproduce
from tests.test_prematch_football_context_capture import CURRENT, PREVIOUS, TARGET, material, END
from tests.test_prematch_football_context_sources import T, binding, raw

OPPORTUNITY = Opportunity(9999, 'HOME_WIN', 'lab-v2-candidate-' + 'a' * 64)
IDENTITY = DecisionIdentity(9999, 'HOME_WIN', OPPORTUNITY.candidate_id, 1, 2, 10, 2026)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('LIVE_IO_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', fail)
    monkeypatch.setattr(socket, 'create_connection', fail)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', fail)


@pytest.fixture
def stores(tmp_path):
    evidence_path, snapshot_path = tmp_path / 'sources.db', tmp_path / 'snapshots.db'
    initialize_evidence(evidence_path)
    initialize(snapshot_path)
    evidence = EvidenceRepository(evidence_path, writable=True, clock=lambda: T)
    snapshots = SnapshotRepository(snapshot_path, writable=True)
    yield evidence, snapshots
    evidence.close()
    snapshots.close()


def capture(evidence, *, history=True, previous=True, end=END, status='NS', target_changes=None):
    row = raw(9999, status=status, kickoff=T + timedelta(hours=1), gf=None, ga=None)
    if target_changes:
        target_changes(row)
    target = evidence.register(material(scope=TARGET, end=end, payload=[row]))
    current = evidence.register(material(end=end)) if history else None
    prior = evidence.register(material(scope=PREVIOUS, end=end, payload=[raw(20, season=2025)])) if previous else None
    return target, current, prior


def snapshot(evidence, **kwargs):
    receipt = evidence.capture_cutoff()
    return assemble(evidence, OPPORTUNITY, receipt, binding(cutoff=receipt.cutoff), **kwargs)


def test_complete_persist_restart_reproduction_and_exact_pins(stores, monkeypatch):
    e, s = stores
    target, current, previous = capture(e, end=T)
    value = snapshot(e)
    assert value.selected_sources == (target.source_id, current.source_id, previous.source_id)
    assert all(r.ordering < value.receipt.ordering for r in (target, current, previous))
    assert value.projection.names == FEATURE_NAMES
    assert value.projection.values[:4] == ('1.000000', '0.000000', '0.000000', '1.000000')
    assert value.projection.missing == (0,) * 7
    assert s.append(value) == s.append(value)
    assert decode(canonical_bytes(value).decode()) == value
    assert snapshot_fingerprint(value) == value.snapshot_hash
    from app.football.client import FootballClient
    monkeypatch.setattr(FootballClient, '_get', lambda *a, **k: pytest.fail('PROVIDER_REPLAY'))
    reader = EvidenceRepository(Path(e.connection.execute('PRAGMA database_list').fetchone()[2]))
    inspection = SnapshotRepository(Path(s.connection.execute('PRAGMA database_list').fetchone()[2]))
    try:
        assert reproduce(reader, inspection.load(OPPORTUNITY.key)) == value
        info = inspection.inspect(OPPORTUNITY.key, reader)
        assert info['reproduction'] == 'VERIFIED' and info['missing_fields'] == ()
        for key in ('evidence_hash', 'input_hash', 'result_hash', 'projection_hash', 'snapshot_hash'):
            assert info[key] == getattr(value, key)
    finally:
        reader.close()
        inspection.close()
    with pytest.raises(FrozenInstanceError):
        value.home_team_id = 3


@pytest.mark.parametrize('end', [T, T + timedelta(microseconds=1)])
def test_after_decision_source_never_enters(stores, end):
    e, _ = stores
    receipt = e.capture_cutoff()
    e.clock = lambda: end
    target, current, _ = capture(e, end=end)
    with pytest.raises(EvidenceUnavailable):
        assemble(e, OPPORTUNITY, receipt, binding())
    # Explicit pins cannot bypass receipt ordering, even with a forged old wall clock.
    with pytest.raises(EvidenceUnavailable, match='ORDER'):
        assemble(e, OPPORTUNITY, receipt, binding(), source_candidates=((target.source_id,), (current.source_id,), ()))


@pytest.mark.parametrize('change', ['missing', 'hash', 'ordering', 'cutoff'])
def test_decision_receipt_requires_exact_persisted_proof(stores, change):
    e, _ = stores
    capture(e, end=T)
    receipt = e.capture_cutoff()
    bad = replace(receipt, **{'hash': {'receipt_hash': '0'*64}, 'missing': {'receipt_hash': 'f'*64},
                            'ordering': {'ordering': receipt.ordering+1}, 'cutoff': {'cutoff': T+timedelta(seconds=1)}}[change])
    with pytest.raises(EvidenceUnavailable):
        assemble(e, OPPORTUNITY, bad, binding(cutoff=bad.cutoff))


def test_legacy_id_missing_receipt_and_missing_order_proof_fail_closed(stores, monkeypatch):
    e, _ = stores
    target, current, _ = capture(e)
    receipt = e.capture_cutoff()
    with pytest.raises(EvidenceUnavailable):
        assemble(e, OPPORTUNITY, receipt, binding(), source_candidates=((target.source_id,), ('legacy',), ()))
    original = e.load
    def unproven(identity, *, decision=None):
        return original(identity)  # Deliberately omit Phase C proof, even for timestamps < T.
    monkeypatch.setattr(e, 'load', unproven)
    with pytest.raises(EvidenceUnavailable, match='ORDER'):
        assemble(e, OPPORTUNITY, receipt, binding(), source_candidates=((target.source_id,), (current.source_id,), ()))


@pytest.mark.parametrize('change', ['competition', 'season', 'fixture', 'teams', 'NS', 'TBD', '1H', 'FT', 'PST'])
def test_target_scope_status_and_expected_team_checks(stores, change):
    e, _ = stores
    def alter(row):
        if change in ('competition', 'season'):
            row['league']['id' if change == 'competition' else 'season'] += 1
        if change == 'fixture':
            row['fixture']['id'] += 1
        if change == 'teams':
            row['teams']['home']['id'] = 3
    capture(e, status=change if change in ('NS', 'TBD', '1H', 'FT', 'PST') else 'NS', target_changes=alter)
    if change == 'NS':
        assert snapshot(e, expected_teams=(1, 2))
    else:
        with pytest.raises(EvidenceUnavailable):
            snapshot(e, expected_teams=(1, 2))


@pytest.mark.parametrize('history,previous', [(False, False), (False, True), (True, False)])
def test_optional_previous_and_missing_current(stores, history, previous):
    e, s = stores
    capture(e, history=history, previous=previous)
    value = snapshot(e)
    assert all(v is None for v in value.projection.values) == (not history)
    if not history:
        assert value.projection.missing == (1,)*7
        assert all('SOURCE_UNAVAILABLE' in reasons for reasons in value.projection.reasons)
    assert value.selected_sources[2] is None if not previous else value.selected_sources[2] is not None
    assert reproduce(e, s.append(value)) == value


@pytest.mark.parametrize('minutes', [None, 90])
def test_unverified_duration_no_default_no_zero_fill(stores, minutes):
    e, s = stores
    capture(e)
    receipt = e.capture_cutoff()
    b = binding(current_format=FormatEvidence(10, 2026, minutes))
    value = assemble(e, OPPORTUNITY, receipt, b)
    assert value.projection.values == (None,)*7
    assert value.projection.missing == (1,)*7
    assert all('REGULATION_UNVERIFIED' in r for r in value.projection.reasons)
    assert reproduce(e, s.append(value)) == value


def test_canonical_decimal_context_and_projection_isolation(stores):
    e, _ = stores
    capture(e)
    receipt = e.capture_cutoff()
    expected = assemble(e, OPPORTUNITY, receipt, binding())
    with localcontext() as context:
        context.prec = 5
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        assert assemble(e, OPPORTUNITY, receipt, binding()) == expected
    assert expected.projection.fingerprint == expected.projection_hash
    assert not {'home_goal_rate', 'away_goal_rate', 'recent_form', 'goals_scored', 'goals_conceded',
                'home_form', 'away_form', 'strength', 'rest_days'} & set(expected.projection.names)
    for changes in ({'names': tuple(reversed(FEATURE_NAMES))}, {'values': (0.,)*7}, {'missing': (1,)*7},
                    {'values': ('-0.000000',)*7}, {'contract': 'LAB_FROZEN_FEATURES_V1'}):
        with pytest.raises(ValueError):
            replace(expected.projection, **changes)


def test_idempotency_conflict_and_later_distinct_market(stores):
    e, s = stores
    capture(e)
    first = snapshot(e)
    s.append(first)
    e.clock = lambda: T + timedelta(seconds=1)
    e.register(material(end=T + timedelta(seconds=1), payload=[raw(gf=5)]))
    later = snapshot(e)
    assert later.snapshot_hash != first.snapshot_hash
    with pytest.raises(ImmutableConflict):
        s.append(later)
    other = assemble(e, replace(OPPORTUNITY, market='AWAY_WIN'), later.receipt, later.binding)
    s.append(other)
    assert s.load(OPPORTUNITY.key) == first
    assert reproduce(e, first) == first  # Later corrections never reselect old pins.
    assert s.connection.execute('SELECT count(*) FROM fc_v2_snapshots').fetchone()[0] == 2


@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE', 'REPLACE', 'UPSERT'])
def test_append_only_guards(stores, operation):
    e, s = stores
    capture(e)
    value = s.append(snapshot(e))
    commands = {'UPDATE': 'UPDATE fc_v2_snapshots SET document=document',
                'DELETE': 'DELETE FROM fc_v2_snapshots',
                'REPLACE': 'INSERT OR REPLACE INTO fc_v2_snapshots SELECT * FROM fc_v2_snapshots',
                'UPSERT': 'INSERT INTO fc_v2_snapshots SELECT * FROM fc_v2_snapshots WHERE 1 ON CONFLICT DO UPDATE SET document=excluded.document'}
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE'):
        s.connection.execute(commands[operation])
    assert s.load(OPPORTUNITY.key) == value


def test_atomic_rollback_and_schema_readonly_checks(stores, tmp_path, monkeypatch):
    e, s = stores
    capture(e)
    value = snapshot(e)
    def fail():
        raise sqlite3.OperationalError('INJECTED')
    monkeypatch.setattr(s, '_commit', fail)
    with pytest.raises(sqlite3.OperationalError):
        s.append(value)
    assert s.load(OPPORTUNITY.key) is None and not s.connection.in_transaction
    path = Path(s.connection.execute('PRAGMA database_list').fetchone()[2])
    initialize(path)
    before = path.read_bytes()
    reader = SnapshotRepository(path)
    try:
        with pytest.raises(ValueError, match='READ_ONLY'):
            reader.append(value)
        with pytest.raises(sqlite3.OperationalError):
            reader.connection.execute('CREATE TABLE unexpected(id)')
        assert reader.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert reader.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        reader.close()
    assert path.read_bytes() == before
    missing = tmp_path / 'missing'
    with pytest.raises(sqlite3.OperationalError):
        SnapshotRepository(missing)
    assert not missing.exists()
    with sqlite3.connect(tmp_path/'empty'):
        pass
    with pytest.raises(ValueError):
        SnapshotRepository(tmp_path/'empty')
    initialize(tmp_path/'empty')
    epath = Path(e.connection.execute('PRAGMA database_list').fetchone()[2])
    with pytest.raises(ValueError):
        initialize(epath)


@pytest.mark.parametrize('corruption', ['snapshot', 'source', 'missing_source', 'receipt', 'missing_receipt'])
def test_corruption_reproduction_fails_closed(stores, corruption):
    e, s = stores
    capture(e)
    value = s.append(snapshot(e))
    if corruption == 'snapshot':
        s.connection.execute('DROP TRIGGER fc_v2_snapshots_no_update')
        doc = json.loads(canonical_bytes(value))
        doc['projection']['values'][0] = '2.000000'
        s.connection.execute('UPDATE fc_v2_snapshots SET document=?', (canonical_bytes(doc).decode(),))
        with pytest.raises(EvidenceUnavailable):
            s.load(OPPORTUNITY.key)
        return
    e.connection.execute('PRAGMA foreign_keys=OFF')
    for table in ('fc_sources', 'fc_receipts'):
        for action in ('update', 'delete'):
            e.connection.execute(f'DROP TRIGGER {table}_no_{action}')
    if corruption == 'source':
        e.connection.execute("UPDATE fc_sources SET material_json='{}' WHERE source_id=?", (value.selected_sources[0],))
    elif corruption == 'missing_source':
        e.connection.execute('DELETE FROM fc_sources WHERE source_id=?', (value.selected_sources[0],))
    elif corruption == 'receipt':
        e.connection.execute("UPDATE fc_receipts SET receipt_hash=? WHERE event='DECISION'", ('0'*64,))
    else:
        e.connection.execute("DELETE FROM fc_receipts WHERE event='DECISION'")
    with pytest.raises(EvidenceUnavailable):
        reproduce(e, value)


def test_observer_pins_first_canonical_and_failure_does_not_raise(stores, monkeypatch):
    e, s = stores
    capture(e)
    observer = SnapshotObserver(e, s, (binding(),))
    observer.bind(observer.begin(), (IDENTITY,))
    observer.observe(IDENTITY, new_opportunity=True)
    original = s.load(OPPORTUNITY.key)
    assert original is not None
    observer.pending.clear()
    observer.observe(IDENTITY, new_opportunity=True)
    assert observer.diagnostics() == {'CAPTURED': 1, 'REPLAY': 1}
    observer.observe(replace(IDENTITY, candidate_id='lab-v2-candidate-'+'b'*64), new_opportunity=True)
    assert observer.diagnostics()['UNAVAILABLE_CONFLICT'] == 1
    assert s.load(OPPORTUNITY.key) == original
    unknown = replace(IDENTITY, market='DRAW')
    observer.observe(unknown, new_opportunity=False)
    assert s.load('9999:DRAW') is None
    def fail(*a, **k):
        raise sqlite3.OperationalError('SECRET_DISK_ERROR')
    monkeypatch.setattr(e, 'capture_cutoff', fail)
    assert observer.begin() is None
    observer.bind(None, (IDENTITY,))
    assert 'SECRET' not in str(observer.diagnostics())


def test_imports_inert():
    script = '''
import os, sys

def audit(event, args):
    if event.startswith(('socket.connect', 'sqlite3.connect')): raise AssertionError(event)
    if event == 'open' and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND): raise AssertionError(event)
sys.addaudithook(audit)
import app.prematch_football_context.snapshot.contracts
import app.prematch_football_context.snapshot.repository
import app.prematch_football_context.snapshot.service
import app.prematch_football_context.snapshot.observer
assert not any(n.startswith(('app.football', 'app.adaptive_lab', 'app.live_lab', 'telegram', 'app.reviewed_historical_odds')) for n in sys.modules)
'''
    result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_real_final_evaluation_to_canonical_freeze_parity(tmp_path, monkeypatch):
    """Full runner and coordinator, actual calculations, no prediction patching."""
    import asyncio
    from app.adaptive_lab.coordinator import LearningCoordinator
    from app.adaptive_lab.repository import AuditRepository
    from app.adaptive_lab.features import captured_features
    from app.lab_v2_shadow.runner import LabV2ShadowRunner
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from app.lab_v2_shadow.publication import _leg
    from app.prematch_football_context.capture.adapter import CaptureAdapter, CaptureScope
    from app.prematch_football_context.evidence import Binding
    from app.prematch_football_context.sources import history_query, target_query, SourceKind
    from tests.test_lab_v2_shadow import LifecycleClient, NOW, results
    from tests.test_prematch_football_context_sources import C

    records = []
    for mode in ('off', 'on', 'persistence_failure', 'receipt_failure', 'throwing_hook'):
        root = tmp_path / mode
        root.mkdir()
        monkeypatch.chdir(root)
        initialize_evidence(root/'e.db')
        initialize(root/'s.db')
        e = EvidenceRepository(root/'e.db', writable=True, clock=lambda: NOW+timedelta(seconds=5))
        s = SnapshotRepository(root/'s.db', writable=True)
        b = Binding(7, 999, 2026, NOW, C,
                    FormatEvidence(999, 2026, 90, 'SYNTHETIC', 'b'*64, NOW-timedelta(days=2)),
                    FormatEvidence(999, 2025))
        observer = SnapshotObserver(e, s, (b,)) if mode != 'off' else None
        if mode == 'persistence_failure':
            def fail():
                raise sqlite3.OperationalError('SECRET_DISK_FAILURE')
            monkeypatch.setattr(s, '_commit', fail)
        if mode == 'receipt_failure':
            def fail():
                raise sqlite3.OperationalError('SECRET_RECEIPT_FAILURE')
            monkeypatch.setattr(e, 'capture_cutoff', fail)
        if mode == 'throwing_hook':
            class Broken:
                def begin(self): raise RuntimeError('SECRET')
                def bind(self, *a): raise RuntimeError('SECRET')
                def observe(self, *a): raise RuntimeError('SECRET')
            observer = Broken()
        adapter = CaptureAdapter(e, (
            CaptureScope(target_query(7), SourceKind.TARGET, timedelta(minutes=2)),
            CaptureScope(history_query(999, 2026), SourceKind.CURRENT, timedelta(hours=6)),
            CaptureScope(history_query(999, 2025), SourceKind.PREVIOUS, timedelta(hours=24))))
        class Client(LifecycleClient):
            def _hit(self, endpoint, query, payload):
                output = super()._hit(endpoint, query, payload)
                if mode != 'off':
                    adapter(endpoint, query, payload, NOW)
                return output
            async def finished_matches(self, league_id, season, last=99):
                rows = [{'fixture': {'id': r.fixture_id, 'date': r.kickoff_utc.isoformat(), 'status': {'short': 'FT'}},
                         'league': {'id': league_id, 'season': season},
                         'teams': {'home': {'id': r.home_team_id}, 'away': {'id': r.away_team_id}},
                         'goals': {'home': r.home_goals, 'away': r.away_goals}} for r in results()]
                return self._hit('/fixtures', {'league': league_id, 'season': season, 'status': 'FT', 'last': last}, rows)
        client = Client(NOW, NOW+timedelta(minutes=30))
        shadow = ShadowEvidenceRepository(root/'shadow.db')
        adaptive = AuditRepository(root/'adaptive.db')
        coordinator = LearningCoordinator(adaptive, football_context_observer=observer)
        runner = LabV2ShadowRunner(client, shadow, capability_cache_path=root/'var/caps.json',
                                  maximum_calls=40, adaptive_learning=coordinator,
                                  football_context_observer=observer)
        # Assert placement: the preliminary pass precedes the sole marker;
        # final evaluation sees it, without patching any calculation.
        original_evaluate = runner._evaluate
        calls = []
        def evaluate(*args, **kwargs):
            calls.append(e.connection.execute("SELECT count(*) FROM fc_receipts WHERE event='DECISION'").fetchone()[0])
            return original_evaluate(*args, **kwargs)
        monkeypatch.setattr(runner, '_evaluate', evaluate)
        try:
            report = asyncio.run(runner.run(now=NOW, horizon_days=1))
            candidates = report['candidate_markets']
            inputs = [_leg(c, NOW+timedelta(seconds=6)) for c in candidates
                      if c['decision'] == 'APPROVED' and c.get('ensemble_probability') and c.get('predictive_family_count', 0)>0]
            assert inputs
            coordinator.shadow(inputs, stream='PREMATCH', now=NOW+timedelta(seconds=6))
            canonical = adaptive.all('canonical_opportunities')
            assert canonical
            records.append((json.dumps(report, sort_keys=True), client.request_count, client.requests,
                            canonical, [captured_features(c) for c in canonical]))
            if mode == 'on':
                assert calls == [0, 1]
                assert observer.diagnostics()['CAPTURED'] == len(canonical)
                for candidate in canonical:
                    value = s.load(f"{candidate['fixture_id']}:{candidate['market']}")
                    assert value.opportunity.candidate_id == candidate['candidate_id']
                    assert value.receipt.cutoff == NOW+timedelta(seconds=5)
                    assert value.receipt.cutoff < __import__('datetime').datetime.fromisoformat(candidate['prepared_at_utc'])
                    assert reproduce(e, value) == value
                # Retry uses the original canonical row and snapshot, even after
                # a later cycle has lost the transient candidate association.
                observer.pending.clear()
                coordinator.shadow(inputs, stream='PREMATCH', now=NOW+timedelta(seconds=7))
                assert observer.diagnostics()['REPLAY'] == len(canonical)
            elif mode == 'persistence_failure':
                assert calls == [0, 1]
                assert observer.diagnostics()['UNAVAILABLE_SNAPSHOT'] == len(canonical)
                assert s.connection.execute('SELECT count(*) FROM fc_v2_snapshots').fetchone()[0] == 0
            else:
                assert calls == [0, 0]
            assert not adaptive.all('learning_observations')
            assert not adaptive.all('live_publications')
            assert report['telegram_transport_constructed'] is False
            assert report['official_mutations'] == 0
        finally:
            e.close(); s.close(); shadow.close(); adaptive.close()
    assert all(record == records[0] for record in records)


@pytest.mark.parametrize('problem', ['competition', 'season', 'malformed', 'stale'])
def test_current_invalid_remains_missing_without_older_fallback(stores, problem):
    e, _ = stores
    capture(e, history=False, previous=False)
    old = material(end=END-timedelta(seconds=1))
    e.register(old)
    row = raw()
    if problem == 'competition': row['league']['id'] = 11
    if problem == 'season': row['league']['season'] = 2025
    if problem == 'malformed': row['goals']['home'] = 'INVALID'
    if problem == 'stale':
        # All history candidates stale; TARGET still fresh at the later cutoff.
        e.clock = lambda: T+timedelta(hours=6)
        e.register(material(scope=TARGET, end=T+timedelta(hours=6), payload=[raw(9999, status='NS', kickoff=T+timedelta(hours=7))]))
    else:
        e.register(material(end=END, payload=[row]))
    value = snapshot(e)
    assert value.projection.values == (None,)*7
    if problem == 'stale':
        assert all('SOURCE_UNAVAILABLE' in r for r in value.projection.reasons)
        assert any(kind == 'CURRENT' and verdict == 'EXPIRED' for kind, _, verdict in value.source_decisions)
    else:
        assert value.validations[1][1] in ('WRONG_COMPETITION', 'WRONG_SEASON', 'MALFORMED')


def test_lock_and_insert_abort_no_partial_snapshot(stores):
    e, s = stores
    capture(e)
    value = snapshot(e)
    path = Path(s.connection.execute('PRAGMA database_list').fetchone()[2])
    blocker = sqlite3.connect(path)
    try:
        blocker.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            s.append(value)
    finally:
        blocker.rollback()
        blocker.close()
    assert s.load(OPPORTUNITY.key) is None
    s.connection.execute("CREATE TRIGGER fail AFTER INSERT ON fc_v2_snapshots BEGIN SELECT RAISE(ABORT,'INJECTED'); END")
    with pytest.raises(sqlite3.IntegrityError):
        s.append(value)
    assert s.load(OPPORTUNITY.key) is None and not s.connection.in_transaction


@pytest.mark.parametrize('field', ['input_hash', 'result_hash', 'evidence_hash', 'selected_sources', 'projection'])
def test_inner_reproduction_rejects_rehashed_corruption(stores, field):
    e, _ = stores
    capture(e)
    value = snapshot(e)
    changes = {field: '0'*64}
    if field == 'selected_sources':
        changes[field] = (value.selected_sources[0], None, value.selected_sources[2])
    elif field == 'projection':
        p = replace(value.projection, values=('2.000000', *value.projection.values[1:]))
        changes = {'projection': p, 'projection_hash': p.fingerprint}
    corrupt = replace(value, snapshot_hash='', **changes)
    corrupt = replace(corrupt, snapshot_hash=snapshot_fingerprint(corrupt))
    with pytest.raises(EvidenceUnavailable):
        reproduce(e, corrupt)


def test_existing_canonical_without_snapshot_cannot_acquire_later_receipt(stores):
    e, s = stores
    capture(e)
    observer = SnapshotObserver(e, s, (binding(),))
    observer.bind(observer.begin(), (IDENTITY,))
    # Identical candidate content does not prove that an OLD canonical row was
    # decided in this cycle. Only a newly created canonical row may be attached.
    observer.observe(IDENTITY, new_opportunity=False)
    assert s.load(OPPORTUNITY.key) is None
    assert observer.diagnostics() == {'UNAVAILABLE_SNAPSHOT': 1}


def test_default_hook_off_and_live_never_invokes_observer(tmp_path):
    from app.adaptive_lab.coordinator import LearningCoordinator
    from app.adaptive_lab.repository import AuditRepository
    from app.lab_v2_shadow.runner import LabV2ShadowRunner
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from tests.test_lab_v2_shadow import FakeClient
    repo = AuditRepository(tmp_path/'a.db')
    shadow = ShadowEvidenceRepository(tmp_path/'shadow.db')
    class Forbidden:
        def observe(self, *args, **kwargs): pytest.fail('LIVE_CONTEXT_HOOK')
    try:
        assert LearningCoordinator(repo).football_context_observer is None
        assert LabV2ShadowRunner(FakeClient(), shadow, capability_cache_path=tmp_path/'unused').football_context_observer is None
        coordinator = LearningCoordinator(repo, football_context_observer=Forbidden())
        # No eligible LIVE row invokes the PREMATCH-only hook. Use a minimal
        # valid opportunity and an empty shadow registry; no model execution.
        candidate = {'fixture_id': 1, 'market': 'HOME_WIN', 'ensemble_probability': '.6',
                     'captured_odds': '2', 'candidate_id': 'live', 'quote_provenance_fingerprint': 'q',
                     'kickoff_utc': T.isoformat(), 'prepared_at_utc': T.isoformat()}
        coordinator.shadow([candidate], stream='LIVE', now=T)
        assert repo.all('canonical_opportunities') == []
    finally:
        repo.close(); shadow.close()


def test_later_receipt_with_older_timestamps_cannot_bypass_order(stores):
    """Adversarial disposable-store rewrite: timestamp eligibility is insufficient."""
    from app.prematch_football_context.sources import digest
    e, _ = stores
    target, _, _ = capture(e, history=False, previous=False)
    receipt = e.capture_cutoff()
    late = e.register(material())
    old_stamp = (END+timedelta(seconds=1)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    doc = {'ordering': late.ordering, 'event': 'SOURCE', 'source_id': late.source_id, 'observed_at': old_stamp}
    e.connection.execute('DROP TRIGGER fc_receipts_no_update')
    e.connection.execute('UPDATE fc_receipts SET observed_at=?,receipt_hash=? WHERE ordering=?',
                         (old_stamp, digest(doc), late.ordering))
    assert e.load(late.source_id, decision=receipt).header.timing.registered_at < receipt.cutoff
    with pytest.raises(EvidenceUnavailable, match='ORDER'):
        assemble(e, OPPORTUNITY, receipt, binding(), source_candidates=((target.source_id,), (late.source_id,), ()))
    value = assemble(e, OPPORTUNITY, receipt, binding())
    assert value.selected_sources[1] is None and value.projection.values == (None,)*7


def test_snapshot_commit_lost_return_replays_original_and_concurrent_append(stores, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    e, s = stores
    capture(e)
    value = snapshot(e)
    original = s._commit
    def lost_return():
        original()
        raise RuntimeError('RETURN_LOST')
    monkeypatch.setattr(s, '_commit', lost_return)
    with pytest.raises(RuntimeError):
        s.append(value)
    assert s.load(OPPORTUNITY.key) == value
    monkeypatch.setattr(s, '_commit', original)
    path = Path(s.connection.execute('PRAGMA database_list').fetchone()[2])
    def append():
        writer = SnapshotRepository(path, writable=True)
        try:
            return writer.append(value)
        finally:
            writer.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: append(), range(2))) == [value, value]
    assert s.connection.execute('SELECT count(*) FROM fc_v2_snapshots').fetchone()[0] == 1
