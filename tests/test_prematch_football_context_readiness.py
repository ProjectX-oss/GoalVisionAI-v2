"""Readiness machinery only: fake transports, synthetic facts, disposable stores."""
import argparse
import asyncio
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

from app.prematch_football_context.readiness.__main__ import initialize, main
from app.prematch_football_context.readiness.composition import ProspectiveObservation, scope_binding
from app.prematch_football_context.readiness.ledger import Ledger
from app.prematch_football_context.readiness.report import coverage, readiness, rate
from app.prematch_football_context.fingerprint import canonical_bytes
from app.prematch_football_context.policy import FEATURE_NAMES
from app.prematch_football_context.snapshot.observer import DecisionIdentity
from app.prematch_football_context.snapshot.service import reproduce
from app.prematch_football_context.snapshot.repository import SnapshotRepository
from app.prematch_football_context.capture.repository import EvidenceRepository
from tests.test_prematch_football_context_sources import T, raw, binding

ROW = (9999, 10, 2026, 'SENIOR_MEN_PRO', 'SYNTHETIC_V1', 'TEST', 'a'*64, 'SENIOR', ())
ID = DecisionIdentity(9999, 'HOME_WIN', 'lab-v2-candidate-'+'a'*64, 1, 2, 10, 2026)


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail('REAL_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def collect(root, *, target=True, current=True, previous=False, verified=False, profile='SENIOR_MEN_PRO', malformed=False):
    initialize(root)
    o = ProspectiveObservation(root, environment='TEST', clock=lambda: T)
    o.prepare((ROW[:3]+(profile,)+ROW[4:],))
    if verified:
        # Explicit synthetic reviewed format, never a runtime default.
        o.scopes[9999] = replace(o.scopes[9999], current_format=binding().current_format)
        o.observer.scopes = o.scopes.copy()
    if target:
        payload = [raw(9999, status='NS', kickoff=T+timedelta(hours=1), gf=None, ga=None)]
        o.capture('/fixtures', {'id': 9999}, payload, T)
    if current:
        payload = {'response': None} if malformed else [raw(i) for i in range(1,9)]
        o.capture('/fixtures', {'league': 10, 'season': 2026, 'status': 'FT', 'last': 99}, payload, T)
    if previous:
        o.capture('/fixtures', {'league': 10, 'season': 2025, 'status': 'FT', 'last': 99}, [raw(20, season=2025)], T)
    o.bind(o.begin(), (ID,))
    o.observe(ID, new_opportunity=True)
    return o


@pytest.mark.parametrize('target,current,previous,verified,profile,malformed', [
    (True, True, False, True, 'SENIOR_MEN_PRO', False),
    (False, True, False, True, 'SENIOR_MEN_PRO', False),
    (True, False, False, True, 'SENIOR_MEN_PRO', False),
    (True, True, True, True, 'SENIOR_MEN_PRO', False),
    (True, True, False, False, 'SENIOR_MEN_PRO', False),
    (True, True, False, True, 'UNKNOWN', False),
    (True, True, False, True, 'SENIOR_MEN_PRO', True),
])
def test_collection_missingness_and_report(tmp_path, target, current, previous, verified, profile, malformed):
    o = collect(tmp_path, target=target, current=current, previous=previous, verified=verified, profile=profile, malformed=malformed)
    if target:
        s = o.snapshots.load('9999:HOME_WIN')
        assert s is not None and reproduce(o.evidence, s) == s
    o.finish(completed=True)
    report = coverage(tmp_path)
    assert report == coverage(tmp_path)
    assert report['observed_canonical_prematch_opportunities'] == report['v2_observation_attempts'] == 1
    assert report['successful_v2_snapshots'] == int(target)
    assert report['snapshot_rate'] == rate(int(target), 1, 'eligible_v2_observation_attempts')
    assert report['first_decision_cutoff'] == report['last_decision_cutoff'] == T
    assert report['unique_fixtures'] == report['unique_competitions'] == 1
    assert report['source_availability']['TARGET']['available'] == int(target)
    assert report['source_availability']['CURRENT']['available'] == int(current and not malformed)
    assert report['source_availability']['PREVIOUS']['available'] == int(previous)
    present = target and current and verified and profile != 'UNKNOWN' and not malformed
    assert report['available_feature_histogram']['7'] == int(present)
    assert report['available_feature_histogram']['0'] == int(target and not present)
    for counts in report['features'].values():
        assert counts['available'] == int(present)
        assert counts['missing'] == int(target and not present)
        assert counts['availability_rate']['denominator'] == int(target)
        if target and not verified:
            assert counts['missing_reasons']['REGULATION_UNVERIFIED'] == 1
        if target and profile == 'UNKNOWN':
            assert counts['missing_reasons']['UNSUPPORTED_PROFILE'] == 1
    assert report['reproduction']['VERIFIED'] == int(target)
    assert report['reproduction']['FAILED'] == 0
    assert report['readiness'] == ('INSUFFICIENT_SAMPLE' if target else 'CAPTURE_BLOCKED')
    assert report['phase_e_authorized'] is False


def test_unrelated_and_cache_legacy_not_certified(tmp_path):
    from app.prematch_football_context.source_adapter import legacy_cache_candidate
    from app.prematch_football_context.sources import SourceKind, history_query, select_source
    initialize(tmp_path)
    o = ProspectiveObservation(tmp_path, environment='LAB', clock=lambda: T)
    o.prepare((ROW,))
    for path, query in [('/fixtures', {'date':'2026-09-23'}), ('/odds', {'fixture':9999}),
                        ('/fixtures', {'league':10,'season':2024,'last':99,'status':'FT'}),
                        ('/fixtures', {'league':10,'season':2026,'last':100,'status':'FT'})]:
        o.capture(path, query, [raw()], T)
    assert o.evidence.inspect() == ()
    query = history_query(10, 2026)
    legacy = legacy_cache_candidate(source_id='old', query=query, kind=SourceKind.CURRENT,
                                   retrieved_at=T, expiry=T+timedelta(hours=1), payload=[raw()])
    result = select_source((legacy,), query, cutoff=T, source_kind=SourceKind.CURRENT)
    assert result.decisions[0].verdict == 'ASOF_UNPROVEN'
    o.bind(o.begin(), (ID,))
    o.observe(ID, new_opportunity=False)
    o.finish(completed=True)
    r = coverage(tmp_path)
    assert r['old_canonical_observations_not_attempted'] == 1
    assert r['v2_observation_attempts'] == r['successful_v2_snapshots'] == 0
    assert r['snapshot_rate']['fraction'] == 'N/A'


def test_empty_readonly_and_no_automatic_format(tmp_path):
    initialize(tmp_path)
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    r = coverage(tmp_path)
    assert r['readiness'] == 'NO_PROSPECTIVE_EVIDENCE'
    assert r['snapshot_rate']['fraction'] == r['all_seven_available']['fraction'] == 'N/A'
    assert all(c['availability_rate']['fraction'] == 'N/A' for c in r['features'].values())
    assert before == {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    scope = scope_binding(ROW, T)
    assert scope.current_format.verdict(T) == 'REGULATION_UNVERIFIED'
    assert scope.previous_format.verdict(T) == 'REGULATION_UNVERIFIED'
    unknown = scope_binding(ROW[:3]+('UNKNOWN',)+ROW[4:], T)
    assert unknown.classification.gender == unknown.classification.team_category == 'UNKNOWN'


@pytest.mark.parametrize('snapshots,competitions,days,failures,incomplete,expected', [
    (0,0,0,0,0,'CAPTURE_BLOCKED'), (99,5,7,0,0,'INSUFFICIENT_SAMPLE'),
    (100,4,7,0,0,'PARTIAL_COVERAGE'), (100,5,6,0,0,'PARTIAL_COVERAGE'),
    (100,5,7,0,0,'READY_FOR_V2_RESEARCH_REVIEW'),
    (100,5,7,1,0,'CAPTURE_BLOCKED'), (100,5,7,0,1,'CAPTURE_BLOCKED')])
def test_declared_readiness_gates(snapshots,competitions,days,failures,incomplete,expected):
    assert readiness(attempts=100, snapshots=snapshots, competitions=competitions, days=days,
                     failures=failures, incomplete=incomplete) == expected


@pytest.mark.parametrize('failure', ['evidence_missing','snapshot_missing','evidence_locked','snapshot_locked',
                                     'capture','receipt','assembly','persist','ledger_locked'])
def test_failure_isolation(tmp_path, monkeypatch, failure):
    initialize(tmp_path)
    if failure.endswith('missing'):
        (tmp_path/('sources.db' if failure.startswith('evidence') else 'snapshots.db')).unlink()
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: T)
    o.prepare((ROW,))
    def fail(*a, **k): raise RuntimeError('SECRET_MUST_NOT_LEAK')
    if failure == 'capture': monkeypatch.setattr(o.adapter, '__call__', fail)  # class special method below
    if failure == 'capture': monkeypatch.setattr(type(o.adapter), '__call__', fail)
    if failure == 'receipt': monkeypatch.setattr(o.evidence, 'capture_cutoff', fail)
    if failure == 'assembly': monkeypatch.setattr('app.prematch_football_context.snapshot.observer.assemble', fail)
    if failure == 'persist': monkeypatch.setattr(o.snapshots, 'append', fail)
    lock = None
    if failure.endswith('locked'):
        path = 'sources.db' if failure.startswith('evidence') else 'snapshots.db' if failure.startswith('snapshot') else 'attempts.db'
        lock = sqlite3.connect(tmp_path/path)
        lock.execute('BEGIN IMMEDIATE')
    try:
        o.capture('/fixtures', {'id':9999}, [raw(9999,status='NS',kickoff=T+timedelta(hours=1))], T)
        o.bind(o.begin(), (ID,))
        o.observe(ID, new_opportunity=True)
    finally:
        if lock:
            lock.rollback(); lock.close()
    counters = o.finish(completed=True)
    assert 'SECRET' not in str(counters)
    r = coverage(tmp_path)
    assert r['readiness'] == 'CAPTURE_BLOCKED'


@pytest.mark.parametrize('corruption', ['snapshot','source','ledger','missing_result','interrupted'])
def test_corruption_and_reproduction_not_silently_verified(tmp_path, corruption):
    o = collect(tmp_path, verified=True)
    if corruption == 'snapshot':
        o.snapshots.connection.execute('DROP TRIGGER fc_v2_snapshots_no_update')
        o.snapshots.connection.execute("UPDATE fc_v2_snapshots SET document='{}'")
        o.snapshots.connection.execute("CREATE TRIGGER fc_v2_snapshots_no_update BEFORE UPDATE ON fc_v2_snapshots BEGIN SELECT RAISE(ABORT,'FC_V2_IMMUTABLE'); END")
    if corruption == 'source':
        o.evidence.connection.execute('DROP TRIGGER fc_sources_no_update')
        o.evidence.connection.execute("UPDATE fc_sources SET material_json='{}'")
        o.evidence.connection.execute("CREATE TRIGGER fc_sources_no_update BEFORE UPDATE ON fc_sources BEGIN SELECT RAISE(ABORT,'FC_IMMUTABLE'); END")
    if corruption == 'ledger':
        o.ledger.connection.execute('DROP TRIGGER fc_readiness_events_no_update')
        o.ledger.connection.execute("UPDATE fc_readiness_events SET hash='invalid'")
    if corruption == 'missing_result':
        o.ledger.connection.execute('DROP TRIGGER fc_readiness_events_no_delete')
        o.ledger.connection.execute("DELETE FROM fc_readiness_events WHERE kind='RESULT'")
    o.finish(completed=corruption != 'interrupted')
    r = coverage(tmp_path)
    assert r['readiness'] == 'CAPTURE_BLOCKED'
    if corruption in ('snapshot','source'):
        assert r['reproduction']['FAILED'] == 1
        assert r['reproduction']['VERIFIED'] == 0


def test_schema_guards_integrity_and_imports(tmp_path):
    initialize(tmp_path)
    ledger = Ledger(tmp_path/'attempts.db', writable=True)
    ledger.append('RUN', 'one', {'environment':'TEST'})
    for sql in ('UPDATE fc_readiness_events SET document=document', 'DELETE FROM fc_readiness_events',
                'INSERT OR REPLACE INTO fc_readiness_events SELECT * FROM fc_readiness_events'):
        with pytest.raises(sqlite3.IntegrityError): ledger.connection.execute(sql)
    assert ledger.connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    assert not ledger.connection.execute('PRAGMA foreign_key_check').fetchall()
    ledger.close()
    script = '''
import os, sys
def audit(event,args):
    if event.startswith(('socket.connect','sqlite3.connect')): raise AssertionError(event)
    if event == 'open' and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND): raise AssertionError(event)
sys.addaudithook(audit)
import app.prematch_football_context.readiness.__main__
assert not any(n.startswith(('app.adaptive_lab','app.football','app.live_lab','telegram')) for n in sys.modules)
'''
    completed = subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
    assert completed.returncode == 0, completed.stderr


def test_cli_requires_explicit_action_and_has_no_send(tmp_path, monkeypatch, capsys):
    assert main(['--root', str(tmp_path), 'init']) == 0
    assert main(['--root', str(tmp_path), 'report']) == 0
    for tail in (['cycle'], ['cycle','--environment','LAB'], ['cycle','--environment','LAB','--observe','--send']):
        with pytest.raises(SystemExit): main(['--root',str(tmp_path),*tail])
    assert not (tmp_path/'adaptive.db').exists()


@pytest.mark.parametrize('near,ucl', [(True, False), (False, False), (True, True)])
def test_real_client_controlled_cycle_exact_parity(tmp_path, monkeypatch, near, ucl):
    """Real CLI, runner, coordinator and FootballClient; only transport is fake."""
    from app.football.client import FootballClient
    from app.lab_v2_shadow import cli
    from app.adaptive_lab.repository import AuditRepository
    from app.adaptive_lab.features import captured_features
    from tests.test_lab_v2_shadow import LifecycleClient, NOW, results

    registry = None
    if ucl:
        from tests.test_prematch_registry_readiness import renewed_registry
        registry = tmp_path/'reviewed-registry.db'
        NOW = renewed_registry(registry)  # Injected TEST time; synthetic football only.
        monkeypatch.setattr('tests.test_lab_v2_shadow.NOW', NOW)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(NOW.isoformat())
    monkeypatch.setattr(cli, 'datetime', Clock)
    monkeypatch.setattr('app.football.client.datetime', Clock)
    def no_send(*a, **k): pytest.fail('TELEGRAM_CONSTRUCTED')
    monkeypatch.setattr(cli, 'LabTelegramTransport', no_send)
    records = []
    modes = ('off', 'on', 'registry', 'registry_missing', 'registry_corrupt', 'registry_locked',
             'registry_expired', 'registry_conflict', 'proof_write') if ucl else (
        'off','on','capture','receipt','persist','evidence_missing','snapshot_missing',
        'evidence_locked','snapshot_locked')
    for mode in modes:
        root = tmp_path/mode
        initialize(root)
        monkeypatch.chdir(root)
        if mode == 'evidence_missing': (root/'sources.db').unlink()
        if mode == 'snapshot_missing': (root/'snapshots.db').unlink()
        selected_registry = registry
        registry_lock = None
        if mode in ('registry_corrupt', 'registry_expired', 'registry_conflict'):
            from tests.test_prematch_football_context_regulation_registry import record, append, initialize as init_registry
            selected_registry = root/'fault-registry.db'
            if mode == 'registry_corrupt':
                selected_registry.write_bytes(b'SYNTHETIC CORRUPT STORE')
            else:
                init_registry(selected_registry)
                append(selected_registry, record(competition_id=2,
                    source_effective_until=NOW if mode == 'registry_expired' else NOW+timedelta(days=1)))
                if mode == 'registry_conflict':
                    append(selected_registry, record(competition_id=2, review_id='SYNTHETIC_CONFLICT', regulation_minutes=80))
        if mode == 'registry_locked':
            registry_lock = sqlite3.connect(registry)
            registry_lock.execute('BEGIN EXCLUSIVE')
        o = None if mode == 'off' else ProspectiveObservation(root, environment='TEST', clock=lambda: NOW,
            regulation_registry=(tmp_path/'absent.db' if mode == 'registry_missing' else selected_registry)
            if mode.startswith('registry') or mode == 'proof_write' else None)
        if registry_lock:
            registry_lock.rollback()
            registry_lock.close()
        def fail(*a, **k): raise RuntimeError('SECRET')
        if mode == 'capture': monkeypatch.setattr(o, 'capture', fail)
        if mode == 'receipt': monkeypatch.setattr(o.evidence, 'capture_cutoff', fail)
        if mode == 'persist': monkeypatch.setattr(o.snapshots, 'append', fail)
        if mode == 'proof_write':
            original_append = o.ledger.append
            def fail_proof(kind, *args):
                if kind == 'REGULATION_PROOF': raise OSError('SYNTHETIC_PROOF_WRITE_FAILURE')
                return original_append(kind, *args)
            monkeypatch.setattr(o.ledger, 'append', fail_proof)
        requests = []
        provider = LifecycleClient(NOW, NOW+timedelta(minutes=30 if near else 240))
        async def handler(request):
            path, q = request.url.path, dict(request.url.params)
            requests.append((path, tuple(sorted(q.items()))))
            if path == '/status': payload = await provider.account_status()
            elif path == '/leagues': payload = await provider.leagues()
            elif path == '/fixtures' and 'date' in q: payload = await provider.fixtures_by_date(q['date'])
            elif path == '/fixtures' and 'id' in q: payload = await provider.fixture(int(q['id']))
            elif path == '/fixtures' and 'league' in q:
                rows = [{'fixture':{'id':r.fixture_id,'date':r.kickoff_utc.isoformat(),'status':{'short':'FT'}},
                         'league':{'id':int(q['league']),'season':int(q['season'])},
                         'teams':{'home':{'id':r.home_team_id},'away':{'id':r.away_team_id}},
                         'goals':{'home':r.home_goals,'away':r.away_goals}} for r in results()]
                payload = {'response':rows}
            elif path == '/odds' and 'date' in q: payload = await provider.current_odds_by_date(q['date'],page=int(q['page']))
            elif path == '/odds': payload = await provider.current_odds(int(q['fixture']))
            elif path == '/fixtures/lineups': payload = await provider.lineup(int(q['fixture']))
            else: payload = (await provider._get(path, params=q)).json()
            if ucl:
                for row in payload.get('response', []):
                    if isinstance(row, dict) and isinstance(row.get('league'), dict):
                        row['league'].update(id=2, name='UEFA Champions League', type='Cup', country='World')
                        if 'seasons' in row: row['country'] = {'name':'World'}
            return httpx.Response(200,json=payload,headers={'x-ratelimit-requests-limit':'7500',
                'x-ratelimit-requests-remaining':'7000','x-ratelimit-limit':'300','x-ratelimit-remaining':'290'})
        clients = []
        def factory(**kwargs):
            client = FootballClient(api_key='SYNTHETIC_ONLY', **kwargs)
            original = client._client
            # The existing client is network inert. Close it before replacing transport.
            async def setup_close(): await original.aclose()
            # Constructor occurs inside the existing running loop; defer closing to close().
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.BASE_URL)
            close = client.close
            async def final_close():
                await close(); await setup_close()
            client.close = final_close
            client.MIN_REQUEST_INTERVAL_SECONDS = 0
            clients.append(client)
            return client
        monkeypatch.setattr(cli,'FootballClient',factory)
        args = argparse.Namespace(shadow_database=root/'shadow.db',analysis_database=root/'analysis.db',
            adaptive_database=root/'adaptive.db',ledger=root/'lab.db',capability_cache=root/'var/caps.json',
            max_calls=40,horizon_days=1,daily_reserve=100,send=False)
        from app.adaptive_lab.baseline import artifact
        from app.adaptive_lab.governance import Governance
        seed = AuditRepository(root/'adaptive.db')
        champion = Governance(seed).bootstrap(artifact(), now=NOW-timedelta(days=1))
        seed.close()
        blocker = None
        if mode in ('evidence_locked', 'snapshot_locked'):
            blocker = sqlite3.connect(root/('sources.db' if mode.startswith('evidence') else 'snapshots.db'))
            blocker.execute('BEGIN IMMEDIATE')
        try:
            report = asyncio.run(cli._cycle(args, football_context=o))
        finally:
            if blocker:
                blocker.rollback(); blocker.close()
        a = AuditRepository(root/'adaptive.db')
        try:
            canonical = a.all('canonical_opportunities')
            assert canonical
            assert a.champion('PREMATCH') == champion
            assert a.champion('LIVE') is None
            for value in canonical:
                old = captured_features(value)
                assert all(old.get(name) is None for name in ('home_goal_rate','away_goal_rate','recent_form',
                    'goals_scored','goals_conceded','home_form','away_form','strength','rest_days'))
            assert not a.all('learning_observations') and not a.all('live_publications')
            records.append((json.dumps(report,sort_keys=True),requests,clients[0].request_count,
                            canonical,[captured_features(v) for v in canonical],a.champion('PREMATCH')))
        finally:
            a.close()
        assert report['telegram_sends'] == 0 and report['official_mutations'] == 0
        if o:
            o.finish(completed=True)
            evidence = coverage(root)
            if (mode == 'on' or mode.startswith('registry_')) and near:
                assert evidence['successful_v2_snapshots'] == len(canonical)
                assert evidence['reproduction']['VERIFIED'] == len(canonical)
                assert evidence['regulation_counts']['REGULATION_UNVERIFIED'] == len(canonical)
                assert evidence['available_feature_histogram']['0'] == len(canonical)
            elif mode == 'registry':
                assert evidence['successful_v2_snapshots'] == len(canonical)
                assert evidence['reproduction']['VERIFIED'] == len(canonical)
                assert evidence['regulation_counts']['VERIFIED_90'] == len(canonical)
                assert all(evidence['features'][name]['available'] == len(canonical) for name in FEATURE_NAMES[:4])
                # Restarted report/verification needs no live registry.
                offline_before = canonical_bytes(evidence)
                registry.rename(tmp_path/'registry-unavailable.db')
                assert canonical_bytes(coverage(root)) == offline_before
                (tmp_path/'registry-unavailable.db').rename(registry)
                print('SYNTHETIC_UCL_E2E', json.dumps({'snapshots': len(canonical),
                    'requests': requests, 'request_count': clients[0].request_count,
                    'features': evidence['features'], 'reproduction': evidence['reproduction']}, sort_keys=True))
            else:
                assert evidence['readiness'] == 'CAPTURE_BLOCKED'
    assert all(r == records[0] for r in records[1:])
    target_calls = sum(path == '/fixtures' and ('id','7') in params for path, params in records[0][1])
    assert bool(target_calls) == near
    assert all('historical' not in path for path, _ in records[0][1])


