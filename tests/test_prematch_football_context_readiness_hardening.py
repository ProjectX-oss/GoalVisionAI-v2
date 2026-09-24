"""Offline hardening regressions: fake responses and disposable append-only stores."""
from dataclasses import replace
from datetime import timedelta
import json
import socket

import httpx
import pytest

from app.prematch_football_context.readiness.__main__ import initialize, main
from app.prematch_football_context.readiness.composition import ProspectiveObservation
from app.prematch_football_context.readiness.ledger import Ledger
from app.prematch_football_context.readiness.report import coverage, run_state
from app.prematch_football_context.snapshot.service import reproduce
from tests.test_prematch_football_context_readiness import ROW, ID, collect
from tests.test_prematch_football_context_sources import T, raw


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('REAL_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)


def target(fixture=9999):
    return {'response': [raw(fixture, status='NS', kickoff=T+timedelta(hours=1), gf=None, ga=None)]}


def decide(observer, decision=ID):
    observer.bind(observer.begin(), (decision,))
    observer.observe(decision, new_opportunity=True)
    return observer.snapshots.load(f'{decision.fixture_id}:{decision.market}')


@pytest.mark.parametrize('before_prepare', [False, True])
def test_one_real_client_response_fans_out_without_requests(tmp_path, before_prepare):
    """Transport count remains one across independent decisions, prepare and restart."""
    import asyncio
    from app.football.client import FootballClient
    initialize(tmp_path)
    now = [T]
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: now[0])
    if not before_prepare:
        o.prepare((ROW,))
    requests = []
    def handler(request):
        requests.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=target())
    async def fetch():
        client = FootballClient(api_key='SYNTHETIC_ONLY', response_observer=o.capture, completion_clock=lambda: T)
        await client._client.aclose()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.BASE_URL)
        try:
            await client.fixture(9999)
            assert client.request_count == 1
        finally:
            await client.close()
    asyncio.run(fetch())
    assert len(o.evidence.inspect()) == 1  # Durable before any eventual prepare/cutoff.
    o.prepare((ROW,))
    first = decide(o)
    now[0] += timedelta(seconds=30)
    second_id = replace(ID, market='DRAW', candidate_id='lab-v2-candidate-'+'b'*64)
    second = decide(o, second_id)
    assert first.selected_sources[0] == second.selected_sources[0]
    assert first.receipt != second.receipt
    assert reproduce(o.evidence, first) == first
    assert reproduce(o.evidence, second) == second
    o.finish(completed=True)
    # Reopening uses the original receipt/material, never a cached response callback.
    now[0] += timedelta(seconds=30)
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: now[0])
    o.prepare((ROW,))
    third = decide(o, replace(ID, market='AWAY_WIN', candidate_id='lab-v2-candidate-'+'c'*64))
    assert third.selected_sources[0] == first.selected_sources[0]
    assert len(o.evidence.inspect()) == 1
    o.finish(completed=True)
    assert requests == [('/fixtures', {'id': '9999'})]
    assert coverage(tmp_path)['reproduction']['VERIFIED'] == 3


@pytest.mark.parametrize('case,expected', [
    ('after_cutoff', 'UNAVAILABLE'), ('wrong_query_fixture', 'UNAVAILABLE'),
    ('wrong_payload_fixture', 'WRONG_TARGET'), ('expiry', 'UNAVAILABLE'),
    ('stale', 'UNAVAILABLE'), ('legacy', 'UNAVAILABLE'), ('date', 'UNAVAILABLE'),
    ('expanded_query', 'UNAVAILABLE'), ('string_id', 'UNAVAILABLE'),
])
def test_invalid_target_never_rescued(tmp_path, case, expected):
    initialize(tmp_path)
    now = [T]
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: now[0])
    o.prepare((ROW,))
    if case == 'after_cutoff':
        o.bind(o.begin(), (ID,))
        now[0] += timedelta(microseconds=1)
    if case == 'legacy':
        # A real legacy cache row exists, but there is no attested response callback.
        from app.lab_v2_shadow.repository import ShadowEvidenceRepository
        cache = ShadowEvidenceRepository(tmp_path/'shadow.db')
        cache.append_cache('/fixtures', {'id': 9999}, target(), retrieved_at=T, ttl=timedelta(minutes=2))
        cache.close()
    else:
        query = {'id': 10000} if case == 'wrong_query_fixture' else {'id': 9999}
        query = {'date': '2026-09-23', 'timezone': 'UTC'} if case == 'date' else query
        query = {'id': 9999, 'timezone': 'UTC'} if case == 'expanded_query' else query
        query = {'id': '9999'} if case == 'string_id' else query
        o.capture('/fixtures', query, target(10000 if case == 'wrong_payload_fixture' else 9999), now[0])
    if case in ('expiry', 'stale'):
        now[0] += timedelta(minutes=2 if case == 'expiry' else 16)
    if case != 'after_cutoff':
        o.bind(o.begin(), (ID,))
    o.observe(ID, new_opportunity=True)
    assert o.snapshots.load('9999:HOME_WIN') is None
    records, _ = o.ledger.read()
    result = next(d for k, _, d in records if k == 'RESULT')
    assert result['sources']['TARGET'] == expected
    detail = result['source_diagnostics']['TARGET']
    if case in ('expiry', 'stale'):
        assert detail['EXPIRED'] == 1  # Existing two-minute expiry is stricter than B's 15m bound.
    if case in ('legacy', 'date', 'expanded_query', 'string_id'):
        assert o.evidence.inspect() == ()
    if case == 'after_cutoff':
        # The same response may serve a later decision, never this earlier one.
        later = decide(o, replace(ID, market='DRAW', candidate_id='lab-v2-candidate-'+'b'*64))
        assert later is not None
        assert o.snapshots.load('9999:HOME_WIN') is None
    o.finish(completed=True)