def test_hundred_real_snapshots_low_feature_coverage_can_reach_research_review(tmp_path):
    """No fake verified verdict: each synthetic snapshot replays through A/B/C/D."""
    initialize(tmp_path)
    now = [T]
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: now[0])
    for i in range(100):
        now[0] = T+timedelta(days=i//15)
        fid, league = 10000+i, 10+i%5
        row = (fid, league, *ROW[2:])
        o.prepare((row,))
        target = raw(fid, status='NS', kickoff=now[0]+timedelta(hours=1), gf=None, ga=None)
        target['league']['id'] = league
        o.capture('/fixtures', {'id':fid}, [target], now[0])
        identity = replace(ID, fixture_id=fid, competition_id=league)
        o.bind(o.begin(), (identity,))
        o.observe(identity, new_opportunity=True)
    o.finish(completed=True)
    r = coverage(tmp_path)
    assert r['readiness'] == 'READY_FOR_V2_RESEARCH_REVIEW'
    assert r['successful_v2_snapshots'] == r['v2_observation_attempts'] == r['unique_fixtures'] == 100
    assert r['snapshot_unique_competitions'] == r['unique_competitions'] == 5
    assert r['snapshot_distinct_utc_days'] == 7
    assert r['first_decision_cutoff'] == T and r['last_decision_cutoff'] == T+timedelta(days=6)
    assert r['available_feature_histogram'] == {'0':100, **{str(i):0 for i in range(1,8)}}
    assert r['regulation_counts']['REGULATION_UNVERIFIED'] == 100
    assert r['reproduction']['VERIFIED'] == 100 and r['reproduction']['FAILED'] == 0
    assert r['reproduction']['rate']['fraction'] == '1.000000'
    assert all(v['snapshots'] == 20 and v['sample_sufficient'] for v in r['competition_profile_breakdown'])
    assert all(c['available'] == 0 and c['missing'] == 100 for c in r['features'].values())
    assert not r['phase_e_authorized']
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    assert canonical_bytes(coverage(tmp_path)) == canonical_bytes(r)
    assert before == {p.name:p.read_bytes() for p in tmp_path.iterdir()}


def test_exact_histogram_all_masks_and_multireason_aggregation():
    """Pure aggregation unit test; these artificial projections are not stored evidence."""
    from app.prematch_football_context.readiness.report import feature_coverage
    from app.prematch_football_context.snapshot.contracts import Projection
    projections = tuple(Projection(tuple('0.000000' if i < count else None for i in range(7)),
        tuple(int(i >= count) for i in range(7)),
        tuple(() if i < count else ('REGULATION_UNVERIFIED','SOURCE_UNAVAILABLE') for i in range(7)))
        for count in range(8))
    histogram, features = feature_coverage(projections)
    assert histogram == {str(i):1 for i in range(8)}
    for i, name in enumerate(FEATURE_NAMES):
        assert features[name]['available'] == 7-i
        assert features[name]['missing'] == i+1
        assert features[name]['missing_reasons'] == {'REGULATION_UNVERIFIED':i+1,'SOURCE_UNAVAILABLE':i+1}
        assert features[name]['availability_rate'] == rate(7-i,8,'successful_immutable_snapshots')


def test_unknown_and_ambiguous_scopes_never_become_senior_default(tmp_path):
    initialize(tmp_path)
    o = ProspectiveObservation(tmp_path, environment='LAB', clock=lambda:T)
    other = (10000,10,2027,*ROW[3:])
    o.prepare((ROW,other))
    # 2026 could be CURRENT or PREVIOUS: reject this ambiguous request plan.
    o.capture('/fixtures', {'league':10,'season':2026,'status':'FT','last':99}, [raw()], T)
    assert not o.evidence.inspect()
    counts = o.finish(completed=True)
    assert counts['AMBIGUOUS_QUERY_SCOPE'] == 1


@pytest.mark.parametrize('case', ['malformed_target','unsupported_regulation','unknown_scope'])
def test_additional_truthful_unavailability(tmp_path, case):
    initialize(tmp_path)
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda:T)
    o.prepare((ROW,))
    if case == 'unsupported_regulation':
        scope = replace(o.scopes[9999], current_format=replace(binding().current_format, minutes=80))
        o.scopes[9999] = o.observer.scopes[9999] = scope
    if case == 'unknown_scope':
        o.scopes.clear()
        o.observer.scopes.clear()
    payload = {'response':None} if case == 'malformed_target' else [raw(9999,status='NS',kickoff=T+timedelta(hours=1))]
    o.capture('/fixtures', {'id':9999}, payload, T)
    o.bind(o.begin(), (ID,))
    o.observe(ID, new_opportunity=True)
    o.finish(completed=True)
    r = coverage(tmp_path)
    if case == 'unsupported_regulation':
        assert r['regulation_counts']['UNSUPPORTED_REGULATION'] == 1
        assert all(v['missing_reasons']['UNSUPPORTED_REGULATION'] == 1 for v in r['features'].values())
    else:
        assert r['successful_v2_snapshots'] == 0
        assert r['snapshot_failure_counts']['TARGET_SOURCE_UNAVAILABLE'] == 1
        assert r['source_availability']['TARGET']['verdict_counts'] == {
            'MALFORMED' if case == 'malformed_target' else 'SCOPE_UNAVAILABLE':1}


def test_report_missing_store_is_readonly_failure(tmp_path):
    r = coverage(tmp_path)
    assert r['readiness'] == 'CAPTURE_BLOCKED'
    assert r['denominator_completeness'] == 'UNPROVEN'
    assert list(tmp_path.iterdir()) == []


def test_manual_cycle_composes_same_existing_paths_without_send(tmp_path, monkeypatch, capsys):
    from app.lab_v2_shadow import cli
    initialize(tmp_path)
    called = []
    async def cycle(args, *, football_context=None):
        assert isinstance(football_context, ProspectiveObservation)
        assert args.send is False
        assert args.adaptive_database == tmp_path/'adaptive.db'
        assert args.shadow_database == tmp_path/'shadow.db'
        assert args.analysis_database == tmp_path/'analysis.db'
        assert args.ledger == tmp_path/'lab-ledger.db'
        called.append(True)
        return {'telegram_sends':0,'test':'EXISTING_CYCLE_OUTPUT'}
    monkeypatch.setattr(cli, '_cycle', cycle)
    assert main(['--root',str(tmp_path),'cycle','--environment','TEST','--observe']) == 0
    assert called == [True]
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {'telegram_sends':0,'test':'EXISTING_CYCLE_OUTPUT'}
    assert 'v2_readiness_diagnostics' in json.loads(captured.err)
    assert coverage(tmp_path)['readiness'] == 'NO_PROSPECTIVE_EVIDENCE'