def test_history_scope_and_optional_previous_unchanged(tmp_path):
    initialize(tmp_path)
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: T)
    history = {'league': 10, 'season': 2026, 'status': 'FT', 'last': 99}
    o.capture('/fixtures', history, [raw()], T)
    assert not o.evidence.inspect()  # Cannot infer current/previous before scope.
    o.capture('/fixtures', {'id': 9999}, target(), T)
    o.prepare((ROW,))
    o.capture('/fixtures', dict(reversed(list(history.items()))), [raw(i) for i in range(1, 9)], T)
    s = decide(o)
    assert s.selected_sources[0] and s.selected_sources[1]
    assert s.selected_sources[2] is None
    assert len(o.evidence.inspect()) == 2
    assert s.projection.values == (None,)*7
    assert all(r == ('REGULATION_UNVERIFIED',) for r in s.projection.reasons)
    o.finish(completed=True)


@pytest.mark.parametrize('legacy', [True, False])
def test_proven_preflight_remains_visible_without_poisoning_window(tmp_path, legacy):
    initialize(tmp_path)
    if legacy:
        ledger = Ledger(tmp_path/'attempts.db', writable=True)
        ledger.append('RUN', 'preflight', {'environment': 'TEST', 'version': 'FC_READINESS_1'})
        ledger.append('END', 'preflight', {'completed': False, 'diagnostics': {}})
        ledger.close()
    else:
        o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: T)
        o.finish(completed=False, credential_failure=True)
    ledger = Ledger(tmp_path/'attempts.db')
    original, _ = ledger.read()
    ledger.close()
    o = collect(tmp_path)
    o.finish(completed=True)
    r = coverage(tmp_path)
    assert r['runs'] == 2 and r['incomplete_runs'] == 1
    assert r['historical_preflight_failures'] == 1
    assert r['evidence_window_incomplete_runs'] == 0
    assert r['completed_observation_runs'] == 1
    assert r['denominator_completeness'] == 'VERIFIED_PERSISTED_RUNS'
    assert r['readiness'] == 'INSUFFICIENT_SAMPLE'
    assert r['v2_observation_attempts'] == 1
    ledger = Ledger(tmp_path/'attempts.db')
    after, _ = ledger.read()
    assert all(row in after for row in original)
    ledger.close()


@pytest.mark.parametrize('case', ['attempt', 'response', 'receipt', 'prepare', 'unknown_failure', 'missing_end', 'lost_events'])
def test_incomplete_evidence_never_hidden(tmp_path, monkeypatch, case):
    initialize(tmp_path)
    o = collect(tmp_path) if case in ('attempt', 'lost_events') else ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: T)
    if case == 'response': o.capture('/fixtures', {'id': 9999}, target(), T)
    if case == 'receipt': o.begin()
    if case == 'prepare': o.prepare((ROW,))
    if case == 'lost_events':
        original = o.ledger.append
        def fail(kind, *args):
            if kind in ('OPPORTUNITY', 'RESULT'): raise OSError('SYNTHETIC')
            return original(kind, *args)
        monkeypatch.setattr(o.ledger, 'append', fail)
        decide(o, replace(ID, market='DRAW', candidate_id='lab-v2-candidate-'+'b'*64))
    if case == 'missing_end':
        for store in (o.evidence, o.snapshots, o.ledger): store.close()
    else:
        o.finish(completed=False, credential_failure=case != 'unknown_failure')
    r = coverage(tmp_path)
    assert r['historical_preflight_failures'] == 0
    assert r['evidence_window_incomplete_runs'] == 1
    assert r['readiness'] == 'CAPTURE_BLOCKED'
    assert r['denominator_completeness'] == 'UNPROVEN'


@pytest.mark.parametrize('run,end,linked', [
    ({'version':'UNKNOWN'}, {'completed':False,'diagnostics':{}}, False),
    ({'version':'FC_READINESS_1'}, {'completed':False}, False),
    ({'version':'FC_READINESS_1'}, {'completed':False,'diagnostics':{}}, True),
    ({'version':'FC_READINESS_1'}, None, False),
    ({'version':'FC_READINESS_1'}, {'completed':False,'diagnostics':{'LEDGER_WRITE_FAILURE':1}}, False),
])
def test_absence_is_not_immutable_zero_proof(run, end, linked):
    assert run_state(run, end, linked_events=linked)[0] == 'INCOMPLETE_EVIDENCE_WINDOW'


def test_credential_exception_cli_and_readonly_commands_use_zero_requests(tmp_path, monkeypatch, capsys):
    from app.football.client import FootballClient
    from app.football.configuration import FootballCredentialError, resolve_api_football_credential
    from app.lab_v2_shadow import cli
    initialize(tmp_path)
    requests = []
    async def forbidden(*args, **kwargs):
        requests.append(True)
        pytest.fail('UNAUTHORIZED_PROVIDER_CALL')
    monkeypatch.setattr(FootballClient, '_get', forbidden)
    async def preflight(*args, **kwargs):
        resolve_api_football_credential(environment={}, env_file=tmp_path/'absent.env')
    monkeypatch.setattr(cli, '_cycle', preflight)
    with pytest.raises(FootballCredentialError):
        main(['--root', str(tmp_path), 'cycle', '--environment', 'TEST', '--observe'])
    assert coverage(tmp_path)['historical_preflight_failures'] == 1
    capsys.readouterr()
    before = {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    for command in ('report', 'verify', 'diagnostics'):
        assert main(['--root', str(tmp_path), command]) == 0
        assert json.loads(capsys.readouterr().out)['v2_observation_attempts'] == 0
    assert before == {p.name:p.read_bytes() for p in tmp_path.iterdir()}
    assert requests == []


@pytest.mark.parametrize('minutes,proof,late,verdict', [
    (None, False, False, 'REGULATION_UNVERIFIED'),
    (90, False, False, 'REGULATION_UNVERIFIED'),
    (90, True, True, 'REGULATION_UNVERIFIED'),
    (90, True, False, 'VERIFIED_90'),
    (80, True, False, 'UNSUPPORTED_REGULATION'),
])
def test_format_proof_lineage_survives_exact_snapshot_reproduction(tmp_path, minutes, proof, late, verdict):
    from app.prematch_football_context.source_adapter import FormatEvidence
    initialize(tmp_path)
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: T)
    o.prepare((ROW,))
    fmt = FormatEvidence(10, 2026, minutes, 'SYNTHETIC_REVIEW' if proof else None,
                         'b'*64 if proof else None, T if late else T-timedelta(days=1))
    scope = replace(o.scopes[9999], current_format=fmt)
    o.scopes[9999] = o.observer.scopes[9999] = scope
    o.capture('/fixtures', {'id': 9999}, target(), T)
    o.capture('/fixtures', {'league': 10, 'season': 2026, 'status': 'FT', 'last': 99},
              [raw(i) for i in range(1, 9)], T)
    snapshot = decide(o)
    assert snapshot.binding.current_format == fmt
    assert reproduce(o.evidence, snapshot) == snapshot
    assert snapshot.binding.current_format.verdict(snapshot.receipt.cutoff) == verdict
    if verdict == 'VERIFIED_90':
        assert snapshot.projection.missing == (0,)*7
    else:
        assert snapshot.projection.values == (None,)*7
        assert all(verdict in r for r in snapshot.projection.reasons)
    o.finish(completed=True)


@pytest.mark.parametrize('status', ['AET', 'PEN'])
def test_extra_time_without_regulation_fulltime_has_no_usable_results(tmp_path, status):
    from tests.test_prematch_football_context_sources import binding
    initialize(tmp_path)
    o = ProspectiveObservation(tmp_path, environment='TEST', clock=lambda: T)
    o.prepare((ROW,))
    scope = replace(o.scopes[9999], current_format=binding().current_format)
    o.scopes[9999] = o.observer.scopes[9999] = scope
    o.capture('/fixtures', {'id': 9999}, target(), T)
    rows = [raw(i, status=status, gf=None, ga=None) for i in range(1, 9)]
    for row in rows:
        row['goals'] = {'home': 3, 'away': 2}
    o.capture('/fixtures', {'league': 10, 'season': 2026, 'status': 'FT', 'last': 99}, rows, T)
    s = decide(o)
    assert s.projection.values == (None,)*7
    assert len(s.exclusions) == 8
    assert all('INVALID_REGULATION_SCORE_PAIR' in reasons for _, reasons in s.exclusions)
    assert reproduce(o.evidence, s) == s
    o.finish(completed=True)


def test_legacy_empty_end_cannot_hide_unassociated_decision_marker(tmp_path):
    from app.prematch_football_context.capture.repository import EvidenceRepository
    initialize(tmp_path)
    ledger = Ledger(tmp_path/'attempts.db', writable=True)
    ledger.append('RUN', 'legacy', {'version': 'FC_READINESS_1', 'environment': 'TEST'})
    ledger.append('END', 'legacy', {'completed': False, 'diagnostics': {}})
    ledger.close()
    evidence = EvidenceRepository(tmp_path/'sources.db', writable=True, clock=lambda: T)
    evidence.capture_cutoff()
    evidence.close()
    r = coverage(tmp_path)
    assert r['historical_preflight_failures'] == 0
    assert r['evidence_window_incomplete_runs'] == 1
    assert r['readiness'] == 'CAPTURE_BLOCKED'
